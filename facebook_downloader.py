#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook Video Downloader.
Downloads videos from Facebook posts, reels, and stories using yt-dlp.
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

logger = get_logger("FacebookDownloader")

DEFAULT_DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Facebook_Videos")

_FACEBOOK_PATTERNS = (
    re.compile(r"https?://(www\.|m\.|web\.)?facebook\.com/[^/]+/videos/[0-9]+"),
    re.compile(r"https?://(www\.|m\.|web\.)?facebook\.com/watch\?v=[0-9]+"),
    re.compile(r"https?://(www\.|m\.|web\.)?facebook\.com/[^/]+/posts/[0-9]+"),
    re.compile(r"https?://(www\.|m\.|web\.)?facebook\.com/[^/]+/videos/[^/]+/[0-9]+"),
    re.compile(r"https?://(www\.|m\.|web\.)?facebook\.com/watch/live/\?v=[0-9]+"),
    re.compile(r"https?://(www\.|m\.|web\.)?fb\.watch/[a-zA-Z0-9_-]+/?"),
    re.compile(r"https?://(www\.|m\.|web\.)?facebook\.com/reel/[0-9]+"),
    re.compile(r"https?://(www\.|m\.|web\.)?facebook\.com/story\.php\?story_fbid=[0-9]+&id=[0-9]+"),
)


def is_valid_facebook_url(url: str) -> bool:
    """Return True if the URL is a valid Facebook video/post/reel URL."""
    is_valid = any(pattern.match(url.strip()) for pattern in _FACEBOOK_PATTERNS)
    if not is_valid:
        logger.warning("Invalid Facebook URL: %s", url)
    return is_valid


def download_facebook_video(
    url: str,
    quality: str = "best",
    download_dir: str = DEFAULT_DOWNLOAD_DIR,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> bool:
    """Download a video from Facebook with targeted fallbacks."""
    if not is_valid_facebook_url(url):
        logger.error("Invalid Facebook URL provided")
        return False

    format_string = QUALITY_FORMAT_MAP.get(quality, QUALITY_FORMAT_MAP["best"])
    base_args = ["--merge-output-format", "mp4", "--geo-bypass"]
    output_template = "facebook_video_%(upload_date)s_%(id)s.%(ext)s"

    mobile_url = url.replace("www.facebook.com", "m.facebook.com")
    if mobile_url == url:
        mobile_url = url.replace("facebook.com", "m.facebook.com")

    attempts = [
        (url, format_string, base_args),
        (url, format_string, base_args + ["--cookies-from-browser", "chrome"]),
        (mobile_url, format_string, base_args),
        (mobile_url, "best", ["--no-check-certificate", "--geo-bypass"]),
    ]

    for target_url, fmt, extra in attempts:
        success, filepath, output = run_yt_dlp_download(
            url=target_url,
            output_dir=download_dir,
            output_template=output_template,
            format_spec=fmt,
            extra_args=extra,
            progress_callback=progress_callback,
            logger=logger,
        )
        if success:
            logger.info("Facebook download succeeded: %s", filepath)
            return True
        logger.warning("Facebook attempt failed for %s: %s", target_url, output)

    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Facebook Video Downloader")
    parser.add_argument("url", help="Facebook video URL")
    parser.add_argument("-q", "--quality", default="best", choices=["best", "medium", "worst"], help="Video quality")
    parser.add_argument("-o", "--output", default=DEFAULT_DOWNLOAD_DIR, help="Output directory")
    args = parser.parse_args()

    ok = download_facebook_video(args.url, args.quality, args.output)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
