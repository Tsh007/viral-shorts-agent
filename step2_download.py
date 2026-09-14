"""
step2_download.py — Download video with yt-dlp and automatic API fallbacks.
"""

from __future__ import annotations

import re
import sys
import requests
from pathlib import Path

from config import SOURCE_VIDEO, logger

# Public Invidious instances used as automated zero-cookie fallbacks
INVIDIOUS_INSTANCES = [
    "https://inv.tux.space",
    "https://invidious.nerdvpn.de",
    "https://vid.puffyan.us",
]


def _extract_video_id(url: str) -> str:
    match = re.search(r"(?:shorts/|v=|=)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else url.split("/")[-1]


def _download_via_invidious(video_id: str, dest_path: Path) -> bool:
    """Fallback method: Downloads direct video streams using public Invidious instances."""
    logger.info("Attempting automated fallback download via Invidious API...")

    for instance in INVIDIOUS_INSTANCES:
        try:
            resp = requests.get(f"{instance}/api/v1/videos/{video_id}", timeout=10)
            if resp.status_code != 200:
                continue

            data = resp.json()
            format_streams = data.get("formatStreams", [])
            
            # Select highest resolution video stream available
            if not format_streams:
                continue
                
            stream_url = format_streams[0]["url"]
            
            with requests.get(stream_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1048576):
                        f.write(chunk)

            if dest_path.exists() and dest_path.stat().st_size > 0:
                logger.info("✓ Downloaded via fallback instance: %s", instance)
                return True

        except Exception as exc:
            logger.warning("Fallback failed on %s: %s", instance, exc)

    return False


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
        "retries": 3,
        "socket_timeout": 30,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "mweb"]
            }
        },
    }

    # Only attach cookies if the file exists AND starts with Netscape header
    cookie_path = Path("output/cookies.txt")
    if cookie_path.exists():
        content = cookie_path.read_text(encoding="utf-8", errors="ignore").strip()
        if content.startswith("# Netscape HTTP Cookie File"):
            ydl_opts["cookiefile"] = str(cookie_path)
        else:
            logger.warning("output/cookies.txt is invalid or empty. Ignoring cookie file.")

    logger.info("Downloading: %s", url)
    
    # Try primary download method via yt-dlp
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.warning("yt-dlp blocked or failed: %s", exc)

    # Validate primary download result
    if out_path.exists() and out_path.stat().st_size > 0:
        logger.info("✓ Downloaded: %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
        return out_path

    alt = out_path.with_suffix(".mp4")
    if alt.exists() and alt.stat().st_size > 0:
        return alt

    # Primary download failed — trigger secondary API fallback
    video_id = _extract_video_id(url)
    if _download_via_invidious(video_id, out_path):
        return out_path

    raise RuntimeError(f"All download attempts failed for {url}")


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