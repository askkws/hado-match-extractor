#!/usr/bin/env python3
"""
HADO Match Extractor - Web Server
FastAPI server for mobile browser access to the HADO match extraction pipeline.
"""

import asyncio
import json
import os
import shutil
import sys
import tempfile
import time
import traceback
import uuid
from pathlib import Path

import aiofiles
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sse_starlette.sse import EventSourceResponse

from hado_detector import HadoMatchExtractor
from hadoworld_detector import HadoWorldMatchExtractor

# --- App setup ---
BASE_DIR = Path(__file__).parent

if sys.platform == 'darwin':
    DATA_DIR = Path.home() / "Library" / "Application Support" / "HADO Match Extractor" / "data"
else:
    _local = os.environ.get("LOCALAPPDATA", str(Path.home() / "AppData" / "Local"))
    DATA_DIR = Path(_local) / "HADO Match Extractor" / "data"

app = FastAPI(title="HADO Match Extractor")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- Job management ---
jobs: dict = {}
processing_lock = asyncio.Lock()
is_processing = False


# --- Startup ---
@app.on_event("startup")
async def startup_event():
    """Clean old data on startup. Add bundled ffmpeg to PATH if present."""
    ffmpeg_dir = BASE_DIR / "ffmpeg"
    if ffmpeg_dir.is_dir():
        os.environ["PATH"] = str(ffmpeg_dir) + os.pathsep + os.environ.get("PATH", "")
    if DATA_DIR.exists():
        shutil.rmtree(DATA_DIR, ignore_errors=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Main page."""
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/upload")
async def upload_video(file: UploadFile = File(...)):
    """Handle video upload via streaming to disk."""
    job_id = str(uuid.uuid4())[:8]
    job_dir = DATA_DIR / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    filename = file.filename or "video.mp4"
    file_path = input_dir / filename

    # Stream upload to disk in 64KB chunks
    total_size = 0
    async with aiofiles.open(file_path, "wb") as f:
        while True:
            chunk = await file.read(65536)
            if not chunk:
                break
            await f.write(chunk)
            total_size += len(chunk)

    jobs[job_id] = {
        "id": job_id,
        "status": "uploaded",
        "filename": filename,
        "file_path": str(file_path),
        "file_size": total_size,
        "output_dir": str(output_dir),
        "progress": [],
        "clips": None,
        "error": None,
        "created_at": time.time(),
    }

    return {"job_id": job_id, "filename": filename, "size": total_size}


@app.post("/upload_path")
async def upload_from_path(request: Request):
    """Handle video by linking/copying from a local file path (desktop app mode)."""
    body = await request.json()
    src_path = body.get("path", "")
    src = Path(src_path)

    if not src.exists() or not src.is_file():
        raise HTTPException(status_code=400, detail="ファイルが見つかりません")

    job_id = str(uuid.uuid4())[:8]
    job_dir = DATA_DIR / job_id
    input_dir = job_dir / "input"
    output_dir = job_dir / "output"
    input_dir.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)

    dest = input_dir / src.name

    def _link_or_copy():
        try:
            os.link(str(src), str(dest))  # hard link: instant, no extra disk usage
        except OSError:
            shutil.copy2(str(src), str(dest))

    loop = asyncio.get_event_loop()
    await loop.run_in_executor(None, _link_or_copy)

    total_size = dest.stat().st_size
    jobs[job_id] = {
        "id": job_id,
        "status": "uploaded",
        "filename": src.name,
        "file_path": str(dest),
        "file_size": total_size,
        "output_dir": str(output_dir),
        "progress": [],
        "clips": None,
        "error": None,
        "created_at": time.time(),
    }

    return {"job_id": job_id, "filename": src.name, "size": total_size}


@app.post("/process/{job_id}")
async def process_video(job_id: str, request: Request):
    """Start processing a video (background task)."""
    global is_processing

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs[job_id]
    if job["status"] not in ("uploaded",):
        raise HTTPException(status_code=400, detail="このジョブは処理できません")

    if is_processing:
        raise HTTPException(status_code=409, detail="別の動画を処理中です。完了までお待ちください。")

    # Read game_type from request body
    try:
        body = await request.json()
        game_type = body.get("game_type", "hado")
    except Exception:
        game_type = "hado"

    is_processing = True
    job["status"] = "processing"
    job["progress"] = []
    job["game_type"] = game_type

    # Launch processing in background
    asyncio.create_task(_run_extraction(job_id))

    return {"status": "processing", "job_id": job_id}


async def _run_extraction(job_id: str):
    """Run extraction in a background thread."""
    global is_processing
    job = jobs[job_id]

    def progress_callback(stage, message, pct):
        entry = {
            "stage": stage,
            "message": message,
            "pct": pct,
            "time": time.time(),
        }
        job["progress"].append(entry)

    try:
        game_type = job.get("game_type", "hado")
        if game_type == "hadoworld":
            extractor = HadoWorldMatchExtractor(
                video_path=job["file_path"],
                output_dir=job["output_dir"],
                temp_dir=os.path.join(tempfile.gettempdir(), f"hado_extraction_{job_id}"),
                progress_callback=progress_callback,
            )
        else:
            extractor = HadoMatchExtractor(
                video_path=job["file_path"],
                output_dir=job["output_dir"],
                temp_dir=os.path.join(tempfile.gettempdir(), f"hado_extraction_{job_id}"),
                progress_callback=progress_callback,
            )

        # Run in thread pool to avoid blocking the event loop
        loop = asyncio.get_event_loop()
        clips = await loop.run_in_executor(None, lambda: extractor.run(cleanup=True))

        if clips:
            job["clips"] = clips
            job["status"] = "completed"

            # Delete input video to save space
            input_dir = Path(job["file_path"]).parent
            shutil.rmtree(input_dir, ignore_errors=True)
        else:
            job["status"] = "failed"
            job["error"] = "HADOの試合が見つかりませんでした。\nHADO大会の試合動画を選択してください。"

    except Exception as e:
        job["status"] = "failed"
        tb = traceback.format_exc()
        job["error"] = str(e)
        print(f"[ERROR] job {job_id}: {e}\n{tb}", flush=True)
    finally:
        is_processing = False


@app.get("/progress/{job_id}")
async def progress_stream(job_id: str):
    """SSE endpoint for processing progress."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    async def event_generator():
        last_index = 0
        while True:
            job = jobs.get(job_id)
            if not job:
                break

            # Send any new progress entries
            progress = job["progress"]
            while last_index < len(progress):
                entry = progress[last_index]
                yield {
                    "event": "progress",
                    "data": json.dumps(entry, ensure_ascii=False),
                }
                last_index += 1

            # Check if done
            if job["status"] == "completed":
                yield {
                    "event": "completed",
                    "data": json.dumps({
                        "clips": job["clips"],
                        "job_id": job_id,
                    }, ensure_ascii=False),
                }
                break
            elif job["status"] == "failed":
                yield {
                    "event": "error",
                    "data": json.dumps({
                        "error": job.get("error", "不明なエラー"),
                    }, ensure_ascii=False),
                }
                break

            await asyncio.sleep(0.5)

    return EventSourceResponse(event_generator())


@app.get("/results/{job_id}")
async def get_results(job_id: str):
    """Get results as JSON."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    job = jobs[job_id]
    if job["status"] != "completed":
        raise HTTPException(status_code=400, detail="処理がまだ完了していません")

    # List output files
    output_dir = Path(job["output_dir"])
    files = []
    for f in sorted(output_dir.iterdir()):
        if f.suffix == ".mp4":
            files.append({
                "filename": f.name,
                "size": f.stat().st_size,
            })

    return {
        "job_id": job_id,
        "clips": job["clips"],
        "files": files,
    }


@app.get("/download/{job_id}/{filename}")
async def download_file(job_id: str, filename: str):
    """Download a clip file."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    # Sanitize filename to prevent path traversal
    safe_filename = Path(filename).name
    file_path = Path(jobs[job_id]["output_dir"]) / safe_filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    return FileResponse(
        path=str(file_path),
        filename=safe_filename,
        media_type="video/mp4",
    )


@app.get("/output_path/{job_id}/{filename}")
async def get_output_path(job_id: str, filename: str):
    """Return the local filesystem path of an output file (desktop app use only)."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")

    safe_filename = Path(filename).name
    file_path = Path(jobs[job_id]["output_dir"]) / safe_filename

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="ファイルが見つかりません")

    return {"path": str(file_path), "filename": safe_filename}


# --- Main ---
if __name__ == "__main__":
    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        timeout_keep_alive=300,
    )
