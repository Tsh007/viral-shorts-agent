"""
step2_download.py — Download video with yt-dlp IPv4 bypass, Cobalt API, and Piped fallbacks.
"""

from __future__ import annotations

import re
import sys
import requests
from pathlib import Path

from config import SOURCE_VIDEO, logger

PIPED_NODES = [
    "https://pipedapi.kavin.rocks",
    "https://pipedapi.tokhmi.xyz",
    "https://api.piped.projectsegfau.lt",
    "https://pipedapi.smnz.de"
]


def _extract_video_id(url: str) -> str:
    match = re.search(r"(?:shorts/|v=|=)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else url.split("/")[-1]


def _download_via_cobalt(url: str, dest_path: Path) -> bool:
    """Fallback: Stream directly using Cobalt API v7."""
    logger.info("Attempting automated fallback download via Cobalt API...")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
    }
    
    try:
        resp = requests.post("https://api.cobalt.tools/", json={"url": url}, headers=headers, timeout=15)
        if resp.status_code == 200:
            media_url = resp.json().get("url")
            if media_url:
                with requests.get(media_url, stream=True, timeout=60) as r:
                    r.raise_for_status()
                    with open(dest_path, "wb") as f:
                        for chunk in r.iter_content(chunk_size=1048576):
                            f.write(chunk)
                if dest_path.exists() and dest_path.stat().st_size > 0:
                    logger.info("✓ Downloaded via Cobalt API")
                    return True
    except Exception as exc:
        logger.warning("Cobalt fallback failed: %s", exc)
    return False


def _download_via_piped(video_id: str, dest_path: Path) -> bool:
    """Fallback: Stream directly from public Piped API nodes."""
    logger.info("Attempting automated fallback download via Piped APIs...")

    for instance in PIPED_NODES:
        try:
            resp = requests.get(f"{instance}/streams/{video_id}", timeout=10)
            if resp.status_code != 200:
                continue

            data = resp.json()
            video_streams = data.get("videoStreams", [])
            if not video_streams:
                continue

            mp4_streams = [s for s in video_streams if s.get("format") == "MPEG_4" or "mp4" in s.get("mimeType", "")]
            target_stream = mp4_streams[0] if mp4_streams else video_streams[0]
            stream_url = target_stream.get("url")

            if not stream_url:
                continue

            with requests.get(stream_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1048576):
                        f.write(chunk)

            if dest_path.exists() and dest_path.stat().st_size > 0:
                logger.info("✓ Downloaded via Piped instance: %s", instance)
                return True
        except Exception as exc:
            logger.warning("Piped fallback failed on %s: %s", instance, exc)

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
        "source_address": "0.0.0.0",  # Force IPv4 to bypass GitHub Actions IPv6 blocks
        "extractor_args": {
            "youtube": {
                "player_client": ["tv", "web_embedded"]
            }
        },
    }

    logger.info("Downloading: %s", url)

    # Attempt 1: yt-dlp
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.warning("yt-dlp download failed: %s", exc)

    if out_path.exists() and out_path.stat().st_size > 0:
        logger.info("✓ Downloaded: %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
        return out_path

    alt = out_path.with_suffix(".mp4")
    if alt.exists() and alt.stat().st_size > 0:
        return alt

    # Attempt 2: Cobalt API v7
    if _download_via_cobalt(url, out_path):
        return out_path

    # Attempt 3: Piped API Network
    video_id = _extract_video_id(url)
    if _download_via_piped(video_id, out_path):
        return out_path

    raise RuntimeError(f"All download attempts failed for {url}")


def main(url: str) -> Path:
    return download_video(url)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    main(sys.argv[1])