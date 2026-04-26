from __future__ import annotations

import os
from pathlib import Path


ELEVENLABS_API_BASE = os.getenv("ELEVENLABS_API_BASE", "https://api.elevenlabs.io").rstrip("/")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "").strip()
ELEVENLABS_API_KEY_APP_VAR = "elevenlabs_api_key"
ELEVENLABS_CREDENTIAL_FILE = Path(os.getenv("ELEVENLABS_CREDENTIAL_FILE", "/tmp/elevenlabs-credentials.json")).expanduser()

DEFAULT_VOICE_ID = os.getenv("ELEVENLABS_DEFAULT_VOICE_ID", "21m00Tcm4TlvDq8ikWAM")
DEFAULT_MODEL_ID = os.getenv("ELEVENLABS_DEFAULT_MODEL_ID", "eleven_multilingual_v2")
DEFAULT_OUTPUT_FORMAT = os.getenv("ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")

OUTPUT_DIR = Path(os.getenv("ELEVENLABS_OUTPUT_DIR", "/tmp/elevenlabs-output")).expanduser()

TRUFFILE_AUDIO_BRIDGE_BASE_URL = os.getenv("TRUFFILE_AUDIO_BRIDGE_BASE_URL", "").strip().rstrip("/")
TRUFFILE_AUDIO_BRIDGE_TOKEN = os.getenv("TRUFFILE_AUDIO_BRIDGE_TOKEN", "").strip()
