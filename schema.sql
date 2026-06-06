-- Profound snapshot DB — schema (SQLite)
-- Single point-in-time snapshot; no date columns. Ranks derived in views.
-- Apply:  sqlite3 profound.db < schema.sql

PRAGMA foreign_keys = ON;

-- ---------- reference / dimension tables ----------
DROP TABLE IF EXISTS category;
CREATE TABLE category (id TEXT PRIMARY KEY, name TEXT);

DROP TABLE IF EXISTS model;
CREATE TABLE model (id TEXT PRIMARY KEY, name TEXT);

DROP TABLE IF EXISTS region;
CREATE TABLE region (id TEXT PRIMARY KEY, name TEXT);

DROP TABLE IF EXISTS topic;
CREATE TABLE topic (id TEXT PRIMARY KEY, name TEXT);

DROP TABLE IF EXISTS tag;
CREATE TABLE tag (id TEXT PRIMARY KEY, name TEXT);

DROP TABLE IF EXISTS domain;
CREATE TABLE domain (id TEXT PRIMARY KEY, name TEXT);

DROP TABLE IF EXISTS prompt;
CREATE TABLE prompt (
  id            TEXT PRIMARY KEY,
  category_id   TEXT REFERENCES category(id),
  text          TEXT,
  status        TEXT,
  topic_id      TEXT REFERENCES topic(id),
  language      TEXT,
  analysis_types TEXT,                 -- JSON array
  profound_persona_id TEXT
);
CREATE INDEX IF NOT EXISTS ix_prompt_text ON prompt(text);

DROP TABLE IF EXISTS prompt_tag;
CREATE TABLE prompt_tag (
  prompt_id TEXT REFERENCES prompt(id),
  tag_id    TEXT REFERENCES tag(id),
  PRIMARY KEY (prompt_id, tag_id)
);

-- ---------- custom persona overlay (your own layer) ----------
DROP TABLE IF EXISTS persona;
CREATE TABLE persona (
  id      TEXT PRIMARY KEY,
  name    TEXT NOT NULL,
  profile TEXT,                        -- JSON
  source  TEXT DEFAULT 'custom'        -- 'custom' | 'profound'
);

DROP TABLE IF EXISTS prompt_persona;
CREATE TABLE prompt_persona (
  prompt_id  TEXT REFERENCES prompt(id),
  persona_id TEXT REFERENCES persona(id),
  PRIMARY KEY (prompt_id, persona_id)
);

-- ---------- fact tables (one snapshot each) ----------

-- (1) visibility leaderboard — every tracked brand
DROP TABLE IF EXISTS fact_visibility;
CREATE TABLE fact_visibility (
  asset_name TEXT,
  model_id   TEXT REFERENCES model(id),
  region_id  TEXT REFERENCES region(id),
  visibility_score REAL,
  share_of_voice   REAL,
  average_position REAL,
  mentions_count   INTEGER,
  executions       INTEGER,
  PRIMARY KEY (asset_name, model_id, region_id)
);

-- (2a) prompt-level visibility — owned brand ChatGPT only
DROP TABLE IF EXISTS fact_prompt_visibility;
CREATE TABLE fact_prompt_visibility (
  prompt_id  TEXT REFERENCES prompt(id),
  model_id   TEXT REFERENCES model(id),
  region_id  TEXT REFERENCES region(id),
  visibility_score REAL,
  share_of_voice   REAL,
  average_position REAL,
  executions       INTEGER,
  PRIMARY KEY (prompt_id, model_id, region_id)
);

-- (2b) prompt-level citations (domain grain, feeds the prompt view)
DROP TABLE IF EXISTS fact_prompt_citation;
CREATE TABLE fact_prompt_citation (
  prompt_id  TEXT REFERENCES prompt(id),
  root_domain TEXT,
  model_id   TEXT REFERENCES model(id),
  region_id  TEXT REFERENCES region(id),
  citation_share REAL,
  count          INTEGER,
  PRIMARY KEY (prompt_id, root_domain, model_id, region_id)
);

-- (3) query fan-out structure — parent prompt -> child queries
DROP TABLE IF EXISTS fact_query_fanout;
CREATE TABLE fact_query_fanout (
  prompt_id  TEXT REFERENCES prompt(id),
  query      TEXT,
  model_id   TEXT REFERENCES model(id),
  region_id  TEXT REFERENCES region(id),
  total_fanouts         REAL,
  fanouts_per_execution REAL,
  share                 REAL,
  PRIMARY KEY (prompt_id, query, model_id, region_id)
);

