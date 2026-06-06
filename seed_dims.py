"""Seed reference tables, prompts, prompt_tag, and Profound personas.

Run after applying schema.sql. Idempotent (INSERT OR REPLACE).
"""
import json
import sqlite3
from config import DB_PATH, CATEGORY_ID
from profound_client import ProfoundClient


def seed():
    pc = ProfoundClient()
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")
    cur = db.cursor()

    # category (single)
    cats = pc.get("/v1/org/categories")
    cats = cats if isinstance(cats, list) else cats.get("data", [])
    for c in cats:
        cur.execute("INSERT OR REPLACE INTO category(id,name) VALUES(?,?)",
                    (c["id"], c["name"]))

    # simple reference arrays
    for path, table in [("/v1/org/models", "model"),
                        ("/v1/org/regions", "region"),
                        (f"/v1/org/categories/{CATEGORY_ID}/topics", "topic"),
                        (f"/v1/org/categories/{CATEGORY_ID}/tags", "tag"),
                        ("/v1/org/domains", "domain")]:
        rows = pc.get(path)
        rows = rows if isinstance(rows, list) else rows.get("data", [])
        cur.executemany(f"INSERT OR REPLACE INTO {table}(id,name) VALUES(?,?)",
                        [(r["id"], r["name"]) for r in rows])
        print(f"  {table}: {len(rows)}")

    # personas (Profound's own) -> source='profound'
    pj = pc.get(f"/v1/org/categories/{CATEGORY_ID}/personas")
    personas = pj.get("data", pj) if isinstance(pj, dict) else pj
    for p in personas:
        cur.execute("INSERT OR REPLACE INTO persona(id,name,profile,source) "
                    "VALUES(?,?,?,'profound')",
                    (p["id"], p["name"], json.dumps(p.get("profile"))))
    print(f"  persona (profound): {len(personas)}")

    # prompts (cursor paginated) + prompt_tag
    cursor, n = None, 0
    while True:
        path = f"/v1/org/categories/{CATEGORY_ID}/prompts?limit=100"
        if cursor:
            path += f"&cursor={cursor}"
        resp = pc.get(path)
        for p in resp["data"]:
            cur.execute(
                "INSERT OR REPLACE INTO prompt"
                "(id,category_id,text,status,topic_id,language,analysis_types,profound_persona_id) "
                "VALUES(?,?,?,?,?,?,?,?)",
                (p["id"], CATEGORY_ID, p["prompt"], p.get("status"),
                 (p.get("topic") or {}).get("id"), p.get("language"),
                 json.dumps(p.get("analysis_types")),
                 (p.get("personas") or [{}])[0].get("id") if p.get("personas") else None))
            for tg in p.get("tags") or []:
                cur.execute("INSERT OR REPLACE INTO prompt_tag(prompt_id,tag_id) VALUES(?,?)",
                            (p["id"], tg["id"]))
            n += 1
        cursor = resp["info"].get("next_cursor")
        if not cursor:
            break
    print(f"  prompt: {n}")

    db.commit()
    db.close()
    print("seed complete")


if __name__ == "__main__":
    seed()
