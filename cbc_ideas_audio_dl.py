#!/usr/bin/env python3
"""
High-level goals:
- Given a CBC story URL, find the related audio episode.
- Resolve a downloadable audio URL from the CBC podcast RSS feed.
- Use yt-dlp to download the episode audio.

Technical steps:
1) Fetch the CBC story HTML and extract window.__INITIAL_STATE__ JSON.
2) Locate the embedded polopoly_media audio block to get title/description/show slug.
3) Fetch the show RSS feed (ideas.xml by default, or override if provided).
4) Score RSS items by keyword overlap and date proximity to the story audio.
5) Choose the best match, grab its enclosure URL, and optionally download with yt-dlp.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
)
DEFAULT_SHOW = "ideas"

PROVIDERS = {
    "auto": None,
    "ideas": "ideas",
    "thecurrent": "thecurrent",
    "q": "q",
    "asithappens": "asithappens",
    "day6": "day6",
}

STOPWORDS = {
    "the", "and", "a", "an", "of", "to", "in", "for", "on", "with", "is", "are",
    "was", "were", "be", "as", "at", "by", "it", "this", "that", "from", "or",
}


@dataclass
class FeedItem:
    title: str
    description: str
    enclosure_url: str
    pubdate: str
    score: int


@dataclass
class StoryItem:
    title: str
    url: str


@dataclass
class ShowItem:
    title: str
    slug: str


class Spinner:
    def __init__(self, label: str, enabled: bool = True):
        self.label = label
        self.enabled = enabled
        self._mode = None
        self._ctx = None

    def __enter__(self):
        if not self.enabled:
            return self
        try:
            from rich.status import Status
            from rich.console import Console

            self._console = Console()
            self._status = Status(self.label, spinner="dots")
            self._status.start()
            self._mode = "rich"
        except Exception:
            try:
                from alive_progress import alive_bar

                self._ctx = alive_bar(None, title=self.label, spinner="dots")
                self._ctx.__enter__()
                self._mode = "alive"
            except Exception:
                try:
                    from yaspin import yaspin

                    self._status = yaspin(text=self.label)
                    self._status.start()
                    self._mode = "yaspin"
                except Exception:
                    self._mode = None
        return self

    def __exit__(self, exc_type, exc, tb):
        if not self._mode:
            return False
        if self._mode == "rich":
            self._status.stop()
        elif self._mode == "alive":
            self._ctx.__exit__(exc_type, exc, tb)
        elif self._mode == "yaspin":
            self._status.stop()
        return False


class Cache:
    def __init__(self, base_dir: Path, ttl_seconds: int = 3600):
        self.base_dir = base_dir
        self.ttl_seconds = ttl_seconds
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _paths(self, url: str) -> tuple[Path, Path]:
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()
        return (
            self.base_dir / f"{key}.body",
            self.base_dir / f"{key}.meta.json",
        )

    def get(self, url: str) -> tuple[str | None, dict[str, Any] | None]:
        body_path, meta_path = self._paths(url)
        if not body_path.exists() or not meta_path.exists():
            return None, None
        try:
            with meta_path.open("r", encoding="utf-8") as fh:
                meta = json.load(fh)
            if time.time() - meta.get("fetched_at", 0) > self.ttl_seconds:
                return None, None
            return body_path.read_text(encoding="utf-8", errors="ignore"), meta
        except Exception:
            return None, None

    def set(self, url: str, body: str, headers: dict[str, Any]):
        body_path, meta_path = self._paths(url)
        meta = {
            "fetched_at": time.time(),
            "etag": headers.get("ETag"),
            "last_modified": headers.get("Last-Modified"),
        }
        body_path.write_text(body, encoding="utf-8")
        meta_path.write_text(json.dumps(meta), encoding="utf-8")


class DebugArchive:
    def __init__(self, base_dir: Path | None):
        self.base_dir = base_dir
        if self.base_dir:
            self.base_dir.mkdir(parents=True, exist_ok=True)

    def write(self, name: str, content: str | dict):
        if not self.base_dir:
            return
        path = self.base_dir / name
        if isinstance(content, dict):
            path.write_text(json.dumps(content, indent=2), encoding="utf-8")
        else:
            path.write_text(content, encoding="utf-8")


def fetch_text(url: str, cache: Cache | None = None, ignore_cache: bool = False) -> str:
    headers = {"User-Agent": USER_AGENT}
    if cache and not ignore_cache:
        cached_body, meta = cache.get(url)
        if meta:
            if meta.get("etag"):
                headers["If-None-Match"] = meta["etag"]
            if meta.get("last_modified"):
                headers["If-Modified-Since"] = meta["last_modified"]
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8", "ignore")
            if cache and not ignore_cache:
                cache.set(url, body, dict(resp.headers))
            return body
    except HTTPError as exc:
        if exc.code == 304 and cache and not ignore_cache:
            cached_body, _meta = cache.get(url)
            if cached_body is not None:
                return cached_body
        raise


def fetch_bytes(url: str) -> bytes:
    req = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(req, timeout=30) as resp:
        return resp.read()


def extract_initial_state(html: str) -> dict:
    m = re.search(r"window.__INITIAL_STATE__ = (\{.*?\});\s*</script>", html)
    if not m:
        raise ValueError("Could not find window.__INITIAL_STATE__ in HTML")
    text = m.group(1)
    text = text.replace(":undefined", ":null")
    return json.loads(text)


def find_audio_block(state: dict) -> dict:
    body = (
        state
        .get("detail", {})
        .get("content", {})
        .get("body", [])
    )

    def walk(obj):
        if isinstance(obj, dict):
            yield obj
            for v in obj.values():
                yield from walk(v)
        elif isinstance(obj, list):
            for v in obj:
                yield from walk(v)

    for node in walk(body):
        if node.get("type") == "polopoly_media":
            media = node.get("content", {})
            if isinstance(media, dict) and media.get("type") == "audio":
                return media
    raise ValueError("Could not locate embedded audio block in story")


def extract_image_url(audio: dict) -> str | None:
    image = audio.get("image")
    if isinstance(image, dict):
        url = image.get("url")
        if url:
            return url
    images = audio.get("images")
    if isinstance(images, dict):
        for key in ("square_620", "square_460", "square_380", "square_300"):
            url = images.get(key)
            if url:
                return url
    return None


def tokenize(text: str):
    text = unescape(text or "").lower()
    words = re.findall(r"[a-z0-9']+", text)
    return [w for w in words if w not in STOPWORDS]


def extract_target_timestamp_ms(audio: dict, state: dict) -> int | None:
    for key in ("publishedAt", "updatedAt", "airDate"):
        val = audio.get(key)
        if isinstance(val, int):
            return val
    media = audio.get("media", {})
    if isinstance(media, dict):
        for key in ("airDate", "publishedAt", "updatedAt"):
            val = media.get(key)
            if isinstance(val, int):
                return val
    content = state.get("detail", {}).get("content", {})
    if isinstance(content, dict):
        for key in ("publishedAt", "updatedAt"):
            val = content.get(key)
            if isinstance(val, int):
                return val
    return None


def parse_pubdate_to_ms(pubdate: str) -> int | None:
    try:
        dt = parsedate_to_datetime(pubdate)
        return int(dt.timestamp() * 1000)
    except Exception:
        return None


def score_item(
    item_title: str,
    item_desc: str,
    target_tokens: set[str],
    target_part: str | None,
    target_ts_ms: int | None,
    pubdate: str,
) -> int:
    item_tokens = set(tokenize(item_title) + tokenize(item_desc))
    score = len(target_tokens & item_tokens)

    item_part_match = re.search(r"\bpt\s*(\d+)\b", item_title.lower())
    item_part = item_part_match.group(1) if item_part_match else None
    if target_part and item_part:
        if target_part == item_part:
            score += 10
        else:
            score -= 5

    if target_ts_ms:
        item_ts = parse_pubdate_to_ms(pubdate)
        if item_ts:
            days = abs(target_ts_ms - item_ts) / (1000 * 60 * 60 * 24)
            if days <= 7:
                score += max(0, int(10 - days))

    return score


def collect_feed_items(feed_xml: str, title: str, description: str, target_ts_ms: int | None) -> list[FeedItem]:
    root = ET.fromstring(feed_xml)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("Invalid RSS: missing channel")

    target_tokens = set(tokenize(title) + tokenize(description))
    part_match = re.search(r"\bpt\s*(\d+)\b", title.lower())
    target_part = part_match.group(1) if part_match else None

    items: list[FeedItem] = []
    for item in channel.findall("item"):
        item_title = item.findtext("title", "")
        item_desc = item.findtext("description", "")
        pubdate = item.findtext("pubDate", "")
        enclosure = item.find("enclosure")
        if enclosure is None:
            continue
        url = enclosure.attrib.get("url")
        if not url:
            continue
        score = score_item(
            item_title,
            item_desc,
            target_tokens,
            target_part,
            target_ts_ms,
            pubdate,
        )
        items.append(
            FeedItem(
                title=item_title,
                description=item_desc,
                enclosure_url=url,
                pubdate=pubdate,
                score=score,
            )
        )

    if not items:
        raise ValueError("No RSS items with enclosures found")
    return items


def best_rss_match(items: list[FeedItem]) -> FeedItem:
    items_sorted = sorted(items, key=lambda x: x.score, reverse=True)
    best = items_sorted[0]
    if best.score <= 0:
        raise ValueError("Could not find a confident RSS match for the story audio")
    return best


def print_list(items: list[FeedItem], limit: int, as_json: bool):
    items_sorted = sorted(items, key=lambda x: x.score, reverse=True)[:limit]
    if as_json:
        print(json.dumps([item.__dict__ for item in items_sorted], indent=2))
        return
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title=f"Top {limit} matches")
        table.add_column("Score", justify="right")
        table.add_column("Title")
        table.add_column("PubDate")
        table.add_column("URL")
        for item in items_sorted:
            table.add_row(str(item.score), item.title, item.pubdate, item.enclosure_url)
        Console().print(table)
    except Exception:
        for item in items_sorted:
            print(f"[{item.score}] {item.title} ({item.pubdate})")
            print(f"  {item.enclosure_url}")


def print_story_list(items: list[StoryItem], limit: int, as_json: bool):
    items_sorted = items[:limit]
    if as_json:
        print(json.dumps([item.__dict__ for item in items_sorted], indent=2))
        return
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title=f"Top {limit} stories")
        table.add_column("#", justify="right")
        table.add_column("Title")
        table.add_column("URL")
        for idx, item in enumerate(items_sorted, start=1):
            table.add_row(str(idx), item.title, item.url)
        Console().print(table)
    except Exception:
        for idx, item in enumerate(items_sorted, start=1):
            print(f"{idx}) {item.title}")
            print(f"  {item.url}")


def print_show_list(items: list[ShowItem], limit: int, as_json: bool):
    items_sorted = items[:limit]
    if as_json:
        print(json.dumps([item.__dict__ for item in items_sorted], indent=2))
        return
    try:
        from rich.console import Console
        from rich.table import Table

        table = Table(title=f"Top {limit} shows")
        table.add_column("#", justify="right")
        table.add_column("Show")
        table.add_column("Slug")
        for idx, item in enumerate(items_sorted, start=1):
            table.add_row(str(idx), item.title, item.slug)
        Console().print(table)
    except Exception:
        for idx, item in enumerate(items_sorted, start=1):
            print(f"{idx}) {item.title} ({item.slug})")


def resolve_show_slug(provider: str | None, show_override: str | None, embedded_slug: str | None, url: str) -> str:
    if show_override:
        return show_override
    if provider and provider in PROVIDERS and PROVIDERS[provider]:
        return PROVIDERS[provider]
    m = re.search(r"/radio/([a-z0-9-]+)/", url)
    if m:
        return m.group(1)
    return (embedded_slug or DEFAULT_SHOW).strip() or DEFAULT_SHOW


def discover_rss_url(html: str) -> str | None:
    m = re.search(r"https?://www\.cbc\.ca/podcasting/includes/[^\"']+\.xml", html)
    if m:
        return m.group(0)
    return None


def parse_feed_items(feed_xml: str) -> list[FeedItem]:
    root = ET.fromstring(feed_xml)
    channel = root.find("channel")
    if channel is None:
        raise ValueError("Invalid RSS: missing channel")
    items: list[FeedItem] = []
    for item in channel.findall("item"):
        title = item.findtext("title", "")
        description = item.findtext("description", "")
        pubdate = item.findtext("pubDate", "")
        enclosure = item.find("enclosure")
        if enclosure is None:
            continue
        url = enclosure.attrib.get("url")
        if not url:
            continue
        items.append(
            FeedItem(
                title=title,
                description=description,
                enclosure_url=url,
                pubdate=pubdate,
                score=0,
            )
        )
    if not items:
        raise ValueError("No RSS items with enclosures found")
    return items


def parse_feed_metadata(feed_xml: str) -> tuple[str | None, str | None]:
    root = ET.fromstring(feed_xml)
    channel = root.find("channel")
    if channel is None:
        return None, None
    title = channel.findtext("title", "").strip() or None
    image_url = None
    image = channel.find("image")
    if image is not None:
        image_url = image.findtext("url")
    if not image_url:
        itunes = channel.find("{http://www.itunes.com/dtds/podcast-1.0.dtd}image")
        if itunes is not None:
            image_url = itunes.attrib.get("href")
    return title, image_url


def candidate_slugs(slug: str) -> list[str]:
    if "/" in slug:
        return [slug]
    candidates = [slug]
    if "-" in slug:
        candidates.append(slug.replace("-", ""))
    if slug.startswith("the-"):
        candidates.append(slug[4:])
    if slug.startswith("the"):
        candidates.append(slug[3:])
    return [c for c in candidates if c]


def resolve_feed_for_slug(slug: str, cache: Cache, ignore_cache: bool) -> tuple[str, str]:
    last_error = None
    for candidate in candidate_slugs(slug):
        url = f"https://www.cbc.ca/podcasting/includes/{candidate}.xml"
        try:
            feed_xml = fetch_text(url, cache=cache, ignore_cache=ignore_cache)
            return url, feed_xml
        except HTTPError as exc:
            last_error = exc
            continue
        except URLError as exc:
            last_error = exc
            continue
    raise ValueError(f"No valid RSS feed found for show slug '{slug}'") from last_error


def is_story_url(url: str) -> bool:
    return bool(re.search(r"-1\.\d+(?:\?.*)?$", url))


def strip_tags(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def discover_story_links(html: str) -> list[StoryItem]:
    items: list[StoryItem] = []
    seen: set[str] = set()
    pattern = re.compile(r'<a[^>]+href="(/radio/[^"]+-1\.\d+[^"]*)"[^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
    for href, inner in pattern.findall(html):
        url = f"https://www.cbc.ca{href}"
        if url in seen:
            continue
        title = strip_tags(inner)
        if not title:
            title = url
        items.append(StoryItem(title=title, url=url))
        seen.add(url)
    return items


def discover_show_links(html: str) -> list[ShowItem]:
    items: list[ShowItem] = []
    seen: set[str] = set()
    pattern = re.compile(r"<a[^>]+href=['\"](?:https?://www\\.cbc\\.ca)?(/radio/([a-z0-9-]+)/)['\"][^>]*>(.*?)</a>", re.IGNORECASE | re.DOTALL)
    for href, slug, inner in pattern.findall(html):
        if slug in seen or slug == "radio":
            continue
        if slug in {"podcastnews", "podcasts", "listen"}:
            continue
        title = strip_tags(inner)
        if not title:
            title = slug
        items.append(ShowItem(title=title, slug=slug))
        seen.add(slug)
    if not items:
        for slug in re.findall(r"/radio/([a-z0-9-]+)/", html, flags=re.IGNORECASE):
            if slug in seen or slug == "radio":
                continue
            if slug in {"podcastnews", "podcasts", "listen"}:
                continue
            items.append(ShowItem(title=slug, slug=slug))
            seen.add(slug)
    return items


def merge_show_lists(primary: list[ShowItem], secondary: list[ShowItem]) -> list[ShowItem]:
    seen = {s.slug for s in primary}
    merged = list(primary)
    for item in secondary:
        if item.slug in seen:
            continue
        merged.append(item)
        seen.add(item.slug)
    return merged


def discover_feed_slugs_from_podcasting(html: str) -> list[ShowItem]:
    items: list[ShowItem] = []
    seen: set[str] = set()
    urls = re.findall(r"https?://[^\"'\s>]+\.xml", html, flags=re.IGNORECASE)
    for url in urls:
        if "/podcasting/includes/" not in url.lower():
            continue
        slug = url.split("/podcasting/includes/", 1)[1]
        if slug.endswith(".xml"):
            slug = slug[:-4]
        slug = slug.strip()
        if not slug or slug in seen:
            continue
        items.append(ShowItem(title=slug, slug=slug))
        seen.add(slug)
    return items


def ensure_yt_dlp() -> bool:
    return bool(shutil.which("yt-dlp"))


def completion_script(shell: str) -> str:
    if shell == "bash":
        return """_cbc_audio_complete() {
  local cur
  cur="${COMP_WORDS[COMP_CWORD]}"
  COMPREPLY=( $(compgen -W "--dry-run --show --rss-url --provider --title --verbose --list --json --no-download --print-url --audio-format --format --output --output-dir --cache-ttl --completion --interactive --non-interactive --tag --no-tag --transcribe --debug --debug-dir --record --repair --rss-discover-only --summary --browse-stories --story-list --show-list" -- "$cur") )
}
complete -F _cbc_audio_complete cbc_ideas_audio_dl.py
"""
    if shell == "zsh":
        return """#compdef cbc_ideas_audio_dl.py
