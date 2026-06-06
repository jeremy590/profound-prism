"""Downstream specialist agents the CMO orchestrator dispatches to.

Each agent does one real downstream task against the (static, read-only) snapshot
and returns a compact result the dashboard renders: a one-line `summary`, a short
`preview` list, and an optional `columns`/`rows` table.

These are the local task implementations. When the matching Profound Agent Builder
graph exists, the same inputs flow to it via agents.runloop instead; until then,
these produce the artifact the team would act on. The CMO summary action, the
Actions-tab card and these tasks all key off the same `agent` id.

    seo_citation_gap_closer   ← engine_gap        (Brand-of-content: where we rank but aren't cited)
    brand_risk_response       ← negative_theme    (sentiment risk → talking points)
    pr_citation_outreach      ← owned_undercited  (third-party domains to pitch)
"""
import os
import sqlite3

from config import DB_PATH

OWNED_DOMAINS = ["openai.com", "chatgpt.com"]


def _con():
    uri = "file:" + os.path.abspath(DB_PATH) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


# ── seo_citation_gap_closer ──────────────────────────────────────────────────
def run_seo(inputs):
    """Prompts where we have visibility but weak citations, on the weak topics —
    each with the domain currently winning that citation (the page to beat)."""
    region = inputs.get("region", "United States")
    topics = inputs.get("weak_topics") or []
    con = _con()
    try:
        # high-visibility, weak-citation prompts in the weak topics
        place = ",".join("?" * len(topics)) if topics else "''"
        gap = _rows(con, f"""
            SELECT prompt, topic,
                   ROUND(visibility_score*100,0) AS vis,
                   ROUND(citation_share,3)       AS cit,
                   citation_rank
            FROM vw_prompt_overview
            WHERE region = ? AND visibility_score > 0.5
              {("AND topic IN (" + place + ")") if topics else ""}
            ORDER BY citation_share ASC
            LIMIT 8
        """, (region, *topics) if topics else (region,))
    finally:
        con.close()
    preview = [f"{g['prompt']}  ·  {g['topic']}  ·  vis {g['vis']:.0f}%, citation {g['cit']}"
               for g in gap]
    eng = ", ".join(inputs.get("weak_engines", [])[:3]) or "weak engines"
    return {
        "summary": f"{len(gap)} prompts have visibility but weak citations on "
                   f"{', '.join(topics[:2]) or 'the weak topics'} — content/citation targets "
                   f"to close the gap on {eng}.",
        "columns": ["Prompt", "Topic", "Visibility %", "Citation Share", "Citation Rank"],
        "rows": [[g["prompt"], g["topic"], g["vis"], g["cit"], g["citation_rank"]] for g in gap],
        "preview": preview,
    }


# ── brand_risk_response ──────────────────────────────────────────────────────
def run_brand(inputs):
    """Net-negative themes about us, side by side with how AI frames the leader —
    the raw material for talking points."""
    region = inputs.get("region", "United States")
    con = _con()
    try:
        ours = _rows(con, """
            SELECT LOWER(theme) AS theme,
                   ROUND(SUM(positive)-SUM(negative),1) AS net,
                   SUM(occurrences) AS occ
            FROM fact_sentiment fs JOIN region r ON fs.region_id=r.id
            WHERE r.name=? AND asset_name='ChatGPT'
            GROUP BY LOWER(theme) HAVING net < 0
            ORDER BY occ DESC, net ASC LIMIT 8
        """, (region,))
        claude = {t["theme"]: t["net"] for t in _rows(con, """
            SELECT LOWER(theme) AS theme, ROUND(SUM(positive)-SUM(negative),1) AS net
            FROM fact_sentiment fs JOIN region r ON fs.region_id=r.id
            WHERE r.name=? AND asset_name='Claude' GROUP BY LOWER(theme)
        """, (region,))}
    finally:
        con.close()
    preview = [f"{t['theme']}: us {t['net']:+.0f} vs Claude {claude.get(t['theme'], 0):+.0f} "
               f"({t['occ']} mentions)" for t in ours]
    return {
        "summary": f"{len(ours)} net-negative themes need a response. Lead with "
                   f"{ours[0]['theme'] if ours else 'the top theme'}, where AI frames us worst "
                   f"relative to Claude.",
        "columns": ["Theme", "Our net", "Claude net", "Mentions"],
        "rows": [[t["theme"], t["net"], claude.get(t["theme"], 0), t["occ"]] for t in ours],
        "preview": preview,
    }


