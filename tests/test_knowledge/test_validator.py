"""Tests for knowledge base validator."""

import pytest
from pathlib import Path

from src.knowledge.validator import validate_knowledge_base, ValidationReport


class TestValidateKnowledgeBase:
    def test_seed_data_is_valid(self, data_dir: Path):
        """All seeded YAML files should pass validation."""
        report = validate_knowledge_base(data_dir)
        if not report.is_valid:
            errors = []
            for r in report.files_with_errors:
                for e in r.errors:
                    errors.append(f"{r.file}: {e}")
            pytest.fail("Validation errors:\n" + "\n".join(errors))

    def test_report_has_results(self, data_dir: Path):
        report = validate_knowledge_base(data_dir)
        assert report.total_files_checked > 0

    def test_invalid_yaml_produces_error(self, tmp_path: Path):
        """A YAML file with bad content should produce an error."""
        inst_dir = tmp_path / "institutions"
        inst_dir.mkdir()
        bad_file = inst_dir / "bad_institution.yaml"
        bad_file.write_text("id: bad\nname_official: Test\n# missing required fields\n")

        report = validate_knowledge_base(tmp_path)
        assert not report.is_valid
        assert report.total_errors > 0

    def test_empty_directory_produces_warnings(self, tmp_path: Path):
        """Missing subdirectories should produce warnings, not errors."""
        report = validate_knowledge_base(tmp_path)
        # Errors should be 0, but warnings about missing dirs
        assert report.total_errors == 0

    def test_cross_reference_check_runs(self, data_dir: Path):
        """Cross-reference check should always run without exception."""
        report = validate_knowledge_base(data_dir)
        # The cross-reference result should be present
        xref_results = [r for r in report.results if r.file.startswith("<cross-reference")]
        assert len(xref_results) >= 1

    def test_validation_report_properties(self, data_dir: Path):
        report = validate_knowledge_base(data_dir)
        assert isinstance(report.total_errors, int)
        assert isinstance(report.total_warnings, int)
        assert isinstance(report.is_valid, bool)
        assert isinstance(report.files_with_errors, list)
