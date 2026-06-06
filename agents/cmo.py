"""Commercial Director / CMO agent — the orchestrator/router.

Pivots the Profound snapshot into an executive brief and FIRES the specialists.
Mirrors Agent Sketch #1, recast for a single snapshot (level-based, no deltas)
and with the tail upgraded from "notify" to "dispatch":

    facts (SQL)  →  synthesise (LLM)  →  threshold gate  →  dispatch  →  brief

The facts are computed deterministically in SQL — the LLM only *frames* them,
it never sources a number. The gate + dispatch are deterministic too, so what
gets escalated and fired is grounded, not model-invented.

Run:
    python -m agents.cmo                 # product lens, US, with LLM framing
    python -m agents.cmo --lens house    # treat ChatGPT + OpenAI as one house
    python -m agents.cmo --no-llm        # deterministic brief, no API call
    python -m agents.cmo --dispatch live # actually POST runs (else guarded)
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3

import yaml

from config import DB_PATH, OWNED_BRAND
from agents.runloop import AgentRunLoop

PRISM_PATH = os.path.join(os.path.dirname(__file__), "..", "prisms", "cmo.yaml")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Brand families: which assets count as "us" under each lens, and which web
# domains we own (for the under-cited → PR signal).
HOUSE_ASSETS = ["ChatGPT", "OpenAI"]
OWNED_DOMAINS = ["openai.com", "chatgpt.com"]


# ── data layer (deterministic facts) ────────────────────────────────────────

def _conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def _rows(con, sql, params=()):
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def pack_position(con, owned_assets, region, min_engines=4):
    """Brand leaderboard by mean SoV across engines → our standing in the pack.

    The raw data carries a long tail of entities mentioned in a single engine;
    the competitive PACK is brands tracked across most engines (>= min_engines).
    Our rank is reported within that pack, and we name who is ahead of us — an
    exec brief says "#5, behind Claude/Google/OpenAI/Gemini", not "5 of 3825".
    """
    board = _rows(con, """
        SELECT asset_name,
               ROUND(AVG(share_of_voice), 4)      AS mean_sov,
               ROUND(AVG(visibility_score)*100,1) AS mean_vis,
               COUNT(*)                           AS engines
        FROM vw_visibility_ranked
        WHERE region = ?
        GROUP BY asset_name
        HAVING engines >= ?
        ORDER BY mean_sov DESC
    """, (region, min_engines))
    if not board:
        return {}
    leader = board[0]
    owned_rows = [b for b in board if b["asset_name"] in owned_assets]
    our_best = owned_rows[0] if owned_rows else None
    our_rank = board.index(our_best) + 1 if our_best else None
    ahead = [b["asset_name"] for b in board[:our_rank - 1]] if our_rank else []
    top = board[:5]
    pack_spread = round(top[0]["mean_sov"] - top[-1]["mean_sov"], 4) if len(top) > 1 else 0.0
    house_share = round(sum(b["mean_sov"] for b in owned_rows), 4)
    return {
        "leaderboard": board[:12],
        "leader": {"asset": leader["asset_name"], "mean_sov": leader["mean_sov"],
                   "mean_vis": leader["mean_vis"]},
        "our_best": {"asset": our_best["asset_name"], "mean_sov": our_best["mean_sov"],
                     "mean_vis": our_best["mean_vis"]} if our_best else None,
        "our_rank": our_rank,
        "ahead": ahead,
        "pack_size": len(board),
        "min_engines": min_engines,
        "pack_spread": pack_spread,
        "house_share": house_share,
        "house_assets": owned_assets,
        "sov_gap_to_leader": round(leader["mean_sov"] - (our_best["mean_sov"] if our_best else 0), 4),
    }


def engine_gap_map(con, owned_assets, region):
    """Per-engine gap (vis pts) between our best owned asset and the engine leader."""
    placeholders = ",".join("?" * len(owned_assets))
    ours = _rows(con, f"""
        SELECT model,
               MAX(visibility_score)*100 AS our_vis,
               MIN(visibility_rank)      AS our_rank
        FROM vw_visibility_ranked
        WHERE region = ? AND asset_name IN ({placeholders})
        GROUP BY model
    """, (region, *owned_assets))
    leaders = _rows(con, """
        SELECT model, asset_name AS leader, visibility_score*100 AS leader_vis
        FROM vw_visibility_ranked
        WHERE region = ? AND visibility_rank = 1
    """, (region,))
    lead_by_model = {r["model"]: r for r in leaders}
    out = []
    for r in ours:
        lead = lead_by_model.get(r["model"])
        if not lead:
            continue
        out.append({
            "engine": r["model"],
            "our_vis": round(r["our_vis"], 1),
            "our_rank": r["our_rank"],
            "leader": lead["leader"],
            "leader_vis": round(lead["leader_vis"], 1),
            "gap_pts": round(lead["leader_vis"] - r["our_vis"], 1),
        })
    out.sort(key=lambda x: x["gap_pts"], reverse=True)
    return out


def weak_topics(con, owned_primary, region, limit=5):
    """Lowest-visibility topics — the SEO dispatch scope and the Product action.

    Aggregated across ALL engines (region-only) so it matches the dashboard's
    default 'All engines' topic tile — the summary and the tile must agree.
    """
    return _rows(con, """
        SELECT topic,
               ROUND(AVG(visibility_score)*100,1) AS avg_vis,
               ROUND(AVG(citation_share),3)       AS avg_cit,
               COUNT(DISTINCT prompt_id)          AS prompts
        FROM vw_prompt_overview
        WHERE region = ? AND visibility_score IS NOT NULL
        GROUP BY topic
        ORDER BY avg_vis ASC
        LIMIT ?
    """, (region, limit))


def sentiment_facts(con, owned_primary, region, net_threshold):
    """Overall net sentiment + the net-negative themes (the Brand dispatch scope)."""
    overall = _rows(con, """
        SELECT asset_name,
               ROUND(SUM(positive),0) AS pos,
               ROUND(SUM(negative),0) AS neg,
               ROUND(SUM(positive)-SUM(negative),0) AS net,
               SUM(occurrences) AS occ
        FROM fact_sentiment fs JOIN region r ON fs.region_id = r.id
        WHERE r.name = ? AND asset_name = ?
        GROUP BY asset_name
    """, (region, owned_primary))
    neg_themes = _rows(con, """
        SELECT LOWER(theme) AS theme,
               ROUND(SUM(positive)-SUM(negative),1) AS net,
               SUM(occurrences) AS occ
        FROM fact_sentiment fs JOIN region r ON fs.region_id = r.id
        WHERE r.name = ? AND asset_name = ?
        GROUP BY LOWER(theme)
        HAVING net < ?
        ORDER BY occ DESC, net ASC
        LIMIT 8
    """, (region, owned_primary, net_threshold))
    return {
        "overall": overall[0] if overall else None,
        "negative_themes": neg_themes,
    }


def owned_domain_citation(con, owned_domains, region):
    """Where our own domains rank in the category citation leaderboard (US, all engines)."""
    board = _rows(con, """
        SELECT root_domain, SUM(count) AS cites
        FROM fact_citation fc JOIN region r ON fc.region_id = r.id
        WHERE r.name = ?
        GROUP BY root_domain
        ORDER BY cites DESC
    """, (region,))
    ranks = {b["root_domain"]: i + 1 for i, b in enumerate(board)}
    total = sum(b["cites"] for b in board) or 1
    owned = []
    for d in owned_domains:
        if d in ranks:
            cites = next(b["cites"] for b in board if b["root_domain"] == d)
            owned.append({"domain": d, "rank": ranks[d], "cites": cites,
                          "share_pct": round(100 * cites / total, 2)})
    best_rank = min((o["rank"] for o in owned), default=None)
    return {"owned": owned, "best_rank": best_rank, "domains_in_category": len(board),
            "top_third_party": [b["root_domain"] for b in board[:5]]}


# ── gate (deterministic) ─────────────────────────────────────────────────────

def threshold_gate(facts, th):
    """Turn facts + thresholds into breaches. Each breach carries the scope value
    the matching dispatch rule needs."""
    breaches = []

    weak_engines = [e for e in facts["engine_gap"] if e["gap_pts"] >= th["engine_gap_pts"]]
    if weak_engines:
        breaches.append({
            "type": "engine_gap",
            "detail": f"{len(weak_engines)} engine(s) ≥{th['engine_gap_pts']}pt gap to leader",
            "engines": [e["engine"] for e in weak_engines],
            "topics": [t["topic"] for t in facts["weak_topics"]],
        })

    neg = facts["sentiment"]["negative_themes"]
    overall = facts["sentiment"]["overall"]
    overall_negative = overall and overall["net"] < th["net_sentiment"]
    if neg or overall_negative:
        breaches.append({
            "type": "negative_sentiment_theme",
            "detail": (f"net {overall['net']:+.0f} overall" if overall else "") +
                      (f"; {len(neg)} net-negative theme(s)" if neg else ""),
            "themes": [t["theme"] for t in neg],
        })

    od = facts["owned_domain"]
    if od["best_rank"] is None or od["best_rank"] > th["visibility_rank_max"]:
        breaches.append({
            "type": "owned_domain_undercited",
            "detail": (f"owned domain best rank {od['best_rank']} of "
                       f"{od['domains_in_category']}" if od["best_rank"]
                       else "owned domains absent from citation leaderboard"),
            "domains": [o["domain"] for o in od["owned"]] or OWNED_DOMAINS,
            "top_third_party": od["top_third_party"],
        })
    return breaches


def build_dispatch(breaches, dispatch_rules, region, mode="guarded"):
    """Map breaches → specialist hand-offs.

    mode:
      plan    — deterministic, NO network: record {status: planned} + inputs.
                Used by the dashboard (static DB → reproducible, offline).
      guarded — resolve each agent by name; record would_dispatch if not built.
      live    — actually POST the run and poll it to a terminal state.
    """
    loop = AgentRunLoop() if mode in ("guarded", "live") else None
    by_type = {d["when"]: d for d in dispatch_rules}
    manifest = []
    for b in breaches:
        rule = by_type.get(b["type"])
        if not rule:
            continue
        inputs = {"region": region}
        if b["type"] == "engine_gap":
            inputs.update({"weak_engines": b["engines"], "weak_topics": b["topics"]})
        elif b["type"] == "negative_sentiment_theme":
            inputs.update({"negative_themes": b["themes"]})
        elif b["type"] == "owned_domain_undercited":
            inputs.update({"owned_domains": b["domains"],
                           "top_third_party": b["top_third_party"]})
        if mode == "plan":
            manifest.append({"agent": rule["agent"], "status": "planned", "inputs": inputs})
        else:
            manifest.append(loop.dispatch(rule["agent"], inputs, wait=mode == "live"))
    return manifest


# ── synthesis (LLM with deterministic fallback) ──────────────────────────────

SYS = """You are the Commercial Director's AI-search analyst. You turn one
point-in-time snapshot of AI-visibility data into an executive brief.

Audience: a CMO who decides whether to WORRY, FUND, ESCALATE, or REALLOCATE.
Not a data dump — at most 5 items, each framed as a decision, not a chart.

HARD RULES:
- This is ONE snapshot. Never say "trend", "this week", "growing", "moved".
- Every number you cite is given to you in FACTS. Never invent one.
- visibility is already in percentage points; share_of_voice is a 0–1 decimal.
- Lead with the single number that most changes the CMO's decision.

For each item's "dispatch", use ONLY a name from DISPATCH_AGENTS (given in the
payload) or "none" — never invent an agent name.

Return ONLY JSON:
{
 "headline_number": {"label": "...", "value": "...", "why": "..."},
 "items": [{"title": "...", "severity": "red|amber|green",
            "finding": "...", "decision": "...", "dispatch": "agent or none"}],
 "north_star": {"metric": "...", "value": "...", "note": "..."}
}"""


def synthesise_llm(facts, breaches, dispatch_agents):
    import anthropic
    client = anthropic.Anthropic()  # ANTHROPIC_API_KEY from env
    payload = {"facts": facts, "breaches": breaches,
               "DISPATCH_AGENTS": dispatch_agents}
    msg = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        system=SYS,
        messages=[{"role": "user",
                   "content": "FACTS + breaches:\n" + json.dumps(payload, default=str)}],
    )
    text = msg.content[0].text.strip()
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()
    return json.loads(text)


def synthesise_fallback(facts, breaches):
    """Deterministic brief when the LLM is off — templated straight from facts."""
    pp, sn = facts["pack_position"], facts["sentiment"]
    leader, our = pp.get("leader", {}), pp.get("our_best", {})
    worst = facts["engine_gap"][0] if facts["engine_gap"] else None
    items = []
    if worst:
        items.append({
            "title": f"Biggest visibility gap is on {worst['engine']}, not our home engine",
            "severity": "red" if worst["gap_pts"] >= 15 else "amber",
            "finding": f"{worst['gap_pts']}pt gap to {worst['leader']} on {worst['engine']} "
                       f"(rank {worst['our_rank']}).",
            "decision": "Reallocate AEO effort to the worst engines, not the strongest.",
            "dispatch": "seo_citation_gap_closer",
        })
    if sn["overall"] and sn["overall"]["net"] < 0:
        items.append({
            "title": "AI characterises us net-negatively",
            "severity": "red",
            "finding": f"Net sentiment {sn['overall']['net']:+.0f} "
                       f"({sn['overall']['pos']:.0f} pos / {sn['overall']['neg']:.0f} neg).",
            "decision": "Escalate as a reputation risk; brief comms on the worst themes.",
            "dispatch": "brand_risk_response",
        })
    wt = facts.get("weak_topics") or []
    if wt:
        names = ", ".join(t["topic"] for t in wt[:2])
        items.append({
            "title": f"Weakest topics are {names}",
            "severity": "amber",
            "finding": f"{wt[0]['topic']} visibility is only {wt[0]['avg_vis']} "
                       f"(citation {wt[0]['avg_cit']}) — our lowest.",
            "decision": f"Fund topic-targeted content for {names}.",
            "dispatch": "seo_citation_gap_closer",
        })
    od = facts.get("owned_domain") or {}
    if od.get("owned"):
        best = min(od["owned"], key=lambda o: o["rank"])
        items.append({
            "title": "Our own domains barely get cited",
            "severity": "amber",
            "finding": f"Best owned domain {best['domain']} ranks #{best['rank']} of "
                       f"{od['domains_in_category']} ({best['share_pct']}% share); "
                       f"third-party sources ({', '.join(od['top_third_party'][:3])}) dominate.",
            "decision": "Fund citation outreach so our properties carry more of the narrative.",
            "dispatch": "pr_citation_outreach",
        })
    if pp.get("pack_spread", 1) < 0.03 and pp.get("our_rank"):
        ahead = ", ".join(pp.get("ahead", [])) or "no one"
        items.append({
            "title": "The race is winnable — the leading pack is tightly bunched",
            "severity": "green",
            "finding": f"#{pp['our_rank']} by share of voice (behind {ahead}); "
                       f"top-5 SoV spread only {pp['pack_spread']:.3f}.",
            "decision": "Fund now while the gap is closeable, not after it widens.",
            "dispatch": "none",
        })
    return {
        "headline_number": {
            "label": f"SoV gap to category leader ({leader.get('asset','?')})",
            "value": f"{pp.get('sov_gap_to_leader', 0):.3f} SoV pts",
            "why": f"#{pp.get('our_rank','?')} by share of voice, behind "
                   f"{', '.join(pp.get('ahead', [])) or 'no one'}; "
                   f"house share {pp.get('house_share',0):.3f}.",
        },
        "items": items[:5],
        "north_star": {
            "metric": "net-sentiment-adjusted SoV vs category leader",
            "value": f"SoV {our.get('mean_sov',0):.3f} @ net {sn['overall']['net']:+.0f}"
                     if sn["overall"] else "n/a",
            "note": "Interim — swap to a revenue-tied metric once referrals/GA4 is connected "
                    "(no referrals table in this snapshot).",
        },
    }


# ── render ───────────────────────────────────────────────────────────────────

def to_markdown(brief, manifest, owned_primary, region, lens):
    hn = brief["headline_number"]
    lines = [
        f"# CMO Exec Brief — {owned_primary} ({lens} lens), {region}",
        "",
        f"**{hn['label']}: {hn['value']}**  ",
        f"_{hn['why']}_",
        "",
        "## Escalation items",
    ]
    sev = {"red": "🔴", "amber": "🟠", "green": "🟢"}
    for it in brief["items"]:
        lines += [
            f"### {sev.get(it['severity'], '•')} {it['title']}",
            f"- **Finding:** {it['finding']}",
            f"- **Decision:** {it['decision']}",
            f"- **Dispatch:** `{it['dispatch']}`" if it.get("dispatch", "none") != "none"
            else "- **Dispatch:** —",
            "",
        ]
    ns = brief["north_star"]
    lines += ["## Proposed north-star", f"- **{ns['metric']}** = {ns['value']}",
              f"- _{ns['note']}_", "", "## Dispatch manifest"]
    if not manifest:
        lines.append("- _no breaches → nothing dispatched_")
    for m in manifest:
        tag = {"dispatched": "✅ live", "would_dispatch": "⏸ guarded",
               "planned": "📋 planned", "dispatch_error": "⚠️ error"}.get(m["status"], m["status"])
        lines.append(f"- **{m['agent']}** [{tag}] — inputs: `{json.dumps(m['inputs'])}`")
        if m.get("note"):
            lines.append(f"  - _{m['note']}_")
    return "\n".join(lines)


# ── orchestrate ──────────────────────────────────────────────────────────────

def run(lens="product", region="United States", use_llm=True, dispatch_mode="guarded"):
    prism = yaml.safe_load(open(PRISM_PATH))
    th = prism["thresholds"]
    dispatch_rules = prism["dispatch"]

    owned_primary = OWNED_BRAND                       # "ChatGPT"
    owned_assets = HOUSE_ASSETS if lens == "house" else [owned_primary]

    con = _conn()
    try:
        facts = {
            "lens": lens,
            "region": region,
            "owned_primary": owned_primary,
            "owned_assets": owned_assets,
            "pack_position": pack_position(con, owned_assets, region),
            "engine_gap": engine_gap_map(con, owned_assets, region),
            "weak_topics": weak_topics(con, owned_primary, region),
            "sentiment": sentiment_facts(con, owned_primary, region, th["net_sentiment"]),
            "owned_domain": owned_domain_citation(con, OWNED_DOMAINS, region),
        }
    finally:
        con.close()

    breaches = threshold_gate(facts, th)

    if use_llm:
        try:
            brief = synthesise_llm(facts, breaches, [d["agent"] for d in dispatch_rules])
        except Exception as e:
            print(f"  LLM synthesis failed ({e}); using deterministic fallback.")
            brief = synthesise_fallback(facts, breaches)
    else:
        brief = synthesise_fallback(facts, breaches)

    manifest = build_dispatch(breaches, dispatch_rules, region, dispatch_mode)

    os.makedirs(OUT_DIR, exist_ok=True)
    out = {"brief": brief, "facts": facts, "breaches": breaches, "dispatch": manifest,
           "context": {"lens": lens, "region": region, "owned": owned_primary}}
    with open(os.path.join(OUT_DIR, "cmo_brief.json"), "w") as f:
        json.dump(out, f, indent=2, default=str)
    md = to_markdown(brief, manifest, owned_primary, region, lens)
    with open(os.path.join(OUT_DIR, "cmo_brief.md"), "w") as f:
        f.write(md)
    print(md)
    print(f"\n[written] data/cmo_brief.md  ·  data/cmo_brief.json")
    return out


# ── dashboard entry (auto-generated, cached, offline) ────────────────────────

def _slug(s):
    return "".join(c.lower() if c.isalnum() else "_" for c in s).strip("_")


def _condensed(facts, breaches):
    """Boil the facts down to the executive form the dashboard shows: two short
    narrative paragraphs + three action points, each routed to a team."""
    pp, sn = facts["pack_position"], facts["sentiment"]
    eg, wt = facts["engine_gap"], facts["weak_topics"]
    leader = pp.get("leader", {}).get("asset", "the leader")
    rank, gap = pp.get("our_rank"), pp.get("sov_gap_to_leader", 0)
    net = sn["overall"]["net"] if sn.get("overall") else None
    worst = eg[0] if eg else None
    us = facts["owned_primary"]

    # House view: sum the OpenAI family (ChatGPT + OpenAI) and rank that combined
    # share against the other single brands — an honest "as one house" figure.
    board = pp.get("leaderboard", [])
    sov = {b["asset_name"]: b["mean_sov"] for b in board}
    house_combined = round(sum(sov.get(a, 0) for a in HOUSE_ASSETS), 4)
    house_rank = 1 + sum(1 for b in board
                         if b["asset_name"] not in HOUSE_ASSETS and b["mean_sov"] > house_combined)
    house_clause = ("would top the category" if house_rank == 1
                    else f"would rank #{house_rank}")

    # Significant figures wrapped in **bold** (the renderer parses it). No em dashes.
    p1 = (f"{us} sits **#{rank}** in the frontier-model pack on share of voice, only "
          f"**{gap:.3f}** behind **{leader}**. But counted as one house, the OpenAI "
          f"family (ChatGPT + OpenAI) combines for **{house_combined:.3f} SoV**, enough "
          f"that it **{house_clause}**. The race is **winnable**.")
    why = []
    if net is not None and net < 0:
        why.append(f"AI engines describe us **net-negatively ({net:+.0f})** while they "
                   f"describe {leader} **positively**")
    if worst:
        why.append(f"the visibility gap is widest on **{worst['engine']}**, where we trail "
                   f"by **{round(worst['gap_pts'])} points**, not on {us} itself")
    p2 = ("The real issue is quality and concentration, not headline rank. " +
          ". ".join(s[0].upper() + s[1:] for s in why) + ".") if why else ""

    # Three actions, each mapped 1:1 to a downstream agent and carrying the
    # scoped inputs that agent needs. Inputs come from the breaches so the
    # summary, the Actions tab and the dispatch manifest all share one identity.
    by = {b["type"]: b for b in breaches}
    actions = []
    if "negative_sentiment_theme" in by:
        themes = ", ".join(t["theme"] for t in sn["negative_themes"][:2]) or "privacy and accuracy"
        actions.append({
            "team": "Brand", "agent": "brand_risk_response",
            "text": f"review the **sentiment gap ({net:+.0f})** and the themes driving it: **{themes}**.",
            "inputs": {"region": facts["region"], "negative_themes": by["negative_sentiment_theme"]["themes"]},
        })
    if "engine_gap" in by:
        names = " and ".join(t["topic"] for t in wt[:2]) if wt else "our weakest topics"
        eng = worst["engine"] if worst else by["engine_gap"]["engines"][0]
        actions.append({
            "team": "SEO", "agent": "seo_citation_gap_closer",
            "text": f"close the citation gap where we are weakest: **{eng}** and the **{names}** topics.",
            "inputs": {"region": facts["region"], "weak_engines": by["engine_gap"]["engines"],
                       "weak_topics": by["engine_gap"]["topics"]},
        })
    if "owned_domain_undercited" in by:
        od = facts.get("owned_domain") or {}
        best = min(od.get("owned") or [{"domain": "our domains", "rank": "?"}], key=lambda o: o.get("rank", 9999))
        actions.append({
            "team": "PR", "agent": "pr_citation_outreach",
            "text": f"our own pages barely get cited (**{best['domain']} #{best['rank']}**); "
                    f"pitch the third-party domains shaping the category.",
            "inputs": {"region": facts["region"], "owned_domains": by["owned_domain_undercited"]["domains"],
                       "top_third_party": by["owned_domain_undercited"]["top_third_party"]},
        })
    return {"summary": [p for p in (p1, p2) if p], "actions": actions[:3]}


def dashboard_brief(region="United States", lens="product", refresh=False):
    """Return the brief for the dashboard. The SQLite snapshot is STATIC, so the
    brief is generated once per (lens, region), cached, and re-served verbatim.

    Deterministic synthesis + plan-mode dispatch → no network, no API key, instant
    and reproducible. The richer LLM-written brief is available via the CLI; the
    dashboard does not depend on it.
    """
    cache = os.path.join(OUT_DIR, f"cmo_brief_{lens}_{_slug(region)}.json")
    if not refresh and os.path.isfile(cache):
        with open(cache) as f:
            data = json.load(f)
        if "condensed" in data:        # cache-version guard
            return data
    prism = yaml.safe_load(open(PRISM_PATH))
    th, rules = prism["thresholds"], prism["dispatch"]
    owned_assets = HOUSE_ASSETS if lens == "house" else [OWNED_BRAND]
    con = _conn()
    try:
        facts = {
            "lens": lens, "region": region, "owned_primary": OWNED_BRAND,
            "owned_assets": owned_assets,
            "pack_position": pack_position(con, owned_assets, region),
            "engine_gap": engine_gap_map(con, owned_assets, region),
            "weak_topics": weak_topics(con, OWNED_BRAND, region),
            "sentiment": sentiment_facts(con, OWNED_BRAND, region, th["net_sentiment"]),
            "owned_domain": owned_domain_citation(con, OWNED_DOMAINS, region),
        }
    finally:
        con.close()
    breaches = threshold_gate(facts, th)
    brief = synthesise_fallback(facts, breaches)
    manifest = build_dispatch(breaches, rules, region, mode="plan")
    condensed = _condensed(facts, breaches)
    out = {"brief": brief, "condensed": condensed, "breaches": breaches,
           "dispatch": manifest,
           "context": {"lens": lens, "region": region, "owned": OWNED_BRAND}}
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(cache, "w") as f:
        json.dump(out, f, indent=2, default=str)
    # Canonical artifact the dashboard's summary slot renders (the default CMO
    # view = product / US). This is the producer→renderer contract: the agent
    # terminal writes it; the dashboard reads it and stays empty until it lands.
    if lens == "product" and region == "United States":
        with open(os.path.join(OUT_DIR, "cmo_summary.json"), "w") as f:
            json.dump({**condensed, "context": out["context"]}, f, indent=2, default=str)
    return out


def main():
    ap = argparse.ArgumentParser(description="CMO orchestrator agent")
    ap.add_argument("--lens", choices=["product", "house"], default="product",
                    help="'product' = ChatGPT only; 'house' = ChatGPT + OpenAI")
    ap.add_argument("--region", default="United States")
    ap.add_argument("--no-llm", action="store_true", help="skip Claude; deterministic brief")
    ap.add_argument("--dispatch", choices=["plan", "guarded", "live"], default="guarded",
                    help="plan=offline intent only; guarded=check existence; live=POST+poll")
    a = ap.parse_args()
    run(lens=a.lens, region=a.region, use_llm=not a.no_llm, dispatch_mode=a.dispatch)


if __name__ == "__main__":
    main()
