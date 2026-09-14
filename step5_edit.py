"""
step5_edit.py — Execute the edit plan using MovieLite + FFmpeg.

For each segment:
  1. Cut the source video at the planned timestamps.
  2. Apply zoom (if requested).
  3. Overlay Hindi text (if requested).
  4. Attach TTS audio.
Then concatenate all segments and duck the original audio.
"""

from __future__ import annotations

import json
import math
import re
import subprocess
import sys
from pathlib import Path

from config import (
    EDIT_PLAN,
    FINAL_VIDEO,
    SEGMENTS_DIR,
    SOURCE_VIDEO,
    VIDEO_FPS,
    VIDEO_HEIGHT,
    VIDEO_WIDTH,
    DUCK_DB,
    DUCK_THRESHOLD,
    DUCK_RATIO,
    ensure_dirs,
    logger,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _run(cmd: list[str], label: str = "") -> None:
    logger.debug("CMD [%s]: %s", label, " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.error("STDERR: %s", result.stderr[-2000:])
        raise RuntimeError(f"Command failed (exit {result.returncode}) — {label}")


def _ts_to_seconds(ts: str) -> float:
    """Convert 'MM:SS' or 'HH:MM:SS' to seconds."""
    parts = [float(p) for p in ts.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    elif len(parts) == 3:
        return parts[0] * 3600 + parts[1] * 60 + parts[2]
    return float(ts)


def _probe_duration(path: Path) -> float:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed: {result.stderr}")
    return float(result.stdout.strip())


# ---------------------------------------------------------------------------
# Segment builder (FFmpeg-based — more reliable than MovieLite for Hindi fonts)
# ---------------------------------------------------------------------------
def _escape_drawtext(text: str) -> str:
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    text = text.replace("[", "\\[")
    text = text.replace("]", "\\]")
    return text


def build_segment(
    source: str,
    start_s: float,
    end_s: float,
    tts_path: str,
    visual_op: str,
    zoom_scale: float,
    text_overlay: str,
    dest: Path,
    hindi_font: str = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf",
) -> None:
    """
    Build one segment:
      - Cut source[start_s:end_s]
      - Scale/pad to 1080x1920
      - Apply zoompan (Ken Burns)
      - Overlay Hindi text (if any)
      - Mix TTS audio over ducked original audio
    """
    seg_dur = end_s - start_s
    if seg_dur <= 0:
        raise ValueError(f"Invalid segment duration: {seg_dur}")

    w, h = VIDEO_WIDTH, VIDEO_HEIGHT
    total_frames = math.ceil(seg_dur * VIDEO_FPS)

    # ── Zoom expression ──────────────────────────────────────────────
    if visual_op == "zoom_in":
        zoom_expr = f"min(1.0+0.0005*on,{zoom_scale})"
    elif visual_op == "zoom_out":
        zoom_expr = f"max({zoom_scale}-0.0005*on,1.0)"
    else:
        zoom_expr = "1.0"

    # ── Video filter chain ───────────────────────────────────────────
    # 1. Scale to fit inside 1080x1920, pad to exactly 1080x1920
    # 2. zoompan
    vf_parts = [
        f"scale={w}:{h}:force_original_aspect_ratio=decrease",
        f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black",
        f"zoompan=z='{zoom_expr}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":d={total_frames}:s={w}x{h}:fps={VIDEO_FPS}",
        "setsar=1",
    ]

    # ── Text overlay ─────────────────────────────────────────────────
    if text_overlay and text_overlay.strip():
        safe = _escape_drawtext(text_overlay.strip())
        font_size = max(40, int(h * 0.045))
        vf_parts.append(
            f"drawtext=text='{safe}':"
            f"fontfile={hindi_font}:"
            f"fontcolor=white:fontsize={font_size}:"
            f"x=(w-text_w)/2:y=h-{font_size + 60}:"
            f"box=1:boxcolor=black@0.55:boxborderw=14:"
            f"line_spacing=6"
        )

    vf = ",".join(vf_parts)

    # ── Audio filter (duck original under TTS) ───────────────────────
    if tts_path and Path(tts_path).exists():
        af = (
            f"[0:a]volume={DUCK_DB}dB[ducked];"
            f"[1:a]volume=0dB[tts];"
            f"[ducked][tts]amix=inputs=2:duration=first:dropout_transition=2[aout]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_s), "-to", str(end_s),
            "-i", source,
            "-i", tts_path,
            "-filter_complex", f"[0:v]{vf}[vout];{af}",
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-r", str(VIDEO_FPS),
            "-t", str(seg_dur),
            str(dest),
        ]
    else:
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(start_s), "-to", str(end_s),
            "-i", source,
            "-filter_complex", f"[0:v]{vf}[vout]",
            "-map", "[vout]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            "-r", str(VIDEO_FPS),
            "-t", str(seg_dur),
            str(dest),
        ]

    _run(cmd, label=f"segment {dest.name}")
    logger.info("  ✓ Segment: %s (%.1fs)", dest.name, seg_dur)


# ---------------------------------------------------------------------------
# Concatenation
# ---------------------------------------------------------------------------
def concatenate(segment_paths: list[Path], output: str = FINAL_VIDEO) -> Path:
    concat_file = Path(output).parent / "concat_list.txt"
    with concat_file.open("w", encoding="utf-8") as fh:
        for p in segment_paths:
            fh.write(f"file '{p.resolve().as_posix()}'\n")

    out = Path(output)
    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac", "-b:a", "128k",
        "-movflags", "+faststart",
        str(out),
    ]
    _run(cmd, label="concat")
    logger.info("✓ Final video: %s (%.1f MB)", out, out.stat().st_size / 1e6)
    return out


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def edit_video(plan: dict, source: str = SOURCE_VIDEO) -> Path:
    ensure_dirs()
    segments = plan["segments"]
    seg_paths: list[Path] = []

    # Check Hindi font availability
    hindi_font = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    if not Path(hindi_font).exists():
        logger.warning(
            "Hindi font not found at %s. Text overlays may render incorrectly.",
            hindi_font,
        )

    for idx, seg in enumerate(segments):
        start_s = _ts_to_seconds(seg["source_start"])
        end_s = _ts_to_seconds(seg["source_end"])
        dest = Path(SEGMENTS_DIR) / f"seg_{idx:02d}.mp4"

        build_segment(
            source=source,
            start_s=start_s,
            end_s=end_s,
            tts_path=seg.get("tts_path", ""),
            visual_op=seg.get("visual_operation", "none"),
            zoom_scale=float(seg.get("zoom_scale", 1.3)),
            text_overlay=seg.get("text_overlay", ""),
            dest=dest,
            hindi_font=hindi_font,
        )
        seg_paths.append(dest)

    final = concatenate(seg_paths)
    return final


def main(plan: dict) -> Path:
    return edit_video(plan)


if __name__ == "__main__":
    from config import EDIT_PLAN

    plan = json.loads(Path(EDIT_PLAN).read_text(encoding="utf-8"))
    try:
        main(plan)
    except Exception as exc:
        logger.critical("Step 5 failed: %s", exc, exc_info=True)
        sys.exit(1)