import os
import sys
import threading
import tkinter as tk
from dataclasses import dataclass
from tkinter import messagebox, ttk
from typing import Callable, Dict, Tuple

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from downloader_core import QUALITY_FORMAT_MAP, configure_root_logging, get_logger
from facebook_downloader import download_facebook_video, is_valid_facebook_url
from instagram_downloader import download_instagram_video, is_valid_instagram_url
from tiktok_downloader import download_tiktok_video, is_valid_tiktok_url
from twitter_downloader import download_twitter_video, validate_twitter_url
from youtube_downloader_hq import download_youtube_video, validate_youtube_url

logger = get_logger("VideoDownloaderGUI")


@dataclass(frozen=True)
class PlatformConfig:
    """Configuration for a supported video platform."""

    validator: Callable[[str], bool]
    output_dir: str
    quality_options: Tuple[str, ...]
    quality_map: Dict[str, str]
    runner: Callable[[str, str, str, Callable[[float, str], None]], Tuple[bool, str]]


def _run_youtube(url: str, output_dir: str, quality: str, on_progress: Callable[[float, str], None]) -> Tuple[bool, str]:
    result = download_youtube_video(
        url,
        output_dir,
        force_high_quality=True,
        quality=quality,
        non_interactive=True,
        progress_callback=on_progress,
    )
    return result.startswith("Success"), result


def _run_twitter(url: str, output_dir: str, quality: str, on_progress: Callable[[float, str], None]) -> Tuple[bool, str]:
    result = download_twitter_video(url, output_dir, quality, progress_callback=on_progress)
    return result.startswith("Success"), result


def _make_bool_runner(platform_name: str, fn: Callable[..., bool]) -> Callable[[str, str, str, Callable[[float, str], None]], Tuple[bool, str]]:
    def _runner(url: str, output_dir: str, quality: str, on_progress: Callable[[float, str], None]) -> Tuple[bool, str]:
        ok = fn(url, quality, output_dir, progress_callback=on_progress)
        if ok:
            return True, f"{platform_name} video downloaded successfully!"
        return False, f"Failed to download {platform_name} video. Check the log for details."
    return _runner


_STANDARD_QUALITIES = ("Best Quality", "Medium Quality", "Worst Quality")
_STANDARD_QUALITY_MAP = {
    "Best Quality": "best",
    "Medium Quality": "medium",
    "Worst Quality": "worst",
}

PLATFORMS: Dict[str, PlatformConfig] = {
    "YouTube": PlatformConfig(
        validator=validate_youtube_url,
        output_dir=os.path.join(os.path.expanduser("~"), "Downloads", "YouTube_Videos_HQ"),
        quality_options=("Maximum Quality", "High Quality", "Medium Quality"),
        quality_map={
            "Maximum Quality": QUALITY_FORMAT_MAP["best"],
            "High Quality": "best",
            "Medium Quality": "18",
        },
        runner=_run_youtube,
    ),
    "Facebook": PlatformConfig(
        validator=is_valid_facebook_url,
        output_dir=os.path.join(os.path.expanduser("~"), "Downloads", "Facebook_Videos"),
        quality_options=_STANDARD_QUALITIES,
        quality_map=_STANDARD_QUALITY_MAP,
        runner=_make_bool_runner("Facebook", download_facebook_video),
    ),
    "Instagram": PlatformConfig(
        validator=is_valid_instagram_url,
        output_dir=os.path.join(os.path.expanduser("~"), "Downloads", "Instagram_Videos"),
        quality_options=_STANDARD_QUALITIES,
        quality_map=_STANDARD_QUALITY_MAP,
        runner=_make_bool_runner("Instagram", download_instagram_video),
    ),
    "TikTok": PlatformConfig(
        validator=is_valid_tiktok_url,
        output_dir=os.path.join(os.path.expanduser("~"), "Downloads", "TikTok_Videos"),
        quality_options=_STANDARD_QUALITIES,
        quality_map=_STANDARD_QUALITY_MAP,
        runner=_make_bool_runner("TikTok", download_tiktok_video),
    ),
    "Twitter": PlatformConfig(
        validator=validate_twitter_url,
        output_dir=os.path.join(os.path.expanduser("~"), "Downloads", "Twitter_Videos"),
        quality_options=_STANDARD_QUALITIES,
        quality_map=_STANDARD_QUALITY_MAP,
        runner=_run_twitter,
    ),
}


def detect_platform(url: str) -> str | None:
    """Return the matching platform name for a URL, or None if unrecognized."""
    cleaned = url.strip()
    if not cleaned:
        return None
    for name, cfg in PLATFORMS.items():
        if cfg.validator(cleaned):
            return name
    return None


