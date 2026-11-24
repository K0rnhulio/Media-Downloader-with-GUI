#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
FastAPI Web Application for Media Downloader.
Designed for containerized deployment on Coolify.
"""

from __future__ import annotations

import os
import shutil
import tempfile
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from typing import Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel

from downloader_core import QUALITY_FORMAT_MAP, get_logger
from facebook_downloader import download_facebook_video, is_valid_facebook_url
from instagram_downloader import download_instagram_video, is_valid_instagram_url
from tiktok_downloader import download_tiktok_video, is_valid_tiktok_url
from twitter_downloader import download_twitter_video, validate_twitter_url
from youtube_downloader_hq import download_youtube_video, validate_youtube_url

logger = get_logger("WebDownloader")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
DOWNLOAD_ROOT = os.environ.get("DOWNLOAD_DIR", os.path.join(tempfile.gettempdir(), "media_downloader_jobs"))
JOB_TTL_SECONDS = int(os.environ.get("JOB_TTL_SECONDS", "1800"))
MAX_WORKERS = int(os.environ.get("MAX_DOWNLOAD_WORKERS", "3"))

os.makedirs(DOWNLOAD_ROOT, exist_ok=True)

VALIDATORS = {
    "YouTube": validate_youtube_url,
    "Facebook": is_valid_facebook_url,
    "Instagram": is_valid_instagram_url,
    "TikTok": is_valid_tiktok_url,
    "Twitter": validate_twitter_url,
}

YOUTUBE_QUALITY_MAP = {
    "best": QUALITY_FORMAT_MAP["best"],
    "medium": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]",
    "worst": "18",
}


@dataclass
class DownloadJob:
    job_id: str
    platform: str
    url: str
    quality: str
    status: str = "queued"
    progress: float = 0.0
    message: str = "Queued..."
    filepath: Optional[str] = None
    filename: Optional[str] = None
    created_at: float = field(default_factory=time.time)

    def to_public_dict(self) -> dict:
        data = asdict(self)
        data.pop("filepath", None)
        return data


class DownloadRequest(BaseModel):
    url: str
    platform: Optional[str] = None
    quality: str = "best"


app = FastAPI(title="Media Downloader", version="1.0.0")
_jobs: Dict[str, DownloadJob] = {}
_jobs_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=MAX_WORKERS)


def detect_platform(url: str) -> Optional[str]:
    """Detect supported platform from URL."""
    cleaned = url.strip()
    if not cleaned:
        return None
    for name, validator in VALIDATORS.items():
        if validator(cleaned):
            return name
    return None


def _cleanup_expired_jobs() -> None:
    """Remove expired job records and their temporary directories."""
    now = time.time()
    expired_ids = []
    with _jobs_lock:
        for job_id, job in _jobs.items():
            if now - job.created_at > JOB_TTL_SECONDS and job.status in ("completed", "failed"):
                expired_ids.append(job_id)
        for job_id in expired_ids:
            _jobs.pop(job_id, None)

    for job_id in expired_ids:
        job_dir = os.path.join(DOWNLOAD_ROOT, job_id)
        if os.path.isdir(job_dir):
            shutil.rmtree(job_dir, ignore_errors=True)


def _find_downloaded_file(job_dir: str) -> Optional[str]:
    """Return the largest downloaded media file in job_dir."""
    if not os.path.isdir(job_dir):
        return None
    candidates = [
        os.path.join(job_dir, name)
        for name in os.listdir(job_dir)
        if os.path.isfile(os.path.join(job_dir, name)) and not name.endswith((".part", ".ytdl", ".temp"))
    ]
    if not candidates:
        return None
    return max(candidates, key=os.path.getsize)


def _run_job(job_id: str) -> None:
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job.status = "downloading"
        job.message = "Starting download..."

    job_dir = os.path.join(DOWNLOAD_ROOT, job_id)
    os.makedirs(job_dir, exist_ok=True)

    def on_progress(pct: float, status: str) -> None:
        with _jobs_lock:
            current = _jobs.get(job_id)
            if current:
                if pct >= 0:
                    current.progress = min(pct, 100.0)
                current.message = status

    try:
        if job.platform == "YouTube":
            fmt = YOUTUBE_QUALITY_MAP.get(job.quality, YOUTUBE_QUALITY_MAP["best"])
            res = download_youtube_video(
                job.url,
                job_dir,
                force_high_quality=True,
                quality=fmt,
                non_interactive=True,
                progress_callback=on_progress,
            )
            ok = res.startswith("Success")
            msg = res
        elif job.platform == "Twitter":
            res = download_twitter_video(job.url, job_dir, job.quality, progress_callback=on_progress)
            ok = res.startswith("Success")
            msg = res
        elif job.platform == "Facebook":
            ok = download_facebook_video(job.url, job.quality, job_dir, progress_callback=on_progress)
            msg = "Facebook video downloaded successfully!" if ok else "Failed to download Facebook video."
        elif job.platform == "Instagram":
            ok = download_instagram_video(job.url, job.quality, job_dir, progress_callback=on_progress)
            msg = "Instagram video downloaded successfully!" if ok else "Failed to download Instagram video."
        elif job.platform == "TikTok":
            ok = download_tiktok_video(job.url, job.quality, job_dir, progress_callback=on_progress)
            msg = "TikTok video downloaded successfully!" if ok else "Failed to download TikTok video."
        else:
            ok = False
            msg = f"Unsupported platform: {job.platform}"

        filepath = _find_downloaded_file(job_dir) if ok else None
        with _jobs_lock:
            current = _jobs.get(job_id)
            if current:
                if ok and filepath:
                    current.status = "completed"
                    current.progress = 100.0
                    current.filepath = filepath
                    current.filename = os.path.basename(filepath)
                    current.message = "Ready to download"
                else:
                    current.status = "failed"
                    current.message = msg or "Download failed"
    except Exception as exc:
        logger.exception("Web download job %s failed: %s", job_id, exc)
        with _jobs_lock:
            current = _jobs.get(job_id)
            if current:
                current.status = "failed"
                current.message = str(exc)


@app.get("/health")
def health() -> dict:
    """Healthcheck endpoint for Coolify."""
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    """Serve the web UI."""
    index_path = os.path.join(STATIC_DIR, "index.html")
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.get("/api/detect")
def api_detect(url: str) -> dict:
    """Detect the platform for a given URL."""
    return {"platform": detect_platform(url)}


@app.post("/api/download")
def api_download(req: DownloadRequest) -> dict:
    """Enqueue a video download job."""
    _cleanup_expired_jobs()

    url = req.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="URL is required.")

    platform = req.platform or detect_platform(url)
    if not platform or platform not in VALIDATORS:
        raise HTTPException(status_code=400, detail="Unsupported or unrecognized URL.")

    if not VALIDATORS[platform](url):
        raise HTTPException(status_code=400, detail=f"Invalid {platform} URL.")

    quality = req.quality if req.quality in ("best", "medium", "worst") else "best"
    job_id = uuid.uuid4().hex
    job = DownloadJob(job_id=job_id, platform=platform, url=url, quality=quality)

    with _jobs_lock:
        _jobs[job_id] = job

    _executor.submit(_run_job, job_id)
    return job.to_public_dict()


@app.get("/api/jobs/{job_id}")
def api_job_status(job_id: str) -> dict:
    """Get current status and progress of a download job."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        return job.to_public_dict()


@app.get("/api/jobs/{job_id}/file")
def api_job_file(job_id: str) -> FileResponse:
    """Stream the downloaded file to the client."""
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found.")
        if job.status != "completed" or not job.filepath or not os.path.exists(job.filepath):
            raise HTTPException(status_code=409, detail="File is not ready.")
        filepath = job.filepath
        filename = job.filename or os.path.basename(filepath)

    return FileResponse(path=filepath, filename=filename, media_type="application/octet-stream")


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run("web_app:app", host="0.0.0.0", port=port)
