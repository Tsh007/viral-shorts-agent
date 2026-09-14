"""
step2_download.py — Download video with yt-dlp, Cobalt API, and dynamic Invidious discovery.
"""

from __future__ import annotations

import re
import sys
import requests
from pathlib import Path

from config import SOURCE_VIDEO, logger


def _extract_video_id(url: str) -> str:
    match = re.search(r"(?:shorts/|v=|=)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else url.split("/")[-1]


def _get_live_invidious_instances() -> list[str]:
    """Dynamically fetch healthy Invidious instances instead of using hardcoded URLs."""
    try:
        resp = requests.get("https://api.invidious.io/instances.json?sort_by=health", timeout=5)
        if resp.status_code == 200:
            instances = []
            for item in resp.json():
                domain, details = item[0], item[1]
                if details.get("type") == "https" and details.get("health", 0) > 80:
                    instances.append(f"https://{domain}")
            return instances[:5]
    except Exception as exc:
        logger.warning("Could not fetch live Invidious list: %s", exc)
    return ["https://yewtu.be", "https://invidious.drgns.space"]


def _download_via_cobalt(url: str, dest_path: Path) -> bool:
    """Fallback download using Cobalt API."""
    cobalt_instances = ["https://api.cobalt.tools", "https://cobalt-api.kwi.li"]
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    payload = {"url": url, "videoQuality": "max"}

    for instance in cobalt_instances:
        try:
            resp = requests.post(instance, json=payload, headers=headers, timeout=15)
            if resp.status_code == 200:
                media_url = resp.json().get("url")
                if media_url:
                    with requests.get(media_url, stream=True, timeout=60) as r:
                        r.raise_for_status()
                        with open(dest_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=1048576):
                                f.write(chunk)
                    if dest_path.exists() and dest_path.stat().st_size > 0:
                        logger.info("✓ Downloaded via Cobalt API: %s", instance)
                        return True
        except Exception as exc:
            logger.warning("Cobalt fallback failed on %s: %s", instance, exc)
    return False


def _download_via_invidious(video_id: str, dest_path: Path) -> bool:
    """Fallback download using live Invidious API instances."""
    instances = _get_live_invidious_instances()
    for instance in instances:
        try:
            resp = requests.get(f"{instance}/api/v1/videos/{video_id}", timeout=10)
            if resp.status_code != 200:
                continue
            streams = resp.json().get("formatStreams", [])
            if not streams:
                continue

            stream_url = streams[0]["url"]
            with requests.get(stream_url, stream=True, timeout=60) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1048576):
                        f.write(chunk)

            if dest_path.exists() and dest_path.stat().st_size > 0:
                logger.info("✓ Downloaded via Invidious instance: %s", instance)
                return True
        except Exception as exc:
            logger.warning("Invidious fallback failed on %s: %s", instance, exc)
    return False


def download_video(url: str, dest: str = SOURCE_VIDEO) -> Path:
    import yt_dlp

    out_path = Path(dest)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # Uses web_embedded and tv clients, which avoid bot checks on datacenter IPs
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
                "player_client": ["web_embedded", "tv", "ios", "mweb"]
            }
        },
    }

    cookie_path = Path("output/cookies.txt")
    if cookie_path.exists():
        content = cookie_path.read_text(encoding="utf-8", errors="ignore").strip()
        if content.startswith("# Netscape HTTP Cookie File"):
            ydl_opts["cookiefile"] = str(cookie_path)

    logger.info("Downloading: %s", url)

    # Attempt 1: yt-dlp with TV/Embedded client emulation
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.warning("yt-dlp blocked or failed: %s", exc)

    if out_path.exists() and out_path.stat().st_size > 0:
        logger.info("✓ Downloaded: %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
        return out_path

    alt = out_path.with_suffix(".mp4")
    if alt.exists() and alt.stat().st_size > 0:
        return alt

    # Attempt 2: Cobalt API
    logger.info("Attempting fallback download via Cobalt API...")
    if _download_via_cobalt(url, out_path):
        return out_path

    # Attempt 3: Dynamic Invidious API
    logger.info("Attempting fallback download via live Invidious instances...")
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