#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
High Quality YouTube Video Downloader.
Downloads videos from YouTube using yt-dlp in a single pass.
"""

import argparse
import os
import re
import subprocess
import sys
from typing import Callable, Optional

from downloader_core import (
    QUALITY_FORMAT_MAP,
    get_ffmpeg_path,
    get_logger,
    get_video_dimensions,
    get_video_info,
    get_yt_dlp_path,
    run_yt_dlp_download,
)

logger = get_logger("YouTubeDownloader")

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "YouTube_Videos_HQ")

_YOUTUBE_PATTERNS = (
    re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/shorts/([a-zA-Z0-9_-]+)(?:\?.*)?$"),
    re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/watch\?v=([a-zA-Z0-9_-]+)(?:&.*)?$"),
    re.compile(r"^https?://(?:www\.|m\.)?youtube\.com/live/([a-zA-Z0-9_-]+)(?:\?.*)?$"),
    re.compile(r"^https?://(?:www\.)?youtu\.be/([a-zA-Z0-9_-]+)(?:\?.*)?$"),
)


def validate_youtube_url(url: str) -> bool:
    """Return True if the URL is a valid YouTube video/shorts/live URL."""
    return any(pattern.match(url.strip()) for pattern in _YOUTUBE_PATTERNS)


def download_youtube_video(
    url: str,
    output_path: Optional[str] = None,
    force_high_quality: bool = True,
    quality: str = "best",
    non_interactive: bool = False,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    Download a YouTube video using yt-dlp in a single pass.

    Returns a status string starting with 'Success:' or 'Error:'.
    """
    if not validate_youtube_url(url):
        return "Error: Invalid YouTube URL."

    if quality in QUALITY_FORMAT_MAP:
        format_id = QUALITY_FORMAT_MAP[quality]
    elif force_high_quality and quality == "best":
        format_id = QUALITY_FORMAT_MAP["best"]
    else:
        format_id = quality

    if not non_interactive:
        video_info = get_video_info(url)
        if video_info:
            print(f"\nVideo Title: {video_info.get('title', 'Unknown')}")
            print(f"Channel: {video_info.get('channel', 'Unknown')}")
            print(f"Duration: {video_info.get('duration', 0)} seconds")

            yt_dlp_path = get_yt_dlp_path()
            if yt_dlp_path:
                subprocess.run([yt_dlp_path, "-F", url])

            if input("\nDo you want to select a specific format? (y/n): ").strip().lower() == "y":
                custom = input("Enter format ID (e.g., 137+140, 22, best): ").strip()
                if custom:
                    format_id = custom

    extra_args = [
        "--merge-output-format", "mp4",
        "--no-check-certificate",
        "--add-metadata",
    ]
    if force_high_quality:
        extra_args.extend(["--audio-quality", "0"])

    success, filepath, output = run_yt_dlp_download(
        url=url,
        output_dir=output_path,
        output_template="%(title)s.%(ext)s",
        format_spec=format_id,
        extra_args=extra_args,
        progress_callback=progress_callback,
        logger=logger,
    )

    if not success:
        return f"Error: {output}"

    if filepath and os.path.exists(filepath):
        file_size = os.path.getsize(filepath) / (1024 * 1024)
        dimensions = get_video_dimensions(filepath, get_ffmpeg_path())
        dimensions_info = f"\nResolution: {dimensions}" if dimensions else ""
        return (
            f"Success: Video downloaded successfully!\n"
            f"Saved to: {filepath}\n"
            f"File size: {file_size:.2f} MB{dimensions_info}"
        )

    return "Success: Video downloaded successfully!"


def main() -> None:
    parser = argparse.ArgumentParser(description="High Quality YouTube Downloader")
    parser.add_argument("url", help="YouTube video URL")
    parser.add_argument("-q", "--quality", default="best", help="Video quality")
    parser.add_argument("-o", "--output", default=DEFAULT_DOWNLOAD_DIR, help="Output directory")
    parser.add_argument("-f", "--force-high-quality", action="store_true", help="Force highest possible quality")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode (no prompts)")
    args = parser.parse_args()

    if not validate_youtube_url(args.url):
        print("Error: This doesn't appear to be a valid YouTube URL.")
        return

    result = download_youtube_video(
        args.url,
        args.output,
        args.force_high_quality,
        args.quality,
        non_interactive=args.non_interactive,
    )
    print(f"\n{result}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDownload canceled by user.")
        sys.exit(0)
    except Exception as exc:
        print(f"\nAn unexpected error occurred: {exc}")
        sys.exit(1)
