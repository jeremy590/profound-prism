# Profound-Prism — snapshot pull

Pulls a single point-in-time snapshot of Profound report data into a local
SQLite DB (`profound.db`) at five grains, with a custom persona overlay and
ranks derived in views. See `DB-Ingestion-Plan.md` for the design.

## Setup
```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```
`.env` holds `PROFOUND_API_KEY`. Window + IDs are in `config.py`
(currently 2026-05-30 → 2026-06-06, owned brand ChatGPT).

## Run (in order)
```bash
sqlite3 profound.db < schema.sql   # build tables + views
python seed_dims.py                # reference tables, prompts, personas
python ingest.py                   # the six report pulls -> fact tables
```

## Then assign your custom personas
```sql
INSERT INTO persona(id,name) VALUES('p1','Burned-out Engineer');
INSERT INTO prompt_persona(prompt_id,persona_id)
SELECT id,'p1' FROM prompt WHERE topic_id IN (SELECT id FROM topic WHERE name='Coding');
```

## Query
```sql
SELECT * FROM vw_prompt_overview WHERE model='ChatGPT' ORDER BY visibility_rank LIMIT 20;
SELECT * FROM vw_visibility_ranked WHERE region='United States' LIMIT 20;
```

## Files
| File | Purpose |
|---|---|
| `schema.sql` | tables + views |
| `config.py` | IDs, window, owned brand, DB path |
| `profound_client.py` | REST client: paginated reports, label-decoded rows |
| `seed_dims.py` | reference tables + prompts + Profound personas |
| `ingest.py` | six report snapshots → fact tables (resolves names→IDs) |
