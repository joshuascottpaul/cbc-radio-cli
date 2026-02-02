#!/usr/bin/env python3
import argparse
import contextlib
import io
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

def _ensure_python_version(min_major: int = 3, min_minor: int = 11) -> None:
    import sys

    if sys.version_info < (min_major, min_minor):
        raise RuntimeError(
            f"Python {min_major}.{min_minor}+ is required. You are running {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}."
        )


try:
    _ensure_python_version()
    from cbc_ideas_audio_dl import build_parser, run
except ModuleNotFoundError:
    script_dir = Path(__file__).resolve().parent
    candidates = [
        script_dir / "cbc_ideas_audio_dl.py",
        script_dir / "cbc-radio-cli",
    ]
    candidate = None
    for path in candidates:
        if path.exists():
            candidate = path
            break
    if candidate is None:
        raise
    import importlib.machinery
    import importlib.util

    loader = importlib.machinery.SourceFileLoader("cbc_ideas_audio_dl", str(candidate))
    spec = importlib.util.spec_from_loader("cbc_ideas_audio_dl", loader)
    if not spec or not spec.loader:
        raise
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build_parser = module.build_parser
    run = module.run

_SCRIPT_DIR = Path(__file__).resolve().parent
_TEMPLATE_CANDIDATES = [
    _SCRIPT_DIR / "web" / "templates",
    _SCRIPT_DIR / "templates",
    _SCRIPT_DIR / ".." / "share" / "cbc-radio-cli" / "templates",
    Path("/opt/homebrew/share/cbc-radio-cli/templates"),
    Path("/usr/local/share/cbc-radio-cli/templates"),
]
_template_dir = None
for path in _TEMPLATE_CANDIDATES:
    if path.exists():
        _template_dir = path
        break
if _template_dir is None:
    raise RuntimeError("Template directory not found. Reinstall cbc-radio-cli.")

TEMPLATES = Jinja2Templates(directory=str(_template_dir))


@dataclass
class Job:
    id: str
    status: str
    output: str
    exit_code: int | None
    started_at: float
    argv: list[str]


app = FastAPI(title="CBC Radio CLI Web")
_jobs: dict[str, Job] = {}
_jobs_lock = threading.Lock()


_LABELS = {
    "dry_run": "Resolve only (no download)",
    "print_url": "Print resolved URL",
    "list": "List top matches",
    "summary": "Summary (non-interactive)",
    "browse_stories": "Browse stories from section URL",
    "story_list": "List stories",
    "show_list": "List shows",
    "show": "Show slug override",
    "rss_url": "RSS override URL",
    "provider": "Provider preset",
    "title": "Title override for matching",
    "no_download": "Resolve only, do not download",
    "output": "Output template",
    "output_dir": "Output directory",
    "audio_format": "Audio format",
    "ytdlp_format": "yt-dlp format selector",
    "tag": "Tag with ID3 metadata",
    "no_tag": "Disable tagging",
    "transcribe": "Transcribe with whisper",
    "transcribe_dir": "Transcription output directory",
    "transcribe_model": "Whisper model",
    "transcribe_start": "Transcribe start time",
    "transcribe_end": "Transcribe end time",
    "transcribe_duration": "Transcribe duration",
    "debug": "Write debug archive",
    "debug_dir": "Debug archive directory",
    "record": "Record fixtures",
    "repair": "Repair (re-resolve on failure)",
    "cache_ttl": "Cache TTL seconds",
    "interactive": "Interactive selection",
    "non_interactive": "Force non-interactive",
}

_GROUPS = {
    "basic": {"url", "dry_run", "print_url", "list", "summary", "browse_stories", "story_list", "show_list"},
    "match": {"show", "rss_url", "provider", "title"},
    "output": {"output", "output_dir", "audio_format", "ytdlp_format"},
    "transcribe": {"transcribe", "transcribe_dir", "transcribe_model", "transcribe_start", "transcribe_end", "transcribe_duration"},
    "advanced": {"tag", "no_tag", "debug", "debug_dir", "record", "repair", "cache_ttl", "interactive", "non_interactive"},
}


