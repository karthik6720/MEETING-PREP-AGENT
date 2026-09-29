"""Central configuration, loaded from environment variables (.env)."""
import os
from dotenv import load_dotenv

load_dotenv()

HINDSIGHT_API_KEY = os.getenv("HINDSIGHT_API_KEY", "")
HINDSIGHT_BASE_URL = os.getenv("HINDSIGHT_BASE_URL", "https://api.hindsight.vectorize.io")

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")
# Speech-to-text for uploaded meeting recordings. whisper-large-v3-turbo is the
# faster default; set GROQ_WHISPER_MODEL=whisper-large-v3 for maximum accuracy.
GROQ_WHISPER_MODEL = os.getenv("GROQ_WHISPER_MODEL", "whisper-large-v3-turbo")
# Language spoken in the recordings (ISO code). Setting it improves accuracy;
# set TRANSCRIPTION_LANGUAGE= (empty) to let Whisper auto-detect.
TRANSCRIPTION_LANGUAGE = os.getenv("TRANSCRIPTION_LANGUAGE", "en")
# Default is disabled (0) to allow long demo recordings to finish. Set a value
# in seconds to enforce a hard timeout during transcription.
TRANSCRIPTION_TIMEOUT_SECONDS = int(os.getenv("TRANSCRIPTION_TIMEOUT_SECONDS", "0") or "0")

# Every contact gets their own isolated Hindsight memory bank, named
# "contact::<slug>". This keeps recall scoped to one relationship at a
# time, which is what a real prep briefing needs.
CONTACT_BANK_PREFIX = "contact"

# One extra bank that never holds contact facts, only the user's own
# feedback on past briefings ("too long", "loved the risk section", etc).
# This is what lets the agent's *briefing style* improve over time, on
# top of it already knowing more about each contact.
STYLE_BANK_ID = "user-style-preferences"


def contact_bank_id(contact_slug: str) -> str:
    return f"{CONTACT_BANK_PREFIX}::{contact_slug}"


def require_config():
    missing = []
    if not HINDSIGHT_API_KEY:
        missing.append("HINDSIGHT_API_KEY")
    if not GROQ_API_KEY:
        missing.append("GROQ_API_KEY")
    if missing:
        raise SystemExit(
            f"Missing required environment variable(s): {', '.join(missing)}\n"
            f"Copy .env.example to .env and fill them in."
        )