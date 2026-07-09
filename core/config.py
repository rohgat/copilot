from __future__ import annotations
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent.parent / ".env")

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"


class Config:
    # Identity — must set in .env
    USER_NAME: str = os.getenv("USER_NAME", "Rohit")
    USER_PHONE: str = os.getenv("USER_PHONE", "")  # E.164 format: +919xxxxxxxxx

    # API keys
    NOTION_TOKEN: str = os.getenv("NOTION_TOKEN", "")

    # Ollama (local LLM — no API key needed)
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")

    # Paths
    CHROMA_PATH: str = str(DATA_DIR / "chroma")
    TRANSCRIPTS_DIR: str = str(DATA_DIR / "transcripts")
    FILES_DIR: str = str(DATA_DIR / "files")
    PREFS_PATH: str = str(DATA_DIR / "preferences" / "profile.json")
    GOOGLE_CREDS_PATH: str = str(BASE_DIR / "google_credentials.json")
    GOOGLE_TOKEN_PATH: str = str(DATA_DIR / "google_token.json")

    # Audio
    AUDIO_DEVICE_NAME: str = os.getenv("AUDIO_DEVICE_NAME", "BlackHole 2ch")
    AUDIO_SAMPLE_RATE: int = 16000
    AUDIO_CHUNK_SECONDS: int = 5

    # Whisper
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "large-v3")
    WHISPER_COMPUTE_TYPE: str = "int8"

    # Detection
    DETECTION_CONFIDENCE_THRESHOLD: float = 0.65
    TRANSCRIPT_BUFFER_LINES: int = 15

    # Silence / auto-end
    SILENCE_THRESHOLD_DB: float = float(os.getenv("SILENCE_THRESHOLD_DB", "-45"))
    SILENCE_DURATION_SECONDS: int = int(os.getenv("SILENCE_DURATION_SECONDS", "60"))

    # Meeting
    PRE_MEETING_BRIEF_MINUTES: int = 5

    # Notion
    NOTION_DATABASE_ID: str = os.getenv("NOTION_DATABASE_ID", "")

    # WhatsApp bridge (Node.js service)
    WHATSAPP_BRIDGE_PORT: int = int(os.getenv("WHATSAPP_BRIDGE_PORT", "3001"))

    @property
    def whatsapp_bridge_url(self) -> str:
        return f"http://localhost:{self.WHATSAPP_BRIDGE_PORT}"

    # Dashboard
    DASHBOARD_PORT: int = int(os.getenv("DASHBOARD_PORT", "8000"))


config = Config()