_arguments \
  '1:url:URL' \
  '--dry-run' \
  '--show[Override show slug]:show:' \
  '--rss-url[Override RSS URL]:url:' \
  '--provider[Preset provider]:provider:(auto ideas thecurrent q asithappens day6)' \
  '--title[Override title for matching]:title:' \
  '--verbose' \
  '--list[Top N matches]:N:' \
  '--json' \
  '--no-download' \
  '--print-url' \
  '--audio-format[Audio format]:format:' \
  '--format[yt-dlp format selector]:selector:' \
  '--output[yt-dlp output template]:template:' \
  '--output-dir[Base output directory]:dir:' \
  '--cache-ttl[Cache TTL seconds]:seconds:' \
  '--completion[Print completion]:shell:(bash zsh fish)' \
  '--interactive' \
  '--non-interactive' \
  '--tag' \
  '--no-tag' \
  '--transcribe' \
  '--debug' \
  '--debug-dir[Debug dir]:dir:' \
  '--record[Record fixtures]:dir:' \
  '--repair' \
  '--rss-discover-only' \
  '--summary[Top N matches summary]:N:' \
  '--browse-stories' \
  '--story-list[Top N stories]:N:' \
  '--show-list[Top N shows]:N:'
"""
    if shell == "fish":
        return """complete -c cbc_ideas_audio_dl.py -l dry-run
