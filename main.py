"""
main.py — Orchestrator. Runs all 6 steps sequentially.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from config import EDIT_PLAN, ensure_dirs, logger

import step1_discover
import step2_download
import step3_analyze_script
import step4_tts
import step5_edit
import step6_upload


def run() -> None:
    ensure_dirs()

    # ── Step 1: Discover ─────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 1 — Discovering viral YouTube Short")
    logger.info("=" * 60)
    video_info = step1_discover.main()
    logger.info("Discovered: %s", video_info["url"])

    # Save discovery result for reference
    Path("output/discovery.json").write_text(
        json.dumps(video_info, indent=2), encoding="utf-8"
    )

    # ── Step 2: Download ─────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 2 — Downloading source video")
    logger.info("=" * 60)
    step2_download.main(video_info["url"])

    # ── Step 3: Analyze + Hindi script + edit plan ───────────────────
    logger.info("=" * 60)
    logger.info("STEP 3 — Gemini analysis + Hindi script + edit plan")
    logger.info("=" * 60)
    plan = step3_analyze_script.main()

    # ── Step 4: TTS ──────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 4 — Generating Hindi TTS audio")
    logger.info("=" * 60)
    step4_tts.main(plan)

    # Re-save plan with tts_path annotations
    Path(EDIT_PLAN).write_text(
        json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    # ── Step 5: Edit ─────────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 5 — Editing video")
    logger.info("=" * 60)
    step5_edit.main(plan)

    # ── Step 6: Upload ───────────────────────────────────────────────
    logger.info("=" * 60)
    logger.info("STEP 6 — Uploading to YouTube")
    logger.info("=" * 60)
    video_id = step6_upload.main()

    logger.info("=" * 60)
    logger.info("✅ PIPELINE COMPLETE")
    logger.info("YouTube URL: https://youtu.be/%s", video_id)
    logger.info("=" * 60)


if __name__ == "__main__":
    try:
        run()
    except Exception as exc:
        logger.critical("Pipeline failed: %s", exc, exc_info=True)
        sys.exit(1)