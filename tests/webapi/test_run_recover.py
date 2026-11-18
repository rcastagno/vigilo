"""Stall helpers + resume eligibility / API."""
from __future__ import annotations

import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select

from src.webapi.engine.provider import get_engine
from src.webapi.models import (
    RUN_FAILED,
    RUN_RUNNING,
    RUN_SUCCEEDED,
    Job,
    Repository,
    Run,
    User,
)
from src.webapi.run_recover import (
    AUTO_RESUME_IDLE_SECONDS,
    STALL_HINT_SECONDS,
    auto_resume_count,
    is_recoverable,
    is_stalled,
    should_auto_resume,
    workflow_log_idle_seconds,
    write_auto_resume_marker,
)
from src.webapi.settings import get_settings


def _run(tmp_path: Path, *, status: str = RUN_RUNNING, session_id: str = "web-abc") -> Run:
    data_dir = tmp_path / "job"
    repo = data_dir / "repo"
    ws = repo / ".vigilo" / session_id
    ws.mkdir(parents=True)
    (ws / "session.json").write_text('{"session":{"id":"web-abc"}}', encoding="utf-8")
    (repo / "README.md").write_text("src\n", encoding="utf-8")
    return Run(
        id=uuid.uuid4(),
        job_id=uuid.uuid4(),
        status=status,
        session_id=session_id,
        data_dir=str(data_dir),
        trigger_type="manual",
        created_at=datetime.now(timezone.utc),
    )


class TestStallHelpers:
    def test_idle_and_stalled(self, tmp_path: Path):
        run = _run(tmp_path)
        log = Path(run.data_dir) / "repo" / ".vigilo" / run.session_id / "workflow.log"
        log.write_text("hi\n", encoding="utf-8")
        old = time.time() - (STALL_HINT_SECONDS + 30)
        os.utime(log, (old, old))
        idle = workflow_log_idle_seconds(run)
        assert idle is not None and idle >= STALL_HINT_SECONDS
        assert is_stalled(run) is True

    def test_not_stalled_when_fresh(self, tmp_path: Path):
        run = _run(tmp_path)
        log = Path(run.data_dir) / "repo" / ".vigilo" / run.session_id / "workflow.log"
        log.write_text("hi\n", encoding="utf-8")
        assert is_stalled(run) is False

    def test_recoverable_running_with_workspace(self, tmp_path: Path):
        run = _run(tmp_path, status=RUN_RUNNING)
        assert is_recoverable(run, durable_engine=True) is True
        assert is_recoverable(run, durable_engine=False) is False

    def test_recoverable_failed_with_workspace(self, tmp_path: Path):
        run = _run(tmp_path, status=RUN_FAILED)
        assert is_recoverable(run, durable_engine=True) is True

    def test_not_recoverable_succeeded(self, tmp_path: Path):
        run = _run(tmp_path, status=RUN_SUCCEEDED)
        assert is_recoverable(run, durable_engine=True) is False

    def test_auto_resume_gate(self, tmp_path: Path):
        run = _run(tmp_path)
        log = Path(run.data_dir) / "repo" / ".vigilo" / run.session_id / "workflow.log"
        log.write_text("x\n", encoding="utf-8")
        old = time.time() - (AUTO_RESUME_IDLE_SECONDS + 10)
        os.utime(log, (old, old))
        assert should_auto_resume(run, durable_engine=True) is True
        write_auto_resume_marker(run.data_dir, count=1)
        assert auto_resume_count(run.data_dir) == 1
        assert should_auto_resume(run, durable_engine=True) is False


class _ResumeEngine:
    durable = True

    def __init__(self) -> None:
        self.resumed: list[str] = []

    async def start(self, run, job, repo):
        raise AssertionError("start not used")

    async def cancel(self, run):
        raise AssertionError("cancel not used")

    async def refresh(self, run):
        return None

    async def resume(self, run, job, repo):
        self.resumed.append(str(run.id))
        run.workflow_id = f"{run.session_id}_resume_test"
        run.status = RUN_RUNNING
        run.error_summary = None
        run.finished_at = None
        run.current_phase = "preflight"


async def _seed_recoverable_run(session_maker, *, status: str = RUN_RUNNING) -> tuple[uuid.UUID, str]:
    settings = get_settings()
    async with session_maker() as s:
        user = (await s.scalars(select(User))).first()
        assert user is not None
        repo = Repository(
            name="r",
            source_type="upload",
            created_by=user.id,
            is_private=False,
            pipeline_config={},
            scan_config={},
        )
        s.add(repo)
        await s.flush()
        job = Job(
            name="j",
            repository_id=repo.id,
            stage_preset="vuln",
            engine="whitebox",
            created_by=user.id,
            pipeline_overrides={},
        )
        s.add(job)
        await s.flush()
        run_id = uuid.uuid4()
        session_id = f"web-{run_id.hex[:12]}"
        data_dir = os.path.join(settings.jobs_data_dir, str(run_id))
        repo = Path(data_dir) / "repo"
        ws = repo / ".vigilo" / session_id
        ws.mkdir(parents=True, exist_ok=True)
        (ws / "session.json").write_text('{"session":{}}', encoding="utf-8")
        (repo / "README.md").write_text("src\n", encoding="utf-8")
        run = Run(
            id=run_id,
            job_id=job.id,
            triggered_by=user.id,
            trigger_type="manual",
            status=status,
            session_id=session_id,
            workflow_id=session_id,
            data_dir=data_dir,
            current_phase="critique",
        )
        s.add(run)
        await s.commit()
    return run_id, session_id


class TestResumeEndpoint:
    async def test_resume_ok(self, client, user_token, session_maker):
        engine = _ResumeEngine()
        client._app.dependency_overrides[get_engine] = lambda: engine
        h = {"Authorization": f"Bearer {user_token}"}
        run_id, session_id = await _seed_recoverable_run(session_maker)

        r = await client.post(f"/runs/{run_id}/resume", headers=h)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["status"] == "running"
        assert body["workflow_id"] == f"{session_id}_resume_test"
        assert body["recoverable"] is True
        assert engine.resumed == [str(run_id)]

        client._app.dependency_overrides.pop(get_engine, None)

    async def test_resume_rejected_when_succeeded(self, client, user_token, session_maker):
        engine = _ResumeEngine()
        client._app.dependency_overrides[get_engine] = lambda: engine
        h = {"Authorization": f"Bearer {user_token}"}
        run_id, _ = await _seed_recoverable_run(session_maker, status=RUN_SUCCEEDED)
        bad = await client.post(f"/runs/{run_id}/resume", headers=h)
        assert bad.status_code == 400
        assert engine.resumed == []
        client._app.dependency_overrides.pop(get_engine, None)
