.PHONY: install dev lint typecheck test validate run clean

# ── Setup ──────────────────────────────────────────────────────
install:
	uv sync

dev:
	uv sync --extra dev

# ── Quality ───────────────────────────────────────────────────
lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

typecheck:
	uv run mypy src/

# ── Tests ─────────────────────────────────────────────────────
test:
	uv run pytest -v

test-coverage:
	uv run pytest --cov=src --cov-report=term-missing -v

# ── Knowledge Base ────────────────────────────────────────────
validate:
	uv run anticorrupt kb validate

search:
	@read -p "Search query: " q; uv run anticorrupt kb search "$$q"

stats:
	uv run anticorrupt kb stats

# ── Content Pipeline ──────────────────────────────────────────
scan:
	uv run anticorrupt news scan

review:
	uv run anticorrupt review list

dashboard:
	uv run anticorrupt dashboard

# ── Utilities ─────────────────────────────────────────────────
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete 2>/dev/null; true
	rm -rf .pytest_cache .ruff_cache .mypy_cache dist build

seed:
	uv run python scripts/seed_knowledge_base.py

export-graph:
	uv run python scripts/export_graph.py
