"""Thin Profound REST client: paginated reports + label-decoded rows.

Everything goes through REST so the two MCP-gap surfaces (query-fanouts,
granular sentiment) use the same code path as the rest.
"""
import time
import requests
from config import API_KEY, BASE_URL, CATEGORY_ID, START_DATE, END_DATE


class ProfoundClient:
    def __init__(self):
        self.s = requests.Session()
        self.s.headers.update({"X-API-Key": API_KEY,
                               "Content-Type": "application/json"})

    # ---- low level ----
    def _request(self, method, path, **kw):
        for attempt in range(6):
            resp = self.s.request(method, f"{BASE_URL}{path}", timeout=60, **kw)
            if resp.status_code == 429:                      # rate limited
                wait = int(resp.headers.get("Retry-After", 5))
                print(f"  429 — backing off {wait}s")
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        raise RuntimeError(f"Gave up after retries: {method} {path}")

    def get(self, path):
        return self._request("GET", path)

    # ---- report fetch with offset pagination + label decode ----
    def report(self, report_name, metrics, dimensions, filters=None,
               page_size=10000):
        """Pull a full /v1/reports/<name>, return list[dict] keyed by
        dimension + metric *labels* (decoded from the response, never by
        request order)."""
        out, offset = [], 0
        while True:
            body = {
                "category_id": CATEGORY_ID,
                "start_date": START_DATE,
                "end_date": END_DATE,
                "metrics": metrics,
                "dimensions": dimensions,
                "filters": filters or [],
                "pagination": {"limit": page_size, "offset": offset},
            }
            resp = self._request("POST", f"/v1/reports/{report_name}", json=body)
            q = resp["info"]["query"]
            dim_labels, met_labels = q["dimensions"], q["metrics"]
            rows = resp.get("data", [])
            for r in rows:
                rec = dict(zip(dim_labels, r["dimensions"]))
                rec.update(dict(zip(met_labels, r["metrics"])))
                out.append(rec)
            total = resp["info"]["total_rows"]
            offset += len(rows)
            print(f"  {report_name}: {offset}/{total}")
            if offset >= total or not rows:
                break
        return out
