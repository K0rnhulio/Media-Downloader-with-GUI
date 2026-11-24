#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Instagram Video Downloader.
Downloads videos from Instagram posts, reels, stories, and IGTV using yt-dlp.
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

logger = get_logger("InstagramDownloader")

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Instagram_Videos")

_INSTAGRAM_PATTERNS = (
    re.compile(r"https?://(www\.)?instagram\.com/p/[a-zA-Z0-9_-]+/?"),
    re.compile(r"https?://(www\.)?instagram\.com/reel/[a-zA-Z0-9_-]+/?"),
    re.compile(r"https?://(www\.)?instagram\.com/stories/[a-zA-Z0-9_.]+/[0-9]+/?"),
    re.compile(r"https?://(www\.)?instagram\.com/tv/[a-zA-Z0-9_-]+/?"),
    re.compile(r"https?://(www\.)?instagr\.am/p/[a-zA-Z0-9_-]+/?"),
    re.compile(r"https?://(www\.)?instagr\.am/reel/[a-zA-Z0-9_-]+/?"),
)


def is_valid_instagram_url(url: str) -> bool:
    """Return True if the URL is a valid Instagram post/reel/story/tv URL."""
    is_valid = any(pattern.match(url.strip()) for pattern in _INSTAGRAM_PATTERNS)
    if not is_valid:
        logger.warning("Invalid Instagram URL: %s", url)
    return is_valid


def download_instagram_video(
    url: str,
    quality: str = "best",
    download_dir: str = DEFAULT_DOWNLOAD_DIR,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> bool:
    """Download a video from Instagram in a single yt-dlp pass."""
    if not is_valid_instagram_url(url):
        logger.error("Invalid Instagram URL provided")
        return False

    format_string = QUALITY_FORMAT_MAP.get(quality, QUALITY_FORMAT_MAP["best"])
    success, filepath, output = run_yt_dlp_download(
        url=url,
        output_dir=download_dir,
        output_template="%(uploader)s_%(upload_date)s_%(title).50s.%(ext)s",
        format_spec=format_string,
        extra_args=["--merge-output-format", "mp4"],
        progress_callback=progress_callback,
        logger=logger,
    )
    if not success:
        logger.error("Instagram download failed: %s", output)
    else:
        logger.info("Instagram download succeeded: %s", filepath)
    return success


def main() -> None:
    parser = argparse.ArgumentParser(description="Instagram Video Downloader")
    parser.add_argument("url", help="Instagram video URL")
    parser.add_argument("-q", "--quality", default="best", choices=["best", "medium", "worst"], help="Video quality")
    parser.add_argument("-o", "--output", default=DEFAULT_DOWNLOAD_DIR, help="Output directory")
    args = parser.parse_args()

    ok = download_instagram_video(args.url, args.quality, args.output)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
