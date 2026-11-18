"""Stall detection and auto-resume markers for durable Temporal runs."""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

from src.webapi.logs import log_path_for
from src.webapi.models import RUN_FAILED, RUN_RUNNING, Run

logger = logging.getLogger(__name__)

# UI / GET: show stalled when workflow.log is this old while running.
STALL_HINT_SECONDS = 15 * 60
# Background: auto-resume once after this much log silence.
AUTO_RESUME_IDLE_SECONDS = 20 * 60
AUTO_RESUME_MARKER = "auto_resume.json"


def session_workspace_exists(run: Run) -> bool:
    if not run.data_dir or not run.session_id:
        return False
    path = os.path.join(
        run.data_dir, "repo", ".vigilo", run.session_id, "session.json"
    )
    return os.path.isfile(path)


def repo_source_present(run: Run) -> bool:
    """True if the checkout still has source (not only ``.vigilo`` after cleanup)."""
    repo = os.path.join(run.data_dir or "", "repo")
    if not os.path.isdir(repo):
        return False
    try:
        return any(entry != ".vigilo" for entry in os.listdir(repo))
    except OSError:
        return False


def workflow_log_idle_seconds(run: Run, *, now: float | None = None) -> int | None:
    """Seconds since workflow.log mtime, or None if the log is missing."""
    path = log_path_for(run.data_dir, run.session_id)
    if not os.path.isfile(path):
        return None
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None
    base = time.time() if now is None else now
    return max(0, int(base - mtime))


def is_stalled(run: Run, *, now: float | None = None) -> bool:
    if run.status != RUN_RUNNING:
        return False
    idle = workflow_log_idle_seconds(run, now=now)
    return idle is not None and idle >= STALL_HINT_SECONDS


def is_recoverable(run: Run, *, durable_engine: bool) -> bool:
    """Manual Recover is allowed for running/failed durable runs with a workspace."""
    if not durable_engine:
        return False
    if run.status not in (RUN_RUNNING, RUN_FAILED):
        return False
    if not run.session_id or not run.data_dir:
        return False
    # Failed runs often have the source cleaned; resume needs the checkout.
    if not session_workspace_exists(run) or not repo_source_present(run):
        return False
    return True


def auto_resume_marker_path(data_dir: str) -> str:
    return os.path.join(data_dir, AUTO_RESUME_MARKER)


def auto_resume_count(data_dir: str) -> int:
    path = auto_resume_marker_path(data_dir)
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return int(data.get("count") or 0)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return 0


def write_auto_resume_marker(data_dir: str, *, count: int = 1) -> None:
    path = auto_resume_marker_path(data_dir)
    os.makedirs(data_dir, exist_ok=True)
    payload: dict[str, Any] = {
        "count": count,
        "at": datetime.now(timezone.utc).isoformat(),
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def should_auto_resume(run: Run, *, durable_engine: bool, now: float | None = None) -> bool:
    if not durable_engine or run.status != RUN_RUNNING:
        return False
    if not session_workspace_exists(run):
        return False
    if auto_resume_count(run.data_dir) >= 1:
        return False
    idle = workflow_log_idle_seconds(run, now=now)
    return idle is not None and idle >= AUTO_RESUME_IDLE_SECONDS