def _parser_fields() -> list[dict[str, Any]]:
    parser = build_parser()
    fields: list[dict[str, Any]] = []
    skip_options = {"--web", "--web-host", "--web-port", "--version", "--completion"}
    for action in parser._actions:
        if not action.option_strings:
            continue
        if action.dest == "help":
            continue
        option = action.option_strings[-1]
        if option in skip_options:
            continue
        name = option.lstrip("-").replace("-", "_")
        help_text = action.help or ""
        if isinstance(action, argparse._StoreTrueAction):
            kind = "checkbox"
        elif action.choices:
            kind = "select"
        elif action.type == int:
            kind = "number"
        else:
            kind = "text"
        placeholder = action.metavar or ""
        label = _LABELS.get(name, option)
        fields.append(
            {
                "name": name,
                "option": option,
                "label": label,
                "help": help_text,
                "kind": kind,
                "choices": list(action.choices) if action.choices else [],
                "placeholder": placeholder,
                "takes_value": not isinstance(action, argparse._StoreTrueAction),
            }
        )
    return fields


def _group_fields(fields: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {k: [] for k in _GROUPS}
    for field in fields:
        group_name = None
        for group, names in _GROUPS.items():
            if field["name"] in names:
                group_name = group
                break
        if not group_name:
            group_name = "advanced"
        grouped[group_name].append(field)
    return grouped


def _run_job(job_id: str, argv: list[str]) -> None:
    buf = io.StringIO()
    exit_code = 1
    status = "error"
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        try:
            parser = build_parser()
            args = parser.parse_args(argv)
            exit_code = run(args)
            status = "done" if exit_code == 0 else "error"
        except SystemExit as exc:
            exit_code = int(getattr(exc, "code", 1) or 1)
            status = "error"
        except Exception as exc:
            print(f"Unhandled error: {exc}")
            status = "error"
            exit_code = 1

    with _jobs_lock:
        job = _jobs[job_id]
        job.output = buf.getvalue()
        job.exit_code = exit_code
        job.status = status


@app.get("/")
def index(request: Request):
    fields = _parser_fields()
    return TEMPLATES.TemplateResponse(
        "index.html",
        {"request": request, "groups": _group_fields(fields), "fields": fields},
    )


@app.post("/run")
async def run_job(request: Request):
    form = await request.form()
    url = (form.get("url") or "").strip()
    if not url:
        return JSONResponse({"error": "URL is required"}, status_code=400)

    argv: list[str] = [url]
    for field in _parser_fields():
        name = field["name"]
        option = field["option"]
        if field["kind"] == "checkbox":
            if form.get(name):
                argv.append(option)
            continue
        value = (form.get(name) or "").strip()
        if value:
            argv.extend([option, value])

    if "--interactive" in argv:
        return JSONResponse({"error": "Interactive mode is not supported in the web UI yet."}, status_code=400)

    if "--non-interactive" not in argv:
        argv.append("--non-interactive")

    job_id = uuid.uuid4().hex[:10]
    with _jobs_lock:
        _jobs[job_id] = Job(
            id=job_id,
            status="running",
            output="",
            exit_code=None,
            started_at=time.time(),
            argv=argv,
        )

    thread = threading.Thread(target=_run_job, args=(job_id, argv), daemon=True)
    thread.start()
    return RedirectResponse(url=f"/job/{job_id}", status_code=303)


@app.get("/job/{job_id}")
def job_view(request: Request, job_id: str):
    return TEMPLATES.TemplateResponse("job.html", {"request": request, "job_id": job_id})


@app.get("/jobs")
def jobs_view(request: Request):
    with _jobs_lock:
        jobs = sorted(_jobs.values(), key=lambda j: j.started_at, reverse=True)
    return TEMPLATES.TemplateResponse("jobs.html", {"request": request, "jobs": jobs})


@app.get("/status/{job_id}")
def job_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return JSONResponse({"error": "Not found"}, status_code=404)
        return JSONResponse(
            {
                "id": job.id,
                "status": job.status,
                "exit_code": job.exit_code,
                "output": job.output,
            }
        )


def run_web(host: str = "127.0.0.1", port: int = 8000) -> None:
    import uvicorn

    uvicorn.run("cbc_radio_web:app", host=host, port=port, reload=False)


def main():
    run_web()


if __name__ == "__main__":
    main()
