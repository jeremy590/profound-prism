# Profound Agents API — Brief for Claude Code

A working brief for a Claude Code session whose job is to test API calls against Profound's Agents API.

---

## What you're working with

Profound is an AEO (Answer Engine Optimization) platform. Its **Agents** are no-code workflow graphs built inside Profound's web UI, then triggered via REST API. This brief covers the API side only.

**Important constraint up front:** the REST API can **run** agents and **read** their schemas/runs. It **cannot create or modify** an agent — that's web-UI only (Profound Agent Builder, or the new Agent Assistant). So if no agents exist in the org yet, the first step is to build one in the UI, not in code.

API status: **beta**. Endpoints/schemas may shift. Documented at [docs.tryprofound.com](https://docs.tryprofound.com).

---

## Auth & environment

**Base URL:** `https://api.tryprofound.com`

**Auth header:** `X-API-Key: <key>` (Bearer also supported)

**API key:** `VXNBFcswmvy5qfTKtIHSC`

> **Treat this file as local-only.** Don't commit it. For the actual build, move the key to a `.env` file at the project root and read `PROFOUND_API_KEY` from env. All examples below use the env var pattern.

Set it once in your shell:

```bash
export PROFOUND_API_KEY=VXNBFcswmvy5qfTKtIHSC
```

Rate limit: **600 requests/hour/key**. Response headers `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset`. 429 with `Retry-After` on overrun.

---

## The four-endpoint loop

The entire Agents API surface is four operations. The canonical interaction loop:

```
list_agents → get_agent (schema) → run_agent → poll_run
```

### 1. List agents

```bash
curl -X GET "https://api.tryprofound.com/v1/agents?statuses=published&limit=100" \
  -H "X-API-Key: $PROFOUND_API_KEY"
```

Returns a paginated list:

```json
{
  "data": [
    {
      "id": "uuid",
      "organization_id": "uuid",
      "name": "Starter Template",
      "status": "published",
      "created_at": "2026-04-24T19:03:15Z",
      "description": "..."
    }
  ],
  "pagination": { "limit": 100, "next_cursor": null }
}
```

Query params:
- `statuses` — `published` (default) or `draft`. Pass `?statuses=draft` to see in-progress agents that haven't been published yet.
- `limit` — max 100 per page
- `next_cursor` — for pagination

### 2. Get an agent (with its schema)

```bash
curl -X GET "https://api.tryprofound.com/v1/agents/{agent_id}?version=published" \
  -H "X-API-Key: $PROFOUND_API_KEY"
```

`version` can be `published` (default) or `draft`. Returns:

```json
{
  "id": "uuid",
  "organization_id": "uuid",
  "name": "Starter Template",
  "status": "published",
  "created_at": "...",
  "description": "...",
  "schema": {
    "input":  { "type": "object", "properties": { "your_input_variable_id": {...} }, "required": [...] },
    "output": { "type": "object", "properties": { "your_output_variable_id": {...} } }
  }
}
```

**Critical:** the keys in `schema.input.properties` are **variable IDs**, not the human-readable labels you see in the UI. You must use these variable IDs as the keys in the `inputs` object when running the agent. Always call `GET /v1/agents/{id}` first to discover them.

### 3. Run an agent

```bash
curl -X POST "https://api.tryprofound.com/v1/agents/{agent_id}/runs" \
  -H "X-API-Key: $PROFOUND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "inputs": { "your_input_variable_id": "<value>" } }'
```

Returns **`202 Accepted`** with:

```json
{
  "id": "run_uuid",
  "agent_id": "uuid",
  "status": "queued",
  "started_at": "2026-04-24T19:08:34Z"
}
```

A 202 only means the run was **queued**. It says nothing about success. You must poll.

### 4. Poll the run

```bash
curl -X GET "https://api.tryprofound.com/v1/agents/{agent_id}/runs/{run_id}" \
  -H "X-API-Key: $PROFOUND_API_KEY"
```

Returns:

```json
{
  "id": "run_uuid",
  "agent_id": "uuid",
  "status": "succeeded",
  "started_at": "...",
  "finished_at": "...",
  "error": null,
  "outputs": { "your_output_variable_id": "<value>" }
}
```

**Run statuses:** `queued`, `running`, `succeeded`, `failed`, `cancelled`, `skipped`, `unknown`. Terminal states are `succeeded`, `failed`, `cancelled`, `skipped`.

When `failed`, an `error` object is populated with details.

Polling pattern: backoff is sensible — start at 2s, double up to ~30s, cap total wait at the agent's expected runtime (most agents finish in seconds–minutes, but iteration-heavy ones can run longer).

---

## Suggested first test sequence

Run these in order. Each is one curl. Stop and inspect output between each.

### Step 1 — Confirm the key works and list agents

```bash
curl -sS "https://api.tryprofound.com/v1/agents?statuses=published&limit=100" \
  -H "X-API-Key: $PROFOUND_API_KEY" | jq .
```

**Expected outcomes:**
- `data: []` → org has no published agents. **Stop and build one in the Profound UI** before continuing. Look for the "Starter Template" in templates.
- `data: [...]` with agents → note one `id` to use in the next step. Prefer "Starter Template" if it exists (simplest input schema for testing).

Also check drafts:

```bash
curl -sS "https://api.tryprofound.com/v1/agents?statuses=draft&limit=100" \
  -H "X-API-Key: $PROFOUND_API_KEY" | jq .
```

### Step 2 — Fetch the agent's schema

```bash
AGENT_ID="<paste id from step 1>"

curl -sS "https://api.tryprofound.com/v1/agents/$AGENT_ID?version=published" \
  -H "X-API-Key: $PROFOUND_API_KEY" | jq .schema
```

Note the variable IDs in `schema.input.properties`. Build the run payload around them.

### Step 3 — Kick off a run

```bash
curl -sS -X POST "https://api.tryprofound.com/v1/agents/$AGENT_ID/runs" \
  -H "X-API-Key: $PROFOUND_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{ "inputs": { "<variable_id_from_schema>": "test input value" } }' | jq .
```

Save the returned `id` as `RUN_ID`.

### Step 4 — Poll until terminal

```bash
RUN_ID="<paste id from step 3>"

while true; do
  STATUS=$(curl -sS "https://api.tryprofound.com/v1/agents/$AGENT_ID/runs/$RUN_ID" \
    -H "X-API-Key: $PROFOUND_API_KEY" | tee /tmp/profound_run.json | jq -r .status)
  echo "status: $STATUS"
  case "$STATUS" in
    succeeded|failed|cancelled|skipped) break ;;
  esac
  sleep 3
done

jq . /tmp/profound_run.json
```

When it lands on `succeeded`, the `outputs` object is the payload.

---

## Python SDK alternative

```bash
pip install profound
```

```python
import os, time
from profound import Profound

client = Profound(api_key=os.environ["PROFOUND_API_KEY"])

# 1. List
agents = client.agents.list()
print([(a.id, a.name) for a in agents.data])

# 2. Get schema
agent_id = agents.data[0].id
agent = client.agents.retrieve(agent_id)
print(agent.schema)

# 3. Run
run = client.agents.runs.create(
    agent_id=agent_id,
    inputs={"your_input_variable_id": "test"},
)
print(f"queued run {run.id}")

# 4. Poll
while True:
    state = client.agents.runs.retrieve(run_id=run.id, agent_id=agent_id)
    print(state.status)
    if state.status in ("succeeded", "failed", "cancelled", "skipped"):
        break
    time.sleep(3)

print(state.outputs)
```

JS SDK is `@profoundai/client` and follows the same shape.

---

## Gotchas to watch for

1. **`inputs` keys must match `schema.input.properties` keys** (the variable IDs). Using the human-readable label will 422.
2. **`POST .../runs` returns 202, not 200.** It does **not** mean success. Always poll.
3. **A 202 with `status: queued` and `started_at: null` is normal.** The run hasn't executed yet.
4. **`outputs` is `{}` until the run reaches `succeeded`.** Don't read it pre-terminal.
5. **Drafts vs. published.** `GET /v1/agents/{id}?version=draft` returns the editing-in-progress version. Use `published` for stable runs.
6. **No agent creation/edit endpoints.** Building or modifying an agent has to happen in the Profound web UI.
7. **No push webhooks for run completion documented.** Polling is the only completion signal today.
8. **Rate limit at 600/hr** — bursty fan-out (e.g. running an agent 50 times across a sheet) can hit this fast.

---

## What the API can't do (yet)

| Capability | Available? | Workaround |
|---|---|---|
| List agents | ✅ | — |
| Get agent schema | ✅ | — |
| Run an agent | ✅ | — |
| Poll a run | ✅ | — |
| **Create an agent** | ❌ | Build in Agent Builder UI |
| **Edit an agent's graph** | ❌ | Edit in Agent Builder UI |
| **Stream/SSE run progress** | ❌ | Poll on a backoff |
| **Push webhook on completion** | ❌ | Build your own polling wrapper that fires a webhook |
| **Cancel a running run** | Unclear — not in docs | Test with a long-running run and report back |

---

## Adjacent endpoints worth knowing

If you want to combine Agent runs with reading Profound data without using MCP, the REST API also exposes:

- **Reports:** `query-visibility`, `query-citations`, `query-sentiment`, `query-fanouts`
- **Agent Analytics:** `get-bots-report-v1/v2`, `get-referrals-report-v1/v2`, `get-logs`, `get-bots`
- **Org:** `categories`, `personas`, `regions`, `models`, `domains`, `assets`, `tags`, `topics`
- **Prompts:** list, create, update, get answers

Same auth, same base URL.

The MCP server (`https://mcp.tryprofound.com/mcp`) covers the read side too — useful for exploratory work from inside Claude itself, but **MCP is read-only and cannot trigger agent runs**. Anything that runs an agent has to go through the REST API.

---

## What to report back after testing

After running the test sequence above, please share:

1. **Did `GET /v1/agents` return any agents?** If yes, names + IDs. If no, this is the signal to go build one in the UI.
2. **For one chosen agent — the full `schema` block** (input + output JSON Schema). This tells us what inputs the agent expects and what it returns, which we need to wire into the role-aware dashboard.
3. **A successful end-to-end run** — payload sent, time to terminal, final `outputs`.
4. **Any unexpected error responses** — particularly anything that contradicts what's documented here.
5. **Observed run latency** for the test agent. This sets our polling budget for the dashboard.

---

## Sources

- [Profound REST API introduction](https://docs.tryprofound.com/rest-api/introduction)
- [Run an agent (OpenAPI)](https://docs.tryprofound.com/api-reference/agents/run-an-agent.md)
- [Get an agent](https://docs.tryprofound.com/api-reference/agents/get-an-agent.md)
- [Get an agent run](https://docs.tryprofound.com/api-reference/agents/get-an-agent-run.md)
- [List agents](https://docs.tryprofound.com/api-reference/agents/list-agents.md)
- [Agents API examples walkthrough](https://docs.tryprofound.com/rest-api/examples/agents.md)
- [SDK overview](https://docs.tryprofound.com/sdks/overview.md)
