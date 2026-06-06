# Profound → SQLite Ingestion Plan (single snapshot)

Plan for landing Profound report data into a local **SQLite** database at the five requested grains, with a **custom persona overlay** and **ranks computed in views**.

**Mode:** one **point-in-time snapshot** — no time series, no `date` dimension, no daily loop, no scheduling. Each report is pulled once, aggregated over the window, and loaded.

**Decisions locked (2026-06-06):**
- Snapshot window: **2026-05-30 → 2026-06-06** (last 7 days). REST `end` is inclusive; MCP `end` is exclusive — for MCP pass `end_date=2026-06-07`.
- Owned brand for the prompt view: **ChatGPT** (`asset_filter="ChatGPT"`).
- `prompt_volume` = **executions** (prompt runs), not fan-out count.
- Ranks: derived in SQL **views** (`RANK() OVER (...)`), never stored.

Validated against org **Profound Marketing Engineer Hackathon** (`1680a859-ec50-451a-a781-995de61d9a40`), category **Frontier Models** (`7943f355-67f3-4792-b172-981db56ef33c`).

---

## 0. The three facts that drive every design choice

1. **Metrics come back ALPHABETICALLY ordered**, on both MCP and REST — *not* in the order requested. Each row is `{dimensions:[...], metrics:[...]}`; zip `metrics` against the response's own metric-label list. Hardcoding positions silently corrupts data.
2. **No "rank" metric exists.** Visibility rank / citation rank are derived by ordering within a partition → SQL views (`RANK() OVER (...)`). SQLite ≥ 3.25 supports window functions.
3. **Two surfaces are REST-only** (`https://api.tryprofound.com`, `X-API-Key`): **Query Fanouts** (no MCP tool) and **granular Sentiment** (MCP `get_sentiment_report` has no `dimensions` arg).

### Response envelopes
- **MCP:** `{rows:[{dimensions,metrics}], metrics:[labels], dimensions:[labels], total_rows, next_cursor}` — paginate with `next_cursor`.
- **REST:** `{info:{total_rows, query:{dimensions, metrics, pagination}}, data:[{dimensions,metrics}]}` — paginate with `pagination.offset`/`limit` (limit up to 10000).

Dates: date-only, EST-based. Since this is a snapshot, dates appear **only in the request window**, never as a stored column.

Rate limit: 600 req/hr/key — a 7-day snapshot is well within budget; page large and back off on 429.

---

## 1. Stack
| Piece | Choice |
|---|---|
| DB | SQLite file `profound.db` in this folder |
| Ingestion | Python — Profound SDK (`pip install profound`) for reads + `requests` for the two REST-only surfaces |
| Loader | One `flatten_*()` helper (zips metrics by label) → `INSERT OR REPLACE` per fact's natural key |
| Run | One-shot script; re-run replaces the snapshot |
| Ranks/overlay | SQL views (window functions) |

```python
def flatten_mcp(resp):
    mets, dims = resp["metrics"], resp["dimensions"]
    return [{**dict(zip(dims, r["dimensions"])), **dict(zip(mets, r["metrics"]))} for r in resp["rows"]]

def flatten_rest(resp):
    q = resp["info"]["query"]; mets, dims = q["metrics"], q["dimensions"]
    return [{**dict(zip(dims, r["dimensions"])), **dict(zip(mets, r["metrics"]))} for r in resp["data"]]
```

---

## 2. Schema

No `date` columns (single snapshot). List fields stored as JSON `TEXT`; tags normalised to a junction table.

### 2.1 Reference / dimension tables (seeded from `list_*`)
```sql
CREATE TABLE category (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE model    (id TEXT PRIMARY KEY, name TEXT);     -- 8
CREATE TABLE region   (id TEXT PRIMARY KEY, name TEXT);     -- 3
CREATE TABLE topic    (id TEXT PRIMARY KEY, name TEXT);     -- 15
CREATE TABLE tag      (id TEXT PRIMARY KEY, name TEXT);
CREATE TABLE domain   (id TEXT PRIMARY KEY, name TEXT);     -- 5

CREATE TABLE prompt (
  id TEXT PRIMARY KEY,
  category_id TEXT REFERENCES category(id),
  text TEXT, status TEXT,
  topic_id TEXT REFERENCES topic(id),
  language TEXT, analysis_types TEXT,        -- JSON array
  profound_persona_id TEXT
);                                            -- 195
CREATE TABLE prompt_tag (
  prompt_id TEXT REFERENCES prompt(id),
  tag_id    TEXT REFERENCES tag(id),
  PRIMARY KEY (prompt_id, tag_id)
);
```

