# AI-Assisted Political & Institutional Explainer Platform

## Complete Project Plan & Technical Blueprint

**Version:** 1.0
**Date:** February 23, 2026
**Status:** Planning
**Primary Language:** Python 3.11+
**Target Region:** Brazil (Phase 1)

---

## Table of Contents

1. [Project Architecture](#1-project-architecture)
2. [Knowledge Base Design](#2-knowledge-base-design)
3. [Technology Stack (Detailed)](#3-technology-stack-detailed)
4. [Phase 0 — Foundation](#4-phase-0--foundation)
5. [Phase 1 — Content Pipeline](#5-phase-1--content-pipeline)
6. [Phase 2 — Visual Generation](#6-phase-2--visual-generation)
7. [Phase 3 — Publishing & Automation](#7-phase-3--publishing--automation)
8. [Phase 4 — Web Platform](#8-phase-4--web-platform)
9. [Phase 5 — Scale & Monetize](#9-phase-5--scale--monetize)
10. [Infrastructure & DevOps](#10-infrastructure--devops)
11. [Editorial Workflow](#11-editorial-workflow)
12. [Legal & Ethical Guardrails](#12-legal--ethical-guardrails)
13. [Cost Estimates](#13-cost-estimates)
14. [Risk Register](#14-risk-register)

---

## 1. Project Architecture

### 1.1 Monorepo Structure

```
anti_corrupt/
│
├── PROJECT_PLAN.md                 # This document
├── pyproject.toml                  # Python project config (dependencies, build)
├── .env.example                    # Template for environment variables
├── .gitignore
├── Makefile                        # Common commands (run, test, lint, build)
│
├── config/                         # Global configuration
│   ├── settings.py                 # App settings (paths, API keys via env)
│   ├── editorial_rules.yaml        # Tone, style, and content guidelines
│   ├── prompts/                    # LLM prompt templates
│   │   ├── summarize_news.yaml
│   │   ├── explain_institution.yaml
│   │   ├── generate_profile.yaml
│   │   ├── generate_timeline.yaml
│   │   └── relationship_mapping.yaml
│   └── style/                      # Visual style definitions
│       ├── colors.yaml             # Color palette per institution/theme
│       ├── fonts.yaml              # Typography rules
│       └── templates.yaml          # Template metadata
│
├── data/                           # Structured knowledge base (version-controlled)
│   ├── institutions/               # One YAML file per institution
│   │   ├── _schema.yaml            # Schema definition
│   │   ├── supremo_tribunal_federal.yaml
│   │   ├── congresso_nacional.yaml
│   │   ├── senado_federal.yaml
│   │   ├── camara_deputados.yaml
│   │   ├── tribunal_superior_eleitoral.yaml
│   │   ├── ministerio_publico_federal.yaml
│   │   └── ...
│   ├── figures/                    # One YAML file per public figure
│   │   ├── _schema.yaml
│   │   └── ...
│   ├── events/                     # Historical events and timelines
│   │   ├── _schema.yaml
│   │   └── ...
│   ├── relationships/              # Graph edges connecting entities
│   │   ├── _schema.yaml
│   │   └── ...
│   └── glossary/                   # Political/legal terms explained
│       ├── _schema.yaml
│       └── terms.yaml
│
├── src/                            # Main application source code
│   ├── __init__.py
│   │
│   ├── knowledge/                  # Knowledge base management
│   │   ├── __init__.py
│   │   ├── models.py              # Pydantic models for all entities
│   │   ├── loader.py              # Load YAML → Python objects
│   │   ├── validator.py           # Validate data against schemas
│   │   ├── graph.py               # Build and query relationship graph
│   │   └── search.py             # Search across knowledge base
│   │
│   ├── sources/                    # News & data ingestion
│   │   ├── __init__.py
│   │   ├── rss.py                 # RSS feed aggregator
│   │   ├── newsapi.py             # NewsAPI integration
│   │   ├── scraper.py             # Web scraper for specific sources
│   │   ├── official.py            # Government gazette / official sources
│   │   └── aggregator.py         # Combine and deduplicate sources
│   │
│   ├── ai/                         # AI processing layer
│   │   ├── __init__.py
│   │   ├── client.py              # LLM client (Claude/OpenAI abstraction)
│   │   ├── summarizer.py          # News summarization
│   │   ├── explainer.py           # Institutional explanations
│   │   ├── profiler.py            # Public figure profile generator
│   │   ├── timeline_gen.py        # Timeline narrative generator
│   │   ├── relationship_mapper.py # Relationship analysis
│   │   ├── translator.py         # PT ↔ EN translation
│   │   └── fact_checker.py       # Cross-reference claims with sources
│   │
│   ├── content/                    # Content management
│   │   ├── __init__.py
│   │   ├── models.py             # Content piece models (draft, review, published)
│   │   ├── queue.py              # Review queue management
│   │   ├── storage.py            # Save/load content drafts
│   │   └── formatter.py          # Format content for different platforms
│   │
│   ├── visuals/                    # Programmatic visual generation
│   │   ├── __init__.py
│   │   ├── renderer.py           # Base renderer (SVG/PNG output)
│   │   ├── carousel.py           # Instagram carousel generator
│   │   ├── diagrams.py           # Flowcharts and institutional diagrams
│   │   ├── timelines.py          # Visual timeline renderer
│   │   ├── network.py            # Network/relationship graph visuals
│   │   ├── profiles.py           # Profile card generator
│   │   └── templates/            # SVG/HTML templates
│   │       ├── carousel_slide.svg
│   │       ├── timeline_horizontal.svg
│   │       ├── profile_card.svg
│   │       └── diagram_base.svg
│   │
│   ├── publish/                    # Publishing to platforms
│   │   ├── __init__.py
│   │   ├── instagram.py          # Instagram Graph API
│   │   ├── twitter.py            # X/Twitter API v2
│   │   ├── scheduler.py          # Schedule posts
│   │   └── analytics.py          # Track post performance
│   │
│   └── cli/                        # Command-line interface
│       ├── __init__.py
│       ├── main.py               # CLI entry point (Typer/Click)
│       ├── review.py             # Review queue commands
│       ├── generate.py           # Content generation commands
│       ├── publish.py            # Publishing commands
│       ├── knowledge.py          # Knowledge base commands
│       └── dashboard.py          # Quick stats and overview
│
├── web/                            # Future web platform (Phase 4)
│   └── (placeholder)
│
├── tests/                          # Test suite
│   ├── __init__.py
│   ├── test_knowledge/
│   ├── test_sources/
│   ├── test_ai/
│   ├── test_content/
│   ├── test_visuals/
│   └── test_publish/
│
├── scripts/                        # Utility scripts
│   ├── seed_knowledge_base.py     # Populate initial data
│   ├── validate_all_data.py       # Validate entire knowledge base
│   └── export_graph.py           # Export relationship graph
│
└── output/                         # Generated content (gitignored)
    ├── drafts/                    # AI-generated drafts awaiting review
    ├── approved/                  # Human-approved content
    ├── images/                    # Generated images
    └── published/                 # Published content archive
```

### 1.2 Design Principles

| Principle | Description |
|---|---|
| **Data as Code** | All knowledge lives in YAML files under version control. Every edit is traceable via git history. |
| **AI as Tool, Human as Editor** | AI generates drafts; humans approve. No content goes live without human sign-off. |
| **Schema-First** | Every data type has a Pydantic model and YAML schema. Validation is automated. |
| **Pipeline Thinking** | Content flows: Source → AI → Draft → Review → Approve → Format → Publish |
| **Reproducibility** | Any piece of content can be regenerated from the same inputs + prompt. |
| **Platform Agnostic** | Content is created once in a canonical format, then adapted per platform. |

---

## 2. Knowledge Base Design

### 2.1 Entity Types

The knowledge base models 5 core entity types that map directly to the content pillars:

#### Institution

```yaml
# data/institutions/_schema.yaml
institution:
  id: string                    # Unique slug (e.g., "stf")
  name_official: string         # Full official name
  name_common: string           # How people refer to it
  acronym: string               # e.g., "STF", "TSE"
  type: enum                    # executive | legislative | judicial | independent | military
  jurisdiction: string          # Federal, State, Municipal
  established: date
  constitutional_basis: string  # Article/section of constitution
  description: string           # 2-3 sentence plain-language summary
  key_functions:
    - string                    # List of main responsibilities
  composition:
    total_members: int
    how_appointed: string
    term_length: string
  current_leadership:
    - name: string
      role: string
      since: date
  hierarchy:
    parent: institution_id | null
    children: [institution_id]
  related_institutions: [institution_id]
  tags: [string]
  sources: [url]
  last_updated: datetime
```

#### Public Figure

```yaml
# data/figures/_schema.yaml
figure:
  id: string                    # Unique slug
  full_name: string
  birth_date: date
  birth_place: string
  education:
    - institution: string
      degree: string
      year: int
  career:                       # Chronological
    - role: string
      institution: string
      start_date: date
      end_date: date | null     # null = current
      description: string
  party_affiliations:
    - party: string
      start: date
      end: date | null
  key_decisions: [event_id]     # Links to events
  controversies:
    - title: string
      date: date
      summary: string
      sources: [url]
      status: enum              # alleged | investigated | charged | convicted | acquitted | ongoing
  public_positions:             # Known public stances
    - topic: string
      position: string
      source: url
  tags: [string]
  sources: [url]
  last_updated: datetime
```

#### Event

```yaml
# data/events/_schema.yaml
event:
  id: string
  title: string
  date: date
  end_date: date | null         # For events spanning time
  type: enum                    # law | decision | crisis | election | appointment | scandal | reform
  summary: string               # 2-3 sentences
  detailed_description: string  # Full explanation
  significance: string          # Why this matters
  actors:                       # People involved
    - figure_id: string
      role: string              # e.g., "author", "defendant", "whistleblower"
  institutions_involved: [institution_id]
  causes: [event_id]           # What led to this
  consequences: [event_id]     # What this led to
  timeline_group: string | null # Group events into named timelines
  tags: [string]
  sources: [url]
  last_updated: datetime
```

#### Relationship

```yaml
# data/relationships/_schema.yaml
relationship:
  id: string
  source_type: enum             # figure | institution | event
  source_id: string
  target_type: enum
  target_id: string
  relationship_type: enum       # appointed_by | member_of | ruled_on | allied_with
                                # opposed | investigated | funded_by | succeeded
  description: string
  start_date: date | null
  end_date: date | null
  strength: enum                # strong | moderate | weak
  sources: [url]
  last_updated: datetime
```

#### Glossary Term

```yaml
# data/glossary/_schema.yaml
term:
  id: string
  term_pt: string               # Portuguese term
  term_en: string | null        # English equivalent
  definition: string            # Plain-language definition
  legal_definition: string | null
  example: string               # Usage in context
  related_terms: [term_id]
  related_institutions: [institution_id]
  tags: [string]
  sources: [url]
```

### 2.2 Relationship Graph

All entities connect through the `relationships` data. This enables:

- **"Who appointed whom"** — figure → figure (appointed_by)
- **"Who belongs to what"** — figure → institution (member_of)
- **"What caused what"** — event → event (caused / led_to)
- **"Who was involved in what"** — figure → event (actor_in)
- **"Which institutions overlap"** — institution → institution (oversees / checks)

This graph is loaded into **NetworkX** (Python) for querying and into **visual renderers** for diagrams.

---

## 3. Technology Stack (Detailed)

### 3.1 Core Language & Runtime

| Component | Choice | Rationale |
|---|---|---|
| **Language** | Python 3.11+ | Rich ecosystem for AI, data, scraping, image generation |
| **Package Manager** | `uv` | Fast, modern Python package manager (replaces pip + venv) |
| **Project Config** | `pyproject.toml` | Single file for all project metadata and dependencies |

### 3.2 Dependencies (by domain)

#### Data & Validation

| Package | Purpose |
|---|---|
| `pydantic` (v2) | Data models with validation, serialization, type safety |
| `pyyaml` | Load/save YAML knowledge base files |
| `networkx` | In-memory graph for relationship queries |
| `sqlite-utils` | Lightweight DB for content queue and drafts (no server needed) |

**Why Pydantic?** Every piece of data passes through a typed model. If someone adds an institution with a missing field, validation catches it before it enters the system. This is critical for a factual platform — bad data = bad content.

**Why YAML over a database?** YAML files are:
- Human-readable and editable
- Version-controlled with git (full history of every change)
- Easy to review in pull requests
- Portable (no database server needed)

For querying, we load YAML into Pydantic models in memory. For relationships, we build a NetworkX graph. This is fast enough for thousands of entities.

#### News Ingestion

| Package | Purpose |
|---|---|
| `feedparser` | Parse RSS feeds from news outlets |
| `httpx` | Modern async HTTP client for API calls and scraping |
| `beautifulsoup4` | HTML parsing for web scraping |
| `newspaper3k` or `trafilatura` | Article extraction (title, text, date, author) |

**News Sources (Brazil):**

| Source | Type | URL |
|---|---|---|
| Folha de S.Paulo | RSS | `https://feeds.folha.uol.com.br/poder/rss091.xml` |
| G1 Política | RSS | `https://g1.globo.com/rss/g1/politica/` |
| Estadão Política | RSS | `https://www.estadao.com.br/politica/feed/` |
| Congresso em Foco | RSS | `https://congressoemfoco.uol.com.br/feed/` |
| Agência Brasil | RSS | `https://agenciabrasil.ebc.com.br/rss/ultimasnoticias/feed.xml` |
| Diário Oficial da União | Official | Scraped from `in.gov.br` |
| Câmara dos Deputados API | API | `https://dadosabertos.camara.leg.br/api/v2/` |
| Senado API | API | `https://legis.senado.leg.br/dadosabertos/` |

#### AI / LLM

| Package | Purpose |
|---|---|
| `anthropic` | Claude API client (primary LLM) |
| `openai` | OpenAI API client (fallback / comparison) |
| `tiktoken` | Token counting for cost management |
| `jinja2` | Prompt templating (fill variables into prompt templates) |

**Why prompt templates in YAML?**

```yaml
# config/prompts/summarize_news.yaml
name: summarize_news
version: "1.2"
model: claude-sonnet-4-20250514
max_tokens: 1000
temperature: 0.3
system: |
  You are an editorial assistant for a Brazilian political education platform.
  Your role is to summarize news in a clear, neutral, and educational tone.
  Always provide context: what happened, why it matters, and what institution
  or system is involved.
  Language: Brazilian Portuguese.
  Never speculate. Never editorialize. Stick to facts.

user_template: |
  Summarize the following news article for a general audience.

  **Article:**
  {{ article_text }}

  **Output format:**
  1. **O que aconteceu** (1-2 sentences)
  2. **Por que importa** (1-2 sentences)
  3. **Contexto institucional** (which institution/system is involved and how)
  4. **Tags**: list of relevant tags

  Keep the total under 200 words.
```

This approach means:
- Prompts are versioned and reviewable
- You can A/B test different prompt versions
- Changing a prompt doesn't require code changes

#### Visual Generation

| Package | Purpose |
|---|---|
| `pillow` (PIL) | Image composition, text rendering, template filling |
| `cairosvg` | SVG → PNG conversion |
| `matplotlib` | Charts and simple diagrams |
| `graphviz` | Directed graphs and flowcharts |
| `pyvis` or `networkx` + `matplotlib` | Network visualizations |

**Visual Pipeline:**

```
Template (SVG/HTML) → Fill with data → Render to PNG → Resize per platform
```

For Instagram carousels:
- Each slide is 1080×1080px
- Template defines layout (header, body, footer, source attribution)
- Python fills in the content and renders

#### CLI & Interface

| Package | Purpose |
|---|---|
| `typer` | Modern CLI framework (auto-generates help, type-safe) |
| `rich` | Beautiful terminal output (tables, panels, progress bars) |
| `questionary` | Interactive prompts for review workflow |

**Example CLI commands:**

```bash
# Knowledge base
anticorrupt kb validate                    # Validate all YAML files
anticorrupt kb search "STF"                # Search knowledge base
anticorrupt kb graph --entity stf          # Show connections for an entity

# Content pipeline
anticorrupt news scan                      # Fetch latest news
anticorrupt news summarize                 # AI-summarize today's top stories
anticorrupt generate explainer --topic "como funciona o impeachment"
anticorrupt generate profile --figure "alexandre-de-moraes"
anticorrupt generate timeline --group "lava-jato"

# Review
anticorrupt review list                    # Show pending drafts
anticorrupt review show <draft-id>         # Display a draft
anticorrupt review approve <draft-id>      # Approve for publishing
anticorrupt review edit <draft-id>         # Open in editor
anticorrupt review reject <draft-id>       # Reject with reason

# Publishing
anticorrupt publish preview <draft-id>     # Preview formatted output
anticorrupt publish send <draft-id> --platform instagram
anticorrupt publish schedule <draft-id> --time "2026-02-24T10:00"

# Dashboard
anticorrupt dashboard                      # Show stats overview
```

#### Publishing

| Package | Purpose |
|---|---|
| `instagrapi` or Instagram Graph API via `httpx` | Post to Instagram |
| `tweepy` | Post to X/Twitter |
| `schedule` or `apscheduler` | Task scheduling |

#### Testing & Quality

| Package | Purpose |
|---|---|
| `pytest` | Test framework |
| `pytest-asyncio` | Async test support |
| `ruff` | Linting and formatting (replaces flake8 + black + isort) |
| `mypy` | Type checking |
| `pre-commit` | Git hooks for quality gates |

---

## 4. Phase 0 — Foundation

**Goal:** Set up the project skeleton, knowledge base schemas, and basic tooling so everything that follows has a solid base.

**Duration:** 1-2 days
**Outcome:** A working project you can `git init`, install dependencies, validate data, and run basic CLI commands.

### 4.1 Tasks

| # | Task | Details |
|---|---|---|
| 1 | **Initialize Python project** | Create `pyproject.toml` with all dependencies, configure `uv` |
| 2 | **Create directory structure** | Full folder tree as defined in §1.1 |
| 3 | **Define Pydantic models** | All 5 entity types (Institution, Figure, Event, Relationship, GlossaryTerm) |
| 4 | **Create YAML schemas** | `_schema.yaml` files documenting expected structure |
| 5 | **Build data loader** | Load YAML files → Pydantic models with validation |
| 6 | **Build data validator** | CLI command to validate the entire knowledge base |
| 7 | **Seed initial data** | 3-5 institutions, 2-3 figures, 2-3 events, sample relationships |
| 8 | **Build relationship graph** | Load relationships into NetworkX, basic queries |
| 9 | **Set up CLI skeleton** | Typer app with `kb`, `news`, `generate`, `review`, `publish` groups |
| 10 | **Configure dev tooling** | Ruff, mypy, pytest, pre-commit, .gitignore, .env.example |
| 11 | **Write initial tests** | Tests for models, loader, validator, and graph |

### 4.2 Acceptance Criteria

- [ ] `uv run anticorrupt kb validate` — validates all YAML files and reports errors
- [ ] `uv run anticorrupt kb search "STF"` — finds the institution
- [ ] `uv run anticorrupt kb graph --entity stf` — shows connected entities
- [ ] All seed data passes validation
- [ ] `pytest` runs with >90% pass rate
- [ ] `ruff check` and `mypy` pass clean

---

## 5. Phase 1 — Content Pipeline

**Goal:** Build the end-to-end flow from news ingestion to AI-generated drafts ready for human review.

**Duration:** 1-2 weeks
**Depends on:** Phase 0

### 5.1 Tasks

| # | Task | Details |
|---|---|---|
| 1 | **RSS feed aggregator** | Fetch from 5+ Brazilian news sources, deduplicate |
| 2 | **Article extractor** | Extract clean text from article URLs |
| 3 | **AI summarizer** | Summarize articles using prompt templates |
| 4 | **AI explainer** | Generate institutional explanations from knowledge base |
| 5 | **AI profiler** | Generate public figure profiles from knowledge base |
| 6 | **AI timeline generator** | Create narrative timelines from event chains |
| 7 | **Content draft storage** | Save drafts to SQLite with status tracking |
| 8 | **Review queue** | CLI-based review workflow (list, show, approve, edit, reject) |
| 9 | **Content formatter** | Format approved content for Instagram (carousel text) and X (thread) |
| 10 | **Prompt versioning** | Track which prompt version generated which content |

### 5.2 Content Generation Flow

```
[News Sources] ──→ [Aggregator] ──→ [Deduplicator]
                                          │
                                          ▼
                                    [AI Summarizer]
                                          │
                                          ▼
                              ┌───── [Draft Queue] ─────┐
                              │                         │
                              ▼                         ▼
                      [Human Review]            [Auto-Enrich]
                       (approve/edit/             (add tags,
                        reject)                   link to KB)
                              │
                              ▼
                      [Approved Content]
                              │
                    ┌─────────┼──────────┐
                    ▼         ▼          ▼
              [Instagram] [X/Twitter] [Archive]
```

### 5.3 AI Processing Details

**Summarization pipeline:**

1. Article comes in (raw text, ~1000-3000 words)
2. Pre-processing: strip ads, navigation, boilerplate
3. Entity extraction: identify institutions and figures mentioned
4. Cross-reference with knowledge base: pull context
5. Generate summary using prompt template + KB context
6. Post-processing: check length, format, add tags
7. Save as draft with metadata (source URL, generation date, prompt version)

**Cost estimation:**
- ~500 tokens input + ~300 tokens output per summary
- At Claude Sonnet pricing (~$3/$15 per 1M tokens): ~$0.005 per summary
- 10 articles/day = ~$0.05/day = ~$1.50/month

---

## 6. Phase 2 — Visual Generation

**Goal:** Programmatically create social media-ready images from content and knowledge base data.

**Duration:** 1-2 weeks
**Depends on:** Phase 1

### 6.1 Visual Types

| Type | Use Case | Tech |
|---|---|---|
| **Carousel slides** | Instagram explainers (4-8 slides) | Pillow + SVG templates |
| **Profile cards** | Public figure summaries | Pillow + SVG templates |
| **Flowcharts** | "How a law is passed" | Graphviz |
| **Timelines** | Historical event sequences | Custom SVG renderer |
| **Network diagrams** | Relationship/power maps | NetworkX + matplotlib |
| **Quote cards** | Key statements with attribution | Pillow + SVG templates |

### 6.2 Template System

Each template is an SVG file with placeholder tokens:

```svg
<text id="title">{{ title }}</text>
<text id="body">{{ body }}</text>
<text id="source">Fonte: {{ source }}</text>
<rect id="accent" fill="{{ accent_color }}"/>
```

Python fills the tokens, renders to PNG at platform-specific dimensions:
- Instagram post: 1080×1080
- Instagram carousel: 1080×1080 per slide
- X/Twitter: 1200×675
- Story: 1080×1920

### 6.3 Color System

Each institution type gets a consistent color:

| Type | Color | Hex |
|---|---|---|
| Judiciary | Deep Blue | `#1A365D` |
| Legislature | Green | `#276749` |
| Executive | Gold/Yellow | `#975A16` |
| Independent Bodies | Purple | `#553C9A` |
| Military | Dark Gray | `#2D3748` |
| General/Neutral | Slate | `#4A5568` |

---

## 7. Phase 3 — Publishing & Automation

**Goal:** Automate the posting process and build scheduling capabilities.

**Duration:** 1 week
**Depends on:** Phase 2

### 7.1 Instagram Publishing

**Requirements:**
- Facebook Developer account
- Instagram Business or Creator account
- Facebook Page linked to Instagram account
- Instagram Graph API access

**Flow:**
1. Upload image(s) to hosting or use Content Publishing API
2. Create media container(s)
3. For carousels: create child containers, then parent
4. Publish with caption

**Rate limits:** 50 API calls per hour, 25 posts per 24-hour period

### 7.2 X/Twitter Publishing

**Requirements:**
- X Developer account (Basic tier: $100/month or Free tier: write-only)
- OAuth 2.0 credentials

**Flow:**
1. Upload media via media upload endpoint
2. Create tweet with media IDs
3. For threads: chain tweets using `reply_to` parameter

### 7.3 Scheduling

```python
# Example scheduling configuration
schedule:
  daily_news:
    time: "10:00"              # BRT (UTC-3)
    type: news_summary
    platforms: [instagram, twitter]

  weekly_explainer:
    day: wednesday
    time: "14:00"
    type: institutional_explainer
    platforms: [instagram]

  weekly_profile:
    day: friday
    time: "14:00"
    type: figure_profile
    platforms: [instagram, twitter]
```

---

## 8. Phase 4 — Web Platform

**Goal:** Build an interactive website for deeper content exploration.

**Duration:** 2-4 weeks
**Depends on:** Phase 3

### 8.1 Features

- **Interactive knowledge graph** — click on entities to explore connections
- **Searchable archive** — all published content, searchable and filterable
- **Interactive timelines** — zoom, pan, click for details
- **Institution explorer** — visual hierarchy of Brazilian government
- **Glossary** — searchable political/legal dictionary

### 8.2 Recommended Stack

| Component | Choice | Rationale |
|---|---|---|
| **Framework** | Next.js or Astro | SSG for content, interactive components where needed |
| **Graph visualization** | D3.js or vis.js | Interactive network diagrams |
| **Timeline** | vis-timeline or custom | Interactive timelines |
| **Styling** | Tailwind CSS | Consistent with clean visual identity |
| **Hosting** | Vercel or Cloudflare Pages | Free tier, fast, easy deploy |
| **CMS** | Content from knowledge base YAML → built at deploy time | No external CMS needed |

---

## 9. Phase 5 — Scale & Monetize

**Goal:** Expand reach and build sustainable revenue.

**Duration:** Ongoing
**Depends on:** Phases 1-4 stable

### 9.1 Growth Channels

| Channel | Strategy |
|---|---|
| **Organic social** | Consistent posting, engagement, hashtags |
| **Collaborations** | Partner with educators, journalists, civic tech orgs |
| **SEO** | Website content optimized for political/institutional queries in Portuguese |
| **Newsletter** | Weekly digest via Substack or Buttondown |
| **YouTube/TikTok** | Short animated explainers (Phase 5+) |

### 9.2 Revenue Models

| Model | Description | Timeline |
|---|---|---|
| **Free tier** | All social media content remains free | Always |
| **Newsletter premium** | Deep dives, exclusive analysis | 6 months |
| **Courses** | "Como funciona o Brasil" structured course | 12 months |
| **API access** | Knowledge base as a service for researchers | 12 months |
| **Sponsorships** | Educational orgs, civic tech companies | 6 months |

---

## 10. Infrastructure & DevOps

### 10.1 Local Development

```bash
# Install uv (if not already)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
git clone <repo-url>
cd anti_corrupt
uv sync                        # Install all dependencies
cp .env.example .env           # Set up environment variables

# Run
uv run anticorrupt --help      # CLI
uv run pytest                  # Tests
uv run ruff check .            # Lint
```

### 10.2 Environment Variables

```bash
# .env.example
ANTHROPIC_API_KEY=sk-ant-...        # Claude API
OPENAI_API_KEY=sk-...               # OpenAI (optional fallback)
NEWSAPI_KEY=...                     # NewsAPI.org
INSTAGRAM_ACCESS_TOKEN=...          # Instagram Graph API
TWITTER_API_KEY=...                 # X API
TWITTER_API_SECRET=...
TWITTER_ACCESS_TOKEN=...
TWITTER_ACCESS_SECRET=...
DATA_DIR=./data                     # Knowledge base location
OUTPUT_DIR=./output                 # Generated content location
LOG_LEVEL=INFO
```

### 10.3 CI/CD (Future)

- **GitHub Actions** for:
  - Run tests on every push
  - Validate knowledge base YAML on every PR
  - Auto-build website on merge to main
  - Lint and type-check

---

## 11. Editorial Workflow

### 11.1 Daily Workflow

```
Morning (8:00-9:00):
  1. Run `anticorrupt news scan` — fetch overnight news
  2. Run `anticorrupt news summarize` — AI generates summaries
  3. Review drafts: `anticorrupt review list`
  4. Approve/edit 1-2 best summaries
  5. Generate visuals: `anticorrupt visuals generate <draft-id>`
  6. Schedule: `anticorrupt publish schedule <draft-id> --time 10:00`

Weekly (Wednesday):
  1. Choose explainer topic based on recent news or audience requests
  2. Run `anticorrupt generate explainer --topic "..."`
  3. Review, edit, approve
  4. Generate carousel visuals
  5. Publish

Weekly (Friday):
  1. Choose a public figure relevant to current events
  2. Run `anticorrupt generate profile --figure "..."`
  3. Review, edit, approve
  4. Generate profile card + thread text
  5. Publish
```

### 11.2 Review Checklist

Every piece of content must pass:

- [ ] **Factual accuracy** — all claims verifiable
- [ ] **Source attribution** — sources listed or linked
- [ ] **Neutral tone** — no editorializing unless labeled
- [ ] **Institutional context** — connects to systems, not just people
- [ ] **Accessibility** — clear language, no jargon without definition
- [ ] **Legal safety** — no unverified allegations as fact
- [ ] **Visual quality** — images render correctly, text readable

---

## 12. Legal & Ethical Guardrails

### 12.1 Content Classification

Every content piece is tagged with one of:

| Label | Meaning | Rules |
|---|---|---|
| `FACT` | Verified, sourced information | Must have 2+ sources |
| `CONTEXT` | Factual background and explanation | Must reference factual basis |
| `ANALYSIS` | Interpretation of facts | Must be labeled as analysis |
| `OPINION` | Editorial position | Must be clearly marked (avoid in Phase 1) |

### 12.2 Automated Guardrails

Built into the AI pipeline:

1. **Source requirement** — AI must cite sources; unsourced claims are flagged
2. **Speculation detector** — flag language like "probably", "likely", "sources say"
3. **Sensitivity filter** — flag content about ongoing investigations, minors, or sealed records
4. **Factual cross-reference** — check AI claims against knowledge base
5. **Tone analyzer** — flag inflammatory or non-neutral language

### 12.3 Correction Policy

- Errors are corrected transparently with a correction notice
- Original content is preserved in git history
- Correction is posted as a follow-up on the same platform

---

## 13. Cost Estimates

### 13.1 Monthly Operating Costs (Phase 1-3)

| Item | Cost | Notes |
|---|---|---|
| Claude API | ~$5-15/month | Depending on volume |
| NewsAPI | Free tier or $449/month | Free tier: 100 requests/day |
| X Developer | $0-100/month | Free tier is write-only |
| Instagram API | Free | Via Facebook Developer |
| Domain | ~$1/month | For future website |
| Hosting (future) | Free-$20/month | Vercel/Cloudflare free tier |
| **Total** | **~$5-50/month** | Lean operation |

### 13.2 Time Investment

| Phase | Estimated Hours |
|---|---|
| Phase 0 | 4-8 hours |
| Phase 1 | 20-40 hours |
| Phase 2 | 15-30 hours |
| Phase 3 | 10-15 hours |
| Phase 4 | 40-60 hours |
| Daily operation | 30-60 min/day |

---

## 14. Risk Register

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **AI generates false information** | Medium | High | Mandatory human review, source requirements, fact-check step |
| **Legal complaint from public figure** | Low | High | Facts-only policy, source everything, separate fact/analysis/opinion |
| **API rate limits or bans** | Medium | Medium | Cache aggressively, respect rate limits, have fallback sources |
| **LLM API cost spike** | Low | Medium | Token budgets, cheaper models for simple tasks, local models as fallback |
| **Editorial burnout (one person)** | High | High | Automate 80%, batch review sessions, buffer content ahead |
| **Platform algorithm changes** | Medium | Medium | Multi-platform strategy, own your audience (website + newsletter) |
| **Data quality degradation** | Medium | Medium | Automated validation, periodic audits, schema enforcement |
| **Plagiarism accusations** | Low | High | Always cite sources, AI generates original phrasing, add disclaimers |

---

## Next Steps

**Ready to begin Phase 0.** In the next command, we will:

1. Initialize the Python project with `pyproject.toml`
2. Create the full directory structure
3. Implement Pydantic models for all entity types
4. Build the YAML data loader and validator
5. Seed the knowledge base with initial Brazilian institutions and figures
6. Build the relationship graph engine
7. Create the CLI skeleton
8. Set up testing and dev tooling

---

*This document is a living plan. It will be updated as the project evolves.*
