# Profound REST API — Working Reference

Consolidated reference for the hackathon build, distilled from Profound's official docs (introduction, authentication, date-ranges, response-format, endpoints-at-a-glance). This is the canonical doc the FastAPI orchestrator should be built against.

API status: **beta** — schemas may shift. Access is gated; request via support@tryprofound.com if not yet granted.

---

## Connection basics

| Setting | Value |
|---|---|
| Base URL | `https://api.tryprofound.com` |
| Auth header | `X-API-Key: <key>` *(recommended)* |
| Auth alternative | `?api_key=<key>` query param *(works but less safe — avoid in logs)* |
| Bearer | Also supported per OpenAPI spec |
| Content type | `application/json` |
| Rate limit | 600 req/hr/key. Headers: `X-RateLimit-Limit`, `-Remaining`, `-Reset`. 429 + `Retry-After` on overrun |

**API key for this project:** stored in memory (`profound_api_key.md`). In code, read `PROFOUND_API_KEY` from env — never inline.

**Versioning:**
- `v1` is the default for everything.
- `v2/reports/*` is the newer surface for **Agent Analytics** report endpoints, supporting hourly granularity. Use v2 if you need anything sub-daily; v1 if daily is fine.

---

## Critical gotcha — dates & timezones

**The system is EST-based, not UTC.** Data is stored in UTC but processed on an EST schedule. Misreading this is the #1 cause of "missing data" complaints.

**Three accepted date formats:**

| Format | Example | Treated as |
|---|---|---|
| Date only *(recommended)* | `2026-06-01` | EST midnight, auto-converted to UTC |
| Datetime no TZ | `2026-06-01T08:00:00` | EST |
| Datetime with Z | `2026-06-01T00:00:00Z` | **Literal UTC** — you must offset for EST yourself |

**Recommended payload for daily queries:**

```json
{ "start_date": "2026-05-01", "end_date": "2026-06-01" }
```

This is interpreted as `2026-05-01 00:00 EST` → `2026-05-01 05:00 UTC`. Range is inclusive (`<= end`).

**Things that will bite you:**

- **`Z` suffix breaks day boundaries.** `2026-01-01T00:00:00Z` is December 31st 19:00 EST — you'll miss 5 hours of data at the start. Avoid `Z` unless you've manually offset.
- **DST is handled automatically** when no timezone is supplied. EST = UTC-5 Nov–Mar; EDT = UTC-4 Mar–Nov.
- **Fractional-offset timezones (IST, NPT, AFT, etc.)** — if querying hourly via `/v2/reports/*`, query **2 consecutive UTC hours** to capture one full local hour, because the local hour straddles two UTC buckets.

---

## Critical gotcha — report response format

Report endpoints (`/v1/reports/*`) return a **positional array** format, not a flat object. Designed for payload efficiency; non-obvious until you've parsed one.

**Shape:**

```json
{
  "data": [
    {
      "dimensions": ["example.com", "/path", "2026-06-01"],
      "metrics": [10, 0.05]
    }
  ],
  "info": {
    "query": {
      "dimensions": ["hostname", "path", "date"],
      "metrics": ["count", "share_of_voice"],
      "filters": [...],
      "date_interval": "day"
    },
    "total_rows": 200
  }
}
```

**Mapping rule:**
- `data[i].dimensions[j]` → `info.query.dimensions[j]` (positional)
- `data[i].metrics[j]` → `info.query.metrics[j]` (positional)

**Always process programmatically using `info.query.dimensions` + `info.query.metrics` as the keys.** Hardcoding array positions will break the moment someone reorders the request.

**Python flattener (for use in our orchestrator):**

```python
def flatten_report(response: dict) -> list[dict]:
    q = response["info"]["query"]
    dims = q["dimensions"]
    mets = q["metrics"]
    return [
        {**dict(zip(dims, row["dimensions"])), **dict(zip(mets, row["metrics"]))}
        for row in response["data"]
    ]
```

