# CBC Audio Downloader

[![CI](https://github.com/joshuascottpaul/cbc-radio-cli/actions/workflows/tests.yml/badge.svg)](https://github.com/joshuascottpaul/cbc-radio-cli/actions/workflows/tests.yml)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)
[![Homebrew Tap](https://img.shields.io/badge/Homebrew-Tap-brightgreen.svg)](https://github.com/joshuascottpaul/homebrew-cbc-radio-cli)

Download CBC audio from CBC story or section URLs with one command. This tool resolves the correct podcast episode behind a story page, fetches the RSS enclosure URL, and hands it to `yt-dlp` so you get a clean audio file without digging through feeds or page HTML.

First 60 seconds:
```bash
brew tap joshuascottpaul/cbc-radio-cli
brew install cbc-radio-cli
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
cbc-radio-cli --web
```

Why this exists:
- CBC pages don’t always link directly to the audio file.
- The audio often lives in a show’s RSS feed, not on the story page.
- Manually finding the right episode is slow and error‑prone.

Common use cases:
- Save an Ideas episode referenced in a story URL.
- Browse a section and pick a story to download.
- Build a local archive or send audio to a transcription pipeline.

Quick install:
```bash
brew tap joshuascottpaul/cbc-radio-cli
brew install cbc-radio-cli
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

Homebrew tap repo: https://github.com/joshuascottpaul/homebrew-cbc-radio-cli

## Table of contents
- [Requirements](#requirements)
- [Install (brew)](#install-brew)
- [Install (from source)](#install-from-source)
- [Install (pipx)](#install-pipx)
- [Quickstart](#quickstart)
- [Web UI (local)](#web-ui-local)
- [Usage (full)](#usage-full)
- [From source usage (short)](#from-source-usage-short)
- [CLI options (highlights)](#cli-options-highlights)
- [Notes](#notes)
- [Troubleshooting](#troubleshooting)
- [Cheatsheet](#cheatsheet)
- [Sample usage (all commands)](#sample-usage-all-commands)
- [Tests](#tests)
- [Homebrew release flow (maintainers)](#homebrew-release-flow-maintainers)

## Requirements
- Python 3.11+
- `yt-dlp` in your PATH
- Internet access

Optional (nice UI):
- `rich` (tables + live progress bar + status)
- `alive-progress` (spinner fallback)
- `yaspin` (spinner fallback)
- `mutagen` (ID3 tagging)
- `whisper` CLI (transcription)
- `ffmpeg` (required for clip transcription)

## Install (brew)
```bash
brew tap joshuascottpaul/cbc-radio-cli
brew install cbc-radio-cli
```

Then run:
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

## Install (from source)
```bash
brew install python yt-dlp ffmpeg
python3 -m pip install --user -r requirements.txt
# or, minimal (no whisper)
python3 -m pip install --user -r requirements-min.txt
```

## Install (pipx)
```bash
pipx install yt-dlp
brew install ffmpeg
python3 -m pip install --user -r requirements.txt
# or, minimal (no whisper)
python3 -m pip install --user -r requirements-min.txt
```

## Quickstart
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

Note: `requirements.txt` includes optional tools (UI, tagging, whisper). Use `requirements-min.txt` to skip whisper.

## Web UI (local)
Run a local web UI that stays in sync with CLI options:
```bash
cbc-radio-cli --web
```
Then open: `http://127.0.0.1:8000`

Notes:
- The web UI runs locally and calls the same CLI logic.
- Interactive mode isn’t supported yet in the web UI (use list/summary or non-interactive flags).
- You can set `--web-host` and `--web-port` if needed.
- If web deps are missing, the CLI will print a one‑liner install command.

## Usage (full)

Basic download:
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

Browse a section (use RSS feed when available, pick an episode interactively):
```bash
cbc-radio-cli https://www.cbc.ca/radio/ --interactive
```

Resolve URL only:
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --dry-run
```

List top matches:
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --list 5
```

JSON output for scripting:
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --print-url --json
```

Generate shell completion:
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --completion zsh
```

## From source usage (short)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

## CLI options (highlights)
- `--provider` preset show slug (`ideas`, `thecurrent`, `q`, `asithappens`, `day6`)
- `--show` override the RSS show slug
- `--rss-url` override the RSS URL directly
- `--title` override title used for matching
- `--list N` list top N matches with scores (or feed items for section URLs)
- `--interactive` pick from top matches if ambiguous
- `--no-download` resolve only
- `--print-url` print the enclosure URL
- `--output` set `yt-dlp` output template
- `--output-dir` set `yt-dlp` output directory (default: `./downloads`)
- `--audio-format` set format for `yt-dlp` (default `mp3`)
- `--format` pass a format selector to `yt-dlp`
- `--tag` tag MP3s with ID3 metadata (requires `mutagen`)
- `--transcribe` use whisper CLI if installed
- `--transcribe-dir` set whisper output directory
- `--transcribe-model` set whisper model (default: base)
- `--transcribe-start` start time for transcription (seconds or HH:MM:SS)
- `--transcribe-end` end time for transcription (seconds or HH:MM:SS)
- `--transcribe-duration` duration to transcribe (seconds or HH:MM:SS)
- `--debug` write debug archive with HTML, RSS, scores
- `--record DIR` write fixtures for tests
- `--repair` bypass cache and re-resolve if download fails
- `--rss-discover-only` print discovered RSS URL and exit
- `--summary N` print top N matches (non-interactive summary)
- `--browse-stories` treat URL as a section and choose a story
- `--story-list N` list top N discovered stories and exit
- `--show-list N` list top N discovered shows and exit (section URLs)
- `--non-interactive` never prompt; requires `--list` or `--summary` to pick an item
- `--web` launch local web UI
- `--web-host` host for web UI (default `127.0.0.1`)
- `--web-port` port for web UI (default `8000`)
- `--version` print version and exit

## Notes
- Matching is heuristic (token overlap + Part number + date proximity). If it ever misses, use `--title` or `--rss-url`.
- Cache is stored in `.cbc_cache` alongside the script.
- When `rich` is installed, download progress is parsed from `yt-dlp --newline` output and shown as a live progress bar.
- RSS feed is auto-discovered from the story HTML when possible.
- For section URLs, RSS feeds are used when available; otherwise HTML story links are used.
- Show discovery is augmented from the `/podcasting/` page for a full feed list.
- If no RSS is found on a section page, you can pick a show (or list shows) and then browse its RSS feed.
- `--browse-stories` forces story selection (even when a section page has an RSS feed or show links).
- In interactive section mode, you’ll be prompted to download, transcribe, both, URL-only, or cancel.
- Interactive action prompt only appears for section URLs (not direct story URLs).
- Transcribe-only downloads audio first, runs whisper, then deletes the audio file.
- Clip transcription requires `ffmpeg` in PATH.
- Use either `--transcribe-end` or `--transcribe-duration` (not both).
- Runs locally; no data is sent anywhere unless you choose to.

## Troubleshooting
- `ffmpeg not found`: install via `brew install ffmpeg`.
- `whisper not found`: install `openai-whisper` (or use `requirements.txt`).
- `No RSS found`: try `--rss-url` or `--title` to help matching.

## Cheatsheet

| Goal | Command |
| --- | --- |
| Download audio | `cbc-radio-cli <URL>` |
| Resolve URL only | `cbc-radio-cli <URL> --dry-run` |
| List top matches | `cbc-radio-cli <URL> --list 5` |
| Interactive pick | `cbc-radio-cli <URL> --interactive` |
| Print URL (JSON) | `cbc-radio-cli <URL> --print-url --json` |
| Override RSS | `cbc-radio-cli <URL> --rss-url <RSS>` |
| Custom output dir | `cbc-radio-cli <URL> --output-dir ./downloads` |
| Tag MP3 | `cbc-radio-cli <URL> --tag` |
| Transcribe | `cbc-radio-cli <URL> --transcribe` |
| Transcribe to dir | `cbc-radio-cli <URL> --transcribe --transcribe-dir ./transcripts` |
| Whisper model | `cbc-radio-cli <URL> --transcribe --transcribe-model small` |
| Transcribe first 30s | `cbc-radio-cli <URL> --transcribe --transcribe-duration 30` |
| Transcribe range | `cbc-radio-cli <URL> --transcribe --transcribe-start 25:31 --transcribe-end 35:00` |
| Debug archive | `cbc-radio-cli <URL> --debug` |
| Browse a section | `cbc-radio-cli https://www.cbc.ca/radio/ --interactive` |
| Browse stories (force story list) | `cbc-radio-cli https://www.cbc.ca/radio/ --browse-stories --interactive` |
| List section feed | `cbc-radio-cli https://www.cbc.ca/radio/ --list 10` |
| List stories | `cbc-radio-cli https://www.cbc.ca/radio/ --story-list 10` |
| List shows | `cbc-radio-cli https://www.cbc.ca/radio/ --show-list 10` |
| Action prompt | `cbc-radio-cli https://www.cbc.ca/radio/ --interactive` |

## Sample usage (all commands)
<details>
<summary>Expand all examples</summary>

Basic download
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

Browse a section (RSS feed when available)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ --interactive
```

Browse stories (force story list)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ --browse-stories --interactive
```

Resolve URL only
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --dry-run
```

Print URL only (same as dry-run, explicit)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --print-url
```

JSON output
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --print-url --json
```

List top matches
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --list 5
```

Non-interactive summary
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --summary 5
```

Interactive selection
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --interactive
```

Force non-interactive
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --non-interactive
```

Override show slug
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --show ideas
```

Use provider preset
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --provider ideas
```

Override RSS URL
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --rss-url https://www.cbc.ca/podcasting/includes/ideas.xml
```

Discover RSS only
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --rss-discover-only
```

Story list (from section URL)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ --story-list 10
```

Section feed list (from section URL)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ --list 10
```

Show list (from section URL)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ --show-list 10
```

Override title for matching
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --title "PT 1 | Injustice For All"
```

No download (resolve only)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --no-download
```

Output directory
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --output-dir ./downloads
```

Output template
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --output "%(uploader)s/%(upload_date)s - %(title)s.%(ext)s"
```

Audio format
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --audio-format mp3
```

yt-dlp format selector
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --format "bestaudio"
```

Cache TTL
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --cache-ttl 7200
```

Repair mode (bypass cache + re-resolve)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --repair
```

Tag MP3 (requires mutagen)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --tag
```

Disable tagging explicitly
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --tag --no-tag
```

Transcribe (requires whisper CLI)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --transcribe
```

Transcribe to a directory
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --transcribe --transcribe-dir ./transcripts
```

Transcribe first 30 seconds
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --transcribe --transcribe-duration 30
```

Transcribe a time range
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --transcribe --transcribe-start 25:31 --transcribe-end 35:00
```

Debug archive (auto dir)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --debug
```

Debug archive (custom dir)
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --debug-dir ./debug_run
```

Record fixtures
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --record ./fixtures
```

Verbose logs
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --verbose
```

Shell completion
```bash
cbc-radio-cli https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --completion zsh
```

</details>

## Tests
```bash
pytest -q
```
If you don’t have `pytest` installed, use:
```bash
brew install pytest
```

## Homebrew release flow (maintainers)
1) Create a GitHub release/tag (e.g., `v0.2.0`) in `cbc-radio-cli`.
2) The `Update Homebrew Tap` workflow updates the tap formula automatically.
3) Ensure `HOMEBREW_TAP_TOKEN` secret is set with `repo` scope for the tap repo.
