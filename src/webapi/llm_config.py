"""Resolve merged LLM config for a platform run (repo → job → worker env)."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from src.ai.llm_run_config import merge_llm_layers
from src.webapi.models import Job, Repository


async def resolve_merged_llm_config(
    session: AsyncSession,
    repo: Repository | None,
    job: Job | None,
) -> dict[str, str]:
    """Merge repository then job LLM overrides for a run.

    Only **explicit** per-repo / per-job keys are included. Worker process env
    (``.env`` / compose) remains the runtime fallback for unset keys.

    AdminConfig is intentionally not merged here: it is always seeded with
    Claude defaults on first boot, which would otherwise override a Codex /
    OpenCode / LiteLLM worker whenever a job left executor/models blank.
    """
    _ = session  # reserved for future admin/policy lookups
    return merge_llm_layers(
        (repo.pipeline_config if repo else None),
        (job.pipeline_overrides if job else None),
    )