### 2.2 Custom persona overlay (your layer)
```sql
CREATE TABLE persona (
  id TEXT PRIMARY KEY, name TEXT NOT NULL,
  profile TEXT, source TEXT DEFAULT 'custom'   -- 'custom' | 'profound'
);
CREATE TABLE prompt_persona (                  -- attach at prompt grain
  prompt_id  TEXT REFERENCES prompt(id),
  persona_id TEXT REFERENCES persona(id),
  PRIMARY KEY (prompt_id, persona_id)
);
```
Overlay path: any fact → `prompt_id` → `prompt_persona` → `persona`.

### 2.3 Fact tables (one snapshot each)

**(1) Visibility leaderboard** — all tracked brands, for rank/SOV/avg position.
```sql
CREATE TABLE fact_visibility (
  asset_name TEXT, model_id TEXT, region_id TEXT,
  visibility_score REAL, share_of_voice REAL, average_position REAL,
  mentions_count INTEGER, executions INTEGER,
  PRIMARY KEY (asset_name, model_id, region_id)
);
```

**(2) Prompt-level facts** — owned brand = **ChatGPT** (pulled with `asset_filter="ChatGPT"`).
```sql
CREATE TABLE fact_prompt_visibility (          -- ChatGPT only
  prompt_id TEXT, model_id TEXT, region_id TEXT,
  visibility_score REAL, share_of_voice REAL, average_position REAL, executions INTEGER,
  PRIMARY KEY (prompt_id, model_id, region_id)
);
CREATE TABLE fact_prompt_citation (
  prompt_id TEXT, root_domain TEXT, model_id TEXT, region_id TEXT,
  citation_share REAL, count INTEGER,
  PRIMARY KEY (prompt_id, root_domain, model_id, region_id)
);
```

**(3) Query fan-out structure** — parent prompt → child queries.
```sql
CREATE TABLE fact_query_fanout (
  prompt_id TEXT, query TEXT, model_id TEXT, region_id TEXT,
  total_fanouts REAL, fanouts_per_execution REAL, share REAL,
  PRIMARY KEY (prompt_id, query, model_id, region_id)
);
```

**(4) Sentiment — most granular.**
```sql
CREATE TABLE fact_sentiment (
  asset_name TEXT, model_id TEXT, region_id TEXT,
  topic_id TEXT, theme TEXT, sentiment_type TEXT,    -- positive|negative|neutral
  positive REAL, negative REAL, occurrences INTEGER, -- positive/negative WEIGHTED, can exceed occurrences
  PRIMARY KEY (asset_name, model_id, region_id, topic_id, theme, sentiment_type)
);
```

**(5) Citations — most granular (url level).**
```sql
CREATE TABLE fact_citation (
  prompt_id TEXT, model_id TEXT, region_id TEXT,
  root_domain TEXT, url TEXT, citation_category TEXT,
  citation_share REAL, count INTEGER,
  PRIMARY KEY (prompt_id, model_id, region_id, url)
);
```

