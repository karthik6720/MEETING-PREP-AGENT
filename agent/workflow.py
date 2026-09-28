"""
High-level workflows shared by the CLI, the web app, and the demo seeder.
Thin glue over llm.py (Groq) and memory.py (Hindsight) -- no logic of its
own beyond wiring the two together the same way every caller needs, so the
CLI and the web UI can never drift out of sync on how a briefing is built.
"""
import os
import re
from datetime import datetime
from typing import Any

from . import llm, memory, mini_markdown

# Recordings: Groq's speech-to-text supports common audio/video formats.
# We allow bigger uploads than the legacy 25 MB ceiling because large files
# are split into chunks internally before transcription.
ALLOWED_MEDIA = {".mp4", ".webm", ".mp3", ".m4a", ".wav", ".ogg", ".flac", ".mpeg", ".mpga"}
MAX_MEDIA_BYTES = 250 * 1024 * 1024
_SENTIMENT_ONLY_MEMORY = re.compile(
    r"^(?:overall )?sentiment of the .+? meeting with .+? was: "
    r"(?:very positive|positive|neutral|cautious|negative)\.?$|"
    r"^the meeting with .+? had a (?:very positive|positive|neutral|cautious|negative) "
    r"sentiment\.?(?:\s*\|.*)?$|"
    r"^the meeting with .+? on \d{4}-\d{2}-\d{2} had a "
    r"(?:very positive|positive|neutral|cautious|negative) sentiment\.?$",
    re.IGNORECASE,
)


class MeetingInputError(Exception):
    """Something the user can fix (unsupported file, nothing to save, a failed
    transcription). The message is written to be shown to them as-is."""


def log_meeting_from_notes(slug: str, contact_name: str, meeting_date: datetime,
                            raw_notes: str,
                            known_facts: dict[str, Any] | None = None) -> dict[str, Any]:
    facts = known_facts or llm.extract_meeting_facts(raw_notes, contact_name)
    count = memory.log_meeting(slug, contact_name, meeting_date, raw_notes, facts)
    return {"facts": facts, "count": count}


def _upload_size(video_file) -> int:
    stream = video_file.stream
    stream.seek(0, os.SEEK_END)
    size = stream.tell()
    stream.seek(0)
    return size


def _transcribe_upload(video_file) -> str:
    extension = os.path.splitext(video_file.filename or "")[1].lower()
    if extension not in ALLOWED_MEDIA:
        raise MeetingInputError(
            f"{extension or 'That'} files aren't supported. Use mp4, webm, mp3, m4a or wav."
        )
    if _upload_size(video_file) > MAX_MEDIA_BYTES:
        raise MeetingInputError(
            f"That recording is over {MAX_MEDIA_BYTES // (1024 * 1024)} MB. "
            "Trim it or export audio only."
        )
    try:
        transcript = (llm.transcribe_video(video_file) or "").strip()
    except Exception as exc:
        raise MeetingInputError(f"Transcription failed: {exc}") from exc
    if not transcript:
        raise MeetingInputError("No speech was found in that recording.")
    return transcript


def log_meeting(slug: str, contact_name: str, meeting_date: datetime,
                notes: str | None = None, video_file=None) -> dict[str, Any]:
    """Log a meeting from a recording, typed notes, or both. A recording is
    transcribed first, then everything goes through the same fact extraction
    and Hindsight retain() path. Raises MeetingInputError for problems the
    user can fix."""
    transcript = _transcribe_upload(video_file) if video_file is not None else ""

    parts = []
    if transcript:
        parts.append(f"Transcript of the meeting recording:\n{transcript}")
    if notes and notes.strip():
        parts.append(f"Notes typed by the user:\n{notes.strip()}")
    if not parts:
        raise MeetingInputError("Add a recording or some notes first.")

    result = log_meeting_from_notes(slug, contact_name, meeting_date, "\n\n".join(parts))
    result["transcript"] = transcript
    return result


def generate_prep(slug: str, contact_name: str, goal: str | None = None) -> dict[str, Any]:
    recalled_sources = memory.recall_sources(
        slug,
        query=f"topics discussed, promises made by both sides, and concerns raised with {contact_name}",
        limit=12,
    )
    sources = [
        source for source in recalled_sources
        if not _SENTIMENT_ONLY_MEMORY.fullmatch(source["text"].strip())
    ]
    for index, source in enumerate(sources, start=1):
        source["n"] = index
    followups = [
        item for item in memory.open_followups(slug, contact_name)
        if not _SENTIMENT_ONLY_MEMORY.fullmatch(item.strip())
    ]
    context = memory.relationship_context(slug, contact_name)
    style = memory.style_notes()
    briefing = llm.compose_briefing(contact_name, context, style, goal, sources)

    numbers = mini_markdown.cited_numbers(briefing)
    return {
        "briefing": briefing,
        "raw_memories": [s["text"] for s in sources],
        "followups": followups,
        "sources": sources,
        "cited": [s for s in sources if s["n"] in numbers],
    }