**Pagination:** use `info.total_rows` to detect more pages. Pagination params go in the request body (`pagination` object).

**Note:** non-report endpoints (`/v1/org/*`, `/v1/prompts/*`, `/v1/agents/*`) use standard JSON object shapes — no positional decoding needed.

---

## Endpoint catalog

### Organization & setup (GET)

| Path | Returns |
|---|---|
| `/v1/org/categories` | Every category the key can see |
| `/v1/org/categories/{id}/assets` | Assets in a category, with `is_owned` + domains |
| `/v1/org/categories/{id}/topics` | Configured topics |
| `/v1/org/categories/{id}/tags` | Configured tags |
| `/v1/org/categories/{id}/personas` | Configured personas |
| `/v1/org/categories/{id}/prompts` | Prompts in a category |
| `/v1/org/regions` | Regions enabled on the org |
| `/v1/org/models` | AI models enabled (ChatGPT, Claude, Gemini, Perplexity, etc.) |
| `/v1/org/domains` | Owned domains |
| `/v1/org/personas` | Personas at org level |

Almost every report call needs at least a `category_id`. Always call `/v1/org/categories` first to get the IDs.

### Reports (POST, scoped by `category_id`)

All reports share the same body shape:
- Required: `category_id`, `start_date`, `end_date`, `metrics`
- Optional: `dimensions`, `date_interval`, `filters`, `pagination`, `order_by`

#### `/v1/reports/visibility`
How often the asset appears in AI answers.

- **Metrics:** `visibility_score`, `share_of_voice`, `average_position`, `mentions_count`, `executions`
- **Dimensions:** `date`, `asset_name`, `model`, `region`, `persona`, `topic`, `tag`
- **Filters:** `asset_name`, `model_id`, `region_id`, `persona_id`, `topic_id`, `tag_id`

#### `/v1/reports/citations`
Which URLs and domains AI answers cite.

- **Metrics:** `count`, `citation_share`
- **Dimensions:** `date`, `root_domain`, `url`, `citation_category`, `model`, `region`, `persona`
- **Filters:** `prompt_type` (e.g. `"visibility"`), `model_id`, `region_id`, `persona_id`
- **Note:** `citation_share` is per-AI-model averaged; `count` is raw. Sorting by one doesn't track the other — pick the question first.

#### `/v1/reports/sentiment`
How positively/negatively AI answers reference the asset.

- **Metrics:** `positive`, `negative`, `occurrences`
- **Dimensions:** `date`, `asset_name`, `theme`, `sentiment_type`, `topic`, `model`, `region`, `persona`
- **Filters:** `asset_name`, `theme`, `topic_id`, `model_id`, `region_id`, `persona_id`
- **Note:** the v1 sentiment endpoint **does not match the Profound app's headline value exactly**. Sentiment v2 is coming. Flag this in the UI if we show sentiment.

#### `/v1/reports/query-fanouts`
How prompts cascade across AI surfaces. Same `{info, data}` shape.

#### `/v1/reports/referrals` (+ `/v2/reports/referrals` for hourly)
Human-referral traffic to your domains attributed back to AI answers.

#### `/v1/reports/bots` (+ `/v2/reports/bots` for hourly)
AI crawler / bot traffic to your domains.

### Answers (per-prompt data)

| Method | Path | Use |
|---|---|---|
| `POST` | `/v1/prompts/answers` | Fetch raw AI answers for prompts in a category |

### Agents (the write side — the orchestrator's main target)

| Method | Path | Use |
|---|---|---|
| `GET` | `/v1/agents` | List agents |
| `GET` | `/v1/agents/{id}` | Get one agent's config + JSON schema |
| `POST` | `/v1/agents/{id}/runs` | Start a run (returns 202) |
| `GET` | `/v1/agents/{id}/runs/{run_id}` | Poll run status + outputs |

See `Profound-Agents-API-Brief.md` for the full lifecycle.

### Prompts (CRUD)

