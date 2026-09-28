"""
Realistic synthetic data for the hackathon demo: a sales rep ("you") tracking
a deal with Rohan Kapoor, VP Engineering at Northwind Logistics, across three
meetings spread over six weeks. Numbers, objections, and follow-ups are
made-up but deliberately specific, per the "use realistic data" guidance --
generic filler doesn't show off memory the way concrete detail does.

build_demo_result() does the actual work and returns plain data, so both
cli.py (rendered with rich) and webapp.py (rendered as HTML) show exactly
the same run without duplicating the retain/recall/reflect logic.
"""
from datetime import datetime
from typing import Any

from agent import config, contacts, memory, workflow

CONTACT_NAME = "Rohan Kapoor"
COMPANY = "Northwind Logistics"
ROLE = "VP Engineering"

MEETINGS = [
    (
        "2026-08-04",
        "First discovery call with Rohan Kapoor (VP Eng, Northwind Logistics). "
        "He's evaluating us against Segment and a homegrown pipeline his team built "
        "two years ago. Main pain point: their current system can't handle their "
        "warehouse IoT event volume, spikes to 40k events/sec during peak season. "
        "He asked pointed questions about our rate limits and whether we support "
        "on-prem deployment -- their compliance team is nervous about cloud-only. "
        "I promised to send a detailed throughput benchmark doc by Friday. He said "
        "he'd loop in their infra lead, Ananya, for the next call. Overall tone: "
        "cautiously interested, skeptical about vendor lock-in given their bad "
        "experience with their last analytics vendor.",
    ),
    (
        "2026-08-22",
        "Second call with Rohan and Ananya (infra lead) from Northwind. They'd read "
        "the benchmark doc and were impressed by the throughput numbers, but Ananya "
        "flagged a hard blocker: no SOC 2 Type II report available yet, and their "
        "procurement policy requires one for any cloud vendor touching warehouse "
        "location data. Rohan pushed back a bit less than last time -- seemed more "
        "warmed up, joked about how much he hates their current vendor's support "
        "response times. He asked for pricing at their expected volume (roughly "
        "2M events/day) and said he wants to move fast because their contract with "
        "the incumbent renews in November and he'd rather not auto-renew. I promised "
        "to get our SOC 2 timeline from our compliance team and follow up with exact "
        "pricing within a week. Ananya promised to send their current architecture "
        "diagram so we can scope the migration.",
    ),
    (
        "2026-09-19",
        "Third call, just Rohan this time -- Ananya was out. He seemed frustrated: "
        "he never got the architecture-diagram exchange fully closed on our side "
        "(pricing took 10 days instead of a week, which he noted). Good news: our "
        "SOC 2 Type II is now on track for a November completion, which lines up "
        "with their renewal window. He said budget is approved for Q4 if we can "
        "commit to a January migration start. His one lingering concern is our "
        "on-call support coverage during their peak season (Nov-Jan) -- their last "
        "vendor left them hanging during a Black Friday incident. I promised a "
        "written support SLA doc before our next call. He promised to get their "
        "CTO on the next call to sign off, tentatively first week of October. He "
        "was noticeably warmer on this call, even suggested we grab coffee at the "
        "logistics industry meetup next month.",
    ),
]

MEETING_FACTS = [
    {
        "topics_discussed": [
            "Northwind's warehouse IoT pipeline cannot handle peak volume of 40k events per second.",
            "Rohan is comparing Segment with Northwind's homegrown pipeline.",
        ],
        "promises_by_user": [
            "Send Rohan a detailed throughput benchmark by Friday.",
        ],
        "promises_by_contact": [
            "Rohan will include infra lead Ananya in the next call.",
        ],
        "concerns_or_objections": [
            "Rohan is wary of vendor lock-in after a bad experience with a previous analytics vendor.",
        ],
        "sentiment": "cautious",
    },
    {
        "topics_discussed": [
            "Northwind expects about 2 million events per day and its incumbent contract renews in November.",
        ],
        "promises_by_user": [
            "Provide the SOC 2 timeline and exact pricing within one week.",
        ],
        "promises_by_contact": [
            "Ananya will send Northwind's current architecture diagram.",
        ],
        "concerns_or_objections": [
            "Ananya identified the missing SOC 2 Type II report as a procurement blocker.",
        ],
        "sentiment": "positive",
    },
    {
        "topics_discussed": [
            "Northwind has Q4 budget if a January migration start can be committed.",
        ],
        "promises_by_user": [
            "Send Rohan a written peak-season support SLA before the next call.",
        ],
        "promises_by_contact": [
            "Rohan will invite the CTO to a call tentatively planned for the first week of October.",
        ],
        "concerns_or_objections": [
            "Rohan is concerned about peak-season on-call coverage after a previous vendor missed a Black Friday incident.",
        ],
        "sentiment": "positive",
    },
]

