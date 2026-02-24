"""Shared test fixtures."""

import pytest
from pathlib import Path


@pytest.fixture
def data_dir() -> Path:
    """Return the path to the seed data directory."""
    return Path(__file__).parent.parent / "data"


@pytest.fixture
def tests_dir() -> Path:
    """Return the path to the tests directory."""
    return Path(__file__).parent
