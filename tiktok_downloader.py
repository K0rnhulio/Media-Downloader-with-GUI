#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TikTok Video Downloader (No Watermark).
Downloads videos from TikTok using yt-dlp in a single pass.
"""

import argparse
import os
import re
import sys
from typing import Callable, Optional

from downloader_core import (
    QUALITY_FORMAT_MAP,
    get_logger,
    run_yt_dlp_download,
)

logger = get_logger("TikTokDownloader")

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "TikTok_Videos")

_TIKTOK_PATTERNS = (
    re.compile(r"https?://(www\.|vm\.)?tiktok\.com/(@[^/]+/video/\d+|[A-Za-z0-9]+/?)"),
    re.compile(r"https?://m\.tiktok\.com/v/\d+"),
    re.compile(r"https?://(www\.)?tiktok\.com/t/[A-Za-z0-9]+/?"),
)


def is_valid_tiktok_url(url: str) -> bool:
    """Return True if the URL is a valid TikTok video URL."""
    is_valid = any(pattern.match(url.strip()) for pattern in _TIKTOK_PATTERNS)
    if not is_valid:
        logger.error("Invalid TikTok URL provided: %s", url)
    return is_valid


def download_tiktok_video(
    url: str,
    quality: str = "best",
    download_dir: str = DEFAULT_DOWNLOAD_DIR,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> bool:
    """Download a video from TikTok in a single yt-dlp pass."""
    if not is_valid_tiktok_url(url):
        return False

    format_string = QUALITY_FORMAT_MAP.get(quality, QUALITY_FORMAT_MAP["best"])
    extra_args = [
        "--merge-output-format", "mp4",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "--add-header", "Referer:https://www.tiktok.com/",
        "--no-check-certificate",
    ]

    success, filepath, output = run_yt_dlp_download(
        url=url,
        output_dir=download_dir,
        output_template="%(uploader)s_%(upload_date)s_%(title).50s.%(ext)s",
        format_spec=format_string,
        extra_args=extra_args,
        progress_callback=progress_callback,
        logger=logger,
    )
    if not success:
        logger.error("TikTok download failed: %s", output)
    else:
        logger.info("TikTok download succeeded: %s", filepath)
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="TikTok Video Downloader (No Watermark)")
    parser.add_argument("url", help="TikTok video URL")
    parser.add_argument("-q", "--quality", default="best", choices=["best", "medium", "worst"], help="Video quality")
    parser.add_argument("-o", "--output", default=DEFAULT_DOWNLOAD_DIR, help="Output directory")
    args = parser.parse_args()

    ok = download_tiktok_video(args.url, args.quality, args.output)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