REFERENCE_NOTES = {
    "rohan-kapoor": {
        "date": "2026-08-04",
        "text": MEETINGS[0][1],
        "facts": MEETING_FACTS[0],
    },
    "priya-menon": {
        "date": "2026-08-28",
        "text": (
            "Quarterly planning call with Priya Menon, VP Sales Operations at Acme Retail. "
            "The team is evaluating a phased inventory analytics pilot across three stores "
            "before expanding to all twelve locations. Current catalog mismatches contribute "
            "to stockouts during promotions. Priya's main concern is integrating with their "
            "existing POS system without disrupting store teams. I promised to send an "
            "integration checklist and a two-week pilot plan by Friday. Priya will share the "
            "three pilot store names and introduce their IT lead by Wednesday. Budget approval "
            "depends on seeing pilot results; target a decision in September."
        ),
        "facts": {
            "topics_discussed": [
                "Acme Retail is considering a phased inventory analytics pilot across three stores before expanding to twelve locations.",
                "Catalog mismatches contribute to stockouts during promotions.",
            ],
            "promises_by_user": [
                "Send Priya an integration checklist and a two-week pilot plan by Friday.",
            ],
            "promises_by_contact": [
                "Priya will share the three pilot store names and introduce the IT lead by Wednesday.",
            ],
            "concerns_or_objections": [
                "Priya is concerned about integrating with the current POS without disrupting store teams.",
                "Budget approval depends on seeing the pilot results.",
            ],
            "sentiment": "cautious",
        },
    },
}

FEEDBACK_TEXT = (
    "For the upcoming CTO sign-off, show only the latest unresolved commitments "
    "and next steps. Leave out older historical commitments and company background. "
    "Use concise bullets and highlight what changed since the prior meeting."
)


def _demo_action_briefing() -> str:
    """Build the pre-personalization briefing from all meeting commitments."""
    our_commitments = []
    contact_commitments = []
    for (date_str, _), facts in zip(MEETINGS, MEETING_FACTS):
        date_label = datetime.fromisoformat(date_str).strftime("%b %d").replace(" 0", " ")
        our_commitments.extend(
            f"- **{date_label} · Our side:** {item}"
            for item in facts["promises_by_user"]
        )
        contact_commitments.extend(
            f"- **{date_label} · Contact:** {item}"
            for item in facts["promises_by_contact"]
        )

    return "\n".join([
        "## Commitments to track (completion not recorded)",
        *our_commitments,
        *contact_commitments,
    ])


def _demo_personalized_briefing() -> str:
    """Focus the personalized prep on current actions for CTO sign-off."""
    return "\n".join([
        "## Current actions for CTO sign-off",
        "- **Our commitment (Sep 19):** Send the written peak-season support SLA before the next call.",
        "- **Rohan's commitment (Sep 19):** Invite the CTO to a sign-off call, tentatively the first week of October.",
        "- **Confirm:** Close the architecture-diagram exchange; the latest notes say it was not fully closed.",
        "- **Pricing:** It took 10 days instead of the promised week; confirm the final pricing is clear.",
        "- **Changed:** SOC 2 Type II is on track for November; Q4 budget depends on a January migration start.",
    ])


def _prepare_demo_recall(prep: dict[str, Any], personalized: bool = False) -> dict[str, Any]:
    """Keep demo recall factual and vary the focus after style feedback."""
    prep["briefing"] = (
        _demo_personalized_briefing() if personalized else _demo_action_briefing()
    )
    prep["followups"] = [
        item for item in prep.get("followups", [])
        if "sentiment" not in item.casefold()
    ]
    prep["sources"] = [
        source for source in prep.get("sources", [])
        if "sentiment" not in source.get("text", "").casefold()
    ]
    return prep


def create_demo_state(contact_slug: str | None = None) -> dict[str, Any]:
    """Create the state needed to run the demo one stage at a time."""
    config.require_config()

    slug = contact_slug or contacts.add_contact(CONTACT_NAME, COMPANY, ROLE)
    memory.ensure_contact_bank(slug, CONTACT_NAME)

    return {
        "contact_name": CONTACT_NAME,
        "company": COMPANY,
        "role": ROLE,
        "slug": slug,
        "stage": 0,
        "steps": [],
        "logged_meetings": [],
        "complete": False,
    }


