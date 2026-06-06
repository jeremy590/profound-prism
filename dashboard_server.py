"""Prism dashboard — local server (live data).

Serves the static front-end (static/index.html) and the API it calls, backed by
read-only queries over profound.db (see dashboard_data.py). Single snapshot — no
trends. The DB is opened read-only; nothing here writes.

Run:
    .venv/bin/python dashboard_server.py
Then open http://127.0.0.1:5050
"""
import os

from flask import Flask, jsonify, request, send_from_directory

import dashboard_data as dd

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
ROLES = {"cmo", "seo", "pm", "brand", "pr"}

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------- static site
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/<path:path>")
def static_files(path):
    return send_from_directory(STATIC_DIR, path)


@app.route("/api/health")
def health():
    return jsonify(status="ok", static=os.path.isdir(STATIC_DIR), db=os.path.isfile(dd.DB_PATH))


# --------------------------------------------------------------- context helper
def _ctx():
    return {
        "brand": request.args.get("brand"),
        "engine": request.args.get("engine"),
        "region": request.args.get("region"),
    }


# --------------------------------------------------------------- api (live)
@app.route("/api/meta")
def meta():
    return jsonify(dd.meta())


@app.route("/api/overview")
def overview():
    c = _ctx()
    return jsonify(dd.overview(c["brand"], c["engine"], c["region"]))


@app.route("/api/prism/<role>")
def prism(role):
    if role not in ROLES:
        return jsonify(error=f"unknown role '{role}'"), 404
    c = _ctx()
    return jsonify(dd.prism(role, c["brand"], c["engine"], c["region"]))


@app.route("/api/prism/<role>/actions")
def prism_actions(role):
    if role not in ROLES:
        return jsonify(error=f"unknown role '{role}'"), 404
    return jsonify(dd.actions(role, _ctx()))


@app.route("/api/actions/<action_id>/run", methods=["POST"])
def run_action(action_id):
    ctx = request.get_json(silent=True) or {}
    return jsonify(dd.run_action(action_id, ctx))


if __name__ == "__main__":
    # 5050 avoids macOS AirPlay on 5000. Bind localhost only.
    app.run(host="127.0.0.1", port=5050, debug=True)
