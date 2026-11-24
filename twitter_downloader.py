#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Twitter/X Video Downloader.
Downloads videos from Twitter/X using yt-dlp in a single pass.
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

logger = get_logger("TwitterDownloader")

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Twitter_Videos")

_TWITTER_PATTERNS = (
    re.compile(r"https?://(www\.|mobile\.)?twitter\.com/\w+/status/\d+"),
    re.compile(r"https?://(www\.|mobile\.)?x\.com/\w+/status/\d+"),
)


def validate_twitter_url(url: str) -> bool:
    """Return True if the URL is a valid Twitter/X status URL."""
    is_valid = any(pattern.match(url.strip()) for pattern in _TWITTER_PATTERNS)
    if not is_valid:
        logger.warning("Invalid Twitter URL: %s", url)
    return is_valid


def download_twitter_video(
    url: str,
    output_path: Optional[str] = None,
    quality: str = "best",
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> str:
    """
    Download a Twitter/X video using yt-dlp in a single pass.

    Returns a status string starting with 'Success:' or 'Error:'.
    """
    if not validate_twitter_url(url):
        return "Error: Invalid Twitter/X URL."

    format_spec = QUALITY_FORMAT_MAP.get(quality, quality)
    extra_args = [
        "--merge-output-format", "mp4",
        "--no-check-certificate",
        "--add-metadata",
    ]

    success, filepath, output = run_yt_dlp_download(
        url=url,
        output_dir=output_path,
        output_template="%(uploader)s_%(upload_date)s_%(id)s.%(ext)s",
        format_spec=format_spec,
        extra_args=extra_args,
        progress_callback=progress_callback,
        logger=logger,
    )

    if not success:
        return f"Error: {output}"

    if filepath and os.path.exists(filepath):
        file_size = os.path.getsize(filepath) / (1024 * 1024)
        return (
            f"Success: Twitter video downloaded successfully!\n"
            f"Saved to: {filepath}\n"
            f"File size: {file_size:.2f} MB"
        )

    return "Success: Twitter video downloaded successfully!"


def main() -> None:
    parser = argparse.ArgumentParser(description="Twitter/X Video Downloader")
    parser.add_argument("url", help="Twitter/X video URL")
    parser.add_argument("-q", "--quality", default="best", choices=["best", "medium", "worst"], help="Video quality")
    parser.add_argument("-o", "--output", default=DEFAULT_DOWNLOAD_DIR, help="Output directory")
    args = parser.parse_args()

    result = download_twitter_video(args.url, args.output, args.quality)
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
