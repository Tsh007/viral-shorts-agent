"""
step2_download.py — Hyper-resilient downloader using Auto-Updating yt-dlp & Multi-Tier APIs.
"""

from __future__ import annotations

import re
import sys
import subprocess
import requests
import urllib3
from pathlib import Path

from config import SOURCE_VIDEO, logger

# Disable SSL warnings for decentralized community fallback APIs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def _ensure_latest_ytdlp() -> None:
    """Forces yt-dlp to the absolute latest version to bypass new YouTube bot checks."""
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
            check=True,
            capture_output=True
        )
    except Exception as exc:
        logger.debug("yt-dlp auto-update skipped: %s", exc)


def _extract_video_id(url: str) -> str:
    match = re.search(r"(?:shorts/|v=|=)([a-zA-Z0-9_-]{11})", url)
    return match.group(1) if match else url.split("/")[-1]


def _download_via_invidious(video_id: str, dest_path: Path) -> bool:
    """Tier 2: Stream directly from dynamically discovered healthy Invidious instances."""
    logger.info("Attempting Tier 2 Fallback: Dynamic Invidious API...")
    
    instances = ["https://yewtu.be", "https://invidious.nerdvpn.de"]
    try:
        # Fetch a real-time list of 100% healthy nodes
        resp = requests.get("https://api.invidious.io/instances.json?sort_by=health", timeout=10)
        if resp.status_code == 200:
            nodes = [f"https://{i[0]}" for i in resp.json() if i[1].get("api") and i[1].get("type") == "https"]
            if nodes:
                instances = nodes[:6]
    except Exception:
        pass

    for instance in instances:
        try:
            r = requests.get(f"{instance}/api/v1/videos/{video_id}", timeout=10, verify=False)
            if r.status_code != 200:
                continue
                
            streams = r.json().get("formatStreams", [])
            mp4_streams = [s for s in streams if "mp4" in s.get("container", "").lower()]
            if not mp4_streams:
                continue

            stream_url = mp4_streams[0]["url"]
            with requests.get(stream_url, stream=True, timeout=60, verify=False) as stream_resp:
                stream_resp.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in stream_resp.iter_content(chunk_size=1048576):
                        f.write(chunk)

            if dest_path.exists() and dest_path.stat().st_size > 0:
                logger.info("✓ Downloaded via Invidious instance: %s", instance)
                return True
        except Exception:
            continue
            
    return False


def _download_via_cobalt(url: str, dest_path: Path) -> bool:
    """Tier 3: Stream via Cobalt v7 API with required Origin spoofing headers."""
    logger.info("Attempting Tier 3 Fallback: Cobalt API...")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://cobalt.tools",
        "Referer": "https://cobalt.tools/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    
    instances = ["https://api.cobalt.tools", "https://cobalt-api.kwi.li"]
    
    for instance in instances:
        try:
            resp = requests.post(instance, json={"url": url}, headers=headers, timeout=15, verify=False)
            if resp.status_code in (200, 201):
                media_url = resp.json().get("url")
                if media_url:
                    with requests.get(media_url, stream=True, timeout=60, verify=False) as r:
                        r.raise_for_status()
                        with open(dest_path, "wb") as f:
                            for chunk in r.iter_content(chunk_size=1048576):
                                f.write(chunk)
                    if dest_path.exists() and dest_path.stat().st_size > 0:
                        logger.info("✓ Downloaded via Cobalt API: %s", instance)
                        return True
        except Exception:
            continue
            
    return False


def _download_via_piped(video_id: str, dest_path: Path) -> bool:
    """Tier 4: Stream via Piped API using error-resistant parsing."""
    logger.info("Attempting Tier 4 Fallback: Piped API...")
    nodes = [
        "https://pipedapi.kavin.rocks",
        "https://pipedapi.tokhmi.xyz",
        "https://api.piped.projectsegfau.lt",
        "https://pipedapi.smnz.de"
    ]

    for node in nodes:
        try:
            resp = requests.get(f"{node}/streams/{video_id}", timeout=10, verify=False)
            if resp.status_code != 200:
                continue

            # Safely handle Cloudflare HTML blocks disguised as 200s
            try:
                data = resp.json()
            except ValueError:
                continue
                
            video_streams = data.get("videoStreams", [])
            if not video_streams:
                continue

            mp4_streams = [s for s in video_streams if s.get("format") == "MPEG_4" or "mp4" in s.get("mimeType", "")]
            target_stream = mp4_streams[0] if mp4_streams else video_streams[0]
            stream_url = target_stream.get("url")

            if not stream_url:
                continue

            with requests.get(stream_url, stream=True, timeout=60, verify=False) as r:
                r.raise_for_status()
                with open(dest_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1048576):
                        f.write(chunk)

            if dest_path.exists() and dest_path.stat().st_size > 0:
                logger.info("✓ Downloaded via Piped instance: %s", node)
                return True
        except Exception:
            continue

    return False


def download_video(url: str, dest: str = SOURCE_VIDEO) -> Path:
    _ensure_latest_ytdlp()
    import yt_dlp

    out_path = Path(dest)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    ydl_opts = {
        "format": "bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(out_path.with_suffix("")) + ".%(ext)s",
        "merge_output_format": "mp4",
        "quiet": False,
        "no_warnings": True,
        "retries": 3,
        "socket_timeout": 30,
        "source_address": "0.0.0.0", 
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web", "tv", "ios"]
            }
        },
    }

    logger.info("Downloading: %s", url)

    # Tier 1: yt-dlp (Primary)
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except Exception as exc:
        logger.warning("Tier 1 (yt-dlp) failed. Moving to fallbacks...")

    if out_path.exists() and out_path.stat().st_size > 0:
        logger.info("✓ Downloaded via yt-dlp: %s (%.1f MB)", out_path, out_path.stat().st_size / 1e6)
        return out_path

    alt = out_path.with_suffix(".mp4")
    if alt.exists() and alt.stat().st_size > 0:
        return alt

    video_id = _extract_video_id(url)

    # Execute Fallback Tiers sequentially
    if _download_via_invidious(video_id, out_path):
        return out_path
        
    if _download_via_cobalt(url, out_path):
        return out_path
        
    if _download_via_piped(video_id, out_path):
        return out_path

    raise RuntimeError(f"Critical Failure: All download tiers (yt-dlp, Invidious, Cobalt, Piped) failed for {url}")


def main(url: str) -> Path:
    return download_video(url)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(1)
    try:
        main(sys.argv[1])
    except Exception as exc:
        logger.critical("Step 2 failed: %s", exc)
        sys.exit(1)