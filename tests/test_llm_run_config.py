"""Tests for per-run LLM config merge and env mapping."""
from __future__ import annotations

from src.ai.llm_run_config import (
    llm_config_to_env,
    merge_llm_layers,
    resolve_model_for_tier,
    workflow_pipeline_config,
)


class TestMergeLlmLayers:
    def test_later_wins(self):
        merged = merge_llm_layers(
            {"model_large": "admin-model", "executor": "claude"},
            {"model_large": "repo-model"},
            {"model_large": "job-model"},
        )
        assert merged["model_large"] == "job-model"
        assert merged["executor"] == "claude"

    def test_blank_skipped(self):
        merged = merge_llm_layers(
            {"model_large": "admin"},
            {"model_large": "  "},
            {"model_medium": "flash"},
        )
        assert merged["model_large"] == "admin"
        assert merged["model_medium"] == "flash"

    def test_unknown_keys_ignored(self):
        merged = merge_llm_layers({"bogus": "x", "model_small": "s"})
        assert "bogus" not in merged
        assert merged["model_small"] == "s"

    def test_invalid_executor_skipped(self):
        merged = merge_llm_layers({"executor": "gpt-magic"})
        assert "executor" not in merged

    def test_max_concurrent_pipelines_normalized(self):
        merged = merge_llm_layers(
            {"max_concurrent_pipelines": "8"},
            {"max_concurrent_pipelines": 1},
        )
        assert merged["max_concurrent_pipelines"] == "1"

    def test_max_concurrent_invalid_skipped(self):
        merged = merge_llm_layers({"max_concurrent_pipelines": "0"})
        assert "max_concurrent_pipelines" not in merged
        merged = merge_llm_layers({"max_concurrent_pipelines": "nope"})
        assert "max_concurrent_pipelines" not in merged


class TestWorkflowPipelineConfig:
    def test_builds_int_for_workflow(self):
        assert workflow_pipeline_config(
            {"max_concurrent_pipelines": "1", "model_large": "x"}
        ) == {"max_concurrent_pipelines": 1}

    def test_empty_when_unset(self):
        assert workflow_pipeline_config({"executor": "codex"}) == {}
        assert workflow_pipeline_config(None) == {}


class TestLlmConfigToEnv:
    def test_codex_maps_code_x_env(self):
        env = llm_config_to_env({
            "executor": "codex",
            "model_large": "Qwen3.8-Flash-Next",
            "model_medium": "Qwen3.8-Flash-Next",
        })
        assert env["VIGILO_EXECUTOR"] == "codex"
        assert env["CODEX_LARGE_MODEL"] == "Qwen3.8-Flash-Next"
        assert env["CODEX_MEDIUM_MODEL"] == "Qwen3.8-Flash-Next"
        assert "ANTHROPIC_LARGE_MODEL" not in env

    def test_opencode_maps_opencode_env(self):
        env = llm_config_to_env({
            "executor": "opencode",
            "model_large": "Qwen3.8-Flash-Next",
        })
        assert env["VIGILO_EXECUTOR"] == "opencode"
        assert env["OPENCODE_LARGE_MODEL"] == "Qwen3.8-Flash-Next"

    def test_claude_maps_anthropic_env(self):
        env = llm_config_to_env({
            "executor": "claude",
            "model_small": "haiku",
        })
        assert env["ANTHROPIC_SMALL_MODEL"] == "haiku"

    def test_empty_returns_empty(self):
        assert llm_config_to_env(None) == {}
        assert llm_config_to_env({}) == {}

    def test_max_concurrent_not_mapped_to_env(self):
        env = llm_config_to_env({
            "executor": "codex",
            "max_concurrent_pipelines": "1",
            "model_large": "Flash",
        })
        assert env["CODEX_LARGE_MODEL"] == "Flash"
        assert "max_concurrent_pipelines" not in env


class TestResolveModelForTier:
    def test_merged_override_wins(self, monkeypatch):
        monkeypatch.setenv("CODEX_LARGE_MODEL", "from-env-27b")
        monkeypatch.setenv("VIGILO_EXECUTOR", "codex")
        assert resolve_model_for_tier(
            "large", {"executor": "codex", "model_large": "Qwen3.8-Flash-Next"}
        ) == "Qwen3.8-Flash-Next"

    def test_falls_back_to_env(self, monkeypatch):
        monkeypatch.setenv("CODEX_LARGE_MODEL", "from-env-27b")
        monkeypatch.setenv("VIGILO_EXECUTOR", "codex")
        for v in ("CODEX_SMALL_MODEL", "CODEX_MEDIUM_MODEL"):
            monkeypatch.delenv(v, raising=False)
        assert resolve_model_for_tier("large", {"executor": "codex"}) == "from-env-27b"

    def test_opencode_adds_litellm_prefix(self, monkeypatch):
        monkeypatch.setenv("VIGILO_EXECUTOR", "opencode")
        assert resolve_model_for_tier(
            "large", {"executor": "opencode", "model_large": "Qwen3.8-Flash-Next"}
        ) == "litellm/Qwen3.8-Flash-Next"
