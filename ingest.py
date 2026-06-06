"""Pull the six report snapshots and load the fact tables.

Reports return dimension NAMES (model/region names, prompt text), not IDs,
so we resolve names -> IDs against the seeded dim tables.
Run after seed_dims.py.
"""
import sqlite3
from config import DB_PATH, OWNED_BRAND
from profound_client import ProfoundClient


def _lookup(cur, table, key="name"):
    return {name: _id for _id, name in cur.execute(f"SELECT id,{key} FROM {table}")}
    # returns name -> id


def load():
    pc = ProfoundClient()
    db = sqlite3.connect(DB_PATH)
    db.execute("PRAGMA foreign_keys = ON")
    cur = db.cursor()

    model_id  = _lookup(cur, "model")
    region_id = _lookup(cur, "region")
    topic_id  = _lookup(cur, "topic")
    prompt_id = {text: pid for pid, text in cur.execute("SELECT id,text FROM prompt")}

    miss = {"model": set(), "region": set(), "topic": set(), "prompt": set()}

    def M(n):
        if n not in model_id: miss["model"].add(n)
        return model_id.get(n)
    def R(n):
        if n not in region_id: miss["region"].add(n)
        return region_id.get(n)
    def T(n):
        if n not in topic_id: miss["topic"].add(n)
        return topic_id.get(n)
    def P(t):
        if t not in prompt_id: miss["prompt"].add(t)
        return prompt_id.get(t)

    # (1) visibility leaderboard ------------------------------------------
    print("(1) fact_visibility")
    rows = pc.report("visibility",
                     metrics=["visibility_score", "share_of_voice",
                              "average_position", "mentions_count", "executions"],
                     dimensions=["asset_name", "model", "region"])
    cur.executemany(
        "INSERT OR REPLACE INTO fact_visibility VALUES(?,?,?,?,?,?,?,?)",
        [(r["asset_name"], M(r["model"]), R(r["region"]),
          r.get("visibility_score"), r.get("share_of_voice"),
          r.get("average_position"), r.get("mentions_count"), r.get("executions"))
         for r in rows])

    # (2a) prompt visibility — ChatGPT only -------------------------------
    print("(2a) fact_prompt_visibility")
    rows = pc.report("visibility",
                     metrics=["visibility_score", "share_of_voice",
                              "average_position", "executions"],
                     dimensions=["prompt", "asset_name", "model", "region"],
                     filters=[{"field": "asset_name", "operator": "is",
                               "value": OWNED_BRAND}])
    cur.executemany(
        "INSERT OR REPLACE INTO fact_prompt_visibility VALUES(?,?,?,?,?,?,?)",
        [(P(r["prompt"]), M(r["model"]), R(r["region"]),
          r.get("visibility_score"), r.get("share_of_voice"),
          r.get("average_position"), r.get("executions"))
         for r in rows])

    # (2b) prompt citations (domain grain) --------------------------------
    print("(2b) fact_prompt_citation")
    rows = pc.report("citations",
                     metrics=["count", "citation_share"],
                     dimensions=["prompt", "root_domain", "model", "region"])
    cur.executemany(
        "INSERT OR REPLACE INTO fact_prompt_citation VALUES(?,?,?,?,?,?)",
        [(P(r["prompt"]), r["root_domain"], M(r["model"]), R(r["region"]),
          r.get("citation_share"), r.get("count"))
         for r in rows])

    # (3) query fan-out ----------------------------------------------------
    print("(3) fact_query_fanout")
    rows = pc.report("query-fanouts",
                     metrics=["total_fanouts", "fanouts_per_execution", "share"],
                     dimensions=["prompt", "query", "model", "region"])
    cur.executemany(
        "INSERT OR REPLACE INTO fact_query_fanout VALUES(?,?,?,?,?,?,?)",
        [(P(r["prompt"]), r["query"], M(r["model"]), R(r["region"]),
          r.get("total_fanouts"), r.get("fanouts_per_execution"), r.get("share"))
         for r in rows])

    # (4) sentiment — most granular ---------------------------------------
    print("(4) fact_sentiment")
    rows = pc.report("sentiment",
                     metrics=["positive", "negative", "occurrences"],
                     dimensions=["asset_name", "model", "region",
                                 "topic", "theme", "sentiment_type"])
    cur.executemany(
        "INSERT OR REPLACE INTO fact_sentiment VALUES(?,?,?,?,?,?,?,?,?)",
        [(r["asset_name"], M(r["model"]), R(r["region"]), T(r["topic"]),
          r.get("theme"), r.get("sentiment_type"),
          r.get("positive"), r.get("negative"), r.get("occurrences"))
         for r in rows])

    # (5) citations — url grain -------------------------------------------
    print("(5) fact_citation")
    rows = pc.report("citations",
                     metrics=["count", "citation_share"],
                     dimensions=["prompt", "url", "root_domain",
                                 "citation_category", "model", "region"])
    cur.executemany(
        "INSERT OR REPLACE INTO fact_citation VALUES(?,?,?,?,?,?,?,?)",
        [(P(r["prompt"]), M(r["model"]), R(r["region"]), r.get("root_domain"),
          r.get("url"), r.get("citation_category"),
          r.get("citation_share"), r.get("count"))
         for r in rows])

    db.commit()
    for k, v in miss.items():
        if v:
            print(f"  WARNING unresolved {k} names ({len(v)}): {list(v)[:5]}")
    db.close()
    print("ingest complete")


if __name__ == "__main__":
    load()
