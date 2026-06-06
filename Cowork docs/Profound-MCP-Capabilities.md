# Profound MCP — Capabilities

Detailed knowledge of what the hosted Profound MCP server exposes, distilled from the official capabilities page.

**Endpoint:** `https://mcp.tryprofound.com/mcp`
**Transport:** HTTP
**Auth:** OAuth 2.1 — every tool runs as the signed-in Profound user, returns only the data that user has access to.

---

## Critical caveat — read-only

**Profound MCP is read-only.** All tools have `readOnlyHint: true` and `idempotentHint: true`. There is no MCP tool for triggering an Agent run, creating prompts, or modifying anything in Profound.

If you want to **execute** an Agent from inside Claude Code or another MCP client, you still need the REST API (`POST /v1/agents/{id}/runs`) — likely wrapped in your own tool. MCP is the read side; REST is the write side.

This shapes our hackathon build: MCP is the fastest way to feed Profound's data into a Claude or custom UI, but to run agents we need a thin REST wrapper sitting next to it.

---

## The workflow shape

Every interaction follows a discovery → report pattern:

1. **`whoami`** — confirm user, orgs, regions, entitlements.
2. **`list_organizations`** → pick an org → **`list_categories`** (for visibility reports) or **`list_domains`** (for traffic reports).
3. **Optional narrowing** via `list_regions`, `list_models`, `list_tags`, `list_topics`, `list_prompts` to grab IDs for filters.
4. **Report** — call one of the six report tools with a category/domain + date range + filters.

Don't skip step 2. Almost every report tool requires either a `category_id` or an exact `domain` hostname, and those IDs only come from discovery.

---

## Conventions across all tools

| Concern | Rule |
|---|---|
| Dates | ISO 8601 `YYYY-MM-DD`, validated server-side, both `start_date` and `end_date` inclusive |
| Pagination | Cursor-based — pass `cursor` from previous response's `next_cursor`; `limit` caps results and forces `next_cursor` to `null` |
| Page size | Default `500`, max `10,000` (where supported) |
| Domains | Exact hostnames — `www.example.com` ≠ `example.com` |
| Filters | Two flavours: dedicated `*_filter` params for common dimensions, plus advanced `filters: [{ field, operator, value }]` for arbitrary predicates |
| Org scoping | Some tools take `organization_id` to disambiguate when the user belongs to multiple orgs |

---

## Discovery tools (9)

Lightweight, mostly no-input. Use them to resolve human-readable context into the IDs the report tools demand.

### `whoami`
- **Input:** none
- **Returns:** authenticated user + accessible orgs + regions + entitlements
- **When to use:** first call in any session — confirms scope before you waste calls

### `list_organizations`
- **Input:** none
- **Returns:** orgs the user can access; IDs feed every downstream tool

### `list_regions`
- **Input (optional):** `org_id`
- **Returns:** geographic regions configured for that org (or all accessible orgs if omitted)
- **Use case:** scope reports to a market — UK vs. US vs. Australia

### `list_models`
- **Input:** none
- **Returns:** tracked AI engines — ChatGPT, Perplexity, Google AI Overviews, Gemini, etc.
- **Use case:** filter a report to one engine

### `list_categories`
- **Input (required):** `org_id`
- **Returns:** tracked categories (markets/segments) for the org. Most visibility reports are scoped to a category, so this is the second call you'll make after `list_organizations`

### `list_domains`
- **Input (required):** `org_id`
- **Returns:** tracked domains. Use the exact hostname when calling traffic reports

### `list_tags`
- **Input (required):** `category_id`
- **Returns:** tags within a category, for filtering prompts/reports

### `list_topics`
- **Input (required):** `category_id`
- **Returns:** topics within a category, for filtering prompts/reports

### `list_prompts`
- **Input (required):** `category_id`
- **Optional:** `status` (`active` | `disabled` | `all`, default `all`), `tag_ids`, `topic_ids`, `exclude_tag_ids`, `exclude_topic_ids`, `combine` (`AND`/`OR`, default `AND`), `limit` (default 100), `cursor`
- **Returns:** the actual prompts Profound runs against AI engines for that category

---

## Brand visibility reports (4) — scoped to `category_id`

### `get_visibility_report`
The headline metric tool. How visible a brand is in AI answers.

- **Required:** `category_id`, `start_date`, `end_date`
- **Default metric:** `visibility_score`
- **Other metrics:** `share_of_voice`, `mentions_count`, `executions`, `average_position`
- **Useful dimensions:** `date`, `region`, `topic`, `model`, `prompt`, `tag`, `persona`
- **Filters:** `topic_filter`, `tag_filter`, `region_filter`, `model_filter`, `persona_filter`, `asset_filter`, plus advanced `filters` predicates
- **Pagination:** `cursor`, `page_size` (default 500, max 10,000), `limit` (Top-N cap → `next_cursor` always `null`)

Example payload:
```json
{
  "category_id": "cat_123",
  "start_date": "2026-04-01",
  "end_date": "2026-05-01",
  "dimensions": ["model"]
}
```

### `get_sentiment_report`
Sentiment expressed about a brand or competitor in AI answers.

- **Required:** `category_id`, `start_date`, `end_date`
- **Default metrics:** `positive`, `negative` (weighted aggregates), `occurrences` (raw count)
- **Filters:** same as visibility plus `theme_filter` (e.g. `pricing`)
- **No `dimensions` field** — sentiment is metric-only

Useful for "why is sentiment dropping?" questions, especially when filtered by `theme_filter`.

