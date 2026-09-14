"""
step2_download.py — Download video using OAuth authentication & Piped API fallbacks.
"""

from __future__ import annotations

import re
import sys
import requests
from pathlib import Path

from config import (
    SOURCE_VIDEO,
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN,
    logger,
)

PIPED_INSTANCES = [
    "https://pipedapi.kavin.rocks",
    "https://api.piped.privacydev.net",
    "https://pipedapi.palvelu.org",
]


def _get_access_token() -> str | None:
    """Refreshes YouTube OAuth access token using existing environment credentials."""
    if not all([YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN]):
        logger.warning("YouTube OAuth credentials missing in environment.")
        return None

    try:
        resp = requests.post(
            "https://oauth2.googleapis.com/token",
            data={
                "client_id": YOUTUBE_CLIENT_ID,
                "client_secret": YOUTUBE_CLIENT_SECRET,
                "refresh_token": YOUTUBE_REFRESH_TOKEN,
                "grant_type": "refresh_token",
            },
            timeout=15,
        )
        if resp.status_code == 200:
            return resp.json().get("access_token")
        logger.warning("OAuth token refresh failed: %d — %s", resp.status_code, resp.text)
    except Exception as exc:
        logger.warning("OAuth token request exception: %s", exc)
    return None


def _extract_video_id(url: str) -> str:
    match = re.search(r"(?:shorts/|v=|=)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else url.split("/")[-1]


def _download_via_piped(video_id: str, dest_path: Path) -> bool:
    """Fallback: Stream directly from public Piped API nodes."""
    logger.info("Attempting automated fallback download via Piped API...")

    for instance in PIPED_INSTANCES:
        try:
            resp = requests.get(f"{instance}/streams/{video_id}", timeout=10)
            if resp.status_code != 200:
                continue

            data = resp.json()
            video_streams = data.get("videoStreams", [])
            if not video_streams:
                continue

            # Pick highest quality MP4 stream
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
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "ios", "web"]
            }
        },
    }

    # Attempt to authenticate yt-dlp using OAuth access token
    access_token = _get_access_token()
    if access_token:
        logger.info("Authenticating yt-dlp request using YouTube OAuth token...")
        ydl_opts["http_headers"] = {
            "Authorization": f"Bearer {access_token}"
        }

    logger.info("Downloading: %s", url)

    # Attempt 1: Authenticated yt-dlp download
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

    # Attempt 2: Piped API streaming fallback
    video_id = _extract_video_id(url)
    if _download_via_piped(video_id, out_path):
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