def advance_demo_state(state: dict[str, Any]) -> None:
    """Run the next demo operation and append its display-ready result."""
    if state["complete"]:
        return

    slug = state["slug"]
    stage = state["stage"]
    if stage == 0:
        state["before"] = workflow.generate_prep(
            slug, CONTACT_NAME, goal="Get oriented before our first call"
        )
        state["steps"].append({
            "kind": "prep",
            "title": "Briefing before any meetings are logged",
            "chapter": "Problem",
            "cue": "This is the agent before it knows the relationship. Notice how little it can say about the deal.",
            "result": state["before"],
        })
    elif 1 <= stage <= len(MEETINGS):
        date_str, notes = MEETINGS[stage - 1]
        meeting_date = datetime.fromisoformat(date_str)
        facts = MEETING_FACTS[stage - 1]
        count = memory.log_meeting(slug, CONTACT_NAME, meeting_date, notes, facts)
        result = {"facts": facts, "count": count}
        meeting = {"date": date_str, "notes": notes, **result}
        state["logged_meetings"].append(meeting)
        state["steps"].append({
            "kind": "meeting",
            "title": f"Meeting {stage} of {len(MEETINGS)} logged",
            "chapter": "Live demo",
            "cue": "I’m adding one real meeting. Hindsight keeps the useful topics, promises, and concerns for next time.",
            "meeting": meeting,
        })
    elif stage == len(MEETINGS) + 1:
        state["after"] = _prepare_demo_recall(workflow.generate_prep(
            slug, CONTACT_NAME, goal="Prep for the call where their CTO signs off"
        ))
        state["steps"].append({
            "kind": "prep",
            "title": "The same briefing, now with meeting memory",
            "chapter": "Recall",
            "cue": "Now the agent can recall what changed, what is still owed, and what Rohan cares about.",
            "result": state["after"],
        })
    elif stage == len(MEETINGS) + 2:
        memory.record_style_feedback(FEEDBACK_TEXT)
        state["feedback_text"] = FEEDBACK_TEXT
        state["steps"].append({
            "kind": "feedback",
            "title": "Style feedback recorded",
            "chapter": "Bonus: personalization",
            "cue": "A quick preference teaches the agent how I want future briefings written.",
            "text": FEEDBACK_TEXT,
        })
    else:
        state["adapted"] = _prepare_demo_recall(workflow.generate_prep(
            slug, CONTACT_NAME, goal="Prep for the call where their CTO signs off"
        ), personalized=True)
        state["steps"].append({
            "kind": "prep",
            "title": "Same request, adapted to that feedback",
            "chapter": "Bonus: personalization",
            "cue": "The personalized briefing drops the broad history and focuses on current CTO-call actions.",
            "result": state["adapted"],
        })

    state["stage"] += 1
    state["complete"] = state["stage"] > len(MEETINGS) + 3


def build_demo_result() -> dict[str, Any]:
    """Run the full demo and return structured results for CLI rendering."""
    state = create_demo_state()
    while not state["complete"]:
        advance_demo_state(state)
    return state


def run_demo(console) -> None:
    """CLI rendering of the demo, using rich."""
    from rich.rule import Rule

    result = build_demo_result()

    console.print(Rule("[bold]STEP 1 -- Prep BEFORE any meetings are logged[/bold]"))
    _render_prep(console, result["contact_name"], result["before"])

    console.print(Rule(
        f"[bold]STEP 2 -- Logging {len(result['logged_meetings'])} real meetings over 6 weeks[/bold]"
    ))
    for m in result["logged_meetings"]:
        console.print(
            f"  [green]{m['date']}[/green]: retained {m['count']} atomic memories "
            f"(sentiment: {m['facts']['sentiment']})"
        )

    console.print(Rule("[bold]STEP 3 -- Prep AFTER three meetings of memory[/bold]"))
    _render_prep(console, result["contact_name"], result["after"])

    console.print(Rule("[bold]STEP 4 -- Teach the agent a style preference[/bold]"))
    console.print(f'  Recorded feedback: "{result["feedback_text"]}"')

    console.print(Rule("[bold]STEP 5 -- Same prep request, now adapted to your style[/bold]"))
    _render_prep(console, result["contact_name"], result["adapted"])


def _render_prep(console, contact_name: str, prep_result: dict[str, Any]) -> None:
    from rich.markdown import Markdown
    from rich.panel import Panel

    console.print(Panel.fit(Markdown(prep_result["briefing"]), title=f"Prep briefing -- {contact_name}"))
    if prep_result["raw_memories"]:
        console.print(f"[dim]({len(prep_result['raw_memories'])} raw memories retrieved from Hindsight)[/dim]")
    if prep_result["followups"]:
        console.print("[bold yellow]Open follow-ups:[/bold yellow]")
        for f in prep_result["followups"]:
            console.print(f"  - {f}")
    console.print()