"""Per-run pipeline/LLM config merge and env mapping (concurrency-safe).

Logical keys: executor, model_small/medium/large, max_concurrent_pipelines.
Merge later layers over earlier ones; blank values are skipped.
Worker process env remains the fallback for unset model/executor keys.
``max_concurrent_pipelines`` is applied via Temporal workflow input (not env).
"""
from __future__ import annotations

from typing import Any, Mapping

CONFIG_KEYS = frozenset({
    "executor",
    "model_small",
    "model_medium",
    "model_large",
    "max_concurrent_pipelines",
})
VALID_EXECUTORS = frozenset({"claude", "codex", "opencode"})
DEFAULT_MAX_CONCURRENT_PIPELINES = 8

_TIER_TO_KEY = {
    "small": "model_small",
    "medium": "model_medium",
    "large": "model_large",
}

_ENV_BY_EXECUTOR: dict[str, dict[str, str]] = {
    "claude": {
        "model_small": "ANTHROPIC_SMALL_MODEL",
        "model_medium": "ANTHROPIC_MEDIUM_MODEL",
        "model_large": "ANTHROPIC_LARGE_MODEL",
    },
    "codex": {
        "model_small": "CODEX_SMALL_MODEL",
        "model_medium": "CODEX_MEDIUM_MODEL",
        "model_large": "CODEX_LARGE_MODEL",
    },
    "opencode": {
        "model_small": "OPENCODE_SMALL_MODEL",
        "model_medium": "OPENCODE_MEDIUM_MODEL",
        "model_large": "OPENCODE_LARGE_MODEL",
    },
}


def _clean_value(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_max_concurrent(raw: Any) -> str | None:
    """Accept positive ints (or digit strings); reject invalid values."""
    value = _clean_value(raw)
    if value is None:
        return None
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    if n < 1:
        return None
    return str(n)


def merge_llm_layers(*layers: Mapping[str, Any] | None) -> dict[str, str]:
    """Shallow merge of pipeline/LLM config dicts. Later layers win; blank skipped."""
    out: dict[str, str] = {}
    for layer in layers:
        if not layer:
            continue
        for key, raw in layer.items():
            if key not in CONFIG_KEYS:
                continue
            if key == "max_concurrent_pipelines":
                value = _normalize_max_concurrent(raw)
                if value is None:
                    continue
                out[key] = value
                continue
            value = _clean_value(raw)
            if value is None:
                continue
            if key == "executor":
                value = value.lower()
                if value not in VALID_EXECUTORS:
                    continue
            out[key] = value
    return out


def workflow_pipeline_config(merged: Mapping[str, str] | None) -> dict[str, Any]:
    """Build Temporal ``pipeline_config`` from merged run overrides.

    Only includes keys the workflow understands today (concurrency). Empty when
    the operator left the field blank (workflow keeps its default of 8).
    """
    if not merged:
        return {}
    raw = merged.get("max_concurrent_pipelines")
    if not raw:
        return {}
    try:
        n = int(raw)
    except (TypeError, ValueError):
        return {}
    if n < 1:
        return {}
    return {"max_concurrent_pipelines": n}


def effective_executor(merged: Mapping[str, str] | None) -> str:
    """Executor from merged config, else env / auto-detect via get_executor_type."""
    if merged:
        exe = _clean_value(merged.get("executor"))
        if exe and exe.lower() in VALID_EXECUTORS:
            return exe.lower()
    from src.ai.executor import get_executor_type

    return get_executor_type()


def resolve_model_for_tier(tier: str, merged: Mapping[str, str] | None = None) -> str:
    """Resolve a tier (or concrete model id) using merged config then backend env.

    If *tier* is not small/medium/large, it is treated as a concrete model id
    (with OpenCode ``litellm/`` prefix when that executor is active).
    """
    executor = effective_executor(merged)
    key = _TIER_TO_KEY.get(tier)

    if key is None:
        # Concrete model identifier — OpenCode needs litellm/ prefix.
        if executor == "opencode":
            from src.ai.opencode_executor import LITELLM_PROVIDER_PREFIX

            if tier.startswith(f"{LITELLM_PROVIDER_PREFIX}/"):
                return tier
            return f"{LITELLM_PROVIDER_PREFIX}/{tier}"
        return tier

    if merged:
        override = _clean_value(merged.get(key))
        if override:
            if executor == "opencode":
                from src.ai.opencode_executor import LITELLM_PROVIDER_PREFIX

                if override.startswith(f"{LITELLM_PROVIDER_PREFIX}/"):
                    return override
                return f"{LITELLM_PROVIDER_PREFIX}/{override}"
            return override

    if executor == "opencode":
        from src.ai.opencode_executor import resolve_model as _resolve
    elif executor == "codex":
        from src.ai.codex_executor import resolve_model as _resolve
    else:
        from src.ai.claude_executor import resolve_model as _resolve
    return _resolve(tier)


def llm_config_to_env(merged: Mapping[str, str] | None) -> dict[str, str]:
    """Map logical LLM config to subprocess env vars for the effective executor."""
    if not merged:
        return {}
    cleaned = merge_llm_layers(merged)
    if not cleaned:
        return {}
    executor = effective_executor(cleaned)
    env: dict[str, str] = {}
    if "executor" in cleaned:
        env["VIGILO_EXECUTOR"] = executor
    model_map = _ENV_BY_EXECUTOR.get(executor, _ENV_BY_EXECUTOR["claude"])
    for logical, env_name in model_map.items():
        value = cleaned.get(logical)
        if value:
            env[env_name] = value
    return env


def admin_config_to_layer(admin: Any | None) -> dict[str, str]:
    """Build a merge layer from an AdminConfig ORM row (or None)."""
    if admin is None:
        return {}
    return merge_llm_layers({
        "executor": getattr(admin, "executor", None),
        "model_small": getattr(admin, "model_small", None),
        "model_medium": getattr(admin, "model_medium", None),
        "model_large": getattr(admin, "model_large", None),
    })
