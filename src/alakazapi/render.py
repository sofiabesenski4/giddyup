"""Turning graph events into terminal output. Pure functions, no printing."""

from __future__ import annotations

from .state import PipelineState

DIM = "\033[2m"
YELLOW = "\033[33m"
GREEN = "\033[32m"
BOLD = "\033[1m"
RED = "\033[31m"
RESET = "\033[0m"

MAX_DETAIL = 80

# The field worth showing differs per tool; for anything else, skip the detail
# rather than dumping a whole tool input into the terminal.
DETAIL_FIELDS = ("command", "file_path", "pattern", "path", "url")


def _detail(tool_input: dict) -> str:
    for field in DETAIL_FIELDS:
        value = tool_input.get(field)
        if value:
            text = str(value)
            return text if len(text) <= MAX_DETAIL else text[: MAX_DETAIL - 1] + "…"
    return ""


def render_event(event: dict) -> str | None:
    """Render one streamed event, or None if it has no visible form."""
    kind = event.get("type")

    if kind == "text":
        return event.get("text", "")
    if kind == "tool":
        detail = _detail(event.get("input") or {})
        suffix = f" {detail}" if detail else ""
        return f"{DIM}  · {event.get('name')}{suffix}{RESET}"
    if kind == "error":
        return f"{RED}  ! {event.get('text')}{RESET}"
    if kind == "analysis":
        return _analysis(event)
    return None


def _analysis(event: dict) -> str:
    verdict = event.get("verdict", "skipped")
    detail = event.get("detail", "")
    colour = {"clean": GREEN, "complex": YELLOW}.get(verdict, DIM)
    head = f"{colour}  analysis: {verdict}{RESET}{DIM} {detail}{RESET}"

    if verdict != "complex":
        return head

    # Only a failing verdict lists files: this is what goes back to the coder.
    lines = [head]
    for entry in event.get("files") or []:
        for violation in entry.get("violations") or []:
            lines.append(f"{DIM}    {entry.get('path')}: {violation.get('message')}{RESET}")
    return "\n".join(lines)


def render_summary(state: PipelineState) -> str:
    """One closing line reporting what the run cost and how it ended."""
    if state.get("error"):
        return f"{RED}failed: {state['error']}{RESET}"

    passes = state.get("iteration", 0)
    label = "pass" if passes == 1 else "passes"
    return (
        f"{DIM}{state.get('verdict', 'unknown')} after {passes} {label} "
        f"· ${state.get('cost_usd', 0.0):.2f}{RESET}"
    )
