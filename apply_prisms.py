"""Apply the Prism overlay to the snapshot DB (build-order step 5).

Two writes, both idempotent:

  1. persona            <- the 5 Prisms in prisms/*.yaml, source='custom'.
  2. prompt_persona     <- per-prompt links for the PROMPT-CURATED prisms only.

Curation modes (see Prism-Plan.md):
  - prompt-curated  (classified per prompt): CMO, PM, Brand  -> written to prompt_persona
  - citation-curated (apply across ALL prompts): SEO, PR     -> NO per-prompt rows by design;
                      they slice the citation frames, not individual prompts.

The classifier is one Claude API call over all 195 prompts (text + topic + tag),
returning a multi-label assignment among {cmo, pm, brand}. Re-running replaces the
custom overlay; the Profound-native persona row is left untouched.

Run:  .venv/bin/python apply_prisms.py
Env:  ANTHROPIC_API_KEY (.env)
"""
import json
import os
import sqlite3
import sys

import requests
import yaml
from dotenv import load_dotenv

from config import DB_PATH

load_dotenv()

PRISMS_DIR = os.path.join(os.path.dirname(__file__), "prisms")
API_KEY = os.environ["ANTHROPIC_API_KEY"]
MODEL = os.environ.get("CLASSIFIER_MODEL", "claude-opus-4-8")

# Prisms whose lens is a per-prompt property -> classified into prompt_persona.
PROMPT_CURATED = {"cmo", "pm", "brand"}

RUBRIC = """\
You label AI-visibility (AEO) prompts for a role-aware dashboard. Each prompt is a
real query that AI answer engines (ChatGPT, Gemini, Perplexity...) get asked about
AI products. Assign every prompt to ALL of the role lenses that genuinely apply.
There are exactly three lenses to choose from (multi-label; most prompts fit 1-2):

- cmo  (Commercial Director): top-line, category-defining or category-comparison
       prompts an exec watches for share-of-voice and emerging search themes.
       Signals: "best/top ... ai", "which company/model is fastest/cheapest",
       broad rankings, free-vs-paid, category-level framing. NOT a specific
       narrow use-case and NOT primarily an opinion/perception question.

- pm   (Product Manager): use-case & capability prompts -- the product doing a
       specific job or having a specific feature. Signals: a named task or
       audience ("ai for cs teams under 50", "hold a story over 50 pages",
       "for coding/image analysis/translation"), API/integration/deployment,
       capability or feature surfacing.

- brand (Brand Lead): opinion / perception / characterisation prompts -- how the
       product is *characterised*, trust/safety/reputation, sentiment. Signals:
       "what do people say about ...", trust/privacy/safety/alignment perception,
       reputation, quality opinions.

Rules:
- A prompt can carry several labels. "what do people say about chatgpt for coding"
  is both pm (coding use-case) and brand (what-do-people-say characterisation).
- Assign at least one label to every prompt -- pick the single best fit if unsure.
- Return ONLY a JSON array, no prose. One object per prompt, same order as input:
  [{"id": "<the id given>", "labels": ["cmo"|"pm"|"brand", ...]}, ...]
"""


def load_prisms():
    prisms = []
    for fn in sorted(os.listdir(PRISMS_DIR)):
        if not fn.endswith(".yaml"):
            continue
        with open(os.path.join(PRISMS_DIR, fn)) as f:
            prisms.append(yaml.safe_load(f))
    return prisms


def upsert_personas(db, prisms):
    """Insert all 5 Prisms as custom personas; profile carries the lens metadata."""
    for p in prisms:
        role = p["role"]
        curation = "prompt" if role in PROMPT_CURATED else "citation"
        profile = json.dumps({
            "title": p["title"],
            "goal": " ".join(p["goal"].split()),
            "questions": p.get("questions", []),
            "prompt_treatment": p["prompt_treatment"],
            "topic_treatment": p["topic_treatment"],
            "curation": curation,
        })
        db.execute(
            "INSERT OR REPLACE INTO persona(id,name,profile,source) VALUES(?,?,?,'custom')",
            (role, p["title"], profile),
        )
    db.commit()


