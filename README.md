# Meeting Prep Agent

A meeting-preparation app that turns meeting notes and recordings into contact-specific memory. It uses [Hindsight](https://hindsight.vectorize.io) to retain and recall relationship facts, and Groq to transcribe recordings, extract facts, and write briefings.

## Quick Start

1. **Create and activate a virtual environment** from the project folder.

	Windows PowerShell:

	```powershell
	python -m venv .venv
	.\.venv\Scripts\Activate.ps1
	```

	macOS or Linux:

	```bash
	python3 -m venv .venv
	source .venv/bin/activate
	```

2. **Install the project requirements.**

	```bash
	python -m pip install -r requirements.txt
	```

3. **Add your API keys.** Create a `.env` file in the project folder and add your [Hindsight API key](https://ui.hindsight.vectorize.io) and [Groq API key](https://console.groq.com):

	```text
	HINDSIGHT_API_KEY=your_hindsight_api_key
	GROQ_API_KEY=your_groq_api_key
	HINDSIGHT_BASE_URL=https://api.hindsight.vectorize.io
	```

	The first two values are required. `.env` is ignored by Git; do not commit API keys.

4. **Start the website.**

	```bash
	python webapp.py
	```

	Open <http://127.0.0.1:5000> in your browser. Install FFmpeg separately if you want to transcribe video recordings.

5. **Optional: try the CLI.**

	```bash
	python cli.py demo
	python cli.py contacts
	```

## Features

- A Hindsight memory bank for each contact keeps their topics, commitments, concerns, and meeting history separate.
- Log a meeting from typed notes or an audio/video recording, then generate a prep briefing from what was retained.
- Rohan Kapoor and Priya Menon have synthetic sample notes on their contact pages and in the floating panel. Use these to try the workflow without writing notes first.
- **Special notes** lets you review proposed commitments and details after meeting logging or briefing generation. Select the items to save, or add your own. Saved notes belong to that contact and appear in both the contact page and panel.
- The web app includes a guided demo with one-step-at-a-time controls. Its core shows a blank-memory briefing, three meetings, and a memory-aware briefing; two additional stages demonstrate personalized briefing focus.

## Guided Demo

The first five stages are the core walkthrough:

1. Generate a briefing before any meetings are logged.
2. Retain each of three synthetic meetings as a separate step.
3. Recall the historical commitments and compare them with a focused CTO sign-off briefing.

Two optional stages record style feedback and show the personalized briefing. The demo's synthetic facts are defined in `data/seed_demo_data.py`.

## Recordings

The web app accepts MP4, WebM, MP3, M4A, WAV, OGG, FLAC, MPEG, and MPGA files up to 250 MB. Video is converted to audio before transcription when FFmpeg is available. The initial upload and later fact extraction/memory saving can take additional time. Short audio-only recordings are usually quickest. The app does not keep the uploaded recording after processing.

## Architecture

```text
webapp.py                 Flask contact pages, floating panel, and guided demo
cli.py                    Click commands for contacts, meetings, prep, feedback, and demo
agent/config.py            Environment settings and bank IDs
agent/contacts.py          Local contact registry and per-contact Special notes
agent/workflow.py          Shared meeting, transcription, and briefing workflows
agent/memory.py            Hindsight retain, recall, and reflect calls
agent/llm.py               Groq transcription, fact extraction, and briefing generation
data/seed_demo_data.py     Synthetic sample notes and guided demo stages
templates/                 Web pages and reusable template macros
static/style.css           Shared site and panel styles
```

Meeting notes are extracted into dated topics, promises, and concerns, then retained as small facts in the contact's Hindsight bank. Prep combines recalled sources, open follow-ups, relationship context, and the user's style preferences to produce the briefing.

## Current Limitations

- Meetings are added manually; there is no calendar or conferencing integration.
- The contact registry and Special notes are stored locally in `data/contacts.json`.
- The app is single-user and does not include authentication or team access controls.