### 2.4 Views (ranks + persona overlay)
```sql
CREATE VIEW vw_visibility_ranked AS
SELECT v.*, m.name AS model, r.name AS region,
       RANK() OVER (PARTITION BY model_id, region_id
                    ORDER BY visibility_score DESC) AS visibility_rank
FROM fact_visibility v
LEFT JOIN model m ON m.id=v.model_id
LEFT JOIN region r ON r.id=v.region_id;

-- Deliverable #2: consolidated prompt view (ChatGPT-owned), persona-overlaid
CREATE VIEW vw_prompt_overview AS
WITH vis AS (
  SELECT prompt_id, model_id, region_id,
         SUM(visibility_score) AS visibility_score,
         AVG(share_of_voice)   AS share_of_voice,
         AVG(average_position) AS average_position,
         SUM(executions)       AS executions       -- = prompt_volume
  FROM fact_prompt_visibility GROUP BY 1,2,3
),
cit AS (
  SELECT prompt_id, model_id, region_id,
         AVG(citation_share) AS citation_share, SUM(count) AS citation_count
  FROM fact_prompt_citation GROUP BY 1,2,3
)
SELECT
  p.id AS prompt_id, p.text, t.name AS topic,
  GROUP_CONCAT(DISTINCT tg.name) AS tags,
  GROUP_CONCAT(DISTINCT pe.name) AS personas,
  m.name AS model, r.name AS region,
  vis.visibility_score, vis.share_of_voice, vis.average_position,
  RANK() OVER (PARTITION BY vis.model_id, vis.region_id
               ORDER BY vis.visibility_score DESC) AS visibility_rank,
  cit.citation_share,
  RANK() OVER (PARTITION BY vis.model_id, vis.region_id
               ORDER BY cit.citation_share DESC)   AS citation_rank,
  vis.executions AS prompt_volume
FROM prompt p
JOIN vis ON vis.prompt_id=p.id
LEFT JOIN cit ON cit.prompt_id=p.id AND cit.model_id=vis.model_id AND cit.region_id=vis.region_id
LEFT JOIN topic t ON t.id=p.topic_id
LEFT JOIN prompt_tag pt ON pt.prompt_id=p.id  LEFT JOIN tag tg ON tg.id=pt.tag_id
LEFT JOIN prompt_persona pp ON pp.prompt_id=p.id LEFT JOIN persona pe ON pe.id=pp.persona_id
LEFT JOIN model m ON m.id=vis.model_id  LEFT JOIN region r ON r.id=vis.region_id
GROUP BY p.id, vis.model_id, vis.region_id;
```
Filter by tag/persona at query time via `prompt_tag` / `prompt_persona`, or `WHERE personas LIKE '%Sabharwal%'`.

---

## 3. API call catalog (one call set per table; window 2026-05-30 → 2026-06-06)

No `date` dimension. Metric label order = the **alphabetical order the API returns** — decode by label.

| Table | Path | Dimensions | Metrics (returned order) | Notes |
|---|---|---|---|---|
| `fact_visibility` | MCP/REST visibility | `asset_name, model, region` | `average_position, executions, mentions_count, share_of_voice, visibility_score` | full leaderboard |
| `fact_prompt_visibility` | MCP/REST visibility | `prompt, model, region` | `average_position, executions, share_of_voice, visibility_score` | **`asset_filter="ChatGPT"`** |
| `fact_prompt_citation` | MCP/REST citations | `prompt, root_domain, model, region` | `citation_share, count` | |
| `fact_citation` | MCP/REST citations | `prompt, url, root_domain, citation_category, model, region` | `citation_share, count` | url grain |
| `fact_query_fanout` | **REST** `/v1/reports/query-fanouts` | `prompt, query, model, region` | `fanouts_per_execution, share, total_fanouts` | `share` requires `query` dim |
| `fact_sentiment` | **REST** `/v1/reports/sentiment` | `asset_name, model, region, topic, theme, sentiment_type` | `negative, occurrences, positive` | MCP lacks `dimensions` |

Reference seeds (once): `list_categories`, `list_models`, `list_regions`, `list_topics`, `list_tags`, `list_domains`, `list_prompts` (→ prompt + prompt_tag, 195 rows), `GET /v1/org/categories/{cat}/personas` (→ persona, source='profound').

Example REST body (sentiment, snapshot):
```json
{ "category_id":"7943f355-...","start_date":"2026-05-30","end_date":"2026-06-06",
  "metrics":["positive","negative","occurrences"],
  "dimensions":["asset_name","model","region","topic","theme","sentiment_type"],
  "pagination":{"limit":10000,"offset":0} }
```

---

## 4. Volume (7-day window, no date split)
Indicative full-window row counts seen live: visibility prompt×asset ~15k (ChatGPT-filtered far smaller), citations ~35k (url grain larger), fan-outs ~11k, sentiment ~43k. SQLite handles this easily; rely on the PK indexes plus add indexes on `(prompt_id)` and `(asset_name)` for the views.

---

## 5. Build order
1. `schema.sql` → `sqlite3 profound.db < schema.sql`
2. `seed_dims.py` — reference tables + prompts + (Profound) personas
3. `ingest.py` — six report pulls (snapshot window) using `flatten_*`, paginate, `INSERT OR REPLACE`, 429 backoff
4. Create views; smoke-test `vw_prompt_overview`
5. Populate `persona` + `prompt_persona` (your custom overlay)

---

## Sources
- Live MCP + REST probes against the org, 2026-06-06 (shapes, owned assets, metric ordering verified)
- `API-Mapping.md` (this folder)
- `~/Documents/Claude/Projects/Profound Hackathon/Profound-REST-API-Reference.md`
