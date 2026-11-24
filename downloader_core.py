#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Shared core utilities for Media Downloader with GUI.

Provides cached binary discovery (yt-dlp, ffmpeg), centralized logging,
single-pass yt-dlp execution with optional progress callbacks, and
shared helper functions to avoid duplication across platform modules.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import platform
import shutil
import subprocess
import tempfile
import urllib.request
import zipfile
from datetime import datetime
from typing import Callable, Iterable, Optional

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BIN_DIR = os.path.join(SCRIPT_DIR, "bin")
DEFAULT_LOG_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "VideoDownloader_Logs")

QUALITY_FORMAT_MAP = {
    "best": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
    "medium": "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]",
    "worst": "worstvideo+worstaudio/worst",
}


def get_logger(name: str, log_to_file: bool = False) -> logging.Logger:
    """Return a configured logger without creating log files on module import."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(logging.NullHandler())

    if log_to_file and not any(isinstance(h, logging.FileHandler) for h in logger.handlers):
        os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
        log_file = os.path.join(
            DEFAULT_LOG_DIR,
            f"{name.lower()}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
        )
        formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def configure_root_logging(prefix: str = "downloader_log") -> str:
    """Configure root logging once for an application session and return log path."""
    os.makedirs(DEFAULT_LOG_DIR, exist_ok=True)
    log_file = os.path.join(
        DEFAULT_LOG_DIR,
        f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt",
    )
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
        force=True,
    )
    return log_file


@functools.lru_cache(maxsize=1)
def get_yt_dlp_path() -> Optional[str]:
    """Locate yt-dlp on PATH or locally, downloading it only if missing."""
    is_windows = platform.system() == "Windows"
    exe_name = "yt-dlp.exe" if is_windows else "yt-dlp"

    local_path = os.path.join(SCRIPT_DIR, exe_name)
    if os.path.exists(local_path):
        return local_path

    system_path = shutil.which("yt-dlp")
    if system_path:
        return system_path

    url = (
        "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        if is_windows
        else "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
    )
    try:
        urllib.request.urlretrieve(url, local_path)
        if not is_windows:
            os.chmod(local_path, 0o755)
        return local_path
    except Exception:
        return None


@functools.lru_cache(maxsize=1)
def get_ffmpeg_path() -> Optional[str]:
    """Locate ffmpeg on PATH or locally, extracting only needed binaries if downloaded."""
    is_windows = platform.system() == "Windows"
    ffmpeg_name = "ffmpeg.exe" if is_windows else "ffmpeg"
    ffprobe_name = "ffprobe.exe" if is_windows else "ffprobe"

    candidates = [
        os.path.join(BIN_DIR, ffmpeg_name),
        os.path.join(SCRIPT_DIR, "ffmpeg", "bin", ffmpeg_name),
        shutil.which("ffmpeg"),
    ]
    for candidate in candidates:
        if candidate and os.path.exists(candidate):
            bin_folder = os.path.dirname(candidate)
            if bin_folder not in os.environ.get("PATH", ""):
                os.environ["PATH"] = bin_folder + os.pathsep + os.environ.get("PATH", "")
            return candidate

    if not is_windows:
        return None

    os.makedirs(BIN_DIR, exist_ok=True)
    ffmpeg_url = "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip"
    target_names = {ffmpeg_name, ffprobe_name}

    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            zip_path = os.path.join(temp_dir, "ffmpeg.zip")
            urllib.request.urlretrieve(ffmpeg_url, zip_path)

            with zipfile.ZipFile(zip_path, "r") as zip_ref:
                for member in zip_ref.infolist():
                    basename = os.path.basename(member.filename)
                    if basename in target_names and "/bin/" in member.filename.replace("\\", "/"):
                        dest_path = os.path.join(BIN_DIR, basename)
                        with zip_ref.open(member) as src, open(dest_path, "wb") as dst:
                            shutil.copyfileobj(src, dst)

        local_ffmpeg = os.path.join(BIN_DIR, ffmpeg_name)
        if os.path.exists(local_ffmpeg):
            os.environ["PATH"] = BIN_DIR + os.pathsep + os.environ.get("PATH", "")
            return local_ffmpeg
    except Exception:
        return None

    return None


def get_video_info(url: str, extra_args: Optional[Iterable[str]] = None) -> Optional[dict]:
    """Fetch video metadata JSON in a single yt-dlp --dump-json call."""
    yt_dlp_path = get_yt_dlp_path()
    if not yt_dlp_path:
        return None

    cmd = [yt_dlp_path, "--dump-json", "--no-playlist", "--no-warnings"]
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception:
        return None
    return None


def get_video_dimensions(file_path: str, ffmpeg_path: Optional[str] = None) -> str:
    """Return 'WIDTHxHEIGHT' via ffprobe, or empty string if unavailable."""
    if not file_path or not os.path.exists(file_path):
        return ""
    ffprobe_name = "ffprobe.exe" if platform.system() == "Windows" else "ffprobe"
    if ffmpeg_path:
        candidate = os.path.join(os.path.dirname(ffmpeg_path), ffprobe_name)
        ffprobe_path = candidate if os.path.exists(candidate) else (shutil.which("ffprobe") or "ffprobe")
    else:
        ffprobe_path = shutil.which("ffprobe") or "ffprobe"

    try:
        cmd = [
            ffprobe_path,
            "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height",
            "-of", "csv=s=x:p=0",
            file_path,
        ]
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


def run_yt_dlp_download(
    url: str,
    output_dir: Optional[str],
    output_template: str,
    format_spec: str,
    extra_args: Optional[Iterable[str]] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    logger: Optional[logging.Logger] = None,
) -> tuple[bool, Optional[str], str]:
    """
    Execute yt-dlp in a single pass and return (success, filepath, error_or_output).

    Uses --print after_move:filepath to capture the exact output path without
    directory scanning or extra --dump-json / --write-info-json subprocesses.
    """
    yt_dlp_path = get_yt_dlp_path()
    if not yt_dlp_path:
        return False, None, "yt-dlp not found and could not be downloaded."

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        full_template = os.path.join(output_dir, output_template)
    else:
        full_template = output_template

    ffmpeg_path = get_ffmpeg_path()

    cmd = [
        yt_dlp_path,
        "--no-warnings",
        "--no-playlist",
        "-f", format_spec,
        "-o", full_template,
        "--newline",
        "--progress-template", "download:PROGRESS:%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s",
        "--print", "after_move:FILEPATH:%(filepath)s",
    ]
    if ffmpeg_path:
        cmd.extend(["--ffmpeg-location", os.path.dirname(ffmpeg_path)])
    if extra_args:
        cmd.extend(extra_args)
    cmd.append(url)

    if logger:
        logger.debug("Running yt-dlp command: %s", " ".join(cmd))

    downloaded_path: Optional[str] = None
    output_lines: list[str] = []

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("PROGRESS:"):
                payload = line[len("PROGRESS:"):]
                parts = payload.split("|")
                pct_str = parts[0].strip().rstrip("%") if parts else ""
                speed = parts[1].strip() if len(parts) > 1 else ""
                eta = parts[2].strip() if len(parts) > 2 else ""
                try:
                    pct = float(pct_str)
                except ValueError:
                    pct = -1.0
                if progress_callback:
                    status = f"Downloading... {pct_str}%"
                    if speed and speed != "N/A":
                        status += f" ({speed}"
                        if eta and eta != "N/A":
                            status += f", ETA {eta}"
                        status += ")"
                    progress_callback(pct, status)
            elif line.startswith("FILEPATH:"):
                downloaded_path = line[len("FILEPATH:"):].strip()
            else:
                output_lines.append(line)

        returncode = proc.wait()
        combined_output = "\n".join(output_lines)
        if returncode == 0:
            return True, downloaded_path, combined_output
        return False, downloaded_path, combined_output or f"yt-dlp exited with code {returncode}"
    except Exception as exc:
        return False, None, str(exc)
