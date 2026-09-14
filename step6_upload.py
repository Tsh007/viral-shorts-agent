"""
step6_upload.py — Upload final video to YouTube via Data API v3 (resumable).
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

from config import (
    FINAL_VIDEO,
    EDIT_PLAN,
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_REFRESH_TOKEN,
    logger,
)


def _get_access_token() -> str:
    logger.info("Refreshing access token…")
    resp = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "client_id": YOUTUBE_CLIENT_ID,
            "client_secret": YOUTUBE_CLIENT_SECRET,
            "refresh_token": YOUTUBE_REFRESH_TOKEN,
            "grant_type": "refresh_token",
        },
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Token refresh failed: {resp.status_code} — {resp.text}")
    return resp.json()["access_token"]


def _initiate_upload(
    access_token: str, video_path: Path, title: str, description: str, tags: list[str]
) -> str:
    logger.info("Initiating resumable upload…")
    size = video_path.stat().st_size

    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json; charset=UTF-8",
        "X-Upload-Content-Type": "video/mp4",
        "X-Upload-Content-Length": str(size),
    }

    body = {
        "snippet": {
            "title": title[:95],
            "description": description,
            "tags": tags,
            "categoryId": "24",  # Entertainment
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    resp = requests.post(
        "https://www.googleapis.com/upload/youtube/v3/videos"
        "?uploadType=resumable&part=snippet,status",
        headers=headers,
        json=body,
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Initiate failed: {resp.status_code} — {resp.text}")

    upload_url = resp.headers.get("Location")
    if not upload_url:
        raise RuntimeError("No Location header in resumable upload response.")
    return upload_url


def _upload_binary(upload_url: str, video_path: Path, max_retries: int = 3) -> str:
    size = video_path.stat().st_size
    headers = {
        "Content-Type": "video/mp4",
        "Content-Length": str(size),
    }

    logger.info("Uploading %.1f MB…", size / 1e6)

    for attempt in range(1, max_retries + 1):
        try:
            with open(video_path, "rb") as fh:
                resp = requests.put(
                    upload_url, headers=headers, data=fh, timeout=600
                )
            if resp.status_code in (200, 201):
                return resp.json()["id"]
            logger.warning("Attempt %d: HTTP %d — %s", attempt, resp.status_code, resp.text[:200])
        except requests.RequestException as exc:
            logger.warning("Attempt %d network error: %s", attempt, exc)

        if attempt < max_retries:
            time.sleep(5 * (2 ** (attempt - 1)))

    raise RuntimeError("Binary upload failed after retries.")


def upload_video(video_path: str = FINAL_VIDEO, plan_path: str = EDIT_PLAN) -> str:
    if not all([YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN]):
        raise EnvironmentError(
            "Missing YouTube OAuth credentials. Set YOUTUBE_CLIENT_ID, "
            "YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN."
        )

    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    title = plan.get("title", "Hindi Short")
    description = plan.get("description", "")
    tags = plan.get("tags", ["hindi", "shorts"])

    access_token = _get_access_token()
    upload_url = _initiate_upload(
        access_token, Path(video_path), title, description, tags
    )
    video_id = _upload_binary(upload_url, Path(video_path))

    url = f"https://youtu.be/{video_id}"
    logger.info("✓ Uploaded! Video ID: %s | URL: %s", video_id, url)
    return video_id


def main() -> str:
    return upload_video()


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.critical("Step 6 failed: %s", exc, exc_info=True)
        sys.exit(1)