complete -c cbc_ideas_audio_dl.py -l show -r
complete -c cbc_ideas_audio_dl.py -l rss-url -r
complete -c cbc_ideas_audio_dl.py -l provider -r -a "auto ideas thecurrent q asithappens day6"
complete -c cbc_ideas_audio_dl.py -l title -r
complete -c cbc_ideas_audio_dl.py -l verbose
complete -c cbc_ideas_audio_dl.py -l list -r
complete -c cbc_ideas_audio_dl.py -l json
complete -c cbc_ideas_audio_dl.py -l no-download
complete -c cbc_ideas_audio_dl.py -l print-url
complete -c cbc_ideas_audio_dl.py -l audio-format -r
complete -c cbc_ideas_audio_dl.py -l format -r
complete -c cbc_ideas_audio_dl.py -l output -r
complete -c cbc_ideas_audio_dl.py -l output-dir -r
complete -c cbc_ideas_audio_dl.py -l cache-ttl -r
complete -c cbc_ideas_audio_dl.py -l completion -r -a "bash zsh fish"
complete -c cbc_ideas_audio_dl.py -l interactive
complete -c cbc_ideas_audio_dl.py -l non-interactive
complete -c cbc_ideas_audio_dl.py -l tag
complete -c cbc_ideas_audio_dl.py -l no-tag
complete -c cbc_ideas_audio_dl.py -l transcribe
complete -c cbc_ideas_audio_dl.py -l debug
complete -c cbc_ideas_audio_dl.py -l debug-dir -r
complete -c cbc_ideas_audio_dl.py -l record -r
complete -c cbc_ideas_audio_dl.py -l repair
complete -c cbc_ideas_audio_dl.py -l rss-discover-only
complete -c cbc_ideas_audio_dl.py -l summary -r
complete -c cbc_ideas_audio_dl.py -l browse-stories
complete -c cbc_ideas_audio_dl.py -l story-list -r
complete -c cbc_ideas_audio_dl.py -l show-list -r
"""
    raise ValueError("Unsupported shell for completion")


def choose_interactive(items: list[FeedItem], page_size: int = 5) -> FeedItem | None:
    items_sorted = sorted(items, key=lambda x: x.score, reverse=True)
    total = len(items_sorted)
    page = 0

    def render_page(page_index: int):
        start = page_index * page_size
        end = min(start + page_size, total)
        page_items = items_sorted[start:end]
        try:
            from rich.console import Console
            from rich.table import Table

            table = Table(title=f"Select an episode ({start + 1}-{end} of {total})")
            table.add_column("#", justify="right")
            table.add_column("Score", justify="right")
            table.add_column("Title")
            table.add_column("PubDate")
            for idx, item in enumerate(page_items, start=1):
                table.add_row(str(idx), str(item.score), item.title, item.pubdate)
            Console().print(table)
        except Exception:
            print(f"Select an episode ({start + 1}-{end} of {total}):")
            for idx, item in enumerate(page_items, start=1):
                print(f"{idx}) [{item.score}] {item.title} ({item.pubdate})")

    while True:
        render_page(page)
        prompt = "Enter number, n(ext), p(rev), or blank to cancel: "
        choice = input(prompt.replace("cancel", "cancel, /filter")).strip().lower()
        if not choice:
            return None
        if choice.startswith("/"):
            query = choice[1:].strip()
            if not query:
                items_sorted = sorted(items, key=lambda x: x.score, reverse=True)
            else:
                items_sorted = [
                    i for i in items
                    if query in i.title.lower() or query in (i.description or "").lower()
                ]
            total = len(items_sorted)
            page = 0
            if total == 0:
                print("No episodes match that filter.")
                items_sorted = sorted(items, key=lambda x: x.score, reverse=True)
                total = len(items_sorted)
            continue
        if choice in {"n", "next"}:
            if (page + 1) * page_size < total:
                page += 1
            continue
        if choice in {"p", "prev"}:
            if page > 0:
                page -= 1
            continue
        try:
            num = int(choice)
            start = page * page_size
            end = min(start + page_size, total)
            if 1 <= num <= (end - start):
                return items_sorted[start + num - 1]
        except Exception:
            continue


def choose_story_interactive(items: list[StoryItem], page_size: int = 5) -> StoryItem | None:
    total = len(items)
    page = 0

    def render_page(page_index: int):
        start = page_index * page_size
        end = min(start + page_size, total)
        page_items = items[start:end]
        try:
            from rich.console import Console
            from rich.table import Table

            table = Table(title=f"Select a story ({start + 1}-{end} of {total})")
            table.add_column("#", justify="right")
            table.add_column("Title")
            for idx, item in enumerate(page_items, start=1):
                table.add_row(str(idx), item.title)
            Console().print(table)
        except Exception:
            print(f"Select a story ({start + 1}-{end} of {total}):")
            for idx, item in enumerate(page_items, start=1):
                print(f"{idx}) {item.title}")

    while True:
        render_page(page)
        choice = input("Enter number, n(ext), p(rev), or blank to cancel: ").strip().lower()
        if not choice:
            return None
        if choice in {"n", "next"}:
            if (page + 1) * page_size < total:
                page += 1
            continue
        if choice in {"p", "prev"}:
            if page > 0:
                page -= 1
            continue
        try:
            num = int(choice)
            start = page * page_size
            end = min(start + page_size, total)
            if 1 <= num <= (end - start):
                return items[start + num - 1]
        except Exception:
            continue


def choose_show_interactive(items: list[ShowItem], page_size: int = 5) -> ShowItem | None:
    items_sorted = items[:]
    total = len(items_sorted)
    page = 0

    def render_page(page_index: int):
        start = page_index * page_size
        end = min(start + page_size, total)
        page_items = items_sorted[start:end]
        try:
            from rich.console import Console
            from rich.table import Table

            table = Table(title=f"Select a show ({start + 1}-{end} of {total})")
            table.add_column("#", justify="right")
            table.add_column("Show")
            table.add_column("Slug")
            for idx, item in enumerate(page_items, start=1):
                table.add_row(str(idx), item.title, item.slug)
            Console().print(table)
        except Exception:
            print(f"Select a show ({start + 1}-{end} of {total}):")
            for idx, item in enumerate(page_items, start=1):
                print(f"{idx}) {item.title} ({item.slug})")

    while True:
        render_page(page)
        choice = input("Enter number, n(ext), p(rev), /filter, or blank to cancel: ").strip().lower()
        if not choice:
            return None
        if choice.startswith("/"):
            query = choice[1:].strip()
            if not query:
                items_sorted = items[:]
            else:
                items_sorted = [
                    s for s in items
                    if query in s.title.lower() or query in s.slug.lower()
                ]
            total = len(items_sorted)
            page = 0
            if total == 0:
                print("No shows match that filter.")
                items_sorted = items[:]
                total = len(items_sorted)
            continue
        if choice in {"n", "next"}:
            if (page + 1) * page_size < total:
                page += 1
            continue
        if choice in {"p", "prev"}:
            if page > 0:
                page -= 1
            continue
        try:
            num = int(choice)
            start = page * page_size
            end = min(start + page_size, total)
            if 1 <= num <= (end - start):
                return items_sorted[start + num - 1]
        except Exception:
            continue


def prompt_action() -> tuple[bool, bool, bool]:
    while True:
        choice = input("Choose action: [d]ownload, [t]ranscribe, [b]oth, [u]rl-only, [c]ancel: ").strip().lower()
        if choice in {"d", "download"}:
            return True, False, False
        if choice in {"t", "transcribe"}:
            return True, True, True
        if choice in {"b", "both"}:
            return True, True, False
        if choice in {"u", "url"}:
            return False, False, False
        if choice in {"c", "cancel"}:
            return False, False, True
        if choice in {"n", "next"}:
            if (page + 1) * page_size < total:
                page += 1
            continue
        if choice in {"p", "prev"}:
            if page > 0:
                page -= 1
            continue
        try:
            num = int(choice)
            start = page * page_size
            end = min(start + page_size, total)
            if 1 <= num <= (end - start):
                return items_sorted[start + num - 1]
        except Exception:
            continue


def run_ytdlp(cmd: list[str], use_live: bool) -> int:
    if not use_live:
        return subprocess.run(cmd).returncode

    try:
        from rich.console import Console
        from rich.progress import (
            Progress,
            BarColumn,
            TextColumn,
            TimeRemainingColumn,
            DownloadColumn,
            TransferSpeedColumn,
        )

        console = Console()
        cmd = cmd + ["--newline"]
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        progress = Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("{task.percentage:>6.2f}%"),
            DownloadColumn(),
            TransferSpeedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        task_id = progress.add_task("Downloading", total=100.0)
        percent_re = re.compile(r"\\s(\\d+\\.\\d+)%")
        with progress:
            while True:
                line = proc.stdout.readline()
                if not line and proc.poll() is not None:
                    break
                if not line:
                    continue
                match = percent_re.search(line)
                if match:
                    pct = float(match.group(1))
                    progress.update(task_id, completed=pct)
        return proc.wait()
    except Exception:
        return subprocess.run(cmd).returncode


def get_expected_filepath(enclosure_url: str, audio_format: str, output_template: str | None, output_dir: str | None) -> str | None:
    if not ensure_yt_dlp():
        return None
    cmd = ["yt-dlp", "--get-filename", "-x", "--audio-format", audio_format]
    if output_template:
        cmd += ["-o", output_template]
    if output_dir:
        cmd += ["-P", output_dir]
    cmd.append(enclosure_url)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        return None
    path = result.stdout.strip().splitlines()[-1]
    return path if path else None


def tag_audio_file(
    filepath: str,
    title: str,
    show: str,
    pubdate: str | None,
    image_url: str | None,
    cache: Cache | None,
    ignore_cache: bool,
) -> bool:
    try:
        from mutagen.id3 import ID3, APIC, TIT2, TALB, TPE1, TDRC
        from mutagen.mp3 import MP3
    except Exception:
        return False

    if not os.path.exists(filepath):
        return False

    audio = MP3(filepath, ID3=ID3)
    audio.add_tags() if audio.tags is None else None

    audio.tags.add(TIT2(encoding=3, text=title))
    audio.tags.add(TALB(encoding=3, text=show))
    audio.tags.add(TPE1(encoding=3, text="CBC"))
    if pubdate:
        audio.tags.add(TDRC(encoding=3, text=pubdate))

    if image_url:
        try:
            img = fetch_bytes(image_url)
            audio.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=img))
        except Exception:
            pass

    audio.save()
    return True


def parse_timestamp(value: str) -> float:
    if value is None:
        raise ValueError("Timestamp is required")
    value = value.strip()
    if not value:
        raise ValueError("Timestamp is required")
    if ":" not in value:
        return float(value)
    parts = value.split(":")
    if len(parts) > 3:
        raise ValueError("Timestamp must be in seconds, MM:SS, or HH:MM:SS")
    try:
        parts = [float(p) for p in parts]
    except ValueError as exc:
        raise ValueError("Timestamp must be numeric") from exc
    while len(parts) < 3:
        parts.insert(0, 0.0)
    hours, minutes, seconds = parts
    return hours * 3600 + minutes * 60 + seconds


def transcribe_audio(
    filepath: str,
    output_dir: str | None,
    model: str,
    clip_start: float | None,
    clip_end: float | None,
    clip_duration: float | None,
) -> bool:
    if not filepath or not os.path.exists(filepath):
        return False
    if not shutil.which("whisper"):
        return False
    clip_path = filepath
    if clip_start is not None or clip_end is not None or clip_duration is not None:
        if not shutil.which("ffmpeg"):
            return False
        start = clip_start or 0.0
        duration = clip_duration
        if clip_end is not None:
            duration = clip_end - start
        if duration is None or duration <= 0:
            return False
        suffix = Path(filepath).suffix or ".mp3"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            clip_path = tmp.name
        cmd = [
            "ffmpeg",
            "-y",
            "-ss",
            str(start),
            "-i",
            filepath,
            "-t",
            str(duration),
            "-c",
            "copy",
            clip_path,
        ]
        if subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
            try:
                os.remove(clip_path)
            except Exception:
                pass
            return False
    cmd = ["whisper", clip_path, "--model", model]
    if output_dir:
        cmd += ["--output_dir", output_dir]
    rc = subprocess.run(cmd).returncode == 0
    if clip_path != filepath:
        try:
            os.remove(clip_path)
        except Exception:
            pass
    return rc


def main():
    parser = argparse.ArgumentParser(
        description="Download CBC audio from a story or section URL using yt-dlp.",
        epilog=(
            "Examples:\n"
            "  cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/...\n"
            "  cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/... --dry-run\n"
            "  cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/... --show ideas\n"
            "  cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/... --rss-url https://www.cbc.ca/podcasting/includes/ideas.xml\n"
            "  cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/... --list 5\n"
            "  cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/... --completion zsh\n\n"
            "Requires: yt-dlp in PATH and internet access. Optional: rich, yaspin, alive-progress, mutagen."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("url", help="CBC story or section URL (e.g., https://www.cbc.ca/radio/ideas/...)")
    parser.add_argument("--dry-run", action="store_true", help="Print the resolved enclosure URL and exit")
    parser.add_argument("--show", help="Override show slug for RSS feed (default: ideas)")
    parser.add_argument("--rss-url", help="Override RSS URL directly")
    parser.add_argument("--provider", choices=sorted(PROVIDERS.keys()), help="Preset show provider")
    parser.add_argument("--title", help="Override story audio title for matching")
    parser.add_argument("--verbose", action="store_true", help="Print extra diagnostic info")
    parser.add_argument("--list", type=int, metavar="N", help="List top N RSS matches (or feed items for section URLs)")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON output")
    parser.add_argument("--no-download", action="store_true", help="Resolve only, do not download")
    parser.add_argument("--print-url", action="store_true", help="Print the resolved enclosure URL")
    parser.add_argument("--audio-format", default="mp3", help="Audio format for yt-dlp (default: mp3)")
    parser.add_argument("--format", dest="ytdlp_format", help="Pass a format selector to yt-dlp")
    parser.add_argument("--output", help="Output template for yt-dlp (-o)")
    parser.add_argument("--output-dir", help="Output directory for yt-dlp (-P)")
    parser.add_argument("--cache-ttl", type=int, default=3600, help="Cache TTL in seconds (default: 3600)")
    parser.add_argument("--completion", choices=["bash", "zsh", "fish"], help="Print shell completion script")
    parser.add_argument("--interactive", action="store_true", help="Prompt to choose if match is ambiguous")
    parser.add_argument("--non-interactive", action="store_true", help="Never prompt; pick best match")
    parser.add_argument("--tag", action="store_true", help="Tag downloaded audio with ID3 metadata")
    parser.add_argument("--no-tag", action="store_true", help="Disable tagging")
    parser.add_argument("--transcribe", action="store_true", help="Transcribe with whisper if installed")
    parser.add_argument("--transcribe-dir", help="Output directory for whisper transcripts")
    parser.add_argument("--transcribe-model", default="base", help="Whisper model (default: base)")
    parser.add_argument("--transcribe-start", help="Start time for transcription (seconds or HH:MM:SS)")
    parser.add_argument("--transcribe-end", help="End time for transcription (seconds or HH:MM:SS)")
    parser.add_argument("--transcribe-duration", help="Duration to transcribe (seconds or HH:MM:SS)")
    parser.add_argument("--debug", action="store_true", help="Write debug archive with HTML, RSS, scores")
    parser.add_argument("--debug-dir", help="Debug archive directory")
    parser.add_argument("--record", help="Record fixtures to a directory")
    parser.add_argument("--repair", action="store_true", help="Bypass cache and re-resolve if download fails")
    parser.add_argument("--rss-discover-only", action="store_true", help="Only print discovered RSS URL and exit")
    parser.add_argument("--summary", type=int, metavar="N", help="Print top N matches (non-interactive summary)")
    parser.add_argument("--browse-stories", action="store_true", help="Treat URL as a section and choose a story")
    parser.add_argument("--story-list", type=int, metavar="N", help="List top N discovered stories and exit")
    parser.add_argument("--show-list", type=int, metavar="N", help="List top N discovered shows and exit")
    args = parser.parse_args()

    if args.completion:
        print(completion_script(args.completion))
        return 0

    if not ensure_yt_dlp() and not (args.dry_run or args.no_download or args.print_url or args.list):
        print("Error: yt-dlp not found in PATH.", file=sys.stderr)
        return 2

    cache_dir = Path(__file__).resolve().parent / ".cbc_cache"
    cache = Cache(cache_dir, ttl_seconds=args.cache_ttl)

    debug_dir = None
    if args.debug_dir:
        debug_dir = Path(args.debug_dir)
    elif args.debug:
        debug_dir = Path.cwd() / f"cbc_debug_{int(time.time())}"
    debug = DebugArchive(debug_dir)

    ignore_cache = args.repair
    enclosure_url = None
    best_item: FeedItem | None = None
    feed_mode = False
    feed_url: str | None = None

    try:
        with Spinner("Fetching story", enabled=not args.verbose):
            html = fetch_text(args.url, cache=cache, ignore_cache=ignore_cache)
        debug.write("story.html", html)
    except (URLError, HTTPError) as exc:
        print(f"Error: failed to read URL: {exc}", file=sys.stderr)
        return 2

    discovered_rss = discover_rss_url(html)
    if args.rss_discover_only:
        if discovered_rss:
            print(discovered_rss)
            return 0
        print("Error: RSS not discovered in HTML.", file=sys.stderr)
        return 2

    if args.browse_stories or not is_story_url(args.url):
        # Always augment show discovery from /podcasting for broader coverage.
        shows_from_section = discover_show_links(html)
        try:
            podcasting_html = fetch_text("https://www.cbc.ca/podcasting/", cache=cache, ignore_cache=True)
            shows_from_podcasting = discover_feed_slugs_from_podcasting(podcasting_html)
            shows_from_section = merge_show_lists(shows_from_section, shows_from_podcasting)
        except Exception:
            pass
        if args.verbose:
            print(f"Shows from section HTML: {len(discover_show_links(html))}")
            if 'shows_from_podcasting' in locals():
                print(f"Shows from /podcasting/: {len(shows_from_podcasting)}")
                if 'podcasting_html' in locals():
                    print(f"/podcasting/ xml links: {podcasting_html.count('.xml')}")
            else:
                print("Shows from /podcasting/: 0")
            print(f"Merged shows: {len(shows_from_section)}")
        if args.story_list:
            stories = discover_story_links(html)
            if not stories:
                print("Error: no story links found on section page.", file=sys.stderr)
                return 2
            print_story_list(stories, args.story_list, args.json)
            return 0
        if args.show_list:
            shows = shows_from_section
            if not shows:
                print("Error: no show links found on section page.", file=sys.stderr)
                return 2
            print_show_list(shows, args.show_list, args.json)
            return 0
        if discovered_rss and not args.browse_stories:
            feed_mode = True
            feed_url = discovered_rss
            try:
                with Spinner("Fetching RSS feed", enabled=not args.verbose):
                    feed_xml = fetch_text(feed_url, cache=cache, ignore_cache=ignore_cache)
                debug.write("feed.xml", feed_xml)
                items = parse_feed_items(feed_xml)
                feed_title, feed_image = parse_feed_metadata(feed_xml)
            except (URLError, HTTPError, ValueError) as exc:
                print(f"Error: failed to read RSS feed: {exc}", file=sys.stderr)
                return 2

            if args.list:
                print_list(items, args.list, args.json)
                return 0
            if args.summary:
                print_list(items, args.summary, args.json)
                return 0

            interactive = args.interactive or (sys.stdin.isatty() and not args.non_interactive)
            if not interactive:
                print("Error: non-interactive mode requires --list or --summary to pick a feed item.", file=sys.stderr)
                return 2
            chosen = choose_interactive(items)
            if not chosen:
                print("No item selected.", file=sys.stderr)
                return 1

            title = args.title or chosen.title
            description = chosen.description
            show_slug = (args.show or feed_title or DEFAULT_SHOW).strip()
            image_url = feed_image
            best_item = chosen
            enclosure_url = chosen.enclosure_url
        else:
            shows = [] if args.browse_stories else shows_from_section
            if shows:
                interactive = args.interactive or (sys.stdin.isatty() and not args.non_interactive)
                if not interactive:
                    print("Error: non-interactive mode requires --show-list to pick a show.", file=sys.stderr)
                    return 2
                while True:
                    chosen_show = choose_show_interactive(shows)
                    if not chosen_show:
                        print("No show selected.", file=sys.stderr)
                        return 1
                    show_url = f"https://www.cbc.ca/radio/{chosen_show.slug}/"
                    feed_url = None
                    feed_xml = None
                    try:
                        show_html = fetch_text(show_url, cache=cache, ignore_cache=ignore_cache)
                        feed_url = discover_rss_url(show_html)
                    except Exception:
                        feed_url = None
                    if feed_url:
                        try:
                            feed_xml = fetch_text(feed_url, cache=cache, ignore_cache=ignore_cache)
                        except Exception:
                            feed_xml = None
                    if not feed_xml:
                        try:
                            feed_url, feed_xml = resolve_feed_for_slug(chosen_show.slug, cache, ignore_cache)
                        except Exception as exc:
                            print(f"Could not resolve RSS for '{chosen_show.slug}'. Pick another show. ({exc})")
                            continue
                    feed_mode = True
                    try:
                        with Spinner("Fetching RSS feed", enabled=not args.verbose):
                            feed_xml = feed_xml or fetch_text(feed_url, cache=cache, ignore_cache=ignore_cache)
                        debug.write("feed.xml", feed_xml)
                        items = parse_feed_items(feed_xml)
                        feed_title, feed_image = parse_feed_metadata(feed_xml)
                    except (URLError, HTTPError, ValueError) as exc:
                        print(f"Error: failed to read RSS feed: {exc}", file=sys.stderr)
                        return 2
                    break

                if args.list:
                    print_list(items, args.list, args.json)
                    return 0
                if args.summary:
                    print_list(items, args.summary, args.json)
                    return 0

                if not interactive:
                    print("Error: non-interactive mode requires --list or --summary to pick a feed item.", file=sys.stderr)
                    return 2
                chosen = choose_interactive(items)
                if not chosen:
                    print("No item selected.", file=sys.stderr)
                    return 1

                title = args.title or chosen.title
                description = chosen.description
                show_slug = (args.show or feed_title or chosen_show.slug or DEFAULT_SHOW).strip()
                image_url = feed_image
                best_item = chosen
                enclosure_url = chosen.enclosure_url
                feed_mode = True
            else:
                stories = discover_story_links(html)
                if not stories:
                    print("Error: no story links found on section page.", file=sys.stderr)
                    return 2
                interactive = args.interactive or (sys.stdin.isatty() and not args.non_interactive)
                if not interactive:
                    print("Error: non-interactive mode requires --story-list to pick a story.", file=sys.stderr)
                    return 2
                chosen_story = choose_story_interactive(stories)
                if not chosen_story:
                    print("No story selected.", file=sys.stderr)
                    return 1
                args.url = chosen_story.url
                with Spinner("Fetching story", enabled=not args.verbose):
                    html = fetch_text(args.url, cache=cache, ignore_cache=ignore_cache)
                debug.write("story.html", html)

    if not feed_mode:
        try:
            state = extract_initial_state(html)
            audio = find_audio_block(state)
        except (ValueError, json.JSONDecodeError) as exc:
            print(f"Error: failed to parse story page: {exc}", file=sys.stderr)
            return 2

        title = args.title or audio.get("title", "")
        description = audio.get("description", "")
        embedded_slug = audio.get("showSlug")
        show_slug = resolve_show_slug(args.provider, args.show, embedded_slug, args.url)
        target_ts_ms = extract_target_timestamp_ms(audio, state)
        image_url = extract_image_url(audio)
        discovered_rss = discover_rss_url(html)
        if args.rss_discover_only:
            if discovered_rss:
                print(discovered_rss)
                return 0
            print("Error: RSS not discovered in story HTML.", file=sys.stderr)
            return 2

        if args.verbose:
            print(f"Resolved title: {title}")
            print(f"Resolved show slug: {show_slug}")
            if target_ts_ms:
                print(f"Target timestamp (ms): {target_ts_ms}")
            if image_url:
                print(f"Image URL: {image_url}")
            if discovered_rss:
                print(f"Discovered RSS: {discovered_rss}")

        feed_url = args.rss_url or discovered_rss or f"https://www.cbc.ca/podcasting/includes/{show_slug}.xml"
        try:
            with Spinner("Fetching RSS feed", enabled=not args.verbose):
                feed_xml = fetch_text(feed_url, cache=cache, ignore_cache=ignore_cache)
            debug.write("feed.xml", feed_xml)
        except (URLError, HTTPError) as exc:
            if not args.rss_url and not discovered_rss:
                try:
                    feed_url, feed_xml = resolve_feed_for_slug(show_slug, cache, ignore_cache)
                    debug.write("feed.xml", feed_xml)
                except Exception:
                    print(f"Error: failed to fetch RSS feed: {exc}", file=sys.stderr)
                    return 2
            else:
                print(f"Error: failed to fetch RSS feed: {exc}", file=sys.stderr)
                return 2

        try:
            items = collect_feed_items(feed_xml, title, description, target_ts_ms)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

        debug.write("scores.json", {"items": [item.__dict__ for item in items]})

        if args.list:
            print_list(items, args.list, args.json)
            return 0
        if args.summary:
            print_list(items, args.summary, args.json)
            return 0

        try:
            best = best_rss_match(items)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2

        interactive = args.interactive or (sys.stdin.isatty() and not args.non_interactive)
        top_sorted = sorted(items, key=lambda x: x.score, reverse=True)
        if interactive and len(top_sorted) > 1:
            if top_sorted[0].score - top_sorted[1].score <= 3:
                chosen = choose_interactive(items)
                if chosen:
                    best = chosen

        best_item = best
        enclosure_url = best.enclosure_url

    if args.print_url or args.dry_run:
        if args.json:
            print(json.dumps({"enclosure_url": enclosure_url}, indent=2))
        else:
            print(enclosure_url)
        return 0

    if feed_mode and (args.interactive or (sys.stdin.isatty() and not args.non_interactive)):
        if not (args.no_download or args.transcribe):
            do_download, do_transcribe, delete_after = prompt_action()
            if not do_download and not do_transcribe and delete_after:
                print("Canceled.")
                return 1
            if not do_download and not do_transcribe:
                if args.json:
                    print(json.dumps({"enclosure_url": enclosure_url}, indent=2))
                else:
                    print(enclosure_url)
                return 0
            if do_transcribe:
                args.transcribe = True
            if not do_download:
                args.no_download = False
                delete_audio_after_transcribe = True
            else:
                delete_audio_after_transcribe = delete_after
        else:
            delete_audio_after_transcribe = False
    else:
        delete_audio_after_transcribe = False

    if args.no_download:
        if args.json:
            print(json.dumps({"enclosure_url": enclosure_url, "download": False}, indent=2))
        else:
            print(f"Resolved URL (no download): {enclosure_url}")
        return 0

    output_template = args.output
    if not output_template:
        output_template = "%(uploader)s/%(upload_date)s - %(title)s.%(ext)s"

    expected_path = get_expected_filepath(
        enclosure_url,
        args.audio_format,
        output_template,
        args.output_dir,
    )

    cmd = ["yt-dlp", "-x", "--audio-format", args.audio_format]
    if args.ytdlp_format:
        cmd += ["-f", args.ytdlp_format]
    if output_template:
        cmd += ["-o", output_template]
    if args.output_dir:
        cmd += ["-P", args.output_dir]
    cmd.append(enclosure_url)

    rc = run_ytdlp(cmd, use_live=not args.verbose)
    if rc != 0 and args.repair and feed_url:
        ignore_cache = True
        try:
            html = fetch_text(args.url, cache=cache, ignore_cache=ignore_cache)
            state = extract_initial_state(html)
            audio = find_audio_block(state)
            title = args.title or audio.get("title", "")
            description = audio.get("description", "")
            target_ts_ms = extract_target_timestamp_ms(audio, state)
            feed_xml = fetch_text(feed_url, cache=cache, ignore_cache=ignore_cache)
            items = collect_feed_items(feed_xml, title, description, target_ts_ms)
            best = best_rss_match(items)
            enclosure_url = best.enclosure_url
            cmd[-1] = enclosure_url
            rc = run_ytdlp(cmd, use_live=not args.verbose)
        except Exception:
            pass

    if rc != 0:
        return rc

    tag_enabled = args.tag and not args.no_tag
    if tag_enabled and expected_path:
        tag_audio_file(
            expected_path,
            title=title,
            show=show_slug,
            pubdate=best_item.pubdate if best_item else None,
            image_url=image_url,
            cache=cache,
            ignore_cache=ignore_cache,
        )

    if args.transcribe and expected_path:
        clip_start = None
        clip_end = None
        clip_duration = None
        if args.transcribe_start:
            try:
                clip_start = parse_timestamp(args.transcribe_start)
            except ValueError as exc:
                print(f"Error: invalid --transcribe-start: {exc}", file=sys.stderr)
                return 2
        if args.transcribe_end:
            try:
                clip_end = parse_timestamp(args.transcribe_end)
            except ValueError as exc:
                print(f"Error: invalid --transcribe-end: {exc}", file=sys.stderr)
                return 2
        if args.transcribe_duration:
            try:
                clip_duration = parse_timestamp(args.transcribe_duration)
            except ValueError as exc:
                print(f"Error: invalid --transcribe-duration: {exc}", file=sys.stderr)
                return 2
        if clip_end is not None and clip_duration is not None:
            print("Error: use --transcribe-end or --transcribe-duration, not both.", file=sys.stderr)
            return 2
        if clip_start is None and clip_end is None and clip_duration is not None:
            clip_start = 0.0
        if clip_start is not None or clip_end is not None or clip_duration is not None:
            if not shutil.which("ffmpeg"):
                print("Error: ffmpeg not found in PATH (required for clip transcription).", file=sys.stderr)
                return 2
        transcribe_audio(
            expected_path,
            args.transcribe_dir,
            args.transcribe_model,
            clip_start,
            clip_end,
            clip_duration,
        )
        if delete_audio_after_transcribe:
            try:
                os.remove(expected_path)
            except Exception:
                pass

    if args.record:
        record_dir = Path(args.record)
        record_dir.mkdir(parents=True, exist_ok=True)
        (record_dir / "story.html").write_text(html, encoding="utf-8")
        (record_dir / "feed.xml").write_text(feed_xml, encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())
