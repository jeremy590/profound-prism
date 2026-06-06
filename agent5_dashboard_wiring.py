# Agent 5 — Strategic Citation Outreach: dashboard wiring
#
# Paste this entry INSIDE the PROFOUND_AGENTS = { ... } dict in dashboard_data.py
# (after the "pm_adjacent" entry, before the closing brace). That registry is what
# turns the PR persona's "Citation outreach" card from a stub into a live run of
# the published Profound graph.
#
# The display slot already exists:
#   AGENT_META["pr_citation_outreach"] = {"title": "PR · Citation outreach"}
# so the key below MUST stay "pr_citation_outreach" to match.
#
# Note on the payload: Agent 5 only requires {brand}. The dashboard's activation
# path (_activate_topic_agent) always sends {topic_id, brand} — the Agent-5 parser
# ignores the extra topic_id and defaults topic_count to 3, so it runs unchanged.
# If you want the dashboard to pass topic_count, _activate_topic_agent needs a
# small tweak; flag me and I'll write it.

    "pr_citation_outreach": {
        "name": "Strategic Citation Outreach",
        "agent_id": "<PASTE-PUBLISHED-AGENT-ID>",   # from the Agent Builder URL once published
        "brand": OWNED_BRAND,                         # ChatGPT
        "topic_metric": "citation",                   # display-only; agent finds topics itself
        "table": "fanout",                            # supporting table shown under the result
        "poll_s": 900,                                # outreach agent crawls the web — give it room
    },
