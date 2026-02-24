"""Jinja2-based prompt template loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, StrictUndefined


class PromptTemplate:
    """A loaded prompt template with rendered system + user messages."""

    def __init__(self, raw: dict, template_path: Path) -> None:
        self._raw = raw
        self.path = template_path
        self.name: str = raw["name"]
        self.version: str = str(raw.get("version", "1.0"))
        self.model: str = raw.get("model", "claude-sonnet-4-20250514")
        self.max_tokens: int = int(raw.get("max_tokens", 1024))
        self.temperature: float = float(raw.get("temperature", 0.3))
        self._system_tpl = raw["system"]
        self._user_tpl = raw["user_template"]
        self._jinja = Environment(undefined=StrictUndefined, autoescape=False)

    def render(self, **kwargs: Any) -> tuple[str, str]:
        """Return (system_prompt, user_prompt) with variables substituted."""
        system = self._jinja.from_string(self._system_tpl).render(**kwargs)
        user = self._jinja.from_string(self._user_tpl).render(**kwargs)
        return system.strip(), user.strip()


class PromptLoader:
    """Loads all YAML prompt templates from the prompts directory."""

    def __init__(self, prompts_dir: Path) -> None:
        self.prompts_dir = prompts_dir
        self._cache: dict[str, PromptTemplate] = {}

    def load(self, name: str) -> PromptTemplate:
        """Load a template by name (without .yaml suffix)."""
        if name in self._cache:
            return self._cache[name]

        path = self.prompts_dir / f"{name}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"Prompt template not found: {path}")

        with path.open("r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)

        tpl = PromptTemplate(raw, path)
        self._cache[name] = tpl
        return tpl

    def load_all(self) -> dict[str, PromptTemplate]:
        """Load every .yaml file in the prompts directory."""
        for yaml_path in self.prompts_dir.glob("*.yaml"):
            name = yaml_path.stem
            if name not in self._cache:
                self.load(name)
        return dict(self._cache)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------


def _default_loader() -> PromptLoader:
    from config.settings import settings  # noqa: PLC0415

    return PromptLoader(settings.prompts_dir)


_loader: PromptLoader | None = None


def get_prompt(name: str) -> PromptTemplate:
    """Load a prompt template by name (uses module-level singleton loader)."""
    global _loader
    if _loader is None:
        _loader = _default_loader()
    return _loader.load(name)
