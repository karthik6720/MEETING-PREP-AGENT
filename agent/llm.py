"""
Groq-backed reasoning layer.

Three jobs:
1. extract_meeting_facts()  -- turn messy human meeting notes into clean,
   atomic facts worth retaining in Hindsight (one bank per contact).
2. compose_briefing()       -- turn Hindsight's raw recall/reflect output
   into a short, sharp prep briefing in the user's preferred style.
3. transcribe_video()       -- turn an uploaded meeting recording into text
   (Groq Whisper) so it can go through the same fact extraction as notes.

Groq's tool-calling occasionally returns malformed or missing tool_calls
(especially on smaller open models under load), so extract_meeting_facts
always has a plain-JSON fallback path instead of crashing the CLI.
"""
import json
import math
import os
import subprocess
import tempfile
import time
from typing import Any

try:
    import ffmpeg
except ModuleNotFoundError:  # Optional; direct Groq upload is the fast path.
    ffmpeg = None
from groq import APIConnectionError, Groq

from . import config

_client: Groq | None = None
_TRANSCRIPTION_DEADLINE_SECONDS = 160
_TRANSCRIPTION_REQUEST_TIMEOUT_SECONDS = 60
_TRANSCRIPTION_TIMEOUT_MESSAGE = (
    "Transcription timed out after 2 minutes 40 seconds. "
    "Try a shorter recording or upload audio only."
)
_AUDIO_ONLY_EXTENSIONS = {".mp3", ".m4a", ".wav", ".ogg", ".flac", ".mpeg", ".mpga"}


def _get_client() -> Groq:
    global _client
    if _client is None:
        _client = Groq(api_key=config.GROQ_API_KEY)
    return _client


EXTRACT_TOOL = {
    "type": "function",
    "function": {
        "name": "record_meeting_facts",
        "description": "Structured facts extracted from one meeting's raw notes.",
        "parameters": {
            "type": "object",
            "properties": {
                "topics_discussed": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Short bullet-style topics that came up.",
                },
                "promises_by_user": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Things the user (our side) committed to doing.",
                },
                "promises_by_contact": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Things the contact/other side committed to doing.",
                },
                "concerns_or_objections": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Concerns, objections, or blockers the contact raised.",
                },
                "sentiment": {
                    "type": "string",
                    "enum": ["very positive", "positive", "neutral", "cautious", "negative"],
                    "description": "Overall tone of the meeting.",
                },
            },
            "required": ["topics_discussed", "promises_by_user", "promises_by_contact",
                         "concerns_or_objections", "sentiment"],
        },
    },
}

_EXTRACT_SYSTEM_PROMPT = (
    "You extract structured facts from raw meeting notes for a CRM-style memory system. "
    "Be concise and factual. Never invent details that aren't in the notes. "
    "Each array item should be a single, self-contained sentence that would still make "
    "sense read on its own, months later, with no other context."
)


def extract_meeting_facts(raw_notes: str, contact_name: str) -> dict[str, Any]:
    client = _get_client()
    messages = [
        {"role": "system", "content": _EXTRACT_SYSTEM_PROMPT},
        {"role": "user", "content": f"Contact: {contact_name}\n\nRaw meeting notes:\n{raw_notes}"},
    ]

    try:
        resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=messages,
            tools=[EXTRACT_TOOL],
            tool_choice={"type": "function", "function": {"name": "record_meeting_facts"}},
            temperature=0.2,
        )
        tool_calls = resp.choices[0].message.tool_calls
        if not tool_calls:
            raise ValueError("model returned no tool_calls")
        args = json.loads(tool_calls[0].function.arguments)
        return _normalize_facts(args)
    except Exception:
        # Fallback: ask for plain JSON in the response body instead of a
        # tool call. Handles models/providers that flake on function calling.
        fallback_messages = messages + [
            {
                "role": "user",
                "content": (
                    "Tool calling isn't available right now. Reply with ONLY a raw JSON "
                    "object with exactly these keys: topics_discussed, promises_by_user, "
                    "promises_by_contact, concerns_or_objections (all string arrays), and "
                    "sentiment (one of: very positive, positive, neutral, cautious, negative). "
                    "No markdown fences, no commentary."
                ),
            }
        ]
        resp = client.chat.completions.create(
            model=config.GROQ_MODEL,
            messages=fallback_messages,
            temperature=0.2,
        )
        text = resp.choices[0].message.content.strip()
        text = text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        return _normalize_facts(json.loads(text))


