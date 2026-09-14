# Auto YouTube Viral Shorts Pipeline

Fully automated daily pipeline that:
1. Discovers the most viral YouTube Short from the last 24 hours
2. Downloads it via yt-dlp
3. Uses Gemini 2.5 Flash to generate a Hindi commentary/comedy script + edit plan
4. Generates Hindi TTS via edge-tts
5. Edits the video with FFmpeg (cuts, zoom, text overlays, audio ducking)
6. Uploads to YouTube automatically

Runs on GitHub Actions — **completely free**.

## Required Secrets

Add these in GitHub → Settings → Secrets and variables → Actions:

| Secret | Description |
|---|---|
| `YOUTUBE_API_KEY` | Google Cloud YouTube Data API v3 key |
| `GEMINI_API_KEY` | Google AI Studio Gemini key |
| `YOUTUBE_CLIENT_ID` | OAuth 2.0 Client ID |
| `YOUTUBE_CLIENT_SECRET` | OAuth 2.0 Client Secret |
| `YOUTUBE_REFRESH_TOKEN` | OAuth 2.0 Refresh Token |

## Schedule

Runs daily at **12:00 PM IST** (Asia/Kolkata). You can also trigger manually
from the Actions tab using `workflow_dispatch`.

## Local Testing

```bash
pip install -r requirements.txt
sudo apt install ffmpeg fonts-noto-devanagari

export YOUTUBE_API_KEY=...
export GEMINI_API_KEY=...
export YOUTUBE_CLIENT_ID=...
export YOUTUBE_CLIENT_SECRET=...
export YOUTUBE_REFRESH_TOKEN=...

python main.py