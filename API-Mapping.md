# Profound API — Mapping Document

Maps the Profound dashboard UI (the ChatGPT model view) to the data pullable via API, validated against the live org **Profound Marketing Engineer Hackathon** (`1680a859-ec50-451a-a781-995de61d9a40`) on 2026-06-06.

Authenticated as `jeremy@wearepioneers.ai`. Two access paths exist:
- **MCP** — the `profound` MCP server (read-only; convenient from inside Claude)
- **REST** — `https://api.tryprofound.com`, `X-API-Key` header (read + write/agent-runs)

---

## Screenshot tab → API mapping

The dashboard's per-model view exposes these tabs. Mapping each to its API surface:

| Tab | Pullable? | MCP tool | REST endpoint | Notes |
|---|---|---|---|---|
| **Visibility** | ✅ MCP + REST | `get_visibility_report` | `POST /v1/reports/visibility` | Metrics: `visibility_score`, `share_of_voice`, `mentions_count`, `executions`, `average_position`. Filter to ChatGPT via `model_filter=[<uuid>]` |
| **Prompts** | ✅ MCP + REST | `list_prompts` + `get_prompt_answers` | `GET/POST /v1/org/categories/{id}/prompts`, `POST /v1/prompts/answers` | 195 prompts in this category. CRUD + status endpoints are write-capable |
| **Query Fanouts** | ⚠️ REST only | — *(no MCP tool)* | `POST /v1/reports/query-fanouts` | Same `{info, data}` positional shape as other reports |
| **Platforms** | ✅ MCP + REST | `list_models` + any report w/ `dimensions=["model"]` | `GET /v1/org/models` | 8 platforms tracked (below) |
| **Regions** | ✅ MCP + REST | `list_regions` + reports w/ `region` dim/filter | `GET /v1/org/regions` | 3 regions (below) |
| **Personas** | ⚠️ REST only | — *(no MCP tool)* | `GET /v1/org/categories/{id}/personas`, `GET /v1/org/personas` | Prompts in this category have `persona_id: null` |
| **Sentiment** *(New)* | ✅ MCP + REST | `get_sentiment_report` | `POST /v1/reports/sentiment` | Metrics: `positive`, `negative`, `occurrences` (weighted, not raw counts). v1 ≠ app headline value; v2 coming |
| **Citations** | ✅ MCP + REST | `get_citations_report` | `POST /v1/reports/citations` | Metrics: `count`, `citation_share`. Dimensions: hostname, path, root_domain, url, model, topic, prompt, tag, persona |

### Not on this screenshot but available via API
| Capability | MCP tool | REST endpoint | Notes |
|---|---|---|---|
| **Bots / crawler traffic** | `get_bots_report` | `POST /v2/reports/bots` (v1 deprecated) | Per-domain AI crawler hits. Dim `bot_provider` for vendor rollup |
| **Referrals** | `get_referrals_report` | `POST /v2/reports/referrals` (v1 deprecated) | Human traffic from AI answers, per domain |
| **Agents (run workflows)** | `list_agents`, `get_agent`, `run_agent`, `get_agent_run` | `GET /v1/agents`, `GET /v1/agents/{id}`, `POST /v1/agents/{id}/runs`, `GET .../runs/{run_id}` | Write side. Run-only via API; build/edit is UI-only |
| **Content optimization** | — | `GET /v1/content/{asset_id}/optimization` | AEO Content Score recommendations |

---

## Live org inventory (as of 2026-06-06)

**Organization:** Profound Marketing Engineer Hackathon — `1680a859-ec50-451a-a781-995de61d9a40`

**Category (only one):** Frontier Models — `7943f355-67f3-4792-b172-981db56ef33c`

