# Anti-Corrupt — TODO

> **Updated:** March 1, 2026  
> **Context:** @brunoclz went viral (4.1M views) on Feb 21 2026 connecting 79 Brazilian open databases via CPF/CNPJ. He validated the exact thesis of this project. Items marked 🔥 are inspired by his approach.

---

## 🔴 BLOCKING — Fix Historical News Ingestion

`scripts/ingest_historical.py` ran for hours against all 1,307 politicians and saved **0 news items**.
Root cause: GDELT, Wayback CDX, and Querido Diário APIs are either timing out or returning nothing from the local machine. Work continues on the Frankfurt server where the network is different.

- [ ] **Test each API from Frankfurt server** (different network, no ISP blocks)
  - GDELT: `"Lula" sourcecountry:brazil sourcelang:portuguese` → expect articles
  - Wayback CDX: `url=g1.globo.com/politica/*&filter=original:.*lula.*` → expect JSON rows
  - Querido Diário: full-text search endpoint → may need API key (returned 403 locally)
  - Use: `cd ~/anti_corrupt_code && .venv/bin/python output/test_apis.py`

- [ ] **Switch primary source to RSS feeds** (more reliable than CDX for recent news)
  - `scripts/ingest_rss.py` already exists — test on Frankfurt first
  - RSS never blocked: Agência Brasil, G1, Folha, Estadão, Poder360, Congresso em Foco
  - Populate `news_items` via RSS first, augment with CDX/GDELT later

- [ ] **Wayback CDX: reconsider slug strategy**
  - Per-politician slugs like `joao.+silva` match nothing — too many deputies have generic names
  - Better: use keyword mode (`--keywords` flag) — searches for `corrupcao`, `lava-jato`, etc. across all domains
  - Test keyword mode separately: `python scripts/ingest_historical.py --keywords --source wayback`

- [ ] **Querido Diário: verify API access**
  - May require API key or IP allowlist — check `https://queridodiario.ok.org.br/api/docs`

- [ ] **Re-run ingest on Frankfurt once a working source is confirmed**
  - Start small: `python scripts/ingest_historical.py --notable --source gdelt`
  - Then expand: `python scripts/ingest_historical.py --all --source wayback --keywords`

---

## 🔥 High-Value Data Enrichment

### Cross-reference signals

- [ ] **CGU sanction lists** 🔥 — instant anti-corruption signal, no AI needed
  - CEIS, CNEP, CEPIM, CEAF via `https://api.portaldatransparencia.gov.br/api-de-dados/` (key required)
  - Match expense supplier CNPJs against CEIS/CNEP → flagged companies
  - Match politician CPFs against CEAF → expelled civil servants
  - Add `sanctioned: bool`, `sanction_list: str` fields to `companies` table

- [ ] **TSE Bens (declared assets)** 🔥
  - Source: `https://dadosabertos.tse.jus.br/dataset/bem-de-candidatos`
  - Import declared wealth per politician per election year (2018, 2022, 2026)
  - Signal: compare year-over-year → unexplained enrichment
  - New table: `declared_assets(politician_id, year, category, value_brl)`

- [ ] **TSE Donation cross-reference** 🔥
  - `prestacao_contas` CSVs: CNPJs of companies that donated to campaigns
  - Pattern: company gets CEAP money from deputy A AND donated to deputy A's campaign
  - Source: `https://dadosabertos.tse.jus.br/dataset/prestacao-de-contas-eleitorais`

- [ ] **CNPJ owner CPF cross-reference** 🔥
  - BrasilAPI returns `socios[].cpf_representante_legal` per CNPJ
  - Match owner CPFs against politician CPFs in DB
  - Self-dealing confirmation: politician → CEAP expense → company owned by politician
  - `output/lookup_cnpj.py` already partially exists

- [ ] **ComprasNet / PNCP (federal procurement)** 🔥
  - Match supplier CNPJs from CEAP expenses against federal contract winners
  - Same company milks CEAP *and* federal contracts = major red flag
  - Source: `https://pncp.gov.br/api/pncp/v1/`

- [ ] **Portal da Transparência — Servidores**
  - Match `cabinet_staff.staff_name` against federal payroll
  - Detect double-dipping: "parliamentary secretary" also on federal payroll

### Analysis (no new data needed — all in DB already)

- [ ] **Nepotism detector** — surname match between `cabinet_staff` and their linked deputy
- [ ] **Shared supplier cross-deputy map** — `shared_supplier=588` already flagged; map which deputies share each supplier
- [ ] **Ghost supplier list** — `inactive=369` companies; cross with CGU lists once loaded
- [ ] **Shell company signals** — company opened <6 months before first CEAP payment

---

## 🕸 Graph Layer

No Neo4j needed — our scale fits in SQLite + NetworkX (sub-second queries for our data size).

- [ ] **Build NetworkX graph from DB** (`output/build_graph.py`)
  - Nodes: politicians, companies, staff, institutions
  - Edges: `PAID_TO`, `OWNS` (when CPF match found), `DONATED_TO`, `WORKS_FOR`, `SHARED_SUPPLIER`
  - Export as JSON → feed into React Flow or `src/visuals/network.py`

- [ ] **`src/knowledge/follow_money.py`** — 3–4 canned SQL CTE investigative queries:
  - politician → expenses → companies → owners → check if owner CPF = politician CPF
  - politician → cabinet staff → surname match → nepotism flag
  - company → all deputies who paid it → total received → rank by amount

- [ ] **Per-politician network image** — generate for top 20 notable politicians
  - Flagged companies in red, shared suppliers highlighted
  - Export as PNG for content pipeline

---

## 🟢 Infrastructure

- [ ] **Create `.env` on Frankfurt server** — without this AI pipeline cannot run remotely
  - `ssh frankfurt "cat > ~/anti_corrupt_code/.env"` then paste keys
  - Minimum: `ANTHROPIC_API_KEY`, `OUTPUT_DIR=output`

- [ ] **DB indexes** on hot query columns
  - `expenses(supplier_cnpj_cpf)`, `expenses(deputy_camara_id, year)`
  - `news_items(published_at)`, `votes(deputy_camara_id, date)`

- [ ] **Incremental daily refresh** (`scripts/refresh_daily.py`)
  - Expenses: 1st of month, re-fetch last 2 months per deputy
  - Votes: Mon–Fri, fetch yesterday's sessions
  - RSS: every 6h
  - Deploy as cron on Frankfurt: `0 6 1 * *` (expenses), `0 */6 * * *` (RSS)

- [ ] **Sync DB from Frankfurt → local** after remote ingest runs
  - `rsync -avz frankfurt:~/anti_corrupt_code/output/history.db output/`
  - Add as `make sync-db` in Makefile

---

## 🔵 Content Pipeline (built, needs real data to test)

Once `news_items` has data, validate each step:

- [ ] **RSS ingestion end-to-end** — run `scripts/ingest_rss.py`, check `news_items` count
- [ ] **AI summarizer** — `anticorrupt generate summarize` on a real news item
- [ ] **AI explainer** — `anticorrupt generate explainer --topic "como funciona o impeachment"`
- [ ] **Review queue** — `anticorrupt review list` → `show` → `approve`
- [ ] **Visuals** — `anticorrupt visuals generate <draft-id>` → verify PNG in `output/images/`
- [ ] **Publishing** — Instagram + Twitter credentials in `.env` → `anticorrupt publish preview`

---

## 📰 Future Sources

- [ ] **DataJud / CNJ — judicial records** 🔥
  - Link politician CPF to active criminal/civil proceedings
  - Source: `https://dadosabertos.cnj.jus.br/`

- [ ] **DOU (Diário Oficial da União)** — monitor for new contracts by known CNPJs
  - Source: `https://inlabs.in.gov.br/`

- [ ] **Serenata de Amor dataset** — pre-labeled CEAP suspicious transactions 2009–2017
  - Import as historical baseline: `https://github.com/okfn-brasil/serenata-de-amor`

- [ ] **Wikipedia / Wikidata** — `src/sources/wikidata.py` exists, finish and run for all politicians

---

## ✅ Completed

- [x] **Phase 0** — project structure, Pydantic models, YAML schemas, CLI skeleton, dev tooling, tests
- [x] **Phase 1** — AI summarizer, explainer, content queue, review CLI, generate CLI, formatter
- [x] **Phase 2** — API cache layer, Câmara/Senado API clients, TSE client, all visuals modules, RSS, scraper
- [x] **DB: politicians** — 13,724 (deputies, senators, STF, STJ, ministers, cabinet heads)
- [x] **DB: expenses** — 171,321 CEAP rows, 2023–2026, all 632 deputies
- [x] **DB: companies** — 16,502 CNPJs enriched (shared_supplier=588, high_value=546, inactive=369)
- [x] **DB: votes** — 4,996 vote records
- [x] **DB: election results** — 12,820 rows (TSE 2022/2024)
- [x] **DB: cabinet staff** — 22,338 secretários parlamentares snapshot
- [x] **Git history cleaned** — large files (243MB CSV, 182MB txt, 102MB DB) stripped
- [x] **Frankfurt server** — ubuntu@158.101.171.79, aarch64, Python 3.12 venv, full git clone, all DBs synced
- [x] **React Flow viz** — 47-node pipeline diagram at `output/project-viz/`
- [x] **.gitignore** — `eleicoes/*.csv`, `eleicoes/*.zip`, `data/rf/` excluded
