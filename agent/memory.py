"""
All Hindsight interaction lives here. This is deliberately the smallest,
most central file in the project -- everything else (CLI, LLM) is plumbing
around it, because for this hackathon *memory is the product*.

Design:
- One Hindsight memory bank per contact ("contact::<slug>"). Isolated
  recall per relationship, exactly like a real rep wouldn't want deal
  memory bleeding across accounts.
- One extra bank ("user-style-preferences") that holds only feedback on
  past briefings, so the agent's *output style* improves independently
  of what it knows about any single contact.
- retain() stores atomic, dated, tagged facts (not whole transcripts) --
  see Hindsight best practices: small self-contained statements recall
  and reflect far better than giant blobs.
- reflect() is where the "before vs. after memory" magic is visible: with
  zero retained facts it returns a generic non-answer; after a few
  logged meetings it returns a grounded, specific relationship summary.
"""
import threading
from datetime import datetime
from typing import Any

from hindsight_client import Hindsight

from . import config

# The Hindsight sync client runs its async HTTP session on the calling
# thread's event loop. Flask serves each request on a different thread, so a
# single shared client breaks ("Timeout context manager should be used inside
# a task"). Keeping one client per thread avoids that; the web app closes it
# at the end of every request (see webapp.py), the CLI closes it on exit.
_local = threading.local()


def get_client() -> Hindsight:
    client = getattr(_local, "client", None)
    if client is None:
        client = Hindsight(base_url=config.HINDSIGHT_BASE_URL, api_key=config.HINDSIGHT_API_KEY)
        _local.client = client
    return client


def close_client() -> None:
    """Best-effort cleanup of this thread's HTTP session, so Python doesn't
    print 'Unclosed client session' warnings."""
    client = getattr(_local, "client", None)
    if client is None:
        return
    try:
        client.close()
    except Exception:
        pass
    _local.client = None


def ensure_bank(bank_id: str, name: str) -> None:
    client = get_client()
    try:
        client.banks.create(bank_id=bank_id, name=name)
    except Exception:
        pass  # already exists -- fine


def ensure_contact_bank(slug: str, contact_name: str) -> str:
    bank_id = config.contact_bank_id(slug)
    ensure_bank(bank_id, name=f"Contact: {contact_name}")
    return bank_id


def delete_contact_bank(slug: str) -> None:
    bank_id = config.contact_bank_id(slug)
    try:
        get_client().delete_bank(bank_id)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Writing memory (retain)
# ---------------------------------------------------------------------------

_KIND_LABELS = {
    "topics_discussed": "discussed",
    "promises_by_user": "promise (us -> them)",
    "promises_by_contact": "promise (them -> us)",
    "concerns_or_objections": "concern/objection",
}


def log_meeting(slug: str, contact_name: str, meeting_date: datetime,
                 raw_notes: str, facts: dict[str, Any]) -> int:
    """Retain every extracted fact as its own atomic, tagged memory.
    Returns the number of facts retained."""
    bank_id = ensure_contact_bank(slug, contact_name)
    client = get_client()
    document_id = f"meeting-{slug}-{meeting_date.date().isoformat()}"
    count = 0

    for kind, label in _KIND_LABELS.items():
        for item in facts.get(kind, []):
            client.retain(
                bank_id=bank_id,
                content=item,
                context=f"{label} during {meeting_date.date().isoformat()} meeting with {contact_name}",
                timestamp=meeting_date,
                document_id=document_id,
                metadata={"kind": kind, "contact": contact_name, "slug": slug},
            )
            count += 1

    sentiment = facts.get("sentiment", "neutral")
    client.retain(
        bank_id=bank_id,
        content=f"Overall sentiment of the {meeting_date.date().isoformat()} meeting with "
                 f"{contact_name} was: {sentiment}.",
        timestamp=meeting_date,
        document_id=document_id,
        metadata={"kind": "sentiment", "contact": contact_name, "slug": slug},
    )
    count += 1
    return count


def record_style_feedback(feedback_text: str) -> None:
    ensure_bank(config.STYLE_BANK_ID, name="User briefing style preferences")
    get_client().retain(
        bank_id=config.STYLE_BANK_ID,
        content=feedback_text,
        timestamp=datetime.now(),
        metadata={"kind": "style_feedback"},
    )


# ---------------------------------------------------------------------------
# Reading memory (recall / reflect)
# ---------------------------------------------------------------------------

def recall_raw(slug: str, query: str, limit: int = 8) -> list[str]:
    """Raw matching memories -- shown to the user so memory is visibly the
    star, not just an invisible LLM prompt-stuffing trick."""
    bank_id = config.contact_bank_id(slug)
    try:
        result = get_client().recall(bank_id=bank_id, query=query)
    except Exception:
        return []
    texts = [r.text for r in getattr(result, "results", [])]
    return texts[:limit]


def recall_sources(slug: str, query: str, limit: int = 12) -> list[dict[str, Any]]:
    """Compatibility wrapper for the app's legacy source-format contract.

    The workflow expects a list of dictionaries with numbered references and a
    date field, while the Hindsight client returns typed recall results.
    """
    bank_id = config.contact_bank_id(slug)
    try:
        result = get_client().recall(bank_id=bank_id, query=query)
    except Exception:
        return []

    sources: list[dict[str, Any]] = []
    for index, item in enumerate(getattr(result, "results", [])[:limit], start=1):
        text = getattr(item, "text", str(item))
        date_value = getattr(item, "occurred_start", None) or getattr(item, "mentioned_at", None)
        if isinstance(date_value, str) and "T" in date_value:
            date_value = date_value.split("T", 1)[0]
        sources.append({
            "n": index,
            "text": text,
            "date": date_value or "",
        })
    return sources


def relationship_context(slug: str, contact_name: str) -> str:
    """Disposition-aware synthesis of everything remembered about this
    contact. Empty history -> Hindsight returns a generic/empty answer,
    which is exactly the 'before' half of the demo's before/after story."""
    bank_id = config.contact_bank_id(slug)
    try:
        answer = get_client().reflect(
            bank_id=bank_id,
            query=(
                f"Summarize everything known about our relationship with {contact_name}: "
                f"what's been discussed across past meetings, promises made by both sides, "
                f"concerns raised, and the overall relationship trajectory."
            ),
        )
        return answer.text
    except Exception as exc:
        return f"(no memory yet for {contact_name} -- {exc})"


def open_followups(slug: str, contact_name: str) -> list[str]:
    return recall_raw(
        slug,
        query=f"promises or follow-ups owed to or by {contact_name} that may still be outstanding",
        limit=6,
    )


def style_notes() -> str:
    ensure_bank(config.STYLE_BANK_ID, name="User briefing style preferences")
    try:
        answer = get_client().reflect(
            bank_id=config.STYLE_BANK_ID,
            query="What are the user's stated preferences for how prep briefings should be written?",
        )
        return answer.text
    except Exception:
        return ""