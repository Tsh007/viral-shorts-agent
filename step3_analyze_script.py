"""
step3_analyze_script.py — Gemini analyzes the source video and produces:
  1. A Hindi commentary/comedy script
  2. A structured JSON edit plan (cut points, zoom, text overlays, SFX)

The edit plan is what downstream FFmpeg/MovieLite code executes.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

from google import genai
from google.genai import types

from config import (
    GEMINI_API_KEY,
    GEMINI_MODEL,
    SOURCE_VIDEO,
    EDIT_PLAN,
    ensure_dirs,
    logger,
)

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------
SYSTEM_PROMPT = """
You are a viral Hindi YouTube Shorts director and scriptwriter.
You watch a source video and produce a complete edit plan in strict JSON.

Your job: transform the source into a 45–90 second Hindi commentary/comedy video.
"""

USER_PROMPT = """
Watch this video carefully.

Your task:
1. Identify the single most viral moment and explain WHY it went viral.
2. Write a Hindi commentary OR comedy-rewrite script that adds new value.
3. Produce a structured edit plan that a video editor can execute.

CONSTRAINTS:
- Output language for Hindi text: Devanagari script.
- Keep commentary density between 35% and 45% of total runtime.
- Total output video length: 45–90 seconds.
- Use 4–8 segments. Each segment must reference source timestamps.

Return ONLY valid JSON in this exact schema — no markdown, no prose:
{
  "approach": "commentary" | "comedy" | "review",
  "title": "<Hindi YouTube title, max 80 chars>",
  "description": "<Hindi description with 5-10 hashtags>",
  "tags": ["hindi", "shorts", "commentary"],
  "segments": [
    {
      "source_start": "MM:SS",
      "source_end": "MM:SS",
      "hindi_text": "<Hindi TTS narration for this segment>",
      "visual_operation": "zoom_in" | "zoom_out" | "none",
      "zoom_scale": 1.3,
      "text_overlay": "<optional Hindi on-screen text, or empty string>",
      "sfx": ""
    }
  ]
}

RULES:
- source_start and source_end must be within the source video duration.
- Each segment's source clip should be 3–15 seconds long.
- hindi_text should be 15–40 words (about 5–15 seconds of speech).
- zoom_scale between 1.1 and 1.8.
- text_overlay must be in Devanagari script (can be empty string).
- sfx must be one of: "", "whoosh", "ding", "record_scratch", "boom".
"""


# ---------------------------------------------------------------------------
# Gemini helpers
# ---------------------------------------------------------------------------
def _upload_video(client: genai.Client, path: Path) -> types.File:
    """Upload video to Gemini File API and wait for processing."""
    logger.info("Uploading video to Gemini File API…")
    file = client.files.upload(file=str(path))

    while file.state.name == "PROCESSING":
        time.sleep(2)
        file = client.files.get(name=file.name)

    if file.state.name == "FAILED":
        raise RuntimeError("Gemini video processing failed.")

    logger.info("Gemini file ready: %s", file.name)
    return file


def _strip_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        end = -1 if lines[-1].strip() == "```" else len(lines)
        raw = "\n".join(lines[1:end]).strip()
    return raw


def _extract_json(raw: str) -> str:
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def analyze_and_plan(video_path: str = SOURCE_VIDEO) -> dict[str, Any]:
    client = genai.Client(api_key=GEMINI_API_KEY)

    video_file = _upload_video(client, Path(video_path))

    config = types.GenerateContentConfig(
        temperature=0.85,
        top_p=0.95,
        max_output_tokens=8192,
        response_mime_type="application/json",
    )

    full_prompt = f"{SYSTEM_PROMPT}\n\n{USER_PROMPT}"

    for attempt in range(1, 4):
        logger.info("Gemini call attempt %d/3…", attempt)
        try:
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=[full_prompt, video_file],
                config=config,
            )
            raw = response.text
            plan = json.loads(_extract_json(_strip_fences(raw)))
            _validate_plan(plan)
            logger.info(
                "✓ Edit plan generated: '%s' (%d segments, approach=%s)",
                plan["title"],
                len(plan["segments"]),
                plan["approach"],
            )
            return plan
        except Exception as exc:
            logger.warning("Attempt %d failed: %s", attempt, exc)
            if attempt < 3:
                time.sleep(5)

    raise RuntimeError("Failed to generate a valid edit plan after 3 attempts.")


def _validate_plan(plan: dict[str, Any]) -> None:
    required = {"approach", "title", "description", "segments"}
    missing = required - plan.keys()
    if missing:
        raise ValueError(f"Missing keys: {missing}")

    segments = plan["segments"]
    if not isinstance(segments, list) or not (3 <= len(segments) <= 10):
        raise ValueError(f"segments must be 3–10 items, got {len(segments)}")

    for i, seg in enumerate(segments):
        for key in ("source_start", "source_end", "hindi_text", "visual_operation"):
            if key not in seg:
                raise ValueError(f"Segment {i} missing '{key}'")


def save_plan(plan: dict[str, Any], path: str = EDIT_PLAN) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Edit plan saved: %s", out)
    return out


def main() -> dict[str, Any]:
    ensure_dirs()
    plan = analyze_and_plan()
    save_plan(plan)
    return plan


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        logger.critical("Step 3 failed: %s", exc, exc_info=True)
        sys.exit(1)