class VideoDownloaderGUI:
    def __init__(self, root: tk.Tk, log_file: str = ""):
        self.root = root
        self.root.title("Video Downloader Suite")
        self.root.geometry("520x350")
        self.root.resizable(False, False)
        self.root.columnconfigure(1, weight=1)

        style = ttk.Style()
        style.configure("TLabel", font=("Arial", 11))
        style.configure("TButton", font=("Arial", 11))
        style.configure("TCombobox", font=("Arial", 11))

        # Platform selection
        ttk.Label(root, text="Select Platform:").grid(row=0, column=0, sticky="w", padx=12, pady=10)
        self.platform_var = tk.StringVar()
        self.platform_combo = ttk.Combobox(root, textvariable=self.platform_var, state="readonly")
        self.platform_combo["values"] = tuple(PLATFORMS.keys())
        self.platform_combo.current(0)
        self.platform_combo.grid(row=0, column=1, sticky="ew", padx=12, pady=10)
        self.platform_combo.bind("<<ComboboxSelected>>", self.on_platform_change)

        # URL input with auto-detection
        ttk.Label(root, text="Enter URL:").grid(row=1, column=0, sticky="w", padx=12, pady=10)
        self.url_entry = ttk.Entry(root, width=42)
        self.url_entry.grid(row=1, column=1, sticky="ew", padx=12, pady=10)
        self.url_entry.bind("<KeyRelease>", self.on_url_change)

        # Quality selection
        self.quality_label = ttk.Label(root, text="Quality:")
        self.quality_label.grid(row=2, column=0, sticky="w", padx=12, pady=10)
        self.quality_var = tk.StringVar()
        self.quality_combo = ttk.Combobox(root, textvariable=self.quality_var, state="readonly")
        self.quality_combo.grid(row=2, column=1, sticky="ew", padx=12, pady=10)
        self._update_quality_options("YouTube")

        # Download button
        self.download_btn = ttk.Button(root, text="Download", command=self.start_download)
        self.download_btn.grid(row=3, column=0, columnspan=2, pady=18)

        # Determinate progress bar
        self.progress = ttk.Progressbar(root, orient="horizontal", mode="determinate", maximum=100, length=480)
        self.progress.grid(row=4, column=0, columnspan=2, sticky="ew", padx=12)
        self.progress.grid_remove()

        # Status message
        self.status_var = tk.StringVar()
        self.status_label = ttk.Label(root, textvariable=self.status_var, wraplength=480)
        self.status_label.grid(row=5, column=0, columnspan=2, sticky="ew", padx=12, pady=10)

        # Log file info
        if log_file:
            ttk.Label(root, text=f"Log file: {log_file}", font=("Arial", 8)).grid(
                row=6, column=0, columnspan=2, sticky="ew", padx=12
            )

    def _update_quality_options(self, platform: str) -> None:
        cfg = PLATFORMS.get(platform)
        if not cfg:
            return
        self.quality_combo["values"] = cfg.quality_options
        self.quality_combo.current(0)

    def on_platform_change(self, _event=None) -> None:
        platform = self.platform_var.get()
        logger.info("Platform changed to: %s", platform)
        self._update_quality_options(platform)

    def on_url_change(self, _event=None) -> None:
        detected = detect_platform(self.url_entry.get())
        if detected and detected != self.platform_var.get():
            self.platform_var.set(detected)
            self._update_quality_options(detected)

    def _on_progress(self, pct: float, status: str) -> None:
        def _update() -> None:
            if pct >= 0:
                self.progress["value"] = min(pct, 100.0)
            self.status_var.set(status)

        self.root.after(0, _update)

    def download_thread(self, platform: str, url: str, quality_arg: str) -> None:
        cfg = PLATFORMS[platform]
        try:
            logger.info("Starting %s download: %s (quality=%s)", platform, url, quality_arg)
            os.makedirs(cfg.output_dir, exist_ok=True)
            ok, message = cfg.runner(url, cfg.output_dir, quality_arg, self._on_progress)

            safe_msg = message.encode("ascii", "replace").decode("ascii") if isinstance(message, str) else str(message)
            self.root.after(0, lambda: self.status_var.set(safe_msg))
            if ok:
                self.root.after(0, lambda: self.progress.configure(value=100))
                self.root.after(0, lambda: messagebox.showinfo("Success", f"{platform} video downloaded successfully!"))
            else:
                self.root.after(0, lambda: messagebox.showerror("Error", safe_msg))
        except Exception as exc:
            logger.exception("Unhandled exception in download thread: %s", exc)
            err = f"Download failed: {exc}"
            self.root.after(0, lambda: self.status_var.set(err))
            self.root.after(0, lambda: messagebox.showerror("Error", err))
        finally:
            self.root.after(0, self.progress.grid_remove)
            self.root.after(0, lambda: self.download_btn.config(state="normal"))

    def start_download(self) -> None:
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL")
            return

        platform = self.platform_var.get()
        cfg = PLATFORMS[platform]
        if not cfg.validator(url):
            messagebox.showerror("Error", f"Invalid {platform} URL")
            return

        quality_label = self.quality_var.get()
        quality_arg = cfg.quality_map.get(quality_label, "best")

        self.download_btn.config(state="disabled")
        self.status_var.set("Starting download... Please wait.")
        self.progress["value"] = 0
        self.progress.grid()

        thread = threading.Thread(
            target=self.download_thread,
            args=(platform, url, quality_arg),
            daemon=True,
        )
        thread.start()


if __name__ == "__main__":
    session_log = configure_root_logging("downloader_log")
    logger.info("Starting Video Downloader GUI. Log file: %s", session_log)
    root = tk.Tk()
    app = VideoDownloaderGUI(root, log_file=session_log)
    root.mainloop()