### Platforms / Models (8)
| Name | model_id |
|---|---|
| ChatGPT | `8e582977-dcf2-428f-9a1c-085c578ceeb8` |
| Google Gemini | `ab90373a-d015-4feb-a7ee-fd9536a0ec53` |
| Meta AI | `6563cc8d-4955-4bba-9c6a-980028915f99` |
| Grok | `cefa8cfd-bb28-4d47-9261-a4f0e9c1e75c` |
| Google AI Mode | `eea7fa6a-481d-4d95-86a7-d084718a7865` |
| Perplexity | `6c262973-268e-4611-8969-06c0520139c0` |
| Google AI Overviews | `dab8d6de-e787-46dd-9e40-9ac0a40c801a` |
| Microsoft Copilot | `94dcfb7c-4f9c-4f9c-9e55-c170c23d5d8a` |

> Note: report `model_filter` requires the **UUID**, not the display name ("ChatGPT" returns 422).

### Regions (3)
| Name | region_id |
|---|---|
| United Kingdom | `07bd33f0-2911-4552-b143-e1f6082a6cd4` |
| United States | `3c37529b-e592-43a9-839a-14bee2673a6b` |
| Canada | `8ffc23c5-1e57-4ace-9070-3142d97d7b38` |

### Topics (15)
API, Coding, Education, Enterprise, Math, Pricing, Privacy, Reasoning, Research, Safety, Speed, Support, Translation, Vision, Writing

### Domains (5) — for bots/referrals reports
| Domain | domain_id |
|---|---|
| booking.com | `2b1b7c17-2615-4c2b-9b80-5c7b7680a54b` |
| www.highcaliberai.com | `4ba4369e-f28b-4022-a71c-595612865e93` |
| willful.co | `a685607c-4d7a-4a04-a94f-cac2a2201d82` |
| engineermarketing.com | `0df64758-9ed9-44ca-bcb8-50ddf6da7f1b` |
| sharongai.com | `35d41c2f-cb11-4c53-bded-e340808f902f` |

### Prompts
**195 total** in the Frontier Models category. Each is configured to run across all 8 platforms, US region, with a topic + tags and `visibility`/`sentiment_v2` analysis types. `persona_id` is null on sampled prompts. Examples:
- "most private ai chatbot" (topic: Privacy)
- "what do people say about claude's reasoning ability" (topic: Reasoning)
- "ai with the strictest alignment" (topic: Safety)
- "which ai company has the fastest inference" (topic: Speed)
- "what do people say about gemini for image analysis" (topic: Vision)

---

## Key gotchas (carry into any build)

1. **Two tabs have no MCP tool** — Query Fanouts and Personas must be pulled via REST directly.
2. **Dates are EST-based.** Use date-only format (`2026-06-01`). MCP report windows are **half-open** (`start` inclusive, `end` exclusive); REST `/v1/reports/*` is inclusive of `end`. Avoid `Z` suffix.
3. **`visibility_score` is a raw decimal** — multiply by 100 for the UI percentage. Without an `asset_name` filter/dimension it's summed across all tracked assets and can exceed 1.0.
4. **Report endpoints return positional arrays** (`data[i].dimensions[j]` → `info.query.dimensions[j]`). Build one `flatten_report()` helper.
5. **`model_filter`/`persona_filter` take UUIDs, not display names.**
6. **Sentiment v1 ≠ app value** — `positive`/`negative` are weighted aggregates, can exceed `occurrences`. Label accordingly if surfaced.
7. **Rate limit 600 req/hr/key** — a fan-out over platforms × regions × reports hits this fast; queue if running at scale.
8. **Agents API is run-only** — list/get-schema/run/poll. Creating or editing agents is Profound-UI-only. Runs are async (202 → poll until terminal).

---

## Sources
- Live MCP/REST calls against the org, 2026-06-06
- `~/Documents/Claude/Projects/Profound Hackathon/Profound-REST-API-Reference.md`
- `~/Documents/Claude/Projects/Profound Hackathon/Profound-Agents-API-Brief.md`
- `~/Documents/Claude/Projects/Profound Hackathon/Profound-Agents-API.md`
