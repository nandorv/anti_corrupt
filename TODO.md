# Anti-Corrupt — TODO

> **Context:** @brunoclz went viral (4.1M views) on Feb 21 2026 connecting 79 Brazilian open databases via CPF/CNPJ in a Neo4j graph. He validated the exact thesis of this project. Items marked 🔥 are stolen or inspired by his approach.

---

## 🔥 High-Priority Steals (from brunoclz's 79-database approach)

- [ ] **CGU sanction lists** — tiny datasets, instant anti-corruption signal 🔥
  - CEIS: companies/people sanctioned by federal government
  - CNEP: companies penalized for corruption, fraud, cartels
  - CEPIM: NGOs blocked from federal transfers
  - CEAF: civil servants expelled for misconduct
  - Source: `https://api.portaldatransparencia.gov.br/api-de-dados/` (free, key required)
  - Match CPF/CNPJ from our expenses + politicians against all four lists
  - One hit = instant red flag; no analysis needed

- [ ] **TSE Bens (declared assets)** — politicians' declared wealth at candidacy 🔥
  - Source: `https://dadosabertos.tse.jus.br/dataset/bem-de-candidatos`
  - Fields: candidato CPF, bem_descricao, bem_valor, ano
  - Key signal: compare wealth declared in 2018 vs 2022 vs 2026 → unexplained enrichment
  - Already have CPF in our `politicians` table → direct join

- [ ] **CNPJ/QSA enrichment** — who owns the companies receiving CEAP money 🔥
  - Source API: `https://brasilapi.com.br/api/cnpj/v1/{cnpj}` (free, no auth)
  - Fields returned: `razao_social`, `socios` (owners with CPF), `atividade_principal`, `situacao_cadastral`, `data_abertura`
  - Plan: `output/lookup_cnpj.py` → `CompanyProfile` model, table `companies`
  - **The core cross-reference:** company owner CPF → matches politician CPF → self-dealing confirmed
  - Also flags: company opened <6 months before first expense → likely shell; `situacao_cadastral = INAPTA` → ghost supplier

- [ ] **ComprasNet / PNCP (federal procurement)** — government contracts by CNPJ 🔥
  - Source: `https://pncp.gov.br/api/pncp/v1/` or `https://compras.dados.gov.br/`
  - Match supplier CNPJs from CEAP expenses against winners of federal contracts
  - Pattern: same company milks both CEAP (office expenses) AND federal contracts

- [ ] **Portal da Transparência — Servidores** — federal payroll 🔥
  - Source: `https://api.portaldatransparencia.gov.br/api-de-dados/servidores`
  - Match staff names from our `cabinet_staff` table against federal payroll
  - Detect double-dipping: a "parliamentary secretary" who is also on federal payroll

- [ ] **DataJud / CNJ — judicial records** — ongoing cases per politician 🔥
  - Source: `https://dadosabertos.cnj.jus.br/`
  - Link politician CPF to active criminal/civil proceedings
  - Especially relevant for STJ/STF cases (foro privilegiado)

---

## 📰 News & Intelligence

### RSS / Recent News (real-time layer)

- [ ] **RSS feed ingestion pipeline** — pull current news into the content pipeline
  - Sources to monitor:
    - Agência Brasil: `https://agenciabrasil.ebc.com.br/rss/politica/feed.xml`
    - G1 Política: `https://g1.globo.com/rss/g1/politica/`
    - Folha de S.Paulo: `https://feeds.folha.uol.com.br/poder/rss091.xml`
    - UOL Política: `https://rss.uol.com.br/feed/noticias/noticias/politica.xml`
    - Estadão Política: `https://www.estadao.com.br/rss/politica.xml`
    - Metrópoles: `https://www.metropoles.com/feed/`
    - Poder360: `https://www.poder360.com.br/feed/`
  - Implementation: `scripts/ingest_rss.py` — poll every 6h, deduplicate by URL hash
  - Model: `NewsItem` (url, title, summary, published_at, source, politician_mentions[])
  - Entity linking: scan title+summary for politician names in DB → create `mentions` join table
  - Use case: "show me all news mentioning [politician] in the last 30 days" → feeds the AI content pipeline

