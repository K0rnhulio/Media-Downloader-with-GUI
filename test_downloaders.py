import os
import unittest
from unittest.mock import MagicMock, patch

import downloader_core
import facebook_downloader
import instagram_downloader
import tiktok_downloader
import twitter_downloader
import video_downloader_gui
import youtube_downloader_hq


class TestURLValidators(unittest.TestCase):
    def test_youtube_urls(self):
        self.assertTrue(youtube_downloader_hq.validate_youtube_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))
        self.assertTrue(youtube_downloader_hq.validate_youtube_url("https://youtu.be/dQw4w9WgXcQ"))
        self.assertTrue(youtube_downloader_hq.validate_youtube_url("https://www.youtube.com/shorts/abc123_-"))
        self.assertTrue(youtube_downloader_hq.validate_youtube_url("https://m.youtube.com/live/abc123"))
        self.assertFalse(youtube_downloader_hq.validate_youtube_url("https://vimeo.com/123456"))

    def test_twitter_urls(self):
        self.assertTrue(twitter_downloader.validate_twitter_url("https://twitter.com/user/status/123456789"))
        self.assertTrue(twitter_downloader.validate_twitter_url("https://x.com/user/status/123456789"))
        self.assertFalse(twitter_downloader.validate_twitter_url("https://x.com/user"))

    def test_facebook_urls(self):
        self.assertTrue(facebook_downloader.is_valid_facebook_url("https://www.facebook.com/watch?v=123456"))
        self.assertTrue(facebook_downloader.is_valid_facebook_url("https://fb.watch/abc123/"))
        self.assertTrue(facebook_downloader.is_valid_facebook_url("https://www.facebook.com/reel/987654321"))
        self.assertFalse(facebook_downloader.is_valid_facebook_url("https://example.com/video"))

    def test_instagram_urls(self):
        self.assertTrue(instagram_downloader.is_valid_instagram_url("https://www.instagram.com/reel/CxYz123/"))
        self.assertTrue(instagram_downloader.is_valid_instagram_url("https://www.instagram.com/p/CxYz123/"))
        self.assertFalse(instagram_downloader.is_valid_instagram_url("https://instagram.com/user/"))

    def test_tiktok_urls(self):
        self.assertTrue(tiktok_downloader.is_valid_tiktok_url("https://www.tiktok.com/@user/video/123456789"))
        self.assertTrue(tiktok_downloader.is_valid_tiktok_url("https://vm.tiktok.com/ZM8abc123/"))
        self.assertFalse(tiktok_downloader.is_valid_tiktok_url("https://tiktok.com/"))

    def test_gui_detect_platform(self):
        self.assertEqual(video_downloader_gui.detect_platform("https://youtu.be/dQw4w9WgXcQ"), "YouTube")
        self.assertEqual(video_downloader_gui.detect_platform("https://x.com/test/status/12345"), "Twitter")
        self.assertEqual(video_downloader_gui.detect_platform("https://www.instagram.com/reel/abc/"), "Instagram")
        self.assertEqual(video_downloader_gui.detect_platform("https://www.tiktok.com/@u/video/123"), "TikTok")
        self.assertEqual(video_downloader_gui.detect_platform("https://fb.watch/abc/"), "Facebook")
        self.assertIsNone(video_downloader_gui.detect_platform("https://example.com"))


class TestDownloaderCore(unittest.TestCase):
    def setUp(self):
        downloader_core.get_yt_dlp_path.cache_clear()
        downloader_core.get_ffmpeg_path.cache_clear()

    @patch("downloader_core.shutil.which", return_value="/usr/bin/yt-dlp")
    @patch("downloader_core.os.path.exists", side_effect=lambda p: p == "/usr/bin/yt-dlp")
    def test_get_yt_dlp_path_cached_from_which(self, _mock_exists, mock_which):
        first = downloader_core.get_yt_dlp_path()
        second = downloader_core.get_yt_dlp_path()
        self.assertEqual(first, "/usr/bin/yt-dlp")
        self.assertEqual(second, "/usr/bin/yt-dlp")
        mock_which.assert_called_once_with("yt-dlp")

    @patch("downloader_core.get_ffmpeg_path", return_value=None)
    @patch("downloader_core.get_yt_dlp_path", return_value="/usr/bin/yt-dlp")
    @patch("downloader_core.subprocess.Popen")
    def test_run_yt_dlp_download_parses_progress_and_filepath(self, mock_popen, _mock_ytdlp, _mock_ffmpeg):
        mock_proc = MagicMock()
        mock_proc.stdout = iter([
            "PROGRESS: 50.0%|2.5MiB/s|00:05\n",
            "PROGRESS:100.0%|3.0MiB/s|00:00\n",
            "FILEPATH:/tmp/video.mp4\n",
        ])
        mock_proc.wait.return_value = 0
        mock_popen.return_value = mock_proc

        progress_updates = []
        ok, filepath, _out = downloader_core.run_yt_dlp_download(
            url="https://youtu.be/dQw4w9WgXcQ",
            output_dir=None,
            output_template="%(title)s.%(ext)s",
            format_spec="best",
            progress_callback=lambda pct, msg: progress_updates.append((pct, msg)),
        )

        self.assertTrue(ok)
        self.assertEqual(filepath, "/tmp/video.mp4")
        self.assertEqual(len(progress_updates), 2)
        self.assertEqual(progress_updates[0][0], 50.0)
        self.assertIn("2.5MiB/s", progress_updates[0][1])
        self.assertEqual(progress_updates[1][0], 100.0)

    @patch("youtube_downloader_hq.run_yt_dlp_download", return_value=(True, None, ""))
    def test_youtube_non_interactive_single_pass(self, mock_run):
        res = youtube_downloader_hq.download_youtube_video(
            "https://youtu.be/dQw4w9WgXcQ",
            output_path=None,
            non_interactive=True,
        )
        self.assertTrue(res.startswith("Success:"))
        mock_run.assert_called_once()

    @patch("facebook_downloader.run_yt_dlp_download")
    def test_facebook_fallback_stops_on_first_success(self, mock_run):
        mock_run.side_effect = [
            (False, None, "err1"),
            (True, "/tmp/fb.mp4", ""),
        ]
        ok = facebook_downloader.download_facebook_video("https://fb.watch/abc/", download_dir=os.getcwd())
        self.assertTrue(ok)
        self.assertEqual(mock_run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
