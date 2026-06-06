# Profound Agents — API Access

Short answer: **yes**, Profound Agents are fully usable via a REST API. The Agents endpoints are first-class citizens in their public REST API (currently in beta, access by emailing support@tryprofound.com). There are also official SDKs and an MCP server.

---

## What's available

Three integration paths, all live:

1. **REST API** — direct HTTP, language-agnostic.
2. **Official SDKs** — Python (`profound`) and JavaScript (`@profoundai/client`).
3. **MCP server** — hosted at `mcp.tryprofound.com`, also runnable locally via `@profoundai/mcp`. Aimed at letting external AI tools (Claude, ChatGPT, custom agents) read Profound data and trigger actions.

---

## REST API basics

- **Base URL:** `https://api.tryprofound.com`
- **Auth:** `X-API-Key: <key>` header (Bearer token also supported). API key generated from user profile in the Profound platform.
- **Status:** Beta — endpoints/schemas may shift. Access is gated; request via support@tryprofound.com.
- **Rate limit:** 600 requests/hour/key by default. Standard `X-RateLimit-*` headers, `429` on overrun, `Retry-After` header on the response.
- **Format:** JSON in, JSON out.
- **Versioning:** `/v1` is the default. `/v2` exists for some Agent Analytics report endpoints (hourly granularity).

---

## The four Agent endpoints

The whole agent workflow is exposed as four endpoints. This is the canonical loop:

### 1. List agents

```http
GET /v1/agents?statuses=published&limit=100
X-API-Key: your_api_key
```

Returns every agent your org has built/published, with id, name, status, description.

### 2. Get agent + schema

```http
GET /v1/agents/{agent_id}?version=published
X-API-Key: your_api_key
```

Returns the agent's **input schema** and **output schema** as JSON Schema. You use `schema.input` to know which fields to send when triggering a run, and `schema.output` to know the shape of what comes back.

**Important quirk:** the `inputs` object must use the schema's **variable IDs** as keys, not the human-readable labels. Get an Agent first, then build your payload.

### 3. Run an agent (kick off)

```http
POST /v1/agents/{agent_id}/runs
Content-Type: application/json
X-API-Key: your_api_key

{
  "inputs": {
    "your_input_variable_id": "<value>"
  }
}
```

Returns `202 Accepted` with `{ id, agent_id, status, started_at }`. **Async pattern** — a 202 only means the run was queued, not that it succeeded.

### 4. Get a run (poll for result)

```http
GET /v1/agents/{agent_id}/runs/{run_id}
X-API-Key: your_api_key
```

Returns current status and, when complete, the `outputs` object keyed by output variable IDs.

**Run statuses:** `queued`, `running`, `succeeded`, `failed`, `cancelled`, `skipped`, `unknown`.

So the pattern is the standard async job: POST to start, poll GET until `status` is terminal.

---

## SDK examples (copy-pasteable)

**Python:**
```python
import os
from profound import Profound

client = Profound(api_key=os.environ.get("PROFOUND_API_KEY"))
run = client.agents.runs.create(agent_id="182bd5e5-6e1a-4fe4-a799-aa6d9a6ab26e")
print(run.id)
```

**JavaScript:**
```js
import Profound from '@profoundai/client';

const client = new Profound({ apiKey: process.env['PROFOUND_API_KEY'] });
const run = await client.agents.runs.create('182bd5e5-6e1a-4fe4-a799-aa6d9a6ab26e');
console.log(run.id);
```

Both SDKs are generated from the same OpenAPI spec, so anything in the REST API is in the SDKs.

---

## Other endpoints worth knowing (for hackathon context)

The data your Agents could be triggered by or read from is also API-exposed:

- **Reports:** `query-visibility`, `query-citations`, `query-sentiment`, `query-fanouts`
- **Agent Analytics:** `get-bots-report-v1/v2`, `get-referrals-report-v1/v2`, `get-logs`, `get-bots`
- **Content:** `optimization-analysis`, `optimization-list`
- **Organization:** categories, personas, regions, models, domains, assets, tags, topics
- **Prompts:** list, create, update, update status, get answers

There's a "Cookbook" of end-to-end recipes — visibility line charts, citation share, top-N leaderboards etc. — that show how to reproduce dashboard tiles from the API. Useful as crib sheets if we need a custom view.

---

## What this unlocks for the hackathon

The big practical implication: **we don't have to build inside their Agent Builder UI**. We can build agents inside Profound (using their nodes/data), then trigger them from anywhere — our own FastAPI service, a Slack bot, a cron job, an LLM tool call — and pull the outputs back to render however we like.

Patterns this enables:

- **External orchestrator → Profound Agent → external rendering.** Useful for the role-aware dashboard idea: a thin FastAPI service exposes a chat endpoint that, per role, calls the right Profound agent(s) by ID, polls for outputs, and streams them back via SSE to a custom UI. Doesn't require Profound to build a "role-aware dashboard" feature — we wrap their API.
- **Cron/webhook-triggered agents.** Background Agents aren't shipped yet, but we can simulate the pattern: scheduled task fires, calls `POST /v1/agents/{id}/runs`, posts the result to Slack. Demos the "24/7" pitch without waiting on their roadmap.
- **Agent-as-tool inside another LLM.** Each Profound agent could be wrapped as a tool in a Claude/GPT agent loop — "if the user asks about competitive citation share, call agent X and return the result." MCP server already does this for read endpoints; the run endpoints make the write side equally accessible.
- **GSC-to-AI-citation tracker (Idea 2):** straight-line build — our service pulls GSC losers, calls a Profound agent that takes "list of URLs" as input and returns AI citation status per URL, we render the red/green verdict. The agent itself is built inside Profound; we just orchestrate.

---

## Caveats

- **Beta status** — schemas can shift, and access requires going through support. Worth pinging them now if we're depending on it.
- **No native webhooks for run completion documented** — pattern is polling. If we want push, we'd build a wrapper that polls and emits to Slack/webhook ourselves.
- **Rate limit is modest** at 600/hr/key. Fine for a demo, possibly tight for a Sheets-mode-style fan-out.
- **Authentication for SSO orgs** — API keys are per-user from the profile; might need a service account discussion if the build is shared.
- **Each agent's input contract is opaque until you `Get` it** — we can't hardcode payloads, we have to fetch the schema first. Plan for that step in any client we build.

---

## Sources

- [Profound REST API introduction](https://docs.tryprofound.com/rest-api/introduction)
- [Agents API examples — full request/response walkthrough](https://docs.tryprofound.com/rest-api/examples/agents.md)
- [Run an agent — OpenAPI spec](https://docs.tryprofound.com/api-reference/agents/run-an-agent.md)
- [Custom Agents overview](https://docs.tryprofound.com/agent-apis/custom-agents)
- [Profound MCP overview](https://docs.tryprofound.com/agent-apis/mcp/overview)
- [SDKs (Python + JS)](https://docs.tryprofound.com/sdks/overview.md)
- [Cookbook — recipes for reproducing dashboard tiles via API](https://docs.tryprofound.com/cookbook/introduction.md)
- [Endpoints at a glance](https://docs.tryprofound.com/cookbook/setup/endpoints-at-a-glance.md)
