"""
A minimal, dependency-free markdown-ish renderer for LLM output. Handles
headers, bold/italic, bullet lists, numbered lists, and paragraphs -- enough
for the structured briefings this agent generates. Not a general markdown
parser; deliberately kept dependency-free so the web UI doesn't add another
pip package on top of what the CLI already needs.
"""
import html
import re


def cited_numbers(text: str) -> set[int]:
    """Extract inline source citations like [3] or [2][5] from briefing text."""
    return {int(match) for match in re.findall(r"\[(\d+)\]", text or "")}


def render(text: str, sources: list[dict] | None = None, prefix: str = "src") -> str:
    text = (text or "").strip()
    if not text:
        return ""

    lines = text.split("\n")
    out: list[str] = []
    in_ul = False
    in_ol = False

    def close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            out.append("</ul>")
            in_ul = False
        if in_ol:
            out.append("</ol>")
            in_ol = False

    def inline(s: str) -> str:
        s = html.escape(s)
        if sources:
            s = re.sub(
                r"\[(\d+)\]",
                lambda m: f'<a href="#{prefix}-{m.group(1)}" class="source-cite">[{m.group(1)}]</a>',
                s,
            )
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", s)
        return s

    for raw in lines:
        line = raw.strip()
        if not line:
            close_lists()
            continue

        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            close_lists()
            level = min(len(m.group(1)) + 2, 6)
            out.append(f"<h{level}>{inline(m.group(2))}</h{level}>")
            continue

        m = re.match(r"^[-*\u2022]\s+(.*)", line)
        if m:
            if not in_ul:
                close_lists()
                out.append("<ul>")
                in_ul = True
            out.append(f"<li>{inline(m.group(1))}</li>")
            continue

        m = re.match(r"^\d+[.)]\s+(.*)", line)
        if m:
            if not in_ol:
                close_lists()
                out.append("<ol>")
                in_ol = True
            out.append(f"<li>{inline(m.group(1))}</li>")
            continue

        close_lists()
        out.append(f"<p>{inline(line)}</p>")

    close_lists()
    return "\n".join(out)