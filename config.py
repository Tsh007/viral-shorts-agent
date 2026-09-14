"""
config.py — Central configuration for auto-youtube-viral pipeline.
All secrets read from environment variables.
"""

import os
import logging

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s – %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger("auto-youtube-viral")


# ---------------------------------------------------------------------------
# Env helpers
# ---------------------------------------------------------------------------
def _require(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise EnvironmentError(
            f"Required environment variable '{name}' is not set. "
            "Add it to your .env file (local) or GitHub Actions secrets."
        )
    return value


def _optional(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


# ---------------------------------------------------------------------------
# Secrets
# ---------------------------------------------------------------------------
YOUTUBE_API_KEY: str = _optional("YOUTUBE_API_KEY")
GEMINI_API_KEY: str = _require("GEMINI_API_KEY")

YOUTUBE_CLIENT_ID: str = _optional("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET: str = _optional("YOUTUBE_CLIENT_SECRET")
YOUTUBE_REFRESH_TOKEN: str = _optional("YOUTUBE_REFRESH_TOKEN")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
OUTPUT_DIR: str = _optional("OUTPUT_DIR", "output")
SOURCE_VIDEO: str = os.path.join(OUTPUT_DIR, "source.mp4")
EDIT_PLAN: str = os.path.join(OUTPUT_DIR, "edit_plan.json")
FINAL_VIDEO: str = os.path.join(OUTPUT_DIR, "final.mp4")
AUDIO_DIR: str = os.path.join(OUTPUT_DIR, "audio")
SEGMENTS_DIR: str = os.path.join(OUTPUT_DIR, "segments")

# ---------------------------------------------------------------------------
# YouTube discovery settings
# ---------------------------------------------------------------------------
MIN_DURATION_S: int = 30          # 30 seconds minimum
MAX_DURATION_S: int = 240         # 4 minutes maximum
MIN_VIEWS: int = 50_000           # minimum view count to consider
SEARCH_WINDOWS_HOURS: list = [6, 12, 24]   # freshness windows
MAX_SEARCH_RESULTS: int = 50      # per API call (max 50)

# ---------------------------------------------------------------------------
# Gemini
# ---------------------------------------------------------------------------
GEMINI_MODEL: str = _optional("GEMINI_MODEL", "gemini-2.5-flash")

# ---------------------------------------------------------------------------
# TTS
# ---------------------------------------------------------------------------
TTS_VOICE: str = _optional("TTS_VOICE", "hi-IN-MadhurNeural")

# ---------------------------------------------------------------------------
# Video output
# ---------------------------------------------------------------------------
VIDEO_WIDTH: int = 1080
VIDEO_HEIGHT: int = 1920
VIDEO_FPS: int = 30

# ---------------------------------------------------------------------------
# Audio ducking
# ---------------------------------------------------------------------------
DUCK_DB: float = -15.0            # dB reduction on original audio when TTS plays
DUCK_THRESHOLD: float = 0.05
DUCK_RATIO: float = 8.0


# ---------------------------------------------------------------------------
# Ensure dirs
# ---------------------------------------------------------------------------
def ensure_dirs() -> None:
    for d in (OUTPUT_DIR, AUDIO_DIR, SEGMENTS_DIR):
        os.makedirs(d, exist_ok=True)
    logger.debug("Output directories ensured.")