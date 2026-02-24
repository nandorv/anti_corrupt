"""
Knowledge base validator.
Validates all YAML files against their Pydantic schemas and runs cross-reference checks.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .loader import load_knowledge_base
from .models import (
    Event,
    GlossaryTerm,
    Institution,
    KnowledgeBase,
    PublicFigure,
    Relationship,
)


# ── Result types ──────────────────────────────────────────────────────────────

@dataclass
class ValidationResult:
    file: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.errors) == 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0


@dataclass
class ValidationReport:
    results: list[ValidationResult] = field(default_factory=list)

    @property
    def total_errors(self) -> int:
        return sum(len(r.errors) for r in self.results)

    @property
    def total_warnings(self) -> int:
        return sum(len(r.warnings) for r in self.results)

    @property
    def is_valid(self) -> bool:
        return self.total_errors == 0

    @property
    def files_with_errors(self) -> list[ValidationResult]:
        return [r for r in self.results if not r.is_valid]

    @property
    def files_with_warnings(self) -> list[ValidationResult]:
        return [r for r in self.results if r.has_warnings]

    @property
    def total_files_checked(self) -> int:
        return len(self.results)


# ── Validators ────────────────────────────────────────────────────────────────

_SUBDIR_MODEL_MAP: dict[str, Any] = {
    "institutions": Institution,
    "figures": PublicFigure,
    "events": Event,
    "glossary": GlossaryTerm,
}


def _load_yaml_safe(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _validate_file(path: Path, subdir: str, data_dir: Path) -> ValidationResult:
    """Validate a single YAML file against its Pydantic model."""
    rel_path = str(path.relative_to(data_dir))
    result = ValidationResult(file=rel_path)

    try:
        raw = _load_yaml_safe(path)
    except yaml.YAMLError as e:
        result.errors.append(f"YAML parse error: {e}")
        return result

    try:
        if subdir == "relationships":
            if isinstance(raw, list):
                for i, item in enumerate(raw):
                    Relationship.model_validate(item)
            elif isinstance(raw, dict) and "relationships" in raw:
                for i, item in enumerate(raw["relationships"]):
                    Relationship.model_validate(item)
            else:
                Relationship.model_validate(raw)
        elif subdir == "glossary":
            if isinstance(raw, dict) and "terms" in raw:
                for i, item in enumerate(raw["terms"]):
                    GlossaryTerm.model_validate(item)
            elif isinstance(raw, list):
                for i, item in enumerate(raw):
                    GlossaryTerm.model_validate(item)
            else:
                GlossaryTerm.model_validate(raw)
        else:
            model_class = _SUBDIR_MODEL_MAP[subdir]
            model_class.model_validate(raw)

    except ValidationError as e:
        for error in e.errors():
            loc = " → ".join(str(x) for x in error["loc"])
            result.errors.append(f"[{loc}] {error['msg']}")
    except Exception as e:
        result.errors.append(f"Unexpected error: {e}")

    return result


def _check_cross_references(kb: KnowledgeBase) -> ValidationResult:
    """Cross-reference check: verify that all IDs referenced in relationships exist."""
    result = ValidationResult(file="<cross-reference checks>")

    for rel in kb.relationships:
        src_type = rel.source_type.value
        tgt_type = rel.target_type.value

        if src_type == "institution" and rel.source_id not in kb.institutions:
            result.warnings.append(
                f"Relationship '{rel.id}': source institution '{rel.source_id}' not in knowledge base"
            )
        if tgt_type == "institution" and rel.target_id not in kb.institutions:
            result.warnings.append(
                f"Relationship '{rel.id}': target institution '{rel.target_id}' not in knowledge base"
            )
        if src_type == "figure" and rel.source_id not in kb.figures:
            result.warnings.append(
                f"Relationship '{rel.id}': source figure '{rel.source_id}' not in knowledge base"
            )
        if tgt_type == "figure" and rel.target_id not in kb.figures:
            result.warnings.append(
                f"Relationship '{rel.id}': target figure '{rel.target_id}' not in knowledge base"
            )
        if src_type == "event" and rel.source_id not in kb.events:
            result.warnings.append(
                f"Relationship '{rel.id}': source event '{rel.source_id}' not in knowledge base"
            )
        if tgt_type == "event" and rel.target_id not in kb.events:
            result.warnings.append(
                f"Relationship '{rel.id}': target event '{rel.target_id}' not in knowledge base"
            )

    # Check event cause/consequence references
    for event_id, event in kb.events.items():
        for cause_id in event.causes:
            if cause_id not in kb.events:
                result.warnings.append(
                    f"Event '{event_id}': cause '{cause_id}' not found in events"
                )
        for cons_id in event.consequences:
            if cons_id not in kb.events:
                result.warnings.append(
                    f"Event '{event_id}': consequence '{cons_id}' not found in events"
                )

    return result


def validate_knowledge_base(data_dir: Path) -> ValidationReport:
    """
    Validate the entire knowledge base.
    1. Validates each YAML file against its Pydantic model (schema check)
    2. Runs cross-reference checks across all entities
    """
    report = ValidationReport()

    # Step 1: Schema validation per file
    subdirs = ["institutions", "figures", "events", "relationships", "glossary"]
    for subdir in subdirs:
        dir_path = data_dir / subdir
        if not dir_path.exists():
            report.results.append(
                ValidationResult(
                    file=f"{subdir}/",
                    warnings=[f"Directory '{subdir}/' does not exist — skipping"],
                )
            )
            continue
        for path in sorted(dir_path.glob("*.yaml")):
            if path.name.startswith("_"):
                continue
            result = _validate_file(path, subdir, data_dir)
            report.results.append(result)

    # Step 2: Cross-reference check
    try:
        kb = load_knowledge_base(data_dir)
        xref_result = _check_cross_references(kb)
        report.results.append(xref_result)
    except Exception as e:
        report.results.append(
            ValidationResult(
                file="<cross-reference>",
                errors=[f"Failed to run cross-reference checks: {e}"],
            )
        )

    return report
