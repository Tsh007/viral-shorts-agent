"""
step2_download.py — Download the discovered video using yt-dlp.
"""

from __future__ import annotations

import sys
from pathlib import Path

from config import SOURCE_VIDEO, logger


def download_video(url: str, dest: str = SOURCE_VIDEO) -> Path:
    """
    Download *url* to *dest* using yt-dlp.

    Prefers MP4 H.264 + AAC so FFmpeg can handle it cleanly.
    """
    import yt_dlp

    out_path = Path(dest)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(out_path.with_suffix("")) + ".%(ext)s",
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
        "retries": 3,
        "fragment_retries": 3,
        "socket_timeout": 30,
    }

    logger.info("Downloading: %s", url)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    # yt-dlp may write source.mp4 or source.webm depending on format
    if not out_path.exists():
        alt = out_path.with_suffix(".mp4")
        if alt.exists():
            return alt
        # search for any matching file
        matches = list(out_path.parent.glob(out_path.stem + ".*"))
        matches = [m for m in matches if m.suffix in (".mp4", ".webm", ".mkv")]
        if matches:
            return matches[0]
        raise FileNotFoundError(f"Downloaded file not found at {out_path}")

    logger.info("✓ Downloaded: %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
    return out_path


def main(url: str) -> Path:
    return download_video(url)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python step2_download.py <VIDEO_URL>")
        sys.exit(1)
    try:
        main(sys.argv[1])
    except Exception as exc:
        logger.critical("Step 2 failed: %s", exc, exc_info=True)
        sys.exit(1)