### `get_citations_report`
Which sources AI engines cite for this category.

- **Required:** `category_id`, `start_date`, `end_date`
- **Default metrics:** `count`, `citation_share`
- **Useful dimensions:** `hostname`, `path`, `root_domain`, `url`, `model`, `topic`, `prompt`, `tag`, `persona`
- **Filters:** standard set plus `root_domain_filter`, `hostname_filter`, `citation_category_filter`
- **Gotcha:** `root_domain_filter` requires `dimensions: ["root_domain"]` — the docs flag this explicitly

This is the tool that powers competitive/source-of-truth analysis. Use this to find which third-party domains we'd want to outreach to.

### `get_prompt_answers`
Raw AI answers behind the metrics.

- **Required:** `category_id`, `start_date`, `end_date`
- **Optional:** `limit` (default 100), `offset` (default 0)
- **Pagination:** offset-based, not cursor

Use sparingly — it returns full answer text, which is heavy. Best for spot-checking a metric or seeding a content brief.

---

## Traffic reports (2) — scoped to `domain`

These are scoped to a tracked domain, not a category. Always call `list_domains` first.

### `get_referrals_report`
Visits a domain received from AI engines.

- **Required:** `domain` (exact hostname), `start_date`, `end_date`
- **Default metric:** `visits`
- **Useful dimensions:** `referral_type`, `referral_source`, `date`
- **Filters:** `referral_source_filter` (vendor, e.g. `openai`), `referral_type_filter` (`internal` | `referer` | `utm` | `none`)
- **Disambiguation:** `organization_id` when the user belongs to multiple orgs

### `get_bots_report`
AI crawler activity against a domain — GPTBot, PerplexityBot, etc.

- **Required:** `domain`, `start_date`, `end_date`
- **Default metrics:** `count`, `citations`
- **Useful dimensions:** `bot_provider`, `bot_name`, `bot_type`, `date`
- **Filters:** `bot_provider_filter` (e.g. `openai`, `anthropic`), `bot_name_filter` (e.g. `GPTBot`), `bot_type_filter` (`ai_assistant` | `ai_training` | `index` | `ai_agent`)

---

## Resources (3) — glossary

MCP also exposes static reference docs as resources rather than tools.

| URI | Audience | Purpose |
|---|---|---|
| `file:///profound/glossary` | Assistant | Compact index — load once per session |
| `file:///profound/glossary/full` | User | Full glossary with definitions + examples |
| `file:///profound/glossary/{term}` | Assistant | Single term lookup by slug |

Glossary covers 38 terms across 7 categories: Identity, Taxonomy, AI Engines, Prompts, Reports, Metrics, Agents. Each entry has a slug, summary, full description, examples, and see-also links.

Standard pattern: load the index once at session start; fetch specific terms (e.g. `file:///profound/glossary/visibility-score`) only when needed.

---

## Tool inventory at a glance

| Type | Count | Tools |
|---|---|---|
| Discovery | 9 | `whoami`, `list_organizations`, `list_regions`, `list_models`, `list_categories`, `list_domains`, `list_tags`, `list_topics`, `list_prompts` |
| Brand visibility (category-scoped) | 4 | `get_visibility_report`, `get_sentiment_report`, `get_citations_report`, `get_prompt_answers` |
| Traffic (domain-scoped) | 2 | `get_referrals_report`, `get_bots_report` |
| Glossary resources | 3 URIs | `file:///profound/glossary[/full|/{term}]` |

**Total tools: 15.**

---

## What this means for the hackathon build

**Strengths to lean into:**

- **Zero infra to start.** Once we run `claude mcp add --transport http profound https://mcp.tryprofound.com/mcp` and OAuth in, we have visibility, sentiment, citation, traffic, and prompt data accessible from Claude Code with no glue code.
- **Region/model/persona filters are first-class.** This lines up directly with the role-aware dashboard idea (Idea 1) — country comparisons via `region_filter`, engine comparisons via `model_filter`, persona-level breakdowns via `persona_filter` are one-call queries.
- **Citations + referrals + bots together** is the GSC-loss-tracker (Idea 2) in three calls: `get_citations_report` to see where AI is citing, `get_referrals_report` to see what traffic the domain is getting back, `get_bots_report` to see who's crawling. Pair that with GSC data we pull ourselves and we have the green/red verdict.

**Gaps we'll have to work around:**

- **No `run_agent` tool.** Anything write-side (kicking off a Profound Agent, drafting content, publishing) must go through the REST API. If we want a Claude-driven demo where the user says "draft outreach for these top-cited domains" and it triggers a Profound agent, we need to register our own MCP tool that wraps `POST /v1/agents/{id}/runs`.
- **No GSC data inside Profound.** Their referral data is post-AI-click; the "where did organic traffic go?" comparison requires us to bring GSC ourselves.
- **OAuth means per-user data.** For a multi-user dashboard demo we'd either share one session or build server-side auth using the REST API key, not MCP.

**Build pattern this suggests:**

```
[Claude Code or custom chat]
    ├── MCP: Profound (read — visibility, citations, sentiment, traffic, bots)
    ├── REST: Profound /v1/agents (write — run agents)
    └── REST: GSC (read — losing pages, biggest impression drops)
        ↓
    [our FastAPI orchestrator + SSE → UI]
```

The two ideas in `Ideas.md` both fit cleanly into this pattern.

---

## Source

- [Profound MCP — Capabilities (official docs)](https://docs.tryprofound.com/agent-apis/mcp/capabilities)
