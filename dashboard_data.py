"""Live data for the Prism dashboard — read-only queries over profound.db.

Returns JSON shapes that match exactly what the front-end tile components consume
(see static/index.html). Single snapshot, no time dimension — nothing here implies
a trend. The connection is opened read-only as defense-in-depth.
"""
import json
import os
import sqlite3

from config import DB_PATH, OWNED_BRAND

# ---- which dims actually carry data (the rest exist but are empty) ----
N_BRANDS = 14            # brand selector size
N_LEADER = 12            # leaderboard rows
SNAPSHOT = {"from": "2026-05-30", "to": "2026-06-06"}

# Synthetic engine value: aggregate every engine into one cross-engine view.
ALL_ENGINES = "All engines"


def _is_all(engine):
    return engine == ALL_ENGINES


def _con():
    uri = "file:" + os.path.abspath(DB_PATH) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _q(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def _q1(con, sql, params=()):
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def pct(x, n=1):
    return None if x is None else round(x * 100, n)


def title(s):
    return s.title() if s and s.isupper() else s


# ============================================================== meta / selectors
def meta():
    con = _con()
    try:
        engines = [r["name"] for r in _q(con,
            "SELECT DISTINCT m.name FROM fact_visibility v JOIN model m ON m.id=v.model_id")]
        regions = [r["name"] for r in _q(con,
            "SELECT DISTINCT r.name FROM fact_visibility v JOIN region r ON r.id=v.region_id")]
        brands = [r["asset_name"] for r in _q(con,
            "SELECT asset_name, SUM(mentions_count) m FROM vw_visibility_ranked "
            "GROUP BY 1 ORDER BY 2 DESC LIMIT ?", (N_BRANDS,))]
    finally:
        con.close()
    # order with the conventional defaults first
    engines.sort(key=lambda e: (e != "ChatGPT", e))
    engines.insert(0, ALL_ENGINES)  # aggregated view across every engine
    if OWNED_BRAND in brands:
        brands.remove(OWNED_BRAND)
        brands.insert(0, OWNED_BRAND)
    default_region = "United States" if "United States" in regions else (regions[0] if regions else None)
    return {
        "brands": brands, "engines": engines, "regions": regions,
        "owned": OWNED_BRAND, "snapshot": SNAPSHOT,
        "defaults": {"brand": OWNED_BRAND, "engine": ALL_ENGINES, "region": default_region},
    }


# ============================================================== shared queries
def leaderboard_rows(con, engine, region, limit=N_LEADER):
    if _is_all(engine):
        # Roll every engine into one: sum mentions; volume-weight the rates by
        # executions (a busier engine counts more); then re-rank.
        rows = _q(con,
            "SELECT asset_name, "
            "SUM(visibility_score*executions)*1.0/NULLIF(SUM(executions),0) visibility_score, "
            "SUM(share_of_voice*executions)*1.0/NULLIF(SUM(executions),0) share_of_voice, "
            "SUM(average_position*executions)*1.0/NULLIF(SUM(executions),0) average_position, "
            "SUM(mentions_count) mentions_count "
            "FROM fact_visibility v JOIN region r ON r.id=v.region_id "
            "WHERE r.name=? GROUP BY asset_name ORDER BY visibility_score DESC", (region,))
        for i, r in enumerate(rows):
            r["visibility_rank"] = i + 1
        return rows[:limit]
    return _q(con,
        "SELECT asset_name, visibility_score, share_of_voice, average_position, "
        "mentions_count, visibility_rank FROM vw_visibility_ranked "
        "WHERE model=? AND region=? ORDER BY visibility_rank LIMIT ?",
        (engine, region, limit))


def brand_row(con, brand, engine, region):
    if _is_all(engine):
        for r in leaderboard_rows(con, engine, region, limit=10 ** 9):
            if r["asset_name"] == brand:
                return r
        return None
    return _q1(con,
        "SELECT asset_name, visibility_score, share_of_voice, average_position, "
        "mentions_count, visibility_rank FROM vw_visibility_ranked "
        "WHERE model=? AND region=? AND asset_name=?", (engine, region, brand))


def sentiment(con, brand, engine, region, limit=None):
    if _is_all(engine):
        sql = ("SELECT theme, SUM(positive) pos, SUM(negative) neg, SUM(occurrences) occ "
               "FROM fact_sentiment s JOIN region r ON r.id=s.region_id "
               "WHERE s.asset_name=? AND r.name=? GROUP BY LOWER(theme) ORDER BY occ DESC")
        params = (brand, region)
    else:
        sql = ("SELECT theme, SUM(positive) pos, SUM(negative) neg, SUM(occurrences) occ "
               "FROM fact_sentiment s JOIN model m ON m.id=s.model_id JOIN region r ON r.id=s.region_id "
               "WHERE s.asset_name=? AND m.name=? AND r.name=? GROUP BY LOWER(theme) ORDER BY occ DESC")
        params = (brand, engine, region)
    if limit:
        sql += " LIMIT %d" % int(limit)
    out = []
    for row in _q(con, sql, params):
        out.append({"theme": title(row["theme"]),
                    "key": row["theme"].lower(),
                    "net": round((row["pos"] or 0) - (row["neg"] or 0)),
                    "occ": row["occ"] or 0})
    return out


def categories(con, engine, region):
    if _is_all(engine):
        rows = _q(con,
            "SELECT citation_category cat, SUM(count) c FROM fact_citation ci "
            "JOIN region r ON r.id=ci.region_id WHERE r.name=? GROUP BY 1 ORDER BY 2 DESC", (region,))
    else:
        rows = _q(con,
            "SELECT citation_category cat, SUM(count) c FROM fact_citation ci "
            "JOIN model m ON m.id=ci.model_id JOIN region r ON r.id=ci.region_id "
            "WHERE m.name=? AND r.name=? GROUP BY 1 ORDER BY 2 DESC", (engine, region))
    total = sum(r["c"] for r in rows) or 1
    return [{"cat": r["cat"], "count": r["c"], "share": round(100 * r["c"] / total, 1)} for r in rows]


def domains(con, engine, region, limit=12):
    if _is_all(engine):
        rows = _q(con,
            "SELECT ci.root_domain d, t.name topic, SUM(ci.count) c "
            "FROM fact_citation ci JOIN region r ON r.id=ci.region_id "
            "LEFT JOIN prompt p ON p.id=ci.prompt_id LEFT JOIN topic t ON t.id=p.topic_id "
            "WHERE r.name=? GROUP BY ci.root_domain, t.name", (region,))
        owned_rows = _q(con,
            "SELECT DISTINCT ci.root_domain FROM fact_citation ci JOIN region r ON r.id=ci.region_id "
            "WHERE r.name=? AND ci.citation_category='owned'", (region,))
    else:
        rows = _q(con,
            "SELECT ci.root_domain d, t.name topic, SUM(ci.count) c "
            "FROM fact_citation ci JOIN model m ON m.id=ci.model_id JOIN region r ON r.id=ci.region_id "
            "LEFT JOIN prompt p ON p.id=ci.prompt_id LEFT JOIN topic t ON t.id=p.topic_id "
            "WHERE m.name=? AND r.name=? GROUP BY ci.root_domain, t.name", (engine, region))
        owned_rows = _q(con,
            "SELECT DISTINCT ci.root_domain FROM fact_citation ci JOIN model m ON m.id=ci.model_id "
            "JOIN region r ON r.id=ci.region_id WHERE m.name=? AND r.name=? AND ci.citation_category='owned'",
            (engine, region))
    agg, beat = {}, {}
    for r in rows:
        agg[r["d"]] = agg.get(r["d"], 0) + r["c"]
        if r["topic"]:
            cur = beat.get(r["d"])
            if cur is None or r["c"] > cur[1]:
                beat[r["d"]] = (r["topic"], r["c"])
    owned = {r["root_domain"] for r in owned_rows}
    total = sum(agg.values()) or 1
    ranked = sorted(agg.items(), key=lambda kv: -kv[1])
    return [{"root_domain": d, "count": c, "share": round(100 * c / total, 1),
             "beat": beat.get(d, ("—", 0))[0], "owned": d in owned}
            for d, c in ranked][:limit]


def prompts(con, engine, region, limit=10, order="vis"):
    by = {"vis": "visibility_score DESC", "gap": "citation_rank DESC"}.get(order, "visibility_score DESC")
    if _is_all(engine):
        # Aggregate each prompt across engines, volume-weighted by prompt_volume
        # (executions): rates and rank weighted, volume summed.
        return _q(con,
            "SELECT prompt, topic, tags, "
            "SUM(visibility_score*prompt_volume)*1.0/NULLIF(SUM(prompt_volume),0) visibility_score, "
            "SUM(citation_share*prompt_volume)*1.0/NULLIF(SUM(prompt_volume),0) citation_share, "
            "CAST(ROUND(SUM(citation_rank*prompt_volume)*1.0/NULLIF(SUM(prompt_volume),0)) AS INT) citation_rank, "
            "SUM(prompt_volume) prompt_volume FROM vw_prompt_overview "
            "WHERE region=? AND visibility_score IS NOT NULL GROUP BY prompt_id "
            "ORDER BY " + by + " LIMIT ?", (region, limit))
    return _q(con,
        "SELECT prompt, topic, tags, visibility_score, citation_share, citation_rank, prompt_volume "
        "FROM vw_prompt_overview WHERE model=? AND region=? AND visibility_score IS NOT NULL "
        "ORDER BY " + by + " LIMIT ?", (engine, region, limit))


def ctx_label(engine, region):
    return engine + " · " + region


# ============================================================== OVERVIEW
def overview(brand, engine, region):
    con = _con()
    try:
        lb = leaderboard_rows(con, engine, region)
        me = brand_row(con, brand, engine, region)
        sent = sentiment(con, brand, engine, region, limit=10)
        cats = categories(con, engine, region)
        doms = domains(con, engine, region, 12)
        pr = prompts(con, engine, region, 10)
    finally:
        con.close()

    leader = lb[0]["asset_name"] if lb else "—"
    kpis = ([
        {"title": "Visibility Rank", "value": "#" + str(me["visibility_rank"]),
         "label": "within " + ctx_label(engine, region)},
        {"title": "Visibility %", "value": str(pct(me["visibility_score"])) + "%",
         "label": "of tracked answers mention " + brand},
        {"title": "Share of Voice %", "value": str(pct(me["share_of_voice"])) + "%",
         "label": "of all brand mentions"},
        {"title": "Avg Position", "value": round(me["average_position"], 1),
         "label": "average rank when mentioned", "caption": "lower is better"},
    ] if me else [
        {"title": "Visibility Rank", "value": "—", "label": brand + " not tracked in " + ctx_label(engine, region)},
        {"title": "Visibility %", "value": "—", "label": "no data"},
        {"title": "Share of Voice %", "value": "—", "label": "no data"},
        {"title": "Avg Position", "value": "—", "label": "no data"},
    ])

    return {
        "kpis": kpis,
        "leaderboard": {
            "type": "leaderboard", "title": "Visibility Leaderboard — " + ctx_label(engine, region),
            "columns": ["Brand", "Visibility %", "Share of Voice %", "Avg Position", "Mentions"],
            "brandKey": "asset_name",
            "rows": [[r["asset_name"], pct(r["visibility_score"]), pct(r["share_of_voice"]),
                      round(r["average_position"], 1), r["mentions_count"]] for r in lb],
            "highlight": brand,
            "insight": (leader + " leads visibility here; " + brand +
                        (" sits at rank #" + str(me["visibility_rank"]) + "." if me else " is not tracked in this engine.")),
            "caveats": "visibility_rank within engine+region; avg position is better when lower (1 = first).",
        },
        "sentiment": {
            "type": "bar", "title": "Net Sentiment by Theme — " + brand, "subtitle": "top 10 themes by occurrences",
            "columns": ["Theme", "Net"],
            "rows": [[s["theme"], s["net"]] for s in sent],
            "meta": [s["occ"] for s in sent], "metaLabel": "occ",
            "insight": ("Net = positive − negative. " + brand + " skews " +
                        ("favourable overall." if sum(s["net"] for s in sent) >= 0 else "unfavourable overall.")
                        if sent else "No sentiment themes recorded for " + brand + " on this engine."),
            "caveats": "Themes grouped case-insensitively; only positive/negative exist (no neutral).",
        },
        "catTile": {
            "type": "bar", "title": "Citations by Source Category", "subtitle": ctx_label(engine, region),
            "columns": ["Category", "Citation Share %"],
            "rows": [[c["cat"], c["share"]] for c in cats],
            "insight": "Social and earned media dominate; owned domains are a minority of citations.",
            "caveats": "Share of total citation volume in this engine + region.",
        },
        "domTile": {
            "type": "leaderboard", "title": "Top Cited Domains", "subtitle": ctx_label(engine, region),
            "columns": ["Domain", "Citations", "Citation Share %"], "brandKey": None,
            "rows": [[d["root_domain"], d["count"], d["share"]] for d in doms],
            "ownedDomains": [d["root_domain"] for d in doms if d["owned"]],
            "insight": (doms[0]["root_domain"] + " is the single heaviest citation source here." if doms else "No citation data."),
            "caveats": "Raw counts within the selected engine + region.",
        },
        "prompts": {
            "type": "table", "title": "Prompt Performance — " + ctx_label(engine, region),
            "columns": ["Prompt", "Topic", "Tags", "Visibility %", "Citation Share %", "Citation Rank", "Volume"],
            "rows": [[p["prompt"], p["topic"], p["tags"] or "", pct(p["visibility_score"]),
                      pct(p["citation_share"]), p["citation_rank"], p["prompt_volume"]] for p in pr],
            "empty": len(pr) == 0,
            "insight": "High-visibility prompts with weak citation rank are the clearest content gaps." if pr else None,
            "caveats": "Prompt-level metrics reflect the owned/tracked prompt set for this engine, not the selected brand.",
        },
    }


# ============================================================== PRISM (role lenses)
ROLE_NAMES = {"cmo": "CMO", "seo": "SEO", "pm": "PM", "brand": "Brand", "pr": "PR"}


# Producer→renderer contract: the agent terminal writes data/<role>_summary.json;
# the dashboard only reads it. The slot renders gracefully empty until it lands.
DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(DB_PATH)), "data")
SUMMARY_PATH = os.path.join(DATA_DIR, "cmo_summary.json")  # kept: cmo_action_cards reads it


def _summary_tile(role, region, badge="Cross-engine view"):
    """The AI-driven summary slot — READ-ONLY over data/<role>_summary.json.

    Does not generate anything. If the artifact is absent the slot stays empty
    (the renderer shows an 'awaiting summary' placeholder)."""
    path = os.path.join(DATA_DIR, role + "_summary.json")
    tile = {"type": "brief", "title": "AI summary", "badge": badge,
            "subtitle": OWNED_BRAND + " · " + region + " · snapshot " +
                        SNAPSHOT["from"] + " to " + SNAPSHOT["to"],
            "summary": [], "actions": []}
    try:
        if os.path.isfile(path):
            with open(path) as f:
                d = json.load(f)
            tile["summary"] = d.get("summary", [])
            tile["actions"] = d.get("actions", [])
    except Exception:
        pass
    return tile


def cmo_brief_tile(region):
    return _summary_tile("cmo", region)


def fanout_queries(con, engine, region, limit=10):
    """Top query fan-outs (the sub-queries engines spin off our prompts)."""
    if _is_all(engine):
        rows = _q(con,
            "SELECT f.query q, SUM(f.total_fanouts) tot FROM fact_query_fanout f "
            "JOIN region r ON r.id=f.region_id WHERE r.name=? "
            "GROUP BY f.query ORDER BY tot DESC LIMIT ?", (region, limit))
    else:
        rows = _q(con,
            "SELECT f.query q FROM fact_query_fanout f JOIN model m ON m.id=f.model_id "
            "JOIN region r ON r.id=f.region_id WHERE m.name=? AND r.name=? "
            "ORDER BY f.share DESC LIMIT ?", (engine, region, limit))
    return [r["q"] for r in rows]


def topics_performance(con, engine, region):
    """Avg visibility per topic for the owned/tracked prompt set — best to worst."""
    if _is_all(engine):
        sql = ("SELECT topic, AVG(visibility_score) v, AVG(citation_share) c "
               "FROM vw_prompt_overview WHERE region=? AND visibility_score IS NOT NULL "
               "GROUP BY topic ORDER BY v DESC")
        params = (region,)
    else:
        sql = ("SELECT topic, AVG(visibility_score) v, AVG(citation_share) c "
               "FROM vw_prompt_overview WHERE model=? AND region=? AND visibility_score IS NOT NULL "
               "GROUP BY topic ORDER BY v DESC")
        params = (engine, region)
    return _q(con, sql, params)


# ============================================================== PM helpers (all-engines, topic-sliced)
def pm_clusters(con, region, limit=8):
    """Use-case clusters = topics, aggregated across every engine."""
    return _q(con,
        "SELECT topic, COUNT(DISTINCT prompt_id) n, AVG(visibility_score) v "
        "FROM vw_prompt_overview WHERE region=? AND visibility_score IS NOT NULL "
        "GROUP BY topic ORDER BY n DESC LIMIT ?", (region, limit))


def competitors_overall(con, region, owned, limit=8):
    """Most-recommended brands across all engines (visibility leaderboard)."""
    rows = leaderboard_rows(con, ALL_ENGINES, region, limit=10 ** 9)
    out = [r for r in rows if r["asset_name"] != owned][:limit]
    return [[r["asset_name"], pct(r["visibility_score"]), pct(r["share_of_voice"])] for r in out]


def competitors_by_topic(con, region):
    """Per-topic brand standing from sentiment coverage (asset × topic): mentions
    + net sentiment, all engines. The only brand×topic signal in the snapshot."""
    rows = _q(con,
        "SELECT t.name topic, s.asset_name brand, SUM(s.occurrences) occ, "
        "SUM(s.positive)-SUM(s.negative) net "
        "FROM fact_sentiment s JOIN region r ON r.id=s.region_id JOIN topic t ON t.id=s.topic_id "
        "WHERE r.name=? GROUP BY t.name, s.asset_name", (region,))
    by = {}
    for r in rows:
        by.setdefault(r["topic"], []).append([r["brand"], r["occ"], round(r["net"] or 0)])
    for t in by:
        by[t].sort(key=lambda x: -x[1])
    return by


def sentiment_by_topic(con, region, brand):
    """Net sentiment per topic for the owned brand, all engines."""
    rows = _q(con,
        "SELECT t.name topic, SUM(s.positive)-SUM(s.negative) net, SUM(s.occurrences) occ "
        "FROM fact_sentiment s JOIN region r ON r.id=s.region_id JOIN topic t ON t.id=s.topic_id "
        "WHERE r.name=? AND s.asset_name=? GROUP BY t.name ORDER BY net DESC", (region, brand))
    return [[r["topic"], round(r["net"] or 0), r["occ"]] for r in rows]


def prompts_by_topic(con, region, limit=30):
    """All tracked prompts per topic (all engines), best-visibility first."""
    rows = _q(con,
        "SELECT topic, prompt, MAX(visibility_score) v FROM vw_prompt_overview "
        "WHERE region=? AND prompt IS NOT NULL GROUP BY topic, prompt "
        "ORDER BY topic, v DESC", (region,))
    by = {}
    for r in rows:
        by.setdefault(r["topic"], [])
        if len(by[r["topic"]]) < limit:
            by[r["topic"]].append(r["prompt"])
    return by


def prism(role, brand, engine, region):
    con = _con()
    try:
        tiles = _role_tiles(con, role, brand, engine, region)
    finally:
        con.close()
    return {"tiles": tiles}


def _role_tiles(con, role, brand, engine, region):
    lb = leaderboard_rows(con, engine, region)
    me = brand_row(con, brand, engine, region)
    rank = me["visibility_rank"] if me else "—"
    sent = sentiment(con, brand, engine, region, limit=10)
    doms = domains(con, engine, region, 20)
    pr = prompts(con, engine, region, 12)
    third = [d for d in doms if not d["owned"]]

    if role == "cmo":
        net = sum(s["net"] for s in sent)
        cats = categories(con, engine, region)
        tp = topics_performance(con, engine, region)
        return [
            # 1 — AI-driven summary (render-only slot)
            cmo_brief_tile(region),
            # 2 — Visibility: KPI strip + leaderboard vs competitors
            {"type": "kpi-strip", "tiles": [
                {"title": "The one number", "value": "#" + str(rank),
                 "label": "visibility rank in " + ctx_label(engine, region),
                 "caption": brand + " vs " + str(max(len(lb) - 1, 0)) + " competitors"},
                {"title": "Visibility %", "value": (str(pct(me["visibility_score"])) + "%") if me else "—",
                 "label": "of answers mention " + brand},
                {"title": "Share of Voice %", "value": (str(pct(me["share_of_voice"])) + "%") if me else "—",
                 "label": "of all brand mentions"},
                {"title": "Sentiment", "value": "Positive" if net >= 0 else "Negative",
                 "label": "net across themes", "caption": "net sum " + ("+" if net >= 0 else "") + str(net)},
            ]},
            {"type": "leaderboard", "title": "Visibility vs top competitors",
             "columns": ["Brand", "Visibility %", "Share of Voice %"],
             "rows": [[r["asset_name"], pct(r["visibility_score"]), pct(r["share_of_voice"])] for r in lb[:5]],
             "highlight": brand,
             "insight": ("Overall sentiment is favourable; visibility is the lever to push." if net >= 0
                         else "Visibility holding, but overall sentiment is a watch-item."),
             "caveats": "Top 5 of " + str(len(lb)) + " brands in this engine + region."},
            # 3 — Citations: source-type mix + heaviest domains
            {"type": "bar", "title": "Citations by source category", "subtitle": ctx_label(engine, region),
             "columns": ["Category", "Citation Share %"],
             "rows": [[c["cat"], c["share"]] for c in cats],
             "insight": "Where AI engines source answers about the category — owned vs earned vs social.",
             "caveats": "Share of total citation volume in this engine + region."},
            {"type": "leaderboard", "title": "Top cited domains", "subtitle": ctx_label(engine, region),
             "columns": ["Domain", "Citations", "Citation Share %"], "brandKey": None,
             "rows": [[d["root_domain"], d["count"], d["share"]] for d in doms[:10]],
             "ownedDomains": [d["root_domain"] for d in doms if d["owned"]],
             "insight": (doms[0]["root_domain"] + " is the single heaviest citation source." if doms else "No citation data."),
             "caveats": "Raw counts within this engine + region."},
            # 4 — Top & bottom performing topics
            {"type": "bar", "title": "Topic performance — best to worst",
             "subtitle": "avg visibility by topic · " + OWNED_BRAND,
             "columns": ["Topic", "Visibility %"],
             "rows": [[t["topic"], pct(t["v"])] for t in tp],
             "insight": (("Strongest: " + tp[0]["topic"] + "; weakest: " + tp[-1]["topic"] + ".") if tp else "No topic data."),
             "caveats": "Average visibility of tracked " + OWNED_BRAND + " prompts per topic."},
            # 5 — Category-defining prompts (moved last)
            {"type": "table", "title": "Category-defining prompts",
             "columns": ["Prompt", "Topic", "Visibility %"],
             "rows": [[p["prompt"], p["topic"], pct(p["visibility_score"])] for p in pr[:5]],
             "insight": "The highest-visibility prompts shaping how the category is described.",
             "caveats": "Top tracked prompts by visibility (single snapshot — not 'new this week')."},
        ]

    if role == "seo":
        gap = sorted(pr, key=lambda p: -(p["citation_rank"] or 0))[:6]
        topic_cit = {}
        for p in pr:
            if p["citation_share"] is not None:
                topic_cit[p["topic"]] = topic_cit.get(p["topic"], 0) + p["citation_share"]
        topics = sorted(([t, round(v * 100, 1)] for t, v in topic_cit.items()), key=lambda x: -x[1])[:6]
        engines = []
        for e in [r["name"] for r in _q(con, "SELECT DISTINCT m.name FROM fact_visibility v JOIN model m ON m.id=v.model_id")]:
            row = _q1(con,
                "SELECT SUM(CASE WHEN citation_category='owned' THEN count ELSE 0 END)*1.0/NULLIF(SUM(count),0) s "
                "FROM fact_citation ci JOIN model m ON m.id=ci.model_id JOIN region r ON r.id=ci.region_id "
                "WHERE m.name=? AND r.name=?", (e, region))
            engines.append([e, round((row["s"] or 0) * 100, 1)])
        engines.sort(key=lambda x: -x[1])
        tp = topics_performance(con, engine, region)
        fan = fanout_queries(con, engine, region, 10)
        return [
            # 1 — AI summary + 3 actions (render-only slot; mirrors the CMO view)
            _summary_tile("seo", region, badge="Citation recovery"),
            # 2 — Visibility by topic (best → worst; the recovery target sits at the bottom)
            {"type": "bar", "title": "Visibility by topic",
             "subtitle": "avg visibility per topic · " + OWNED_BRAND,
             "columns": ["Topic", "Visibility %"],
             "rows": [[t["topic"], pct(t["v"])] for t in tp],
             "insight": (("Strongest on " + tp[0]["topic"] + "; weakest on " + tp[-1]["topic"] +
                          " — the clearest recovery target.") if tp else "No topic data."),
             "caveats": "Average visibility of tracked " + OWNED_BRAND + " prompts per topic, " +
                        ctx_label(engine, region) + "."},
            # 3 — Share of voice
            {"type": "leaderboard", "title": "Share of voice", "subtitle": ctx_label(engine, region),
             "columns": ["Brand", "Share of Voice %", "Visibility %"],
             "rows": [[r["asset_name"], pct(r["share_of_voice"]), pct(r["visibility_score"])] for r in lb],
             "highlight": brand,
             "insight": ((lb[0]["asset_name"] + " holds the most share of voice; " + brand +
                          " sits at rank #" + str(rank) + ".") if lb else "No data."),
             "caveats": "Share of all brand mentions in this engine + region."},
            # 4 — Query fan-out (the proposed queries to target, listed underneath)
            {"type": "chips", "title": "Query fan-out — proposed queries",
             "subtitle": ctx_label(engine, region),
             "items": fan or ["No fan-out queries recorded"],
             "insight": "Sub-queries AI engines spin off our prompts — the queries to target with new or refreshed pages.",
             "caveats": "Top query fan-outs by share for this engine + region."},
            # 5 — Third-party domains holding the citations we want
            {"type": "leaderboard", "title": "Third-party domains cited for the category",
             "columns": ["Domain", "Citations", "Topic beat"],
             "rows": [[d["root_domain"], d["count"], d["beat"]] for d in third[:8]],
             "insight": "These domains rank for the category but aren't owned — citation-recovery targets.",
             "caveats": "Excludes domains categorised as owned."},
            {"type": "table", "title": "Owned-page citation gaps (keyword view)",
             "columns": ["Prompt", "Topic", "Citation Rank", "Citation Share %"],
             "rows": [[p["prompt"], p["topic"], p["citation_rank"], pct(p["citation_share"])] for p in gap],
             "empty": len(gap) == 0,
             "insight": "High visibility but weak citation rank = pages to build or refresh first.",
             "caveats": "Higher citation_rank is worse."},
            {"type": "table", "title": "Engine citation coverage", "columns": ["Engine", "Owned Citation Share %"],
             "rows": engines, "highlight": engine, "highlightCol": 0,
             "insight": "You're least cited on " + (engines[-1][0] if engines else "—") + " — an under-served engine.",
             "caveats": "Share of citations categorised 'owned', by engine, current region."},
            {"type": "bar", "title": "Topic citation leaders", "columns": ["Topic", "Citation Share %"],
             "rows": topics, "insight": "These topics convert the most citations.",
             "caveats": "Summed citation share across tracked prompts per topic."},
        ]

    if role == "pm":
        # The PM view is always an aggregated, cross-engine read — ignore the
        # engine selector and roll every engine into one.
        clusters = pm_clusters(con, region, 8)
        fan = fanout_queries(con, ALL_ENGINES, region, 10)
        comp_overall = competitors_overall(con, region, brand, 8)
        comp_topics = competitors_by_topic(con, region)
        sent_topics = sentiment_by_topic(con, region, brand)
        topic_prompts = prompts_by_topic(con, region, 30)
        filter_topics = [c["topic"] for c in clusters]
        return [
            # 1 — Use-case clusters
            {"type": "table", "title": "Use-case clusters", "subtitle": "all engines · " + region,
             "columns": ["Cluster", "Member Prompts", "Avg Visibility %"],
             "rows": [[c["topic"], c["n"], pct(c["v"])] for c in clusters],
             "insight": "Topics where the tracked product surfaces most often — the use-case map.",
             "caveats": "Prompts grouped by topic, aggregated across every engine."},
            # 2 — Adjacent questions to answer
            {"type": "chips", "title": "Adjacent questions to answer", "subtitle": "all engines · " + region,
             "items": fan or ["No fan-out queries recorded"],
             "insight": "Sub-queries engines spin off these prompts — gaps the product/docs could own.",
             "caveats": "Top query fan-outs by share, aggregated across engines."},
            # 3 — Competitors most recommended, with clickable topic filters
            {"type": "comp-filter", "title": "Competitors most recommended", "subtitle": "all engines · " + region,
             "topics": filter_topics,
             "overall": {"columns": ["Brand", "Visibility %", "Share of Voice %"], "rows": comp_overall},
             "byTopic": {t: {"columns": ["Brand", "Mentions", "Net sentiment"], "rows": comp_topics.get(t, [])}
                         for t in filter_topics},
             "insight": "Most-recommended brands overall; filter by topic to see who leads each use case.",
             "caveats": "Overall = visibility leaderboard. Per-topic = mention/sentiment coverage (frontier-model set)."},
            # 4 — Sentiment by topic: sort best/worst, click a topic to see its prompts
            {"type": "topic-sentiment", "title": "Sentiment by topic", "subtitle": brand + " · all engines · " + region,
             "columns": ["Topic", "Net sentiment", "Mentions"],
             "rows": sent_topics,
             "prompts": {t: topic_prompts.get(t, []) for t, _, _ in sent_topics},
             "insight": "Net sentiment per topic. Sort best/worst, then click a topic to see all its prompts.",
             "caveats": "Net = positive − negative across all engines for " + brand + "."},
        ]

    if role == "brand":
        comps = [r["asset_name"] for r in lb if r["asset_name"] != brand][:2]
        comp_maps = {c: {s["key"]: s["net"] for s in sentiment(con, c, engine, region)} for c in comps}
        rows = [[s["theme"], s["net"]] + [comp_maps[c].get(s["key"], 0) for c in comps] for s in sent]
        risks = [s["theme"] for s in sent if s["net"] < 0]
        attrs = [s["theme"] for s in sent if s["net"] > 0][:6]
        return [
            {"type": "bar", "title": "Net sentiment — " + brand + " vs competitors",
             "columns": ["Theme", brand] + comps, "rows": rows,
             "insight": brand + " is characterised most favourably on its top themes; gaps show where rivals win.",
             "caveats": "Net = positive − negative, by theme. Negative = unfavourable."},
            {"type": "chips", "title": "Themes AI associates with " + brand,
             "items": attrs or ["No net-positive themes"], "tone": "pos",
             "insight": "Themes carrying net-positive sentiment for the brand.",
             "caveats": "Top positive-net themes by occurrence."},
            {"type": "chips", "title": "Reputation-risk themes",
             "items": risks or ["None this snapshot"], "tone": "risk",
             "insight": ("Negative-net themes to prepare responses for." if risks else "No net-negative themes this snapshot."),
             "caveats": "Themes with net sentiment below zero."},
        ]

    if role == "pr":
        not_citing = [d for d in third if d["beat"] != "—"][:6]
        cats = categories(con, engine, region)
        return [
            {"type": "leaderboard", "title": "Third-party domains by citations", "columns": ["Domain", "Citations"],
             "rows": [[d["root_domain"], d["count"]] for d in third[:10]],
             "insight": "The domains shaping category answers — your outreach universe.",
             "caveats": "Excludes owned domains."},
            {"type": "table", "title": "Domain × topic beat map", "columns": ["Domain", "Topic beat", "Citations"],
             "rows": [[d["root_domain"], d["beat"], d["count"]] for d in third[:8]],
             "insight": "Map each domain to the beat it owns before pitching.",
             "caveats": "Beat = dominant topic the domain is cited for."},
            {"type": "bar", "title": "Source-type mix", "columns": ["Category", "Citation Share %"],
             "rows": [[c["cat"], c["share"]] for c in cats],
             "insight": "Social and earned media dominate the citation mix.",
             "caveats": "Share of total citation volume."},
            {"type": "table", "title": "Domains not citing us", "columns": ["Domain", "Topic beat", "Citations"],
             "rows": [[d["root_domain"], d["beat"], d["count"]] for d in not_citing],
             "insight": "Cited for the category but not owned — prime outreach list.",
             "caveats": "Citation-curated across all prompts."},
        ]

    return []


# ============================================================== ACTIONS (agent stubs)
ACTIONS = {
    "cmo": [
        {"id": "cmo_brief", "title": "Generate weekly exec brief",
         "desc": "Summarise visibility, share of voice and sentiment into a one-page brief for leadership.",
         "inputs": [["Top 5", "competitors"], ["10", "sentiment themes"], ["1", "brand context"]]},
        {"id": "cmo_compwatch", "title": "Draft competitor-watch summary",
         "desc": "Flag where competitors lead on share of voice and the themes driving it.",
         "inputs": [["all", "competitors"], ["SoV", "by brand"]]},
    ],
    "seo": [
        {"id": "seo_brief", "title": "Build content brief for citation-gap prompts",
         "desc": "Draft content briefs targeting prompts where you rank but aren't cited.",
         "inputs": [["6", "citation-gap prompts"], ["topic", "clusters"]]},
        {"id": "seo_refresh", "title": "Draft page-refresh checklist",
         "desc": "A checklist to refresh owned pages for under-cited topics and engines.",
         "inputs": [["1", "owned domain"], ["weak", "topics"]]},
        {"id": "seo_engine", "title": "Plan engine citation-coverage push",
         "desc": "A plan to lift owned-citation share on the engines where you're least cited.",
         "inputs": [["weak", "engines"], ["owned", "domains"]]},
    ],
    "pm": [
        {"id": "pm_adjacent", "title": "Cluster & summarise adjacent questions",
         "desc": "Group fan-out questions into a prioritised roadmap input.",
         "inputs": [["8", "adjacent questions"], ["6", "use-case clusters"]]},
        {"id": "pm_teardown", "title": "Competitor use-case teardown",
         "desc": "Compare how competitors are recommended across each use-case cluster.",
         "inputs": [["3", "competitors"], ["use-case", "prompts"]]},
    ],
    "brand": [
        {"id": "brand_risk", "title": "Draft sentiment-risk response notes",
         "desc": "Prepare talking points for the net-negative sentiment themes.",
         "inputs": [["risk", "themes"], ["competitor", "sentiment"]]},
        {"id": "brand_claim", "title": "Claim-these-themes content plan",
         "desc": "Plan content to own the positive themes competitors currently win.",
         "inputs": [["positive", "themes"], ["competitor", "gaps"]]},
    ],
    "pr": [
        {"id": "pr_pitch", "title": "Draft outreach pitches for target domains",
         "desc": "Personalised pitches for third-party domains that don't cite you yet.",
         "inputs": [["target", "domains"], ["topic", "beats"]]},
        {"id": "pr_beats", "title": "Build journalist / domain beat list",
         "desc": "Map domains to the topics they cover for targeted, relevant outreach.",
         "inputs": [["all", "domains"], ["topic", "beats"]]},
    ],
}

RUN_RESULTS = {
    "cmo_brief": {"summary": "Drafted a 1-page exec brief: rank, SoV and sentiment headline with 3 recommended decisions.",
                  "preview": "1. Headline — current visibility rank + sentiment net\n2. Watch — fastest-rising competitor on SoV\n3. Decide — fund citation recovery on top third-party domains"},
    "cmo_compwatch": {"summary": "Drafted a competitor-watch summary with the themes moving share of voice.",
                      "preview": "• Leader — strongest on argumentation & coding\n• Riser — gaining on multimodal\n• Niche — strong on research citations"},
    "seo_brief": {"summary": "Drafted content briefs for the citation-gap prompts, each with target domains and an outline.",
                  "preview": "1. \"safest AI model\" — cite arxiv, anthropic\n2. \"fastest AI model\" — benchmark table page\n3. \"best AI for coding\" — comparison hub"},
    "seo_refresh": {"summary": "Built a page-refresh checklist for the under-cited topics across owned pages.",
                    "preview": "☐ Add FAQ schema to /pricing\n☐ Refresh /enterprise with case studies\n☐ Add benchmarks to /coding"},
    "seo_engine": {"summary": "Drafted an engine citation-coverage plan for the engines where owned pages are least cited.",
                   "preview": "• Google Gemini (0.8%) — structured data + canonical docs\n• Perplexity (0.9%) — concise, citable summaries\n• Track owned-citation share weekly"},
    "pm_adjacent": {"summary": "Clustered the adjacent fan-out questions into a roadmap input with suggested owners.",
                    "preview": "• Tooling — MCP support, rate limits\n• Docs — long-document handling\n• Infra — offline / on-prem"},
    "pm_teardown": {"summary": "Drafted a competitor use-case teardown across the top recommended rivals.",
                    "preview": "Leader — coding, reasoning\nRiser — multimodal, search\nNiche — research, citations"},
    "brand_risk": {"summary": "Drafted response notes for the net-negative sentiment themes.",
                   "preview": "• Cost — frame value vs. token efficiency\n• Verbosity — concise-mode messaging\n• Hallucination — grounding & citations story"},
    "brand_claim": {"summary": "Drafted a content plan to claim the positive themes competitors currently win.",
                    "preview": "1. Reasoning depth — technical deep-dives\n2. Safety — trust center updates\n3. Writing quality — showcase gallery"},
    "pr_pitch": {"summary": "Drafted outreach pitches for target domains, ready for review.",
                 "preview": "1. reddit.com — relevant subreddit mods …\n2. techradar.com — reviews desk …\n3. theverge.com — AI desk …"},
    "pr_beats": {"summary": "Built a journalist / domain beat list mapping domains to topic beats.",
                 "preview": "• techradar.com → Reviews\n• theverge.com → News\n• arxiv.org → Research\n• reddit.com → Community"},
}


# Downstream-agent display metadata. The CMO Actions tab is derived from the
# summary artifact (so a card == a summary action == a downstream agent).
AGENT_META = {
    "brand_risk_response":     {"title": "Brand · Sentiment-risk response"},
    "seo_citation_gap_closer": {"title": "SEO · Citation-gap closer"},
    "pr_citation_outreach":    {"title": "PR · Citation outreach"},
}
INPUT_LABELS = {"weak_topics": "weak topics", "weak_engines": "weak engines",
                "negative_themes": "risk themes", "owned_domains": "owned domains",
                "top_third_party": "target domains"}


def _input_chips(inputs):
    """Scoped-inputs dict → [[count, label], …] chips for the card."""
    chips = []
    for k, v in (inputs or {}).items():
        if k == "region":
            continue
        n = len(v) if isinstance(v, list) else v
        chips.append([str(n), INPUT_LABELS.get(k, k.replace("_", " "))])
    return chips


def cmo_action_cards():
    """The three downstream agents the summary dispatches, read from the same
    artifact the summary slot renders — guaranteeing card ↔ action identity."""
    from agents import downstream
    cards = []
    if os.path.isfile(SUMMARY_PATH):
        try:
            with open(SUMMARY_PATH) as f:
                d = json.load(f)
        except Exception:
            d = {}
        for a in d.get("actions", []):
            agent = a.get("agent")
            if not agent:
                continue
            built = downstream.is_built(agent)
            cards.append({
                "id": agent, "agent": agent, "team": a.get("team"),
                "title": AGENT_META.get(agent, {}).get("title", agent),
                "desc": a.get("text", ""),
                "inputs": a.get("inputs", {}),       # scoped inputs (sent on run)
                "inputChips": _input_chips(a.get("inputs", {})),
                "built": built,
                "status": "built" if built else "planned",
            })
    return cards


def actions(role):
    if role == "cmo":
        return {"actions": cmo_action_cards()}
    return {"actions": ACTIONS.get(role, [])}


# ---- live Profound agent activations ----------------------------------------
# Action ids (Actions tab + CMO dispatch name) that, on run, configure and fire a
# real Profound Agent-Builder graph via the REST API (agents/runloop.py), poll it
# to a terminal state, and return its output as the run summary. id -> spec.
PROFOUND_AGENTS = {
    "brand_risk": {  # Brand · Sentiment-risk response (Actions tab)
        "name": "Top Sentiment Themes Report",
        "agent_id": "019e9d89-ccfb-7223-a8d0-69070c817bcb",
        "input_var": "403aa7a7-9ab4-4bca-a74d-149593bce97f",   # "Profound Topic"
        "output_var": "31eb9b22-20a1-4664-a20d-2089d5af2d5b",  # "Final Report"
    },
}
PROFOUND_AGENTS["brand_risk_response"] = PROFOUND_AGENTS["brand_risk"]  # CMO dispatch name


def _negative_themes(region, limit=8):
    """Owned-brand themes with net-negative sentiment, worst first (snapshot)."""
    con = _con()
    try:
        rows = _q(con,
            "SELECT LOWER(theme) theme, ROUND(SUM(positive)-SUM(negative),0) net, "
            "SUM(occurrences) occ FROM fact_sentiment fs JOIN region r ON fs.region_id=r.id "
            "WHERE r.name=? AND asset_name=? GROUP BY LOWER(theme) HAVING net<0 "
            "ORDER BY net ASC, occ DESC LIMIT ?", (region, OWNED_BRAND, limit))
        taxonomy = [r["name"] for r in _q(con, "SELECT name FROM topic")]
    finally:
        con.close()
    return [{"theme": r["theme"], "net": int(r["net"]), "occ": r["occ"]} for r in rows], taxonomy


def _map_to_topic(themes, taxonomy):
    """Pick the Profound taxonomy topic the worst negative theme belongs to."""
    for t in themes:                                   # worst-first
        for top in taxonomy:
            if top.lower() in t["theme"]:
                return top
    return "Privacy" if "Privacy" in taxonomy else (taxonomy[0] if taxonomy else "Privacy")


def _activate_profound_agent(spec, value, poll_s=120):
    """Configure → run → poll a live Profound agent. Returns a render block."""
    from agents.runloop import AgentRunLoop
    block = {"name": spec["name"], "agentId": spec["agent_id"],
             "configured": {spec.get("input_title", "Profound Topic"): value},
             "status": "error", "report": "", "runId": None}
    try:
        rl = AgentRunLoop()
        run = rl.run_agent(spec["agent_id"], {spec["input_var"]: value})
        block["runId"] = run.get("id")
        res = rl.poll_run(spec["agent_id"], block["runId"], timeout_s=poll_s)
        block["status"] = res.get("status", "unknown")
        out = res.get("outputs") or {}
        block["report"] = out.get(spec["output_var"]) or (next(iter(out.values()), "") if out else "")
    except Exception as e:
        block["status"] = "error"
        block["report"] = "Agent run error: " + str(e)
    return block


def run_brand_sentiment_action(action_id, ctx):
    """Show the topics with the most negative sentiment, then fire the live
    Profound sentiment agent on the worst topic and return its report."""
    region = (ctx or {}).get("region") or "United States"
    themes, taxonomy = _negative_themes(region)
    topic = _map_to_topic(themes, taxonomy)
    agent_run = _activate_profound_agent(PROFOUND_AGENTS[action_id], topic)
    worst = themes[0]["theme"].title() if themes else "—"
    summary = (str(len(themes)) + " net-negative themes need a response — worst is '" + worst +
               "'. Activated the Profound '" + agent_run["name"] + "' agent on topic '" +
               topic + "' (" + agent_run["status"] + ").")
    return {
        "runId": "run_" + os.urandom(2).hex(), "status": "done", "agent": action_id,
        "summary": summary,
        "columns": ["Theme", "Net sentiment", "Mentions"],
        "rows": [[t["theme"].title(), t["net"], t["occ"]] for t in themes],
        "preview": [t["theme"].title() + ": net " + ("+" if t["net"] >= 0 else "") + str(t["net"]) +
                    " (" + str(t["occ"]) + " mentions)" for t in themes],
        "agentRun": agent_run,
        "seeded": ctx,
    }


def run_action(action_id, ctx):
    # Actions wired to a live Profound Agent-Builder graph run it for real.
    if action_id in PROFOUND_AGENTS:
        return run_brand_sentiment_action(action_id, ctx)
    # Downstream specialist agents do a real task against the snapshot.
    from agents import downstream
    if downstream.is_built(action_id):
        r = downstream.run_task(action_id, ctx or {})
        return {"runId": "run_" + os.urandom(2).hex(), "status": "done", "agent": action_id,
                "summary": r.get("summary", ""), "preview": r.get("preview", []),
                "columns": r.get("columns", []), "rows": r.get("rows", []), "seeded": ctx}
    base = RUN_RESULTS.get(action_id, {"summary": "Action completed.", "preview": "—"})
    return {"runId": "run_" + os.urandom(2).hex(), "status": "done",
            "summary": base["summary"], "preview": base["preview"], "seeded": ctx}
