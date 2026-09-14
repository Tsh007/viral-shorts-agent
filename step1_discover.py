"""
step1_discover.py — Discover the most viral English/International YouTube Short.
"""

from __future__ import annotations

import re
import sys
from datetime import datetime, timezone, timedelta
from typing import Any

import requests

from config import (
    YOUTUBE_API_KEY,
    MIN_DURATION_S,
    MAX_DURATION_S,
    MIN_VIEWS,
    SEARCH_WINDOWS_HOURS,
    MAX_SEARCH_RESULTS,
    logger,
)

BASE_URL = "https://www.googleapis.com/youtube/v3"

# Common Hinglish words used in Romanized Hindi titles
HINGLISH_WORDS = {
    "papa", "mummy", "bhai", "kiya", "chalna", "shuru", "hai", "mein", 
    "desi", "vlog", "jugaad", "kaise", "kya", "ko", "se", "aur", "yeh", 
    "woh", "mera", "meri", "hum", "aap", "nahi", "ke", "liye", "diya"
}


def _parse_iso_duration(iso: str) -> int:
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    return int(m.group(1) or 0) * 3600 + int(m.group(2) or 0) * 60 + int(m.group(3) or 0)


def _is_hindi_or_hinglish(text: str) -> bool:
    """Return True if text contains Devanagari or common Hinglish words."""
    if bool(re.search(r"[\u0900-\u097F]", text)):
        return True
    
    # Strip punctuation and check for Romanized Hindi words
    words = set(re.findall(r'\b[a-z]+\b', text.lower()))
    if words.intersection(HINGLISH_WORDS):
        return True
        
    return False


def _search_window(published_after: str, query: str) -> list[dict[str, Any]]:
    params = {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "videoDuration": "short",
        "publishedAfter": published_after,
        "q": query,
        "regionCode": "US",
        "relevanceLanguage": "en",
        "maxResults": MAX_SEARCH_RESULTS,
        "key": YOUTUBE_API_KEY,
    }
    resp = requests.get(f"{BASE_URL}/search", params=params, timeout=30)
    if resp.status_code != 200:
        logger.warning("search.list failed: %s", resp.text[:200])
        return []
    return resp.json().get("items", [])


def discover_viral_video() -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    candidates: dict[str, dict[str, Any]] = {}

    # Target strict international viral niches
    queries = ["satisfying ASMR", "funny fail", "epic moment", "tech gadgets", "life hacks"]

    for hours in SEARCH_WINDOWS_HOURS:
        published_after = (now - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for q in queries:
            items = _search_window(published_after, q)
            for item in items:
                vid = item["id"].get("videoId")
                if not vid or vid in candidates:
                    continue

                snippet = item["snippet"]
                title = snippet.get("title", "")

                # Exclude Devanagari and Hinglish
                if _is_hindi_or_hinglish(title):
                    continue

                candidates[vid] = {
                    "video_id": vid,
                    "title": title,
                    "channel": snippet.get("channelTitle", ""),
                    "published_at": snippet.get("publishedAt", ""),
                }

    logger.info("Discovery: %d unique international candidates collected.", len(candidates))
    if not candidates:
        return None

    ids = list(candidates.keys())
    for i in range(0, len(ids), 50):
        batch = ids[i : i + 50]
        resp = requests.get(
            f"{BASE_URL}/videos",
            params={
                "part": "contentDetails,statistics",
                "id": ",".join(batch),
                "key": YOUTUBE_API_KEY,
            },
            timeout=30,
        )
        if resp.status_code != 200:
            continue
            
        for item in resp.json().get("items", []):
            vid = item["id"]
            candidates[vid]["duration_s"] = _parse_iso_duration(
                item["contentDetails"].get("duration", "")
            )
            candidates[vid]["views"] = int(item["statistics"].get("viewCount", 0))

    qualified: list[dict[str, Any]] = []
    for vid, data in candidates.items():
        duration = data.get("duration_s", 0)
        views = data.get("views", 0)

        if duration < MIN_DURATION_S or duration > MAX_DURATION_S or views < MIN_VIEWS:
            continue

        published = datetime.fromisoformat(data["published_at"].replace("Z", "+00:00"))
        hours_live = max((now - published).total_seconds() / 3600, 0.5)
        
        data["vph"] = round(views / hours_live, 2)
        data["url"] = f"https://youtube.com/shorts/{vid}"
        qualified.append(data)

    if not qualified:
        return None

    qualified.sort(key=lambda x: x["vph"], reverse=True)
    best = qualified[0]

    logger.info("🏆 Winner: '%s' | VPH=%.0f | views=%d | %s", best["title"][:60], best["vph"], best["views"], best["url"])
    return best


def main() -> dict[str, Any]:
    result = discover_viral_video()
    if not result:
        raise RuntimeError("No viral video found.")
    return result


if __name__ == "__main__":
    main()