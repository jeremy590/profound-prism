"""Per-role AI summaries for the Prism dashboard (the producer side).

Writes data/<role>_summary.json = {"summary": [two paragraphs], "actions": [one
action]} for SEO, PM, Brand and PR. (CMO is produced by agents/cmo.py.)

Deterministic + offline: pure functions of the static snapshot, so the same DB
yields the same summary every time. Same rules as the CMO summary — no em
dashes, significant figures wrapped in **bold** for the renderer. Each summary
carries exactly ONE action, mapped 1:1 to a downstream agent with scoped inputs.

    SEO   → seo_citation_gap_closer
    PM    → pm_usecase_tracker
    Brand → brand_risk_response   (a live Profound graph in the dashboard)
    PR    → pr_citation_outreach

Run:  python -m agents.summaries          # writes all four
"""
import json
import os
import sqlite3

from config import DB_PATH, OWNED_BRAND
from agents import downstream

OUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OWNED_DOMAINS = downstream.OWNED_DOMAINS


def _con():
    uri = "file:" + os.path.abspath(DB_PATH) + "?mode=ro"
    con = sqlite3.connect(uri, uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def _topics_by_vis(con, region):
    return _rows(con, """
        SELECT topic, ROUND(AVG(visibility_score)*100,0) AS vis
        FROM vw_prompt_overview WHERE region=? AND visibility_score IS NOT NULL
        GROUP BY topic ORDER BY vis DESC
    """, (region,))


def _owned_domain_rank(con, region):
    board = _rows(con, """
        SELECT root_domain, SUM(count) AS c
        FROM fact_citation ci JOIN region r ON r.id=ci.region_id
        WHERE r.name=? GROUP BY root_domain ORDER BY c DESC
    """, (region,))
    ranks = {b["root_domain"]: i + 1 for i, b in enumerate(board)}
    for d in OWNED_DOMAINS:
        if d in ranks:
            return d, ranks[d], len(board)
    return OWNED_DOMAINS[0], None, len(board)


def _weak_engines(con, region, n=3):
    rows = _rows(con, """
        SELECT m.name AS engine,
               SUM(CASE WHEN ci.citation_category='owned' THEN ci.count ELSE 0 END)*1.0
                 / NULLIF(SUM(ci.count),0) AS owned_share
        FROM fact_citation ci JOIN model m ON m.id=ci.model_id JOIN region r ON r.id=ci.region_id
        WHERE r.name=? GROUP BY m.name ORDER BY owned_share ASC LIMIT ?
    """, (region, n))
    return [r["engine"] for r in rows]


def _sentiment_net(con, region, asset):
    r = _rows(con, """
        SELECT ROUND(SUM(positive)-SUM(negative),0) AS net
        FROM fact_sentiment s JOIN region r ON r.id=s.region_id
        WHERE r.name=? AND asset_name=?
    """, (region, asset))
    return int(r[0]["net"]) if r and r[0]["net"] is not None else 0


def _competitors(con, region, owned, n=2):
    rows = _rows(con, """
        SELECT asset_name, AVG(share_of_voice) AS sov
        FROM vw_visibility_ranked WHERE region=?
        GROUP BY asset_name HAVING COUNT(*) >= 4 ORDER BY sov DESC
    """, (region,))
    return [r["asset_name"] for r in rows if r["asset_name"] != owned][:n]


# ── per-role generators ──────────────────────────────────────────────────────
def _seo(region):
    con = _con()
    try:
        topics = _topics_by_vis(con, region)
        weak = [t["topic"] for t in topics[-5:]][::-1]
        dom, rank, total = _owned_domain_rank(con, region)
        weak_eng = _weak_engines(con, region, 3)
        gap = _rows(con, """
            SELECT COUNT(*) AS n FROM vw_prompt_overview
            WHERE region=? AND visibility_score > 0.5 AND citation_share < 0.05
        """, (region,))[0]["n"]
    finally:
        con.close()
    w0, w1 = (weak + ["", ""])[:2]
    p1 = (f"Across the category, third-party domains hold the citations and our own pages "
          f"barely register: **{dom}** ranks **#{rank}** of {total} cited domains.")
    p2 = (f"**{gap}** prompts have strong visibility but weak citations, concentrated in "
          f"**{w0} and {w1}**. Those are the pages to build or refresh first.")
    action = {"team": "SEO", "agent": "seo_citation_gap_closer",
              "text": f"build content for the citation-gap prompts in **{w0} and {w1}**.",
              "inputs": {"region": region, "weak_topics": weak, "weak_engines": weak_eng}}
    return {"summary": [p1, p2], "actions": [action]}


def _pm(region):
    con = _con()
    try:
        topics = _topics_by_vis(con, region)
        comps = _competitors(con, region, OWNED_BRAND, 2)
    finally:
        con.close()
    top, bottom = topics[0]["topic"], topics[-1]["topic"]
    weak = [t["topic"] for t in topics[-3:]][::-1]
    adj = downstream.run_pm({"region": region})
    adj0 = (adj["rows"][0][0] if adj["rows"] else "adjacent questions")
    comp_str = " and ".join("**" + c + "**" for c in comps) or "rival products"
    p1 = (f"We surface most strongly in **{top}** use-cases and weakest in **{bottom}**, "
          f"across {len(topics)} tracked topics.")
    p2 = (f"Engines spin off adjacent questions like **{adj0}**; the products recommended "
          f"alongside us include {comp_str}.")
    action = {"team": "PM", "agent": "pm_usecase_tracker",
              "text": f"cluster the weak use-cases (**{', '.join(weak)}**) and surface the "
                      f"adjacent questions to answer.",
              "inputs": {"region": region, "weak_topics": weak}}
    return {"summary": [p1, p2], "actions": [action]}


def _brand(region):
    con = _con()
    try:
        net = _sentiment_net(con, region, OWNED_BRAND)
        comps = _competitors(con, region, OWNED_BRAND, 1)
        leader = comps[0] if comps else "Claude"
        leader_net = _sentiment_net(con, region, leader)
    finally:
        con.close()
    br = downstream.run_brand({"region": region})
    neg = [r[0] for r in br.get("rows", [])][:2]
    neg_str = ", ".join("**" + t + "**" for t in neg) or "**privacy and accuracy**"
    us_word = "negatively" if net < 0 else "positively"
    ld_word = "positively" if leader_net >= 0 else "negatively"
    p1 = (f"AI frames us **net-{us_word} ({net:+d})** overall, while it frames **{leader}** "
          f"**{ld_word} ({leader_net:+d})**.")
    p2 = (f"The themes dragging us down are {neg_str}. These are the characterisations to "
          f"respond to before they cap visibility.")
    action = {"team": "Brand", "agent": "brand_risk_response",
              "text": f"draft responses for the net-negative themes: {neg_str}.",
              "inputs": {"region": region, "negative_themes": neg}}
    return {"summary": [p1, p2], "actions": [action]}


def _pr(region):
    pr = downstream.run_pr({"region": region, "owned_domains": OWNED_DOMAINS})
    rows = pr.get("rows", [])
    top = rows[:3]
    names = ", ".join("**" + r[0] + "**" for r in top) or "third-party domains"
    b0 = (top[0][0] + " owns **" + str(top[0][1]) + "**") if top else ""
    b1 = (top[1][0] + " owns **" + str(top[1][1]) + "**") if len(top) > 1 else ""
    p1 = (f"**{len(rows)}** third-party domains shape category answers and none are ours; "
          f"the heaviest are {names}.")
    p2 = (f"By beat, {b0} and {b1} — the publications to pitch so our story carries more "
          f"weight than community sources.")
    action = {"team": "PR", "agent": "pr_citation_outreach",
              "text": "pitch the third-party domains shaping the category that do not cite us.",
              "inputs": {"region": region, "owned_domains": OWNED_DOMAINS,
                         "top_third_party": [r[0] for r in rows[:5]]}}
    return {"summary": [p1, p2], "actions": [action]}


GENERATORS = {"seo": _seo, "pm": _pm, "brand": _brand, "pr": _pr}


def generate(role, region="United States"):
    out = GENERATORS[role](region)
    out["context"] = {"role": role, "region": region, "owned": OWNED_BRAND}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, role + "_summary.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    return out


def generate_all(region="United States"):
    return {role: generate(role, region) for role in GENERATORS}


if __name__ == "__main__":
    for role, out in generate_all().items():
        print(f"\n### {role}")
        for p in out["summary"]:
            print("  ", p)
        for a in out["actions"]:
            print("   ->", a["team"], a["agent"], a["text"])