-- (4) sentiment — most granular
DROP TABLE IF EXISTS fact_sentiment;
CREATE TABLE fact_sentiment (
  asset_name TEXT,
  model_id   TEXT REFERENCES model(id),
  region_id  TEXT REFERENCES region(id),
  topic_id   TEXT REFERENCES topic(id),
  theme      TEXT,
  sentiment_type TEXT,                 -- positive | negative | neutral
  positive    REAL,                    -- weighted, can exceed occurrences
  negative    REAL,
  occurrences INTEGER,
  PRIMARY KEY (asset_name, model_id, region_id, topic_id, theme, sentiment_type)
);

-- (5) citations — most granular (url level)
DROP TABLE IF EXISTS fact_citation;
CREATE TABLE fact_citation (
  prompt_id  TEXT REFERENCES prompt(id),
  model_id   TEXT REFERENCES model(id),
  region_id  TEXT REFERENCES region(id),
  root_domain TEXT,
  url         TEXT,
  citation_category TEXT,
  citation_share REAL,
  count          INTEGER,
  PRIMARY KEY (prompt_id, model_id, region_id, url)
);

CREATE INDEX IF NOT EXISTS ix_pv_prompt  ON fact_prompt_visibility(prompt_id);
CREATE INDEX IF NOT EXISTS ix_pc_prompt  ON fact_prompt_citation(prompt_id);
CREATE INDEX IF NOT EXISTS ix_cit_prompt ON fact_citation(prompt_id);
CREATE INDEX IF NOT EXISTS ix_fan_prompt ON fact_query_fanout(prompt_id);
CREATE INDEX IF NOT EXISTS ix_vis_asset  ON fact_visibility(asset_name);

-- ---------- views (ranks derived; persona overlay) ----------

DROP VIEW IF EXISTS vw_visibility_ranked;
CREATE VIEW vw_visibility_ranked AS
SELECT v.asset_name, m.name AS model, r.name AS region,
       v.visibility_score, v.share_of_voice, v.average_position,
       v.mentions_count, v.executions,
       RANK() OVER (PARTITION BY v.model_id, v.region_id
                    ORDER BY v.visibility_score DESC) AS visibility_rank
FROM fact_visibility v
LEFT JOIN model  m ON m.id = v.model_id
LEFT JOIN region r ON r.id = v.region_id;

-- Deliverable #2: consolidated prompt view (ChatGPT-owned), persona-overlaid
DROP VIEW IF EXISTS vw_prompt_overview;
CREATE VIEW vw_prompt_overview AS
WITH vis AS (
  SELECT prompt_id, model_id, region_id,
         SUM(visibility_score) AS visibility_score,
         AVG(share_of_voice)   AS share_of_voice,
         AVG(average_position) AS average_position,
         SUM(executions)       AS executions
  FROM fact_prompt_visibility GROUP BY 1,2,3
),
cit AS (
  SELECT prompt_id, model_id, region_id,
         AVG(citation_share) AS citation_share,
         SUM(count)          AS citation_count
  FROM fact_prompt_citation GROUP BY 1,2,3
)
SELECT
  p.id   AS prompt_id,
  p.text AS prompt,
  t.name AS topic,
  (SELECT GROUP_CONCAT(tg.name, ', ') FROM prompt_tag pt JOIN tag tg ON tg.id=pt.tag_id WHERE pt.prompt_id=p.id) AS tags,
  (SELECT GROUP_CONCAT(pe.name, ', ') FROM prompt_persona pp JOIN persona pe ON pe.id=pp.persona_id WHERE pp.prompt_id=p.id) AS personas,
  m.name AS model,
  r.name AS region,
  vis.visibility_score,
  RANK() OVER (PARTITION BY vis.model_id, vis.region_id ORDER BY vis.visibility_score DESC) AS visibility_rank,
  vis.share_of_voice,
  vis.average_position,
  cit.citation_share,
  RANK() OVER (PARTITION BY vis.model_id, vis.region_id ORDER BY cit.citation_share DESC) AS citation_rank,
  vis.executions AS prompt_volume
FROM prompt p
JOIN vis            ON vis.prompt_id = p.id
LEFT JOIN cit       ON cit.prompt_id = p.id AND cit.model_id = vis.model_id AND cit.region_id = vis.region_id
LEFT JOIN topic t   ON t.id = p.topic_id
LEFT JOIN model m   ON m.id = vis.model_id
LEFT JOIN region r  ON r.id = vis.region_id;
