"""Tests for src/ai/prompts.py — Jinja2 prompt template loader."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.ai.prompts import PromptLoader, PromptTemplate


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_template(tmp_path: Path, name: str, content: dict) -> Path:
    """Write a prompt YAML to a tmp directory and return its path."""
    path = tmp_path / f"{name}.yaml"
    path.write_text(yaml.dump(content, allow_unicode=True))
    return path


MINIMAL_TEMPLATE = {
    "name": "test_prompt",
    "version": "1.0",
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 512,
    "temperature": 0.3,
    "system": "Você é um assistente de {{ role }}.",
    "user_template": "Explique {{ topic }} em {{ lang }}.",
}

MULTI_VAR_TEMPLATE = {
    "name": "multi_vars",
    "version": "1.0",
    "model": "mock",
    "max_tokens": 256,
    "temperature": 0.0,
    "system": "Sistema: {{ context }}",
    "user_template": "Usuário: {{ query }} — limite: {{ limit }} palavras",
}


# ---------------------------------------------------------------------------
# PromptTemplate
# ---------------------------------------------------------------------------


class TestPromptTemplate:
    """Unit tests for PromptTemplate.render()."""

    def test_render_returns_tuple_of_strings(self, tmp_path: Path):
        _write_template(tmp_path, "test_prompt", MINIMAL_TEMPLATE)
        loader = PromptLoader(tmp_path)
        tpl = loader.load("test_prompt")
        system, user = tpl.render(role="jornalismo", topic="corrupção", lang="português")
        assert isinstance(system, str)
        assert isinstance(user, str)

    def test_render_substitutes_system_variable(self, tmp_path: Path):
        _write_template(tmp_path, "test_prompt", MINIMAL_TEMPLATE)
        loader = PromptLoader(tmp_path)
        tpl = loader.load("test_prompt")
        system, _ = tpl.render(role="política", topic="STF", lang="pt-BR")
        assert "política" in system

    def test_render_substitutes_user_variable(self, tmp_path: Path):
        _write_template(tmp_path, "test_prompt", MINIMAL_TEMPLATE)
        loader = PromptLoader(tmp_path)
        tpl = loader.load("test_prompt")
        _, user = tpl.render(role="x", topic="Lava Jato", lang="pt-BR")
        assert "Lava Jato" in user
        assert "pt-BR" in user

    def test_render_raises_on_missing_variable(self, tmp_path: Path):
        _write_template(tmp_path, "test_prompt", MINIMAL_TEMPLATE)
        loader = PromptLoader(tmp_path)
        tpl = loader.load("test_prompt")
        with pytest.raises(Exception):  # jinja2.UndefinedError
            tpl.render(role="x")  # missing 'topic' and 'lang'

    def test_template_metadata_stored(self, tmp_path: Path):
        _write_template(tmp_path, "test_prompt", MINIMAL_TEMPLATE)
        loader = PromptLoader(tmp_path)
        tpl = loader.load("test_prompt")
        assert tpl.name == "test_prompt"
        assert tpl.version == "1.0"
        assert tpl.max_tokens == 512
        assert tpl.temperature == 0.3
        assert tpl.model == "claude-sonnet-4-20250514"

    def test_render_strips_whitespace(self, tmp_path: Path):
        template = dict(MINIMAL_TEMPLATE)
        template["system"] = "\n  Sistema de teste  \n"
        template["user_template"] = "\n  Usuário {{ q }}  \n"
        _write_template(tmp_path, "ws_test", template)
        loader = PromptLoader(tmp_path)
        tpl = loader.load("ws_test")
        system, user = tpl.render(q="question")
        assert not system.startswith(" ")
        assert not user.endswith(" ")

    def test_render_multiple_variables(self, tmp_path: Path):
        _write_template(tmp_path, "multi_vars", MULTI_VAR_TEMPLATE)
        loader = PromptLoader(tmp_path)
        tpl = loader.load("multi_vars")
        system, user = tpl.render(context="Brazil politics", query="STF ruling", limit=200)
        assert "Brazil politics" in system
        assert "STF ruling" in user
        assert "200" in user


# ---------------------------------------------------------------------------
# PromptLoader
# ---------------------------------------------------------------------------


class TestPromptLoader:
    """Unit tests for PromptLoader."""

    def test_load_returns_prompt_template(self, tmp_path: Path):
        _write_template(tmp_path, "my_prompt", MINIMAL_TEMPLATE)
        loader = PromptLoader(tmp_path)
        tpl = loader.load("my_prompt")
        assert isinstance(tpl, PromptTemplate)

    def test_load_caches_template(self, tmp_path: Path):
        _write_template(tmp_path, "cached_prompt", MINIMAL_TEMPLATE)
        loader = PromptLoader(tmp_path)
        tpl1 = loader.load("cached_prompt")
        tpl2 = loader.load("cached_prompt")
        assert tpl1 is tpl2  # same object from cache

    def test_load_nonexistent_raises_file_not_found(self, tmp_path: Path):
        loader = PromptLoader(tmp_path)
        with pytest.raises(FileNotFoundError):
            loader.load("no_such_template")

    def test_load_all_returns_dict(self, tmp_path: Path):
        _write_template(tmp_path, "alpha", MINIMAL_TEMPLATE)
        _write_template(tmp_path, "beta", MULTI_VAR_TEMPLATE)
        loader = PromptLoader(tmp_path)
        all_tpls = loader.load_all()
        assert "alpha" in all_tpls
        assert "beta" in all_tpls
        assert len(all_tpls) == 2

    def test_load_all_caches_all_templates(self, tmp_path: Path):
        _write_template(tmp_path, "one", MINIMAL_TEMPLATE)
        loader = PromptLoader(tmp_path)
        loader.load_all()
        # After load_all, loading by name should hit cache
        tpl = loader.load("one")
        assert isinstance(tpl, PromptTemplate)


# ---------------------------------------------------------------------------
# Real prompt templates on disk
# ---------------------------------------------------------------------------


class TestRealPromptTemplates:
    """Smoke tests against the actual YAML templates in config/prompts/."""

    @pytest.fixture
    def prompts_dir(self) -> Path:
        return Path(__file__).parent.parent.parent / "config" / "prompts"

    def test_prompts_dir_exists(self, prompts_dir: Path):
        assert prompts_dir.exists(), f"Prompts dir not found: {prompts_dir}"

    def test_summarize_news_loadable(self, prompts_dir: Path):
        loader = PromptLoader(prompts_dir)
        tpl = loader.load("summarize_news")
        assert tpl.name == "summarize_news"

    def test_explain_institution_loadable(self, prompts_dir: Path):
        loader = PromptLoader(prompts_dir)
        tpl = loader.load("explain_institution")
        assert tpl.name == "explain_institution"

    def test_generate_profile_loadable(self, prompts_dir: Path):
        loader = PromptLoader(prompts_dir)
        tpl = loader.load("generate_profile")
        assert tpl.name == "generate_profile"

    def test_generate_timeline_loadable(self, prompts_dir: Path):
        loader = PromptLoader(prompts_dir)
        tpl = loader.load("generate_timeline")
        assert tpl.name == "generate_timeline"
