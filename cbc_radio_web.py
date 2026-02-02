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

try:
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
    import importlib.util

    spec = importlib.util.spec_from_file_location("cbc_ideas_audio_dl", candidate)
    if not spec or not spec.loader:
        raise
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    build_parser = module.build_parser
    run = module.run

TEMPLATES = Jinja2Templates(directory="web/templates")


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
        fields.append(
            {
                "name": name,
                "option": option,
                "label": option,
                "help": help_text,
                "kind": kind,
                "choices": list(action.choices) if action.choices else [],
                "placeholder": placeholder,
                "takes_value": not isinstance(action, argparse._StoreTrueAction),
            }
        )
    return fields


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
    return TEMPLATES.TemplateResponse(
        "index.html",
        {"request": request, "fields": _parser_fields()},
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