| Method | Path | Use |
|---|---|---|
| `GET` | `/v1/org/categories/{id}/prompts` | List prompts |
| `POST` | `/v1/org/categories/{id}/prompts` | Add a prompt |
| `PATCH` | `/v1/org/categories/{id}/prompts` | Edit prompts |
| `PATCH` | `/v1/org/categories/{id}/prompts/status` | Enable/disable prompts |

The Regional Lead agent's "flag prompts for localisation" output could feed this — auto-add region-specific prompt variants once approved by the prompt-set owner.

### Content optimization

| Method | Path | Use |
|---|---|---|
| `GET` | `/v1/content/{asset_id}/optimization` | Optimization opportunities for an asset |
| `GET` | `/v1/content/{asset_id}/optimization/{content_id}` | One optimization in detail |

Powered by their proprietary AEO Content Score. Probably overlaps with the SEO agent's "what to refresh" output — worth checking if this gives us pre-computed page-level recommendations we can lean on rather than rebuilding.

### Agent Analytics (legacy — `/v1`)

| Method | Path | Use |
|---|---|---|
| `POST` | `/v1/agent-analytics/logs` | Raw access logs *(deprecated, use `/v2`)* |
| `POST` | `/v1/agent-analytics/bots` | Bot reports *(deprecated, use `/v2`)* |

Use `/v2/reports/bots` and `/v2/reports/referrals` instead for new work.

---

## Authentication errors

| Status | Meaning | Action |
|---|---|---|
| `401` | Invalid / expired key | Check env var, regenerate if expired |
| `403` | Insufficient permissions | Key is valid but org doesn't have access to that resource |
| `429` | Rate limit exceeded (600/hr/key) | Honour `Retry-After`, back off |

---

## Getting a new API key (for reference)

The key for this project is already stored. If we need a new one later:

1. Sign in at platform.tryprofound.com
2. Bottom-left → name → **Settings**
3. Left sidebar → **API Keys**
4. Set a name (>2 chars) + expiry date → **Create API Key**
5. **Copy immediately** — the key is shown once and cannot be retrieved again

If the API Keys tab isn't visible, email support to request access.

---

## What this means for the build

A few decisions this reference forces:

1. **Always use date-only format (no `Z`).** Cleaner, less error-prone, EST-correct by default. Our orchestrator should never emit `Z`-suffixed timestamps unless we explicitly need a UTC literal.

2. **Build the report flattener once, use everywhere.** The positional array format is awkward but uniform. A single `flatten_report()` utility means every downstream consumer sees normal dicts.

3. **Cache org metadata aggressively.** `/v1/org/categories`, `/v1/org/regions`, `/v1/org/models` don't change minute-to-minute. Cache on app start and refresh on a slow timer. Saves rate-limit budget.

4. **Sentiment v1 ≠ app sentiment value.** If the dashboard shows sentiment, label it as "API value (v1)" or wait for v2. Don't blindly match it to the UI number.

5. **Agent run polling** belongs in a wrapper that exponential-backs-off and emits SSE events to the front-end. Don't sync-block the API request.

6. **Prompt CRUD endpoints are write-capable** — interesting because they let the Regional agent's "add localised prompt variant" recommendation become an actionable button rather than a brief.

7. **Rate limit budgeting** — at 600/hr a fan-out over 6 personas × multiple regions × multiple reports can hit ceiling fast. Need a request queue with per-key concurrency limits if we run agents at scale.

---

## Sources

- [REST API — Introduction](https://docs.tryprofound.com/rest-api/introduction)
- [REST API — Authentication](https://docs.tryprofound.com/rest-api/authentication)
- [REST API — Date Ranges & Timezones](https://docs.tryprofound.com/rest-api/date-ranges)
- [REST API — Response Format](https://docs.tryprofound.com/rest-api/response-format)
- [Cookbook — Endpoints at a glance](https://docs.tryprofound.com/cookbook/setup/endpoints-at-a-glance)
- [SDKs](https://docs.tryprofound.com/sdks/overview)
