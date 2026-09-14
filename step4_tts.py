"""
step4_tts.py — Generate Hindi TTS audio for each segment using edge-tts.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from config import AUDIO_DIR, TTS_VOICE, logger


async def _synthesize(text: str, dest: Path, voice: str) -> None:
    import edge_tts

    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(str(dest))


def generate_tts(segments: list[dict], audio_dir: str = AUDIO_DIR) -> list[Path]:
    """
    Generate one MP3 per segment. Returns ordered list of paths.
    Annotates each segment with 'tts_path'.
    """
    out = Path(audio_dir)
    out.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []

    for idx, seg in enumerate(segments):
        text = seg["hindi_text"].strip()
        if not text:
            logger.warning("Segment %d has empty hindi_text — skipping TTS.", idx)
            seg["tts_path"] = ""
            continue

        dest = out / f"tts_{idx:02d}.mp3"
        logger.info("TTS %d: '%s…' → %s", idx, text[:40], dest)
        asyncio.run(_synthesize(text, dest, TTS_VOICE))
        seg["tts_path"] = str(dest)
        paths.append(dest)

    logger.info("Generated %d TTS files.", len(paths))
    return paths


def main(plan: dict) -> list[Path]:
    return generate_tts(plan["segments"])


if __name__ == "__main__":
    import json
    from config import EDIT_PLAN

    plan = json.loads(Path(EDIT_PLAN).read_text(encoding="utf-8"))
    try:
        main(plan)
    except Exception as exc:
        logger.critical("Step 4 failed: %s", exc, exc_info=True)
        sys.exit(1)