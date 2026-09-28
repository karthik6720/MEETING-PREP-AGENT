"""
A tiny local registry mapping human-friendly contact info to Hindsight bank
slugs. Hindsight owns the *memory*; this just owns the address book so the
CLI can say "log a meeting with Priya Menon" instead of a raw bank_id.
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / "data" / "contacts.json"


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _load() -> dict[str, Any]:
    if not _REGISTRY_PATH.exists():
        return {}
    return json.loads(_REGISTRY_PATH.read_text())


def _save(data: dict[str, Any]) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    _REGISTRY_PATH.write_text(json.dumps(data, indent=2))


def add_contact(name: str, company: str = "", role: str = "") -> str:
    slug = _slugify(name)
    data = _load()
    contact = data.get(slug, {})
    contact.update({"name": name, "company": company, "role": role})
    data[slug] = contact
    _save(data)
    return slug


def get_contact(slug: str) -> dict[str, Any] | None:
    return _load().get(slug)


def special_notes(slug: str) -> list[dict[str, Any]]:
    contact = get_contact(slug)
    if not contact:
        return []
    return contact.get("special_notes", [])


def save_special_notes(slug: str, notes: list[dict[str, Any]]) -> int:
    data = _load()
    contact = data.get(slug)
    if not contact:
        return 0

    saved = contact.setdefault("special_notes", [])
    known = {
        (note.get("text", "").casefold(), note.get("date", ""))
        for note in saved
    }
    added = 0
    for note in notes:
        text = str(note.get("text", "")).strip()
        if not text:
            continue
        date = str(note.get("date", "")).strip()
        identity = (text.casefold(), date)
        if identity in known:
            continue
        saved.append({
            "text": text,
            "date": date,
            "source": str(note.get("source", "User note")).strip() or "User note",
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        })
        known.add(identity)
        added += 1

    if added:
        _save(data)
    return added


def delete_contact(slug: str) -> bool:
    data = _load()
    if slug not in data:
        return False
    del data[slug]
    _save(data)
    return True


def resolve(name_or_slug: str) -> tuple[str, dict[str, Any]] | None:
    data = _load()
    if name_or_slug in data:
        return name_or_slug, data[name_or_slug]
    slug = _slugify(name_or_slug)
    if slug in data:
        return slug, data[slug]
    return None


def list_contacts() -> dict[str, Any]:
    return _load()