def _normalize_facts(args: dict[str, Any]) -> dict[str, Any]:
    defaults = {
        "topics_discussed": [],
        "promises_by_user": [],
        "promises_by_contact": [],
        "concerns_or_objections": [],
        "sentiment": "neutral",
    }
    defaults.update({k: v for k, v in args.items() if k in defaults and v})
    return defaults


_BRIEFING_SYSTEM_PROMPT = (
    "You are a meeting-prep assistant. You are given (a) synthesized memory of everything "
    "known about a contact and the relationship history, and (b) the user's stated style "
    "preferences for briefings. Write a short prep briefing for the user's upcoming meeting. "
    "Ground every claim in the memory context given -- never invent history. "
    "Prioritize concrete topics, commitments, dates, blockers, and next actions from meeting notes. "
    "Do not treat sentiment summaries as follow-ups or substitute sentiment status for meeting facts. "
    "The style preferences are a hard constraint, not a suggestion: if they ask for a length "
    "limit, obey it exactly. If they ask you to skip or shorten a section, drop or shrink it "
    "entirely rather than keeping a smaller version of it -- 'skip the relationship history' "
    "means that section does not appear at all, even as one line. "
    "You may also be given numbered source memories. After a claim that is directly "
    "supported by one of them, add its number in square brackets, like [3] or [2][5]. "
    "Only use numbers that appear in the list, never invent one, and add no number when "
    "no source memory supports the claim."
)


def compose_briefing(contact_name: str, memory_context: str, style_notes: str,
                      meeting_goal: str | None,
                      sources: list[dict] | None = None) -> str:
    client = _get_client()
    goal_line = f"\nUpcoming meeting purpose (from user): {meeting_goal}" if meeting_goal else ""
    has_style = bool(style_notes and style_notes.strip())
    default_sections = (
        "Write the briefing now with these sections: Relationship snapshot, "
        "Open commitments & follow-ups, Talking points, Watch-outs, Suggested opener."
    )
    section_instruction = (
        "Use whatever section structure best satisfies the style preferences above -- they "
        "take priority over any default structure. Only fall back to the default sections "
        "(Relationship snapshot, Open commitments & follow-ups, Talking points, Watch-outs, "
        "Suggested opener) for anything the style preferences don't address."
        if has_style else default_sections
    )
    if sources:
        numbered = "\n".join(
            f"[{src['n']}] ({src['date'] or 'undated'}) {src['text']}" for src in sources
        )
        sources_block = f"--- Numbered source memories (cite by number) ---\n{numbered}\n\n"
    else:
        sources_block = ""
    user_content = (
        f"Contact: {contact_name}{goal_line}\n\n"
        f"--- Memory context from Hindsight (relationship history) ---\n{memory_context}\n\n"
        f"{sources_block}"
        f"--- User's briefing style preferences (may be empty if none learned yet) ---\n"
        f"{style_notes or '(none recorded yet -- default to tight, scannable bullets)'}\n\n"
        f"{section_instruction}"
    )
    resp = client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=[
            {"role": "system", "content": _BRIEFING_SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.4,
    )
    return resp.choices[0].message.content.strip()


def _remaining_transcription_time(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(_TRANSCRIPTION_TIMEOUT_MESSAGE)
    return remaining


def _run_ffmpeg(stream, deadline: float) -> None:
    process = stream.run_async(pipe_stdout=True, pipe_stderr=True)
    try:
        _, stderr = process.communicate(timeout=_remaining_transcription_time(deadline))
    except (subprocess.TimeoutExpired, TimeoutError) as exc:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        process.communicate()
        raise TimeoutError(_TRANSCRIPTION_TIMEOUT_MESSAGE) from exc
    if process.returncode:
        message = stderr.decode(errors="replace").strip()
        raise RuntimeError(message or "Audio conversion failed.")


def transcribe_media(filename: str, data: bytes, deadline: float | None = None) -> str:
    """Speech-to-text for a recording via Groq's Whisper endpoint. Groq accepts
    mp3, mp4, mpeg, mpga, m4a, wav and webm up to 25 MB; if a file has several
    audio tracks, only the first is transcribed."""
    options = {}
    if config.TRANSCRIPTION_LANGUAGE:
        options["language"] = config.TRANSCRIPTION_LANGUAGE
    for attempt in range(3):
        try:
            timeout = (
                min(_TRANSCRIPTION_REQUEST_TIMEOUT_SECONDS,
                    _remaining_transcription_time(deadline))
                if deadline is not None else 300
            )
            resp = _get_client().audio.transcriptions.create(
                file=(filename, data),
                model=config.GROQ_WHISPER_MODEL,
                response_format="json",
                timeout=timeout,
                **options,
            )
            if deadline is not None:
                _remaining_transcription_time(deadline)
            return (resp.text or "").strip()
        except APIConnectionError:
            if attempt == 2 or deadline is None:
                raise
            time.sleep(min(2, _remaining_transcription_time(deadline)))


def _transcribe_file(file_path: str, deadline: float | None = None) -> str:
    with open(file_path, "rb") as audio_file:
        data = audio_file.read()
    if deadline is not None:
        _remaining_transcription_time(deadline)
    return transcribe_media(os.path.basename(file_path), data, deadline)


def transcribe_video(video_file) -> str:
    """Send the original upload to Groq first; only fall back to ffmpeg conversion if the API rejects it."""
    deadline = time.monotonic() + _TRANSCRIPTION_DEADLINE_SECONDS
    suffix = os.path.splitext(video_file.filename or "")[1] or ".mp4"
    video_path = None
    audio_path = None

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            video_file.save(tmp)
            video_path = tmp.name

        direct_audio_upload = (
            suffix.lower() in _AUDIO_ONLY_EXTENSIONS
            and os.path.getsize(video_path) <= 24 * 1024 * 1024
        )
        raw_video_fallback = ffmpeg is None and os.path.getsize(video_path) <= 24 * 1024 * 1024
        if direct_audio_upload or raw_video_fallback:
            try:
                return _transcribe_file(video_path, deadline)
            except Exception:
                _remaining_transcription_time(deadline)
                if ffmpeg is None:
                    raise
        elif ffmpeg is None:
            raise RuntimeError("Install ffmpeg to transcribe video files over 24 MB.")

        audio_path = f"{video_path}.mp3"
        _run_ffmpeg(
            ffmpeg
            .input(video_path)
            .output(
                audio_path,
                acodec="libmp3lame",
                audio_bitrate="48k",
                ac=1,
                ar="16000",
                vn=None,
            )
            .overwrite_output(),
            deadline,
        )

        _remaining_transcription_time(deadline)
        if os.path.getsize(audio_path) <= 24 * 1024 * 1024:
            return _transcribe_file(audio_path, deadline)

        probe = ffmpeg.probe(audio_path)
        _remaining_transcription_time(deadline)
        duration = float(probe["format"].get("duration", 0) or 0)
        if duration <= 0:
            raise RuntimeError("Could not determine the compressed audio duration.")

        chunk_length = 600
        total_chunks = math.ceil(duration / chunk_length)
        parts: list[str] = []
        with tempfile.TemporaryDirectory() as tmpdir:
            for idx in range(total_chunks):
                _remaining_transcription_time(deadline)
                chunk_path = os.path.join(tmpdir, f"chunk_{idx}.mp3")
                _run_ffmpeg(
                    ffmpeg
                    .input(audio_path, ss=idx * chunk_length, t=chunk_length)
                    .output(chunk_path, acodec="copy")
                    .overwrite_output(),
                    deadline,
                )
                part = _transcribe_file(chunk_path, deadline)
                if part:
                    parts.append(part)
        return "\n\n".join(parts).strip()
    finally:
        for path in (video_path, audio_path):
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                except OSError:
                    pass