# ── pr_citation_outreach ─────────────────────────────────────────────────────
def run_pr(inputs):
    """Third-party domains shaping category answers that we don't own — ranked by
    citations, with the topic beat each one owns (the pitch list)."""
    region = inputs.get("region", "United States")
    con = _con()
    try:
        rows = _rows(con, """
            SELECT ci.root_domain AS domain, t.name AS topic, SUM(ci.count) AS cites
            FROM fact_citation ci JOIN region r ON r.id=ci.region_id
            LEFT JOIN prompt p ON p.id=ci.prompt_id LEFT JOIN topic t ON t.id=p.topic_id
            WHERE r.name=? AND ci.citation_category != 'owned'
            GROUP BY ci.root_domain, t.name
        """, (region,))
    finally:
        con.close()
    agg, beat = {}, {}
    for r in rows:
        agg[r["domain"]] = agg.get(r["domain"], 0) + (r["cites"] or 0)
        if r["topic"] and (r["domain"] not in beat or r["cites"] > beat[r["domain"]][1]):
            beat[r["domain"]] = (r["topic"], r["cites"])
    owned = set(inputs.get("owned_domains") or OWNED_DOMAINS)
    ranked = sorted(((d, c) for d, c in agg.items() if d not in owned), key=lambda kv: -kv[1])[:10]
    preview = [f"{d}  ·  beat: {beat.get(d, ('—', 0))[0]}  ·  {c} citations" for d, c in ranked]
    return {
        "summary": f"{len(ranked)} third-party domains shape category answers and don't cite us. "
                   f"Top target: {ranked[0][0] if ranked else '—'}.",
        "columns": ["Domain", "Topic beat", "Citations"],
        "rows": [[d, beat.get(d, ("—", 0))[0], c] for d, c in ranked],
        "preview": preview,
    }


# ── pm_usecase_tracker ───────────────────────────────────────────────────────
def run_pm(inputs):
    """Adjacent questions engines spin off our prompts — the use-case gaps the
    product/docs could own, plus the weakest tracked use-case topics."""
    region = inputs.get("region", "United States")
    con = _con()
    try:
        adj = _rows(con, """
            SELECT query, SUM(total_fanouts) AS tf
            FROM fact_query_fanout f JOIN region r ON r.id=f.region_id
            WHERE r.name=? GROUP BY query ORDER BY tf DESC LIMIT 10
        """, (region,))
        weak = _rows(con, """
            SELECT topic, ROUND(AVG(visibility_score)*100,0) AS vis
            FROM vw_prompt_overview WHERE region=? AND visibility_score IS NOT NULL
            GROUP BY topic ORDER BY vis ASC LIMIT 3
        """, (region,))
    finally:
        con.close()
    weak_names = ", ".join(w["topic"] for w in weak)
    return {
        "summary": f"{len(adj)} adjacent questions engines spin off that the product or docs "
                   f"could own; weakest use-cases are {weak_names}.",
        "columns": ["Adjacent question", "Fan-outs"],
        "rows": [[a["query"], a["tf"]] for a in adj],
        "preview": [a["query"] for a in adj],
    }


REGISTRY = {
    "seo_citation_gap_closer": run_seo,
    "brand_risk_response": run_brand,
    "pr_citation_outreach": run_pr,
    "pm_usecase_tracker": run_pm,
}


def is_built(agent_id):
    return agent_id in REGISTRY


def run_task(agent_id, inputs):
    fn = REGISTRY.get(agent_id)
    if not fn:
        return {"summary": "Agent not built yet.", "preview": [], "columns": [], "rows": []}
    try:
        return fn(inputs or {})
    except Exception as e:
        return {"summary": "Agent error: " + str(e), "preview": [], "columns": [], "rows": []}
