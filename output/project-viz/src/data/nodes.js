// ═══════════════════════════════════════════════════════════════════
// Anti-Corrupt — Full Pipeline Architecture
// ═══════════════════════════════════════════════════════════════════
//
// Layout (left → right):
//   Col 1  (x=0):    External Data Sources / APIs
//   Col 2  (x=340):  Source Clients (src/sources/)
//   Col 3  (x=680):  Seed & Ingest Scripts
//   Col 4  (x=1040): Databases (SQLite)
//   Col 5  (x=1380): Models & Knowledge Base
//   Col 6  (x=1720): AI + Content + Visuals Pipeline
//   Col 7  (x=2060): Publishing & Output
//
// Row spacing: ~180px per node

const X = {
  sources:  0,
  clients:  350,
  scripts:  700,
  dbs:      1060,
  models:   1400,
  process:  1740,
  output:   2100,
};

const nodes = [
  // ═══════════════════════════════════════════════════════════════
  // COLUMN 1 — External Data Sources & APIs
  // ═══════════════════════════════════════════════════════════════
  {
    id: 'ext-camara',
    type: 'pipeline',
    position: { x: X.sources, y: 40 },
    data: {
      label: 'Câmara dos Deputados',
      icon: '🏛️',
      category: 'api',
      badge: 'rest api',
      description: 'dadosabertos.camara.leg.br',
      stats: [
        { label: 'Endpoints', value: 'deputies, votes, expenses' },
        { label: 'Legislature', value: '57th (2023–27)' },
      ],
    },
  },
  {
    id: 'ext-senado',
    type: 'pipeline',
    position: { x: X.sources, y: 220 },
    data: {
      label: 'Senado Federal',
      icon: '🏛️',
      category: 'api',
      badge: 'rest api',
      description: 'legis.senado.leg.br/dadosabertos',
      stats: [
        { label: 'Data', value: 'current senators' },
      ],
    },
  },
  {
    id: 'ext-tse',
    type: 'pipeline',
    position: { x: X.sources, y: 380 },
    data: {
      label: 'TSE Candidaturas',
      icon: '🗳️',
      category: 'source',
      badge: 'csv/zip',
      description: 'cdn.tse.jus.br — election archives',
      stats: [
        { label: 'Election years', value: '16 (1994–2024)' },
        { label: 'Encoding', value: 'Latin-1, semicolons' },
      ],
    },
  },
  {
    id: 'ext-wikidata',
    type: 'pipeline',
    position: { x: X.sources, y: 550 },
    data: {
      label: 'Wikidata SPARQL',
      icon: '🌍',
      category: 'api',
      badge: 'sparql',
      description: 'query.wikidata.org — politicians, events',
      stats: [
        { label: 'QIDs', value: 'Brazil, STF, Congress…' },
      ],
    },
  },
  {
    id: 'ext-brasil',
    type: 'pipeline',
    position: { x: X.sources, y: 710 },
    data: {
      label: 'BrasilAPI / CNPJ',
      icon: '🏢',
      category: 'api',
      badge: 'rest api',
      description: 'brasilapi.com.br/api/cnpj/v1',
      stats: [
        { label: 'Enriched', value: '16,502 CNPJs' },
        { label: 'Coverage', value: '99.99%' },
      ],
    },
  },
  {
    id: 'ext-rf',
    type: 'pipeline',
    position: { x: X.sources, y: 870 },
    data: {
      label: 'Receita Federal Bulk',
      icon: '📋',
      category: 'source',
      badge: 'bulk csv',
      description: 'dadosabertos.rfb.gov.br — CNPJ dumps',
      stats: [
        { label: 'Socios file', value: '~2 GB' },
        { label: 'Empresas file', value: '~3 GB' },
      ],
    },
  },
  {
    id: 'ext-rss',
    type: 'pipeline',
    position: { x: X.sources, y: 1030 },
    data: {
      label: 'RSS News Feeds',
      icon: '📡',
      category: 'source',
      badge: '7 feeds',
      description: 'Folha, G1, Estadão, Congresso em Foco…',
      stats: [
        { label: 'Daemon loop', value: 'every 6h' },
      ],
    },
  },
  {
    id: 'ext-wayback',
    type: 'pipeline',
    position: { x: X.sources, y: 1190 },
    data: {
      label: 'Wayback CDX',
      icon: '🌐',
      category: 'source',
      badge: 'archive',
      description: 'web.archive.org/cdx — URL index',
      stats: [
        { label: 'Domains', value: '8 news outlets' },
        { label: 'Year range', value: '2010 → 2025' },
      ],
    },
  },
  {
    id: 'ext-wikipedia',
    type: 'pipeline',
    position: { x: X.sources, y: 1350 },
    data: {
      label: 'Wikipedia PT',
      icon: '📖',
      category: 'api',
      badge: 'rest api',
      description: 'pt.wikipedia.org — summaries & search',
      stats: [
        { label: 'Auth', value: 'no key needed' },
      ],
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // COLUMN 2 — Source Clients (src/sources/)
  // ═══════════════════════════════════════════════════════════════
  {
    id: 'cli-camara',
    type: 'pipeline',
    position: { x: X.clients, y: 40 },
    data: {
      label: 'camara.py',
      icon: '🔌',
      category: 'model',
      badge: 'client',
      description: 'Deputies, votes, propositions, parties',
      stats: [
        { label: 'Lines', value: '465' },
      ],
    },
  },
  {
    id: 'cli-senado',
    type: 'pipeline',
    position: { x: X.clients, y: 220 },
    data: {
      label: 'senado.py',
      icon: '🔌',
      category: 'model',
      badge: 'client',
      description: 'Current senators open data',
      stats: [
        { label: 'Lines', value: '146' },
      ],
    },
  },
  {
    id: 'cli-tse',
    type: 'pipeline',
    position: { x: X.clients, y: 380 },
    data: {
      label: 'tse.py',
      icon: '🔌',
      category: 'model',
      badge: 'client',
      description: 'Downloads ZIP/CSV, parses 50-col TSE files',
      stats: [
        { label: 'Lines', value: '361' },
      ],
    },
  },
  {
    id: 'cli-wikidata',
    type: 'pipeline',
    position: { x: X.clients, y: 550 },
    data: {
      label: 'wikidata.py',
      icon: '🔌',
      category: 'model',
      badge: 'client',
      description: 'SPARQL queries for politicians & events',
      stats: [
        { label: 'Lines', value: '879' },
      ],
    },
  },
  {
    id: 'cli-csv',
    type: 'pipeline',
    position: { x: X.clients, y: 710 },
    data: {
      label: 'csv_importer.py',
      icon: '🔌',
      category: 'model',
      badge: 'client',
      description: 'Generic CSV → politicians, maps 20+ tribunals',
      stats: [
        { label: 'Lines', value: '183' },
      ],
    },
  },
  {
    id: 'cli-rss',
    type: 'pipeline',
    position: { x: X.clients, y: 1030 },
    data: {
      label: 'rss.py',
      icon: '🔌',
      category: 'model',
      badge: 'client',
      description: 'Aggregator for 7+ Brazilian news feeds',
      stats: [
        { label: 'Lines', value: '250' },
      ],
    },
  },
  {
    id: 'cli-article',
    type: 'pipeline',
    position: { x: X.clients, y: 1190 },
    data: {
      label: 'article_extractor.py',
      icon: '🔌',
      category: 'model',
      badge: 'client',
      description: 'trafilatura — full-text extract, min 80 words',
      stats: [
        { label: 'Lines', value: '177' },
      ],
    },
  },
  {
    id: 'cli-wikipedia',
    type: 'pipeline',
    position: { x: X.clients, y: 1350 },
    data: {
      label: 'wikipedia.py',
      icon: '🔌',
      category: 'model',
      badge: 'client',
      description: 'PT Wikipedia summaries & search',
      stats: [
        { label: 'Lines', value: '205' },
      ],
    },
  },
  {
    id: 'cli-cache',
    type: 'pipeline',
    position: { x: X.clients, y: 870 },
    data: {
      label: 'api_cache.py',
      icon: '💾',
      category: 'store',
      badge: 'cache',
      description: 'SQLite response cache with TTL + offline',
      stats: [
        { label: 'Câmara TTL', value: '24h' },
        { label: 'RSS TTL', value: '30min' },
      ],
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // COLUMN 3 — Seed & Ingest Scripts
  // ═══════════════════════════════════════════════════════════════
  {
    id: 'scr-seed',
    type: 'pipeline',
    position: { x: X.scripts, y: 40 },
    data: {
      label: 'seed_db.py',
      icon: '⚙️',
      category: 'script',
      badge: 'master seed',
      description: 'Câmara + Senado + TSE + Wikidata → all tables',
      stats: [
        { label: 'Sources', value: '4 APIs' },
        { label: 'Lines', value: '143' },
      ],
    },
  },
  {
    id: 'scr-deputies',
    type: 'pipeline',
    position: { x: X.scripts, y: 210 },
    data: {
      label: 'seed_deputies.py',
      icon: '⚙️',
      category: 'script',
      badge: 'pipeline',
      description: 'Bulk-import votes + CEAP expenses',
      stats: [
        { label: 'Deputies', value: '632' },
        { label: 'Expenses', value: '171,321' },
        { label: 'Votes', value: '4,996' },
      ],
    },
  },
  {
    id: 'scr-eleicoes',
    type: 'pipeline',
    position: { x: X.scripts, y: 400 },
    data: {
      label: 'seed_eleicoes.py',
      icon: '⚙️',
      category: 'script',
      badge: 'pipeline',
      description: 'TSE CSV → politicians + election results',
      stats: [
        { label: 'Politicians', value: '13,724' },
        { label: 'Elections', value: '12,820' },
      ],
    },
  },
  {
    id: 'scr-magistrados',
    type: 'pipeline',
    position: { x: X.scripts, y: 570 },
    data: {
      label: 'seed_magistrados.py',
      icon: '⚙️',
      category: 'script',
      badge: 'pipeline',
      description: 'CSV import of judges (STF, STJ, TRFs)',
      stats: [
        { label: 'Magistrates', value: '~230' },
      ],
    },
  },
  {
    id: 'scr-secretarios',
    type: 'pipeline',
    position: { x: X.scripts, y: 730 },
    data: {
      label: 'seed_secretarios.py',
      icon: '⚙️',
      category: 'script',
      badge: 'pipeline',
      description: 'Câmara bulk JSON → cabinet staff snapshots',
      stats: [
        { label: 'Secretários', value: '~10,000' },
        { label: 'CNE assessores', value: '~1,700' },
        { label: 'Staff total', value: '22,338' },
      ],
    },
  },
  {
    id: 'scr-cnpj',
    type: 'pipeline',
    position: { x: X.scripts, y: 900 },
    data: {
      label: 'lookup_cnpj.py',
      icon: '⚙️',
      category: 'script',
      badge: 'pipeline',
      description: 'CNPJ enrichment + red-flag detection',
      stats: [
        { label: 'CNPJs queried', value: '16,503' },
        { label: 'Flags found', value: '1,503' },
      ],
    },
  },
  {
    id: 'scr-rf',
    type: 'pipeline',
    position: { x: X.scripts, y: 1060 },
    data: {
      label: 'import_rf_bulk.py',
      icon: '⚙️',
      category: 'script',
      badge: 'pipeline',
      description: 'Receita Federal bulk → socios.db + self_dealing flag',
      stats: [
        { label: 'Download', value: '~5 GB' },
      ],
    },
  },
  {
    id: 'scr-rss',
    type: 'pipeline',
    position: { x: X.scripts, y: 1200 },
    data: {
      label: 'ingest_rss.py',
      icon: '⚙️',
      category: 'script',
      badge: 'pipeline',
      description: 'RSS → deduplicate → entity-link → news_items',
      stats: [
        { label: 'Lines', value: '349' },
        { label: 'Mode', value: 'daemon (6h loop)' },
      ],
    },
  },
  {
    id: 'scr-historical',
    type: 'pipeline',
    position: { x: X.scripts, y: 1360 },
    data: {
      label: 'ingest_historical.py',
      icon: '⚙️',
      category: 'script',
      badge: 'pipeline',
      description: 'Wayback CDX + GDELT + Querido Diário',
      stats: [
        { label: 'Politicians', value: '1,307' },
        { label: 'Lines', value: '1,244' },
      ],
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // COLUMN 4 — Databases
  // ═══════════════════════════════════════════════════════════════
  {
    id: 'db-history',
    type: 'pipeline',
    position: { x: X.dbs, y: 300 },
    data: {
      label: 'history.db',
      icon: '🗄️',
      category: 'store',
      badge: 'sqlite',
      description: 'Central DB — 9 tables, 956-line store',
      stats: [
        { label: 'Politicians', value: '13,724' },
        { label: 'Expenses', value: '171,321' },
        { label: 'Companies', value: '16,502' },
        { label: 'Votes', value: '4,996' },
        { label: 'Elections', value: '12,820' },
        { label: 'Cabinet staff', value: '22,338' },
        { label: 'News items', value: 'ingesting…' },
      ],
    },
  },
  {
    id: 'db-cache',
    type: 'pipeline',
    position: { x: X.dbs, y: 680 },
    data: {
      label: 'api_cache.db',
      icon: '💾',
      category: 'store',
      badge: 'sqlite',
      description: 'API response cache with TTL + offline fallback',
      stats: [
        { label: 'Strategy', value: 'TTL per source' },
      ],
    },
  },
  {
    id: 'db-socios',
    type: 'pipeline',
    position: { x: X.dbs, y: 850 },
    data: {
      label: 'socios.db',
      icon: '💾',
      category: 'store',
      badge: 'sqlite',
      description: 'Receita Federal partner data (socios + empresas)',
      stats: [
        { label: 'Tables', value: 'socios, empresas' },
        { label: 'Cross-ref', value: 'CPF → politician' },
      ],
    },
  },
  {
    id: 'db-drafts',
    type: 'pipeline',
    position: { x: X.dbs, y: 1030 },
    data: {
      label: 'drafts.db',
      icon: '📝',
      category: 'store',
      badge: 'sqlite',
      description: 'Content pipeline — editorial drafts',
      stats: [
        { label: 'States', value: 'raw → draft → approved' },
        { label: 'Types', value: '7 content types' },
      ],
    },
  },
  {
    id: 'db-schedule',
    type: 'pipeline',
    position: { x: X.dbs, y: 1190 },
    data: {
      label: 'schedule.db',
      icon: '📅',
      category: 'store',
      badge: 'sqlite',
      description: 'Post scheduler queue',
      stats: [
        { label: 'States', value: 'pending → done/failed' },
      ],
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // COLUMN 5 — Models & Knowledge Base
  // ═══════════════════════════════════════════════════════════════
  {
    id: 'mod-history',
    type: 'pipeline',
    position: { x: X.models, y: 100 },
    data: {
      label: 'History Models',
      icon: '📐',
      category: 'model',
      badge: 'pydantic',
      description: 'src/history/models.py — 10 models',
      stats: [
        { label: 'Politician', value: 'roles, CPF, tags' },
        { label: 'Expense', value: 'CNPJ → company' },
        { label: 'CompanyProfile', value: 'flags[]' },
        { label: 'NewsItem', value: 'mentions[]' },
        { label: 'Vote / Election', value: 'per-session' },
        { label: 'CabinetStaff', value: 'snapshots' },
      ],
    },
  },
  {
    id: 'kb-yaml',
    type: 'pipeline',
    position: { x: X.models, y: 440 },
    data: {
      label: 'Knowledge Base',
      icon: '📚',
      category: 'source',
      badge: 'yaml',
      description: 'data/ — institutions, figures, events, glossary',
      stats: [
        { label: 'Institutions', value: '7 (STF, MPF, TSE…)' },
        { label: 'Figures', value: '3 (Lula, Moraes…)' },
        { label: 'Events', value: '3 (Lava Jato…)' },
        { label: 'Glossary', value: 'political/legal terms' },
      ],
    },
  },
  {
    id: 'kb-models',
    type: 'pipeline',
    position: { x: X.models, y: 680 },
    data: {
      label: 'KB Models',
      icon: '📐',
      category: 'model',
      badge: 'pydantic',
      description: 'src/knowledge/models.py — 8 primary models',
      stats: [
        { label: 'Models', value: 'Institution, Figure…' },
        { label: 'Enums', value: '7' },
        { label: 'Sub-models', value: '10+' },
      ],
    },
  },
  {
    id: 'kb-graph',
    type: 'pipeline',
    position: { x: X.models, y: 880 },
    data: {
      label: 'Knowledge Graph',
      icon: '🕸️',
      category: 'output',
      badge: 'networkx',
      description: 'DiGraph — institutions, figures, events as nodes',
      stats: [
        { label: 'Export', value: 'JSON (D3) + GEXF' },
        { label: 'Edges', value: 'relationships YAML' },
      ],
    },
  },
  {
    id: 'kb-search',
    type: 'pipeline',
    position: { x: X.models, y: 1060 },
    data: {
      label: 'KB Search',
      icon: '🔍',
      category: 'model',
      badge: 'full-text',
      description: 'Scored full-text search across all entities',
      stats: [
        { label: 'Lines', value: '144' },
      ],
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // COLUMN 6 — AI + Content + Visuals Pipeline
  // ═══════════════════════════════════════════════════════════════
  {
    id: 'ai-llm',
    type: 'pipeline',
    position: { x: X.process, y: 40 },
    data: {
      label: 'LLM Client',
      icon: '🤖',
      category: 'api',
      badge: 'claude / gpt',
      description: 'src/ai/llm.py — Anthropic + OpenAI fallback',
      stats: [
        { label: 'Primary', value: 'Claude Sonnet' },
        { label: 'Fallback', value: 'GPT-4o' },
      ],
    },
  },
  {
    id: 'ai-summarizer',
    type: 'pipeline',
    position: { x: X.process, y: 220 },
    data: {
      label: 'Summarizer',
      icon: '📝',
      category: 'script',
      badge: 'ai',
      description: 'Raw articles → structured PT-BR summaries',
      stats: [
        { label: 'Sections', value: 'O que / Por que / Contexto' },
        { label: 'Max tokens', value: '1,000' },
      ],
    },
  },
  {
    id: 'ai-explainer',
    type: 'pipeline',
    position: { x: X.process, y: 400 },
    data: {
      label: 'Explainer',
      icon: '🎓',
      category: 'script',
      badge: 'ai',
      description: 'Educational explainers for institutions & figures',
      stats: [
        { label: 'Templates', value: '5 YAML prompts' },
        { label: 'Types', value: 'institution, profile, timeline' },
      ],
    },
  },
  {
    id: 'content-draft',
    type: 'pipeline',
    position: { x: X.process, y: 590 },
    data: {
      label: 'Content Pipeline',
      icon: '✍️',
      category: 'script',
      badge: 'editorial',
      description: 'ContentDraft state machine + review queue',
      stats: [
        { label: 'States', value: 'raw → approved' },
        { label: 'Types', value: '7 (news, profile, timeline…)' },
        { label: 'Formats', value: 'IG, X, Threads, Newsletter' },
      ],
    },
  },
  {
    id: 'vis-carousel',
    type: 'pipeline',
    position: { x: X.process, y: 790 },
    data: {
      label: 'Carousel Generator',
      icon: '🎨',
      category: 'output',
      badge: 'pillow',
      description: 'Instagram carousel slides (1080×1080)',
      stats: [
        { label: 'Max slides', value: '10' },
      ],
    },
  },
  {
    id: 'vis-profile',
    type: 'pipeline',
    position: { x: X.process, y: 940 },
    data: {
      label: 'Profile Card',
      icon: '🎨',
      category: 'output',
      badge: 'pillow',
      description: 'Figure profile — name, party, facts, controversy',
      stats: [
        { label: 'Size', value: '1080×1080' },
      ],
    },
  },
  {
    id: 'vis-timeline',
    type: 'pipeline',
    position: { x: X.process, y: 1080 },
    data: {
      label: 'Timeline',
      icon: '🎨',
      category: 'output',
      badge: 'pillow',
      description: 'Horizontal event timeline (1200×675)',
    },
  },
  {
    id: 'vis-diagram',
    type: 'pipeline',
    position: { x: X.process, y: 1210 },
    data: {
      label: 'Flowchart / Network',
      icon: '🎨',
      category: 'output',
      badge: 'pillow + mpl',
      description: 'Institutional diagram + relationship graph',
      stats: [
        { label: 'Engine', value: 'NetworkX + matplotlib' },
      ],
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // COLUMN 7 — Publishing & Final Output
  // ═══════════════════════════════════════════════════════════════
  {
    id: 'pub-instagram',
    type: 'pipeline',
    position: { x: X.output, y: 220 },
    data: {
      label: 'Instagram API',
      icon: '📸',
      category: 'api',
      badge: 'graph api',
      description: 'Single image + carousel (≤10 slides)',
      stats: [
        { label: 'Rate limit', value: '25 posts/24h' },
        { label: 'Image', value: '1080×1080' },
      ],
    },
  },
  {
    id: 'pub-twitter',
    type: 'pipeline',
    position: { x: X.output, y: 420 },
    data: {
      label: 'X / Twitter API',
      icon: '🐦',
      category: 'api',
      badge: 'v2 + tweepy',
      description: 'Tweets + threads + media upload',
      stats: [
        { label: 'Free tier', value: '1,500 tweets/mo' },
        { label: 'Thread max', value: '20 tweets' },
      ],
    },
  },
  {
    id: 'pub-scheduler',
    type: 'pipeline',
    position: { x: X.output, y: 620 },
    data: {
      label: 'Post Scheduler',
      icon: '📅',
      category: 'script',
      badge: 'queue',
      description: 'Schedule posts for future publishing',
      stats: [
        { label: 'DB', value: 'schedule.db' },
      ],
    },
  },
  {
    id: 'pub-metrics',
    type: 'pipeline',
    position: { x: X.output, y: 800 },
    data: {
      label: 'Analytics / Metrics',
      icon: '📊',
      category: 'output',
      badge: 'tracking',
      description: 'Impressions, reach, likes over time',
      stats: [
        { label: 'Platforms', value: 'IG + X' },
      ],
    },
  },
  {
    id: 'out-flags',
    type: 'pipeline',
    position: { x: X.output, y: 1000 },
    data: {
      label: 'Red-Flag Detection',
      icon: '🚩',
      category: 'output',
      badge: 'analysis',
      description: 'Automated anomaly detection on expenses',
      stats: [
        { label: 'Shared supplier', value: '588' },
        { label: 'High value', value: '546' },
        { label: 'Inactive CNPJ', value: '369' },
        { label: 'Self-dealing', value: 'CPF cross-ref' },
      ],
    },
  },
  {
    id: 'out-images',
    type: 'pipeline',
    position: { x: X.output, y: 1200 },
    data: {
      label: 'output/images/',
      icon: '🖼️',
      category: 'output',
      badge: 'png',
      description: 'Generated social media images',
      stats: [
        { label: 'Formats', value: 'IG, X, story' },
      ],
    },
  },

  // ═══════════════════════════════════════════════════════════════
  // CLI (spanning bottom)
  // ═══════════════════════════════════════════════════════════════
  {
    id: 'cli-typer',
    type: 'pipeline',
    position: { x: X.models, y: 1280 },
    data: {
      label: 'CLI — anticorrupt',
      icon: '⌨️',
      category: 'script',
      badge: 'typer',
      description: '9 sub-commands: kb, generate, review, publish, visuals, sources, history, dashboard',
      stats: [
        { label: 'Entry', value: 'src/cli/app.py' },
        { label: 'history.py', value: '915 lines' },
        { label: 'publish.py', value: '518 lines' },
      ],
    },
  },
];

export default nodes;
