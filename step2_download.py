"""
step2_download.py — Download the discovered video using yt-dlp.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from config import SOURCE_VIDEO, logger


def download_video(url: str, dest: str = SOURCE_VIDEO) -> Path:
    import yt_dlp

    out_path = Path(dest)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(out_path.with_suffix("")) + ".%(ext)s",
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": False,
        "retries": 5,
        "fragment_retries": 5,
        "socket_timeout": 30,
        # Rotate through mobile player clients to bypass bot checks
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb"]
            }
        },
    }

    # Load cookies if exported to output/cookies.txt or passed via env variable
    cookie_path = Path("output/cookies.txt")
    if cookie_path.exists():
        ydl_opts["cookiefile"] = str(cookie_path)

    logger.info("Downloading: %s", url)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([url])

    if not out_path.exists():
        alt = out_path.with_suffix(".mp4")
        if alt.exists():
            return alt
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