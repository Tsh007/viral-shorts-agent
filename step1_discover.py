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


def _parse_iso_duration(iso: str) -> int:
    """Parse PT45S / PT2M30S → total seconds."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    hours = int(m.group(1) or 0)
    minutes = int(m.group(2) or 0)
    seconds = int(m.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


def _is_devanagari_script(text: str) -> bool:
    """Return True if text contains Devanagari (Hindi) characters."""
    return bool(re.search(r"[\u0900-\u097F]", text))


def _search_window(
    published_after: str,
    query: str,
    max_results: int = MAX_SEARCH_RESULTS,
) -> list[dict[str, Any]]:
    """Search for viral videos enforcing US region and English language."""
    params = {
        "part": "snippet",
        "type": "video",
        "order": "viewCount",
        "videoDuration": "short",
        "publishedAfter": published_after,
        "q": query,
        "regionCode": "US",             # Enforces US/Global region content
        "relevanceLanguage": "en",      # Filters primarily for English metadata
        "maxResults": max_results,
        "key": YOUTUBE_API_KEY,
    }
    resp = requests.get(f"{BASE_URL}/search", params=params, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(
            f"search.list failed: {resp.status_code} — {resp.text[:400]}"
        )
    return resp.json().get("items", [])


def discover_viral_video() -> dict[str, Any] | None:
    now = datetime.now(timezone.utc)
    candidates: dict[str, dict[str, Any]] = {}

    # Target English international viral niches
    queries = ["#shorts", "viral shorts", "satisfying moments", "funny clips", "life hacks"]

    for hours in SEARCH_WINDOWS_HOURS:
        published_after = (now - timedelta(hours=hours)).strftime(
            "%Y-%m-%dT%H:%M:%SZ"
        )
        for q in queries:
            try:
                items = _search_window(published_after, q)
            except Exception as exc:
                logger.warning("Search failed (window=%dh, q='%s'): %s", hours, q, exc)
                continue

            for item in items:
                vid = item["id"].get("videoId")
                if not vid or vid in candidates:
                    continue

                snippet = item["snippet"]
                title = snippet.get("title", "")

                # Exclude any titles containing Devanagari script
                if _is_devanagari_script(title):
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

    # Fetch details
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
            logger.warning("videos.list failed: %s", resp.text[:200])
            continue
        for item in resp.json().get("items", []):
            vid = item["id"]
            candidates[vid]["duration_s"] = _parse_iso_duration(
                item["contentDetails"].get("duration", "")
            )
            candidates[vid]["views"] = int(
                item["statistics"].get("viewCount", 0)
            )

    # Filter & score VPH
    qualified: list[dict[str, Any]] = []
    for vid, data in candidates.items():
        duration = data.get("duration_s", 0)
        views = data.get("views", 0)

        if duration < MIN_DURATION_S or duration > MAX_DURATION_S:
            continue
        if views < MIN_VIEWS:
            continue

        try:
            head = requests.head(
                f"https://www.youtube.com/shorts/{vid}",
                allow_redirects=False,
                timeout=5,
            )
            if head.status_code != 200:
                continue
        except Exception:
            continue

        published = datetime.fromisoformat(
            data["published_at"].replace("Z", "+00:00")
        )
        hours_live = max((now - published).total_seconds() / 3600, 0.5)
        vph = views / hours_live

        data["vph"] = round(vph, 2)
        data["url"] = f"https://youtube.com/shorts/{vid}"
        qualified.append(data)

    if not qualified:
        logger.warning("No qualified international videos found after filtering.")
        return None

    qualified.sort(key=lambda x: x["vph"], reverse=True)
    best = qualified[0]

    logger.info(
        "🏆 Winner: '%s' | VPH=%.0f | views=%d | duration=%ds | %s",
        best["title"][:60],
        best["vph"],
        best["views"],
        best["duration_s"],
        best["url"],
    )
    return best


def main() -> dict[str, Any]:
    if not YOUTUBE_API_KEY:
        raise EnvironmentError("YOUTUBE_API_KEY is not set.")
    result = discover_viral_video()
    if not result:
        raise RuntimeError("No viral video found in the last 24 hours.")
    return result


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.critical("Step 1 failed: %s", exc, exc_info=True)
        sys.exit(1)