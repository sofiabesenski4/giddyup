"""Static analysis gate — an HTTP client for the Ruby analyzer service."""

from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable

from ..config import RunConfig
from ..state import PipelineState

TIMEOUT_SECONDS = 30
MAX_FILES = 50


def _git_changed(repo: Path) -> list[str] | None:
    """Paths git reports as added or modified, or None outside a git repo."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all"],
            cwd=repo, capture_output=True, text=True, timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None

    paths = []
    for line in proc.stdout.splitlines():
        if len(line) > 3:
            # Rename entries read "R  old -> new"; the new path is what changed.
            paths.append(line[3:].split(" -> ")[-1].strip().strip('"'))
    return paths


def collect_ruby_files(repo: Path) -> list[dict[str, str]]:
    """Gather the Ruby the coding pass actually touched.

    Judging the whole codebase would punish the agent for pre-existing code, so
    prefer git's view of what changed and fall back to a full scan only outside
    a repository.
    """
    repo = Path(repo)
    changed = _git_changed(repo)
    candidates = (
        [repo / p for p in changed] if changed is not None else sorted(repo.rglob("*.rb"))
    )

    files = []
    for path in candidates:
        if path.suffix != ".rb" or not path.is_file():
            continue
        try:
            files.append(
                {"path": str(path.relative_to(repo)), "source": path.read_text(encoding="utf-8")}
            )
        except (OSError, UnicodeDecodeError):
            continue
        if len(files) >= MAX_FILES:
            break
    return files


def format_violations(files: list[dict[str, Any]]) -> str:
    """Turn the report into feedback a coding agent can act on."""
    lines = []
    for entry in files:
        violations = entry.get("violations") or []
        if not violations:
            continue
        lines.append(f"{entry.get('path')}:")
        for violation in violations:
            lines.append(f"  - [{violation.get('rule')}] {violation.get('message')}")
    return "\n".join(lines)


def _post(url: str, payload: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"content-type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


async def analyze_node(
    state: PipelineState,
    config: RunConfig,
    post: Callable[[str, dict], dict] = _post,
    emit: Callable[[dict], None] | None = None,
) -> dict:
    """Score the changed Ruby and turn any violations into coder feedback."""

    def publish(event: dict) -> None:
        if emit is not None:
            emit(event)

    files = collect_ruby_files(config.repo)
    if not files:
        publish({"type": "analysis", "verdict": "skipped", "detail": "no Ruby changed"})
        return {"analysis_verdict": "skipped", "analysis": {}}

    payload = {
        "files": files,
        "thresholds": {
            "flog_average": config.flog_average_limit,
            "smells": config.smells_limit,
        },
    }

    try:
        report = post(f"{config.analyzer_url.rstrip('/')}/analyze", payload)
    except (OSError, urllib.error.URLError, ValueError) as exc:
        # A missing analyzer degrades the pipeline, it does not break it.
        publish({"type": "analysis", "verdict": "skipped", "detail": f"analyzer unavailable: {exc}"})
        return {"analysis_verdict": "skipped", "analysis": {"error": str(exc)}}

    verdict = report.get("verdict", "skipped")
    reported = report.get("files", [])
    publish(
        {
            "type": "analysis",
            "verdict": verdict,
            "detail": f"{len(files)} file(s)",
            "files": reported,
        }
    )

    update: dict = {"analysis_verdict": verdict, "analysis": report}
    if verdict == "complex":
        update["feedback"] = format_violations(reported)
    return update