- [ ] **Querido Diário — official gazette NLP** 🔥
  - Source: `https://queridodiario.ok.org.br/api/` (Serenata de Amor / Open Knowledge)
  - Structured access to DOUs + DOEs with full-text search
  - Query by politician name → find appointments, contracts, penalties, nominations
  - Historical depth: covers gazettes back to 2000s for many states
  - Use case: find when a supplier company got first federal/state contract → correlate with politician career timeline

- [ ] **DOU (Diário Oficial da União) direct** — appointments and contracts 🔥
  - Source: `https://www.in.gov.br/servicos/buscar-diario-oficial` or `https://inlabs.in.gov.br/`
  - Monitor for: new CNPJ contracts, politician appointments, sanctioned entities
  - Trigger: when a known CNPJ (from our `companies` table) appears in DOU → flag for review

### Historical News Archive

- [ ] **News archive ingestion** — get pre-2024 coverage into our knowledge base
  - **Approach 1 — Common Crawl:** free, petabytes of web archive; filter `.br` domains by politician name/CPF
    - API: `https://index.commoncrawl.org/` — returns CDX records for a given URL pattern
    - Use case: find old Folha/Estadão articles about a politician that are no longer on their live site
  - **Approach 2 — Wayback Machine CDX API:** `http://web.archive.org/cdx/search/cdx?url=*.folha.uol.com.br/*lula*`
    - Free, rate-limited; returns snapshots of specific URLs
    - Good for recovering deleted articles (e.g. retracted corruption stories)
  - **Approach 3 — Serenata de Amor dataset:** pre-labeled CEAP suspicious transactions 2009–2017
    - `https://github.com/okfn-brasil/serenata-de-amor` — already processed, labeled, with news links
    - Import their flags into our DB as a historical baseline
  - **Approach 4 — Archive.org bulk download per politician:**
    - Script: for each politician in DB → query Wayback CDX for name → collect article URLs → fetch + store summaries
    - Cache in `api_cache.db` to avoid re-fetching; attach to politician profile as `historical_coverage`
  - Priority: Serenata de Amor dataset first (already labeled), then Querido Diário, then Wayback CDX

- [ ] **Wikipedia / Wikidata scrape for historical bios**
  - Already partially done (Wikidata explored in past session)
  - Wikidata SPARQL: `https://query.wikidata.org/sparql` — get birth date, party history, notable events per politician
  - Use case: fill historical gaps in politician profiles that predate our TSE data (e.g. pre-2022 mandates)

---

## 🕸 Graph Layer

> **Is Neo4j worth it for us?** Bruno needed it because he's connecting 79 databases with complex multi-hop queries at scale (128GB RAM server). Our goals are different — we're building a *content + investigation tool*, not a raw query engine. The answer is: **not Neo4j, but yes to a lightweight graph layer.**

- [ ] **Relationship graph with NetworkX (analysis layer)**
  - Add `output/build_graph.py` — export DB relationships into a NetworkX DiGraph:
    - Nodes: politicians, companies, staff, institutions
    - Edges: `PAID_TO` (expense → company), `OWNS` (company → politician CPF match), `DONATED_TO` (company → politician campaign), `WORKS_FOR` (staff → deputy), `RELATED_TO` (same surname → nepotism flag)
  - Use for: shortest path queries ("how is politician A connected to company X?"), centrality analysis ("which companies appear most across multiple deputies?"), cluster detection ("which deputies share the same suppliers?")
  - Output: JSON graph data → feeds `src/visuals/` for relationship diagrams in published content
  - **Does NOT need a separate DB** — NetworkX loads from SQLite at query time; sub-second for our scale