def fetch_prompts(db):
    rows = db.execute(
        "SELECT p.id, t.name AS topic, "
        "       (SELECT GROUP_CONCAT(tg.name, '/') FROM prompt_tag pt "
        "         JOIN tag tg ON tg.id=pt.tag_id WHERE pt.prompt_id=p.id) AS tags, "
        "       p.text "
        "FROM prompt p LEFT JOIN topic t ON t.id=p.topic_id ORDER BY p.id"
    ).fetchall()
    return [dict(r) for r in rows]


def classify(prompts):
    """One Claude call -> {prompt_id: [labels]}. Validates coverage + label set."""
    listing = "\n".join(
        f'{i}. id={p["id"]} | topic={p["topic"]} | tag={p["tags"]} | {p["text"]}'
        for i, p in enumerate(prompts)
    )
    body = {
        "model": MODEL,
        "max_tokens": 16000,
        "system": RUBRIC,
        "messages": [{
            "role": "user",
            "content": f"Classify these {len(prompts)} prompts:\n\n{listing}",
        }],
    }
    resp = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json=body,
        timeout=300,
    )
    resp.raise_for_status()
    text = "".join(b.get("text", "") for b in resp.json()["content"])
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1:
        sys.exit(f"No JSON array in model response:\n{text[:500]}")
    parsed = json.loads(text[start:end + 1])

    valid_ids = {p["id"] for p in prompts}
    out = {}
    for item in parsed:
        pid = item["id"]
        if pid not in valid_ids:
            sys.exit(f"Model returned unknown prompt id: {pid}")
        labels = [l for l in item.get("labels", []) if l in PROMPT_CURATED]
        if not labels:
            sys.exit(f"Prompt {pid} got no valid label from {item.get('labels')}")
        out[pid] = sorted(set(labels))

    missing = valid_ids - set(out)
    if missing:
        sys.exit(f"{len(missing)} prompts unclassified, e.g. {list(missing)[:3]}")
    return out


def write_links(db, assignments):
    """Replace the custom prompt_persona overlay (CMO/PM/Brand only)."""
    db.execute(
        "DELETE FROM prompt_persona WHERE persona_id IN "
        "(SELECT id FROM persona WHERE source='custom')"
    )
    rows = [(pid, role) for pid, roles in assignments.items() for role in roles]
    db.executemany(
        "INSERT OR REPLACE INTO prompt_persona(prompt_id,persona_id) VALUES(?,?)", rows
    )
    db.commit()
    return len(rows)


def main():
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA foreign_keys = ON")

    prisms = load_prisms()
    upsert_personas(db, prisms)
    print(f"personas (custom): {len(prisms)}  "
          f"[prompt-curated: {sorted(PROMPT_CURATED)}; citation-curated: SEO, PR]")

    prompts = fetch_prompts(db)
    print(f"classifying {len(prompts)} prompts via {MODEL} ...")
    assignments = classify(prompts)
    n_links = write_links(db, assignments)

    counts = {r["name"]: r["n"] for r in db.execute(
        "SELECT pe.name, COUNT(*) AS n FROM prompt_persona pp "
        "JOIN persona pe ON pe.id=pp.persona_id WHERE pe.source='custom' "
        "GROUP BY pe.name ORDER BY n DESC")}
    multi = db.execute(
        "SELECT COUNT(*) FROM (SELECT prompt_id FROM prompt_persona pp "
        "JOIN persona pe ON pe.id=pp.persona_id WHERE pe.source='custom' "
        "GROUP BY prompt_id HAVING COUNT(*)>1)").fetchone()[0]
    print(f"prompt_persona links: {n_links}  ({multi} prompts multi-labelled)")
    for name, n in counts.items():
        print(f"  {name:<28} {n}")
    db.close()


if __name__ == "__main__":
    main()
