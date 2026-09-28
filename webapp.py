"""
Web UI for the Meeting Prep Agent.

This is a thin Flask front-end over the same agent/ package cli.py uses --
nothing here talks to Hindsight or Groq directly, it only calls into
agent.contacts / agent.memory / agent.workflow, exactly like the CLI does.
Run either one, or both; they share the same contact registry and the same
Hindsight memory banks.

Run with:  python webapp.py
Then open: http://127.0.0.1:5000
"""
from datetime import datetime
import json
import secrets

from flask import Flask, redirect, render_template, request, url_for

from agent import config, contacts, memory, mini_markdown, workflow
from data.seed_demo_data import REFERENCE_NOTES, advance_demo_state, create_demo_state

app = Flask(__name__)
app.jinja_env.filters["briefing_html"] = mini_markdown.render
_DEMO_RUNS = {}
# Allow large uploads to reach the chunked transcription path instead of being
# rejected by Flask before the app can split the file into smaller chunks.
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024


@app.teardown_request
def close_hindsight_client(exc):
    # Each request runs on its own thread with its own Hindsight client;
    # close it so HTTP sessions don't leak.
    memory.close_client()


@app.context_processor
def inject_nav_contacts():
    return {"nav_contacts": contacts.list_contacts()}


@app.errorhandler(413)
def too_large(_):
    return "That file is too large. Recordings must be under 250 MB.", 413


def _process_meeting_form(slug, info):
    """Shared by the main contact page and the side panel. Reads the meeting
    form (date, optional recording, optional notes), logs it, and returns
    (meeting_result, error_message)."""
    notes = request.form.get("notes", "").strip()
    date_str = request.form.get("date", "").strip()
    video = request.files.get("video")
    try:
        meeting_date = datetime.fromisoformat(date_str) if date_str else datetime.now()
    except ValueError:
        return None, "That date isn't valid."
    try:
        has_video = bool(video and video.filename)
        reference = REFERENCE_NOTES.get(slug)
        if reference and notes == reference["text"] and not has_video:
            result = workflow.log_meeting_from_notes(
                slug, info["name"], meeting_date, notes,
                known_facts=reference["facts"],
            )
            result["transcript"] = ""
        else:
            result = workflow.log_meeting(
                slug=slug,
                contact_name=info["name"],
                meeting_date=meeting_date,
                notes=notes or None,
                video_file=video if has_video else None,
            )
    except workflow.MeetingInputError as exc:
        return None, str(exc)
    result["meeting_date"] = meeting_date.date().isoformat()
    return result, None


def _meeting_note_candidates(meeting_result):
    facts = meeting_result["facts"]
    groups = (
        ("Topics discussed", "topics_discussed"),
        ("Our commitment", "promises_by_user"),
        ("Contact commitment", "promises_by_contact"),
        ("Concern or blocker", "concerns_or_objections"),
    )
    return [
        {
            "text": text,
            "date": meeting_result["meeting_date"],
            "source": label,
        }
        for label, key in groups
        for text in facts.get(key, [])
        if text.strip()
    ]


def _prep_note_candidates(prep_result):
    candidates = []
    seen = set()
    for text in prep_result.get("followups", []):
        candidate = {"text": text, "date": "", "source": "Generated open follow-up"}
        identity = text.strip().casefold()
        if identity and identity not in seen:
            candidates.append(candidate)
            seen.add(identity)
    for source in prep_result.get("sources", []):
        text = source.get("text", "").strip()
        identity = text.casefold()
        if text and identity not in seen:
            candidates.append({
                "text": text,
                "date": str(source.get("date", "")),
                "source": "Recalled contact detail",
            })
            seen.add(identity)
    return candidates


def _render_contact_page(slug, info, **overrides):
    context = {
        "slug": slug,
        "info": info,
        "active_slug": slug,
        "meeting_result": None,
        "prep_result": None,
        "goal": "",
        "error": None,
        "reference_notes": REFERENCE_NOTES.get(slug),
        "special_notes": contacts.special_notes(slug),
        "note_candidates": [],
        "notes_saved": request.args.get("saved", type=int, default=0),
    }
    context.update(overrides)
    return render_template("contact.html", **context)


# ---------------------------------------------------------------------------
# Main site
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", contacts=contacts.list_contacts())


@app.route("/contacts", methods=["POST"])
def add_contact():
    name = request.form.get("name", "").strip()
    if not name:
        return redirect(url_for("index"))
    company = request.form.get("company", "").strip()
    role = request.form.get("role", "").strip()
    slug = contacts.add_contact(name, company, role)
    memory.ensure_contact_bank(slug, name)
    return redirect(url_for("contact_page", slug=slug))


@app.route("/contact/<slug>")
def contact_page(slug):
    info = contacts.get_contact(slug)
    if not info:
        return redirect(url_for("index"))
    return _render_contact_page(slug, info)


@app.route("/contact/<slug>/log-meeting", methods=["POST"])
def log_meeting(slug):
    info = contacts.get_contact(slug)
    if not info:
        return redirect(url_for("index"))
    meeting_result, error = _process_meeting_form(slug, info)
    return _render_contact_page(
        slug, info, meeting_result=meeting_result, error=error,
        note_candidates=_meeting_note_candidates(meeting_result) if meeting_result else [],
    )


