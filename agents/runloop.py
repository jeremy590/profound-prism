"""Profound Agents API — the four-endpoint run loop, plus guarded dispatch.

The REST API can RUN agents and READ their schemas/runs; it CANNOT create or
edit them (that's Profound's Agent Builder UI). So this client is run-side only:

    list_agents → get_agent (schema) → run_agent → poll_run

`dispatch()` wraps that loop with a guard: it resolves the downstream agent by
NAME against the live org, and if no such agent exists yet (the SEO/Brand/PR
graphs may not be built), it records a `would_dispatch` result instead of
failing. That lets the CMO orchestrator ship before its specialists do.

Auth + base URL are shared with the snapshot pull (config.py).
"""
import time

import requests

from config import API_KEY, BASE_URL

# Terminal run states (Profound-Agents-API-Brief.md §4).
TERMINAL = {"succeeded", "failed", "cancelled", "skipped"}


class AgentRunLoop:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"X-API-Key": API_KEY,
                               "Content-Type": "application/json"})

    # ---- low level (shared 429 backoff with profound_client) ----
    def _request(self, method, path, **kw):
        for _ in range(6):
            resp = self.s.request(method, f"{BASE_URL}{path}", timeout=60, **kw)
            if resp.status_code == 429:
                wait = int(resp.headers.get("Retry-After", 5))
                print(f"  429 — backing off {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Gave up after retries: {method} {path}")

    # ---- the four endpoints ----
    def list_agents(self, statuses="published", limit=100):
        path = f"/v1/agents?statuses={statuses}&limit={limit}"
        return self._request("GET", path).get("data", [])

    def get_agent(self, agent_id, version="published"):
        return self._request("GET", f"/v1/agents/{agent_id}?version={version}")

    def run_agent(self, agent_id, inputs):
        # POST returns 202 + {status: queued}; success is only known after poll.
        return self._request("POST", f"/v1/agents/{agent_id}/runs",
                             json={"inputs": inputs})

    def poll_run(self, agent_id, run_id, timeout_s=300):
        """Poll one run to a terminal state, backing off 2s→30s."""
        wait, waited = 2, 0
        while waited < timeout_s:
            run = self._request("GET", f"/v1/agents/{agent_id}/runs/{run_id}")
            if run.get("status") in TERMINAL:
                return run
            time.sleep(wait)
            waited += wait
            wait = min(wait * 2, 30)
        return {"status": "timeout", "run_id": run_id, "agent_id": agent_id}

    # ---- name resolution + guarded dispatch ----
    def resolve(self, name):
        """Return the agent dict whose name matches `name` (case-insensitive,
        also tolerant of snake_case vs spaces), or None if not built yet."""
        want = name.strip().lower().replace("_", " ")
        for a in self.list_agents():
            got = a.get("name", "").strip().lower().replace("_", " ")
            if got == want:
                return a
        return None

    def dispatch(self, name, inputs, wait=False):
        """Fire a downstream agent by name. Guarded: if the agent does not yet
        exist in the org, return a `would_dispatch` record rather than raising.

        Returns a manifest dict the orchestrator logs into the brief.
        """
        try:
            agent = self.resolve(name)
        except Exception as e:                       # API/transport problem
            return {"agent": name, "status": "dispatch_error", "inputs": inputs,
                    "error": str(e)}

        if agent is None:
            return {"agent": name, "status": "would_dispatch", "inputs": inputs,
                    "note": "no such agent in org yet — build the graph in "
                            "Profound Agent Builder, then this run goes live"}

        run = self.run_agent(agent["id"], inputs)
        record = {"agent": name, "agent_id": agent["id"], "status": "dispatched",
                  "run_id": run.get("id"), "inputs": inputs}
        if wait:
            record["result"] = self.poll_run(agent["id"], run["id"])
        return record