- [ ] **Graph visualization for content pipeline**
  - Generate per-politician relationship SVGs/PNGs using `pyvis` or `graphviz`
  - Example: "Fernando's network" — shows all companies paid by his CEAP, flagged ones in red, shared suppliers with other deputies highlighted
  - Export as static images for articles/posts (feeds `src/visuals/`)

- [ ] **Recursive SQL queries for multi-hop follow-the-money**
  - SQLite supports CTEs including recursive ones — no graph DB needed for 2-3 hop queries
  - Example query: politician → expenses → CNPJ → QSA owners → check if owner CPF = any politician CPF
  - Implement as `src/knowledge/follow_money.py` with 3-4 canned investigative query templates

---

## Data Collection

- [ ] **Full expense scrape** — all 632 deputies × 4 years (2023–2026)
  - `output/seed_deputies.py --expenses-only --start-year 2023 --end-year 2026 --resume`
  - Est. ~50 min, ~650k rows, ~260 MB

- [ ] **Full vote scrape** — all sessions 2023–2026
  - `output/seed_deputies.py --votes-only --start-year 2023 --end-year 2026 --resume`
  - Est. ~40–60 min, ~200k rows, ~70 MB

- [x] **Cabinet staff (secretários parlamentares)**
  - Source: Câmara `funcionarios.json` bulk file (all 14,995 Câmara staff, filtered to `codGrupo=6` + `2` linked to deputies)
  - Model: `CabinetStaff` in `src/history/models.py`, table `cabinet_staff` in store
  - Script: `output/seed_secretarios.py` — each run creates a new snapshot tagged with `YYYY-MM` (old snapshots preserved for turnover tracking)
  - **Re-run every 6 months** — `--force` overwrites current month's snapshot only; prior months remain intact
  - Snapshots enable: "who was in this cabinet in Feb 2026 but not in Aug 2026?" → churned staff
  - Fields: `deputy_camara_id`, `staff_name`, `role`, `start_date`, `legislature`, `snapshot_month`
  - Anti-corruption angles:
    - Matching surnames between staff and deputy → nepotism flag
    - Same staff in multiple deputies' cabinets in same snapshot → ghost employee
    - Staff who later appear as CEAP expense suppliers → revolving door
    - High turnover between snapshots → possible political pressure / instability

---

## Analysis / Cross-Reference

- [ ] **TSE donation cross-reference** — match expense suppliers against political donors
  - TSE publishes `prestacao_contas` CSVs with CNPJ of donors to campaigns
  - Classic pattern: company receives CEAP money from deputy A, same company donated to deputy A's campaign
  - Source: `https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais`

- [ ] **Nepotism detector** — surname matching between cabinet staff and deputy
  - Already have the data; just needs a query: compare last word of `staff_name` against last word of deputy `name`
  - Brazilian convention: last surname is family name → high confidence match
  - Output: flagged list for manual review or auto-tagging

- [ ] **Ghost supplier detector** — companies that appear in multiple deputies' CEAP but have no web presence
  - Signals: `situacao_cadastral = INAPTA`, zero employees (RAIS), registered <6 months before first CEAP payment
  - Cross-reference with CGU sanction lists (CEIS/CNEP)

---

## Infrastructure

- [ ] **Incremental daily refresh script**
  - Votes: Mon–Fri only, fetch yesterday's sessions (check `periodoEmExercicio` to skip recess)
  - Expenses: 1st of month only, re-fetch last 2 months per deputy (covers late submissions)
  - RSS feeds: every 6h via `scripts/ingest_rss.py`
  - Implementation: `scripts/refresh_daily.py` with a cron entry or launchd plist

- [ ] **Indexes** on hot query columns
  - `expenses(supplier_cnpj_cpf)` — for CNPJ lookups
  - `expenses(deputy_camara_id, year)` — for per-deputy queries
  - `votes(deputy_camara_id, date)` — for timeline queries
  - `news_items(published_at)`, `news_items(politician_id)` — for feed queries