@app.route("/contact/<slug>/prep", methods=["POST"])
def prep(slug):
    info = contacts.get_contact(slug)
    if not info:
        return redirect(url_for("index"))
    goal = request.form.get("goal", "").strip()
    prep_result = workflow.generate_prep(slug, info["name"], goal or None)
    return _render_contact_page(
        slug, info, prep_result=prep_result, goal=goal,
        note_candidates=_prep_note_candidates(prep_result),
    )


@app.route("/contact/<slug>/delete", methods=["POST"])
def delete_contact(slug):
    if not contacts.get_contact(slug):
        return redirect(url_for("index"))
    contacts.delete_contact(slug)
    memory.delete_contact_bank(slug)
    return redirect(url_for("index"))


# ---------------------------------------------------------------------------
# Compact side-panel page (templates/panel.html)
# ---------------------------------------------------------------------------

def _render_panel(slug=None, **overrides):
    context = {
        "contacts": contacts.list_contacts(),
        "slug": slug,
        "info": contacts.get_contact(slug) if slug else None,
        "meeting_result": None,
        "prep_result": None,
        "goal": "",
        "error": None,
        "reference_notes": REFERENCE_NOTES.get(slug) if slug else None,
        "special_notes": contacts.special_notes(slug) if slug else [],
        "note_candidates": [],
        "notes_saved": request.args.get("saved", type=int, default=0),
    }
    context.update(overrides)
    return render_template("panel.html", **context)


@app.route("/panel")
def panel_home():
    return _render_panel()


@app.route("/panel/<slug>")
def panel_contact(slug):
    if not contacts.get_contact(slug):
        return redirect(url_for("panel_home"))
    return _render_panel(slug)


@app.route("/panel/<slug>/log-meeting", methods=["POST"])
def panel_log_meeting(slug):
    info = contacts.get_contact(slug)
    if not info:
        return redirect(url_for("panel_home"))
    meeting_result, error = _process_meeting_form(slug, info)
    return _render_panel(
        slug, meeting_result=meeting_result, error=error,
        note_candidates=_meeting_note_candidates(meeting_result) if meeting_result else [],
    )


@app.route("/panel/<slug>/prep", methods=["POST"])
def panel_prep(slug):
    info = contacts.get_contact(slug)
    if not info:
        return redirect(url_for("panel_home"))
    goal = request.form.get("goal", "").strip()
    prep_result = workflow.generate_prep(slug, info["name"], goal or None)
    return _render_panel(
        slug, prep_result=prep_result, goal=goal,
        note_candidates=_prep_note_candidates(prep_result),
    )


@app.route("/contact/<slug>/special-notes", methods=["POST"])
def save_contact_special_notes(slug):
    if not contacts.get_contact(slug):
        return redirect(url_for("index"))

    approved = []
    for payload in request.form.getlist("selected_notes"):
        try:
            note = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(note, dict) and note.get("text"):
            approved.append(note)

    manual_note = request.form.get("manual_note", "").strip()
    if manual_note:
        approved.append({"text": manual_note, "source": "User note"})

    saved = contacts.save_special_notes(slug, approved)
    is_panel = request.form.get("view") == "panel"
    endpoint = "panel_contact" if is_panel else "contact_page"
    return redirect(url_for(endpoint, slug=slug, saved=saved))


# ---------------------------------------------------------------------------
# Other pages
# ---------------------------------------------------------------------------

@app.route("/about")
def about():
    return render_template("about.html", model=config.GROQ_MODEL)


@app.route("/style")
def style_page():
    return render_template("style.html", style_notes=memory.style_notes(), saved=False)


@app.route("/style", methods=["POST"])
def style_feedback():
    feedback_text = request.form.get("feedback", "").strip()
    if feedback_text:
        memory.record_style_feedback(feedback_text)
    return render_template("style.html", style_notes=memory.style_notes(), saved=bool(feedback_text))


@app.route("/demo")
def demo_page():
    return render_template("demo.html", result=None)


@app.route("/demo", methods=["POST"])
def run_demo():
    run_id = secrets.token_hex(12)
    result = create_demo_state(contact_slug=f"demo-{run_id}")
    _DEMO_RUNS[run_id] = result
    advance_demo_state(result)
    return redirect(url_for("demo_run", run_id=run_id))


@app.route("/demo/<run_id>")
def demo_run(run_id):
    result = _DEMO_RUNS.get(run_id)
    if result is None:
        return redirect(url_for("demo_page"))
    return render_template("demo.html", result=result, run_id=run_id)


@app.route("/demo/<run_id>/next", methods=["POST"])
def advance_demo(run_id):
    result = _DEMO_RUNS.get(run_id)
    if result is None:
        return redirect(url_for("demo_page"))
    advance_demo_state(result)
    if result["complete"]:
        memory.delete_contact_bank(result["slug"])
    return redirect(url_for("demo_run", run_id=run_id))


if __name__ == "__main__":
    config.require_config()
    try:
        app.run(debug=True)
    finally:
        memory.close_client()