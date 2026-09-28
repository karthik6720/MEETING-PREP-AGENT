#!/usr/bin/env python3
"""
Meeting Prep Agent -- CLI

A memory-powered agent that briefs you before a meeting with full context
from every past interaction with that contact, built on Hindsight.

Commands:
    contact-add   Register a new contact
    contacts      List registered contacts
    meeting-log   Log notes from a meeting (facts get retained to memory)
    prep          Generate a prep briefing before your next meeting
    feedback      Teach the agent how you like briefings written
    demo          Seed realistic synthetic history and show the before/after
"""
from datetime import datetime

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from agent import config, contacts, llm, memory, workflow

console = Console()


@click.group()
def cli():
    pass


@cli.command("contact-add")
@click.argument("name")
@click.option("--company", default="", help="Contact's company")
@click.option("--role", default="", help="Contact's role/title")
def contact_add(name, company, role):
    config.require_config()
    slug = contacts.add_contact(name, company, role)
    memory.ensure_contact_bank(slug, name)
    console.print(f"[green]Added contact[/green] '{name}' -> bank id [bold]{slug}[/bold]")


@cli.command("contacts")
def contacts_list():
    reg = contacts.list_contacts()
    if not reg:
        console.print("No contacts yet. Try: [bold]python cli.py contact-add \"Jane Doe\"[/bold]")
        return
    for slug, info in reg.items():
        extra = " / ".join(x for x in [info.get("role"), info.get("company")] if x)
        console.print(f"[bold]{slug}[/bold] -- {info['name']}" + (f" ({extra})" if extra else ""))


@cli.command("meeting-log")
@click.argument("name_or_slug")
@click.option("--notes", required=True, help="Raw meeting notes (quote the whole thing)")
@click.option("--date", default=None, help="Meeting date, YYYY-MM-DD (default: today)")
def meeting_log(name_or_slug, notes, date):
    config.require_config()
    resolved = contacts.resolve(name_or_slug)
    if not resolved:
        console.print(f"[red]No contact found matching '{name_or_slug}'.[/red] "
                       f"Add them first with contact-add.")
        return
    slug, info = resolved
    meeting_date = datetime.fromisoformat(date) if date else datetime.now()

    with console.status("Extracting facts from your notes and retaining to Hindsight..."):
        result = workflow.log_meeting_from_notes(slug, info["name"], meeting_date, notes)

    facts = result["facts"]
    console.print(Panel.fit(
        f"[bold]{result['count']} atomic memories[/bold] retained for {info['name']} "
        f"({meeting_date.date().isoformat()})\n\n"
        f"Sentiment: [bold]{facts['sentiment']}[/bold]\n"
        f"Topics: {len(facts['topics_discussed'])} | "
        f"Promises (us): {len(facts['promises_by_user'])} | "
        f"Promises (them): {len(facts['promises_by_contact'])} | "
        f"Concerns: {len(facts['concerns_or_objections'])}",
        title="Meeting logged",
    ))


@cli.command("prep")
@click.argument("name_or_slug")
@click.option("--goal", default=None, help="What you want out of the upcoming meeting")
def prep(name_or_slug, goal):
    config.require_config()
    resolved = contacts.resolve(name_or_slug)
    if not resolved:
        console.print(f"[red]No contact found matching '{name_or_slug}'.[/red]")
        return
    slug, info = resolved

    with console.status(f"Recalling memory and composing briefing for {info['name']}..."):
        result = workflow.generate_prep(slug, info["name"], goal)

    console.print(Panel.fit(Markdown(result["briefing"]), title=f"Prep briefing -- {info['name']}"))

    if result["raw_memories"]:
        console.print("\n[dim]Raw memories retrieved from Hindsight (what the briefing is grounded in):[/dim]")
        for m in result["raw_memories"][:6]:
            console.print(f"  [dim]-[/dim] {m}")
    if result["followups"]:
        console.print("\n[bold yellow]Open follow-ups surfaced:[/bold yellow]")
        for f in result["followups"]:
            console.print(f"  - {f}")


@cli.command("feedback")
@click.argument("feedback_text")
def feedback(feedback_text):
    config.require_config()
    memory.record_style_feedback(feedback_text)
    console.print("[green]Got it -- future briefings will adapt to this.[/green]")


@cli.command("demo")
def demo():
    """Seeds two contacts with a realistic multi-meeting history, then runs
    `prep` before and after so the memory effect is obvious in one command."""
    from data.seed_demo_data import run_demo
    run_demo(console)


if __name__ == "__main__":
    try:
        cli()
    finally:
        memory.close_client()