// ═══════════════════════════════════════════════════════════════════
// Anti-Corrupt — Full Pipeline Edges
// ═══════════════════════════════════════════════════════════════════

import { MarkerType } from '@xyflow/react';

const COLORS = {
  source: '#4a9eff',
  api:    '#ff6b6b',
  script: '#b380ff',
  store:  '#4ecdc4',
  model:  '#45b7d1',
  output: '#ffa726',
};

const marker = {
  type: MarkerType.ArrowClosed,
  color: '#58a6ff',
  width: 14,
  height: 14,
};

const base = {
  animated:  true,
  markerEnd: marker,
  type:      'smoothstep',
  style:     { strokeWidth: 1.6, opacity: 0.55 },
};

const e = (source, target, color, label) => ({
  id: `${source}-${target}`,
  source,
  target,
  ...base,
  style: { ...base.style, stroke: color },
  ...(label ? { label, labelStyle: { fill: '#8b949e', fontSize: 9, fontWeight: 500 } } : {}),
});

const edges = [
  // ═══════════════════════════════════════════════════════════════
  // External Sources → Source Clients
  // ═══════════════════════════════════════════════════════════════
  e('ext-camara',    'cli-camara',    COLORS.api,    'REST'),
  e('ext-senado',    'cli-senado',    COLORS.api,    'REST'),
  e('ext-tse',       'cli-tse',       COLORS.source, 'CSV/ZIP'),
  e('ext-wikidata',  'cli-wikidata',  COLORS.api,    'SPARQL'),
  e('ext-brasil',    'cli-csv',       COLORS.api,    'JSON'),
  e('ext-rss',       'cli-rss',       COLORS.source, 'XML'),
  e('ext-wayback',   'cli-article',   COLORS.source, 'CDX → URL'),
  e('ext-wikipedia', 'cli-wikipedia', COLORS.api,    'REST'),

  // ═══════════════════════════════════════════════════════════════
  // Source Clients → Cache
  // ═══════════════════════════════════════════════════════════════
  e('cli-camara',    'cli-cache', COLORS.store),
  e('cli-senado',    'cli-cache', COLORS.store),
  e('cli-tse',       'cli-cache', COLORS.store),
  e('cli-rss',       'cli-cache', COLORS.store),
  e('cli-wikidata',  'cli-cache', COLORS.store),

  // Cache → cache DB
  e('cli-cache',     'db-cache',  COLORS.store,  'persist'),

  // ═══════════════════════════════════════════════════════════════
  // Source Clients → Seed/Ingest Scripts
  // ═══════════════════════════════════════════════════════════════
  e('cli-camara',    'scr-seed',        COLORS.model,   'deputies'),
  e('cli-camara',    'scr-deputies',    COLORS.model,   'votes, expenses'),
  e('cli-camara',    'scr-secretarios', COLORS.model,   'cabinet JSON'),
  e('cli-senado',    'scr-seed',        COLORS.model,   'senators'),
  e('cli-tse',       'scr-eleicoes',    COLORS.model,   'parsed rows'),
  e('cli-wikidata',  'scr-seed',        COLORS.model,   'events'),
  e('cli-csv',       'scr-magistrados', COLORS.model,   'judges'),
  e('cli-rss',       'scr-rss',         COLORS.model,   'entries'),
  e('cli-article',   'scr-historical',  COLORS.model,   'full text'),

  // BrasilAPI → CNPJ enrichment
  e('ext-brasil',    'scr-cnpj',        COLORS.api,     'CNPJ → JSON'),

  // Receita Federal → RF bulk script
  e('ext-rf',        'scr-rf',          COLORS.source,  'bulk CSV'),

  // ═══════════════════════════════════════════════════════════════
  // Seed/Ingest Scripts → Databases
  // ═══════════════════════════════════════════════════════════════
  e('scr-seed',        'db-history', COLORS.script, 'politicians, events'),
  e('scr-deputies',    'db-history', COLORS.script, 'votes, expenses'),
  e('scr-eleicoes',    'db-history', COLORS.script, 'elections'),
  e('scr-magistrados', 'db-history', COLORS.script, 'judges'),
  e('scr-secretarios', 'db-history', COLORS.script, 'cabinet staff'),
  e('scr-cnpj',        'db-history', COLORS.script, 'companies + flags'),
  e('scr-rss',         'db-history', COLORS.script, 'news_items'),
  e('scr-historical',  'db-history', COLORS.script, 'news_items'),
  e('scr-rf',          'db-socios',  COLORS.script, 'socios, empresas'),

  // ═══════════════════════════════════════════════════════════════
  // Databases → Models & Knowledge
  // ═══════════════════════════════════════════════════════════════
  e('db-history',    'mod-history',   COLORS.store,  'ORM read/write'),
  e('db-socios',     'mod-history',   COLORS.store,  'self-dealing flag'),
  e('kb-yaml',       'kb-models',     COLORS.source, 'load/validate'),
  e('kb-models',     'kb-graph',      COLORS.model,  'DiGraph build'),
  e('kb-models',     'kb-search',     COLORS.model,  'index'),

  // ═══════════════════════════════════════════════════════════════
  // Models → AI + Content Pipeline
  // ═══════════════════════════════════════════════════════════════
  e('mod-history',   'ai-summarizer',   COLORS.model,  'news_items'),
  e('mod-history',   'ai-explainer',    COLORS.model,  'politicians'),
  e('mod-history',   'out-flags',       COLORS.model,  'expense flags'),
  e('ai-llm',       'ai-summarizer',   COLORS.api,    'Claude API'),
  e('ai-llm',       'ai-explainer',    COLORS.api,    'Claude API'),
  e('ai-summarizer', 'content-draft',  COLORS.script, 'summaries'),
  e('ai-explainer',  'content-draft',  COLORS.script, 'explainers'),

  // Content → Drafts DB
  e('content-draft', 'db-drafts',      COLORS.store,  'persist drafts'),

  // Content → Visual generators
  e('content-draft', 'vis-carousel',   COLORS.script, 'approved'),
  e('content-draft', 'vis-profile',    COLORS.script, 'approved'),
  e('content-draft', 'vis-timeline',   COLORS.script, 'approved'),
  e('content-draft', 'vis-diagram',    COLORS.script, 'approved'),

  // Visuals → output images
  e('vis-carousel',  'out-images',     COLORS.output, 'PNG'),
  e('vis-profile',   'out-images',     COLORS.output, 'PNG'),
  e('vis-timeline',  'out-images',     COLORS.output, 'PNG'),
  e('vis-diagram',   'out-images',     COLORS.output, 'PNG'),

  // ═══════════════════════════════════════════════════════════════
  // Publishing
  // ═══════════════════════════════════════════════════════════════
  e('out-images',    'pub-instagram',  COLORS.output, 'upload'),
  e('out-images',    'pub-twitter',    COLORS.output, 'upload'),
  e('content-draft', 'pub-twitter',    COLORS.script, 'text'),
  e('pub-scheduler', 'pub-instagram',  COLORS.script, 'queue'),
  e('pub-scheduler', 'pub-twitter',    COLORS.script, 'queue'),
  e('pub-scheduler', 'db-schedule',    COLORS.store,  'persist'),
  e('pub-instagram', 'pub-metrics',    COLORS.api,    'insights'),
  e('pub-twitter',   'pub-metrics',    COLORS.api,    'analytics'),

  // ═══════════════════════════════════════════════════════════════
  // Knowledge Graph → exports
  // ═══════════════════════════════════════════════════════════════
  e('kb-graph',      'vis-diagram',    COLORS.model,  'DiGraph'),

  // CLI spans the whole pipeline
  e('cli-typer',     'mod-history',    COLORS.script, 'history cmds'),
  e('cli-typer',     'content-draft',  COLORS.script, 'content cmds'),
  e('cli-typer',     'pub-scheduler',  COLORS.script, 'publish cmds'),
  e('cli-typer',     'kb-yaml',        COLORS.script, 'kb cmds'),
];

export default edges;
