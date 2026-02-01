# CBC Audio Downloader

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](LICENSE)

Download CBC audio from a story URL by resolving the matching podcast episode and handing the enclosure URL to `yt-dlp`.

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
brew install python yt-dlp ffmpeg
python3 -m pip install --user -r requirements.txt
```

## Install (pipx)
```bash
pipx install yt-dlp
brew install ffmpeg
python3 -m pip install --user -r requirements.txt
```

## Quickstart
```bash
brew install yt-dlp ffmpeg
python3 -m pip install --user -r requirements.txt
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

Note: `requirements.txt` includes optional tools (UI, tagging, whisper). Use `requirements-min.txt` to skip whisper.

## Usage (full)

Basic download:
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

Browse a section (use RSS feed when available, pick an episode interactively):
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --interactive
```

Resolve URL only:
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --dry-run
```

List top matches:
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --list 5
```

JSON output for scripting:
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --print-url --json
```

Generate shell completion:
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --completion zsh
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
- `--output-dir` set `yt-dlp` output directory
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

## Cheatsheet

| Goal | Command |
| --- | --- |
| Download audio | `./cbc_ideas_audio_dl.py <URL>` |
| Resolve URL only | `./cbc_ideas_audio_dl.py <URL> --dry-run` |
| List top matches | `./cbc_ideas_audio_dl.py <URL> --list 5` |
| Interactive pick | `./cbc_ideas_audio_dl.py <URL> --interactive` |
| Print URL (JSON) | `./cbc_ideas_audio_dl.py <URL> --print-url --json` |
| Override RSS | `./cbc_ideas_audio_dl.py <URL> --rss-url <RSS>` |
| Custom output dir | `./cbc_ideas_audio_dl.py <URL> --output-dir ./downloads` |
| Tag MP3 | `./cbc_ideas_audio_dl.py <URL> --tag` |
| Transcribe | `./cbc_ideas_audio_dl.py <URL> --transcribe` |
| Transcribe to dir | `./cbc_ideas_audio_dl.py <URL> --transcribe --transcribe-dir ./transcripts` |
| Whisper model | `./cbc_ideas_audio_dl.py <URL> --transcribe --transcribe-model small` |
| Transcribe first 30s | `./cbc_ideas_audio_dl.py <URL> --transcribe --transcribe-duration 30` |
| Transcribe range | `./cbc_ideas_audio_dl.py <URL> --transcribe --transcribe-start 25:31 --transcribe-end 35:00` |
| Debug archive | `./cbc_ideas_audio_dl.py <URL> --debug` |
| Browse a section | `./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --interactive` |
| Browse stories (force story list) | `./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --browse-stories --interactive` |
| List section feed | `./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --list 10` |
| List stories | `./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --story-list 10` |
| List shows | `./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --show-list 10` |
| Action prompt | `./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --interactive` |

## Sample usage (all commands)

Basic download
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073
```

Browse a section (RSS feed when available)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --interactive
```

Browse stories (force story list)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --browse-stories --interactive
```

Resolve URL only
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --dry-run
```

Print URL only (same as dry-run, explicit)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --print-url
```

JSON output
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --print-url --json
```

List top matches
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --list 5
```

Non-interactive summary
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --summary 5
```

Interactive selection
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --interactive
```

Force non-interactive
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --non-interactive
```

Override show slug
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --show ideas
```

Use provider preset
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --provider ideas
```

Override RSS URL
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --rss-url https://www.cbc.ca/podcasting/includes/ideas.xml
```

Discover RSS only
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --rss-discover-only
```

Story list (from section URL)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --story-list 10
```

Section feed list (from section URL)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --list 10
```

Show list (from section URL)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ --show-list 10
```

Override title for matching
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --title "PT 1 | Injustice For All"
```

No download (resolve only)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --no-download
```

Output directory
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --output-dir ./downloads
```

Output template
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --output "%(uploader)s/%(upload_date)s - %(title)s.%(ext)s"
```

Audio format
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --audio-format mp3
```

yt-dlp format selector
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --format "bestaudio"
```

Cache TTL
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --cache-ttl 7200
```

Repair mode (bypass cache + re-resolve)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --repair
```

Tag MP3 (requires mutagen)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --tag
```

Disable tagging explicitly
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --tag --no-tag
```

Transcribe (requires whisper CLI)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --transcribe
```

Transcribe to a directory
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --transcribe --transcribe-dir ./transcripts
```

Transcribe first 30 seconds
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --transcribe --transcribe-duration 30
```

Transcribe a time range
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --transcribe --transcribe-start 25:31 --transcribe-end 35:00
```

Debug archive (auto dir)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --debug
```

Debug archive (custom dir)
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --debug-dir ./debug_run
```

Record fixtures
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --record ./fixtures
```

Verbose logs
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --verbose
```

Shell completion
```bash
./cbc_ideas_audio_dl.py https://www.cbc.ca/radio/ideas/canadian-court-system-lawyers-fairness-justice-1.6836073 --completion zsh
```

Run tests
```bash
python3 -m unittest /Users/jpaul/Desktop/tests/test_cbc_ideas_audio_dl.py
```
