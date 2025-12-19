import json
import logging
import uuid
from io import StringIO
from queue import Queue, Empty
from threading import Thread, Event
from urllib.parse import urlparse, unquote_plus
import requests
import os
import sys

from flask import Flask, request, render_template, jsonify, Response

from edhrec_provider import ClientProvidedEdhrecProvider, ServerEdhrecProvider
from main import BudgetType, DeckBuilder

# When packaged with PyInstaller, templates are extracted to sys._MEIPASS; support both dev and frozen modes
base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
template_dir = os.path.join(base_dir, 'templates')
app = Flask(__name__, template_folder=template_dir)

# Simple in-memory session store for builds
# build_id -> {queue: Queue(), provider_payload: dict, finished: bool, update_event: Event, cancelled: bool}
BUILD_SESSIONS: dict[str, dict] = {}


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


def sse_format(event: str, data: dict) -> str:
    payload = json.dumps(data)
    return f"event: {event}\ndata: {payload}\n\n"


@app.route("/start", methods=["POST"])
def start_build():
    inventory = request.files.get("inventory")
    commander = request.form.get("commander")
    partner = request.form.get("partner") or None
    theme = request.form.get("theme") or None
    budget = request.form.get("budget") or None
    edhrec_data = request.form.get("edhrec_data")

    if not inventory:
        return jsonify({"error": "No inventory file provided"}), 400
    if not commander:
        return jsonify({"error": "Commander is required"}), 400
    if not inventory.filename or not inventory.filename.endswith(".csv"):
        return jsonify({"error": "Invalid file format. Please upload a CSV file."}), 400

    build_id = str(uuid.uuid4())
    session = {"queue": Queue(), "provider_payload": {}, "finished": False, "update_event": Event(), "cancelled": False}
    BUILD_SESSIONS[build_id] = session

    # if client provided edhrec_data upfront, store it
    if edhrec_data:
        try:
            # keep for informational purposes; provider selection is below
            parsed = json.loads(edhrec_data)
        except Exception:
            logging.getLogger(__name__).exception("Invalid edhrec_data JSON")
            return jsonify({"error": "Invalid edhrec_data JSON"}), 400

    budget_raw = (budget or "").upper()

    try:
        budget_type = BudgetType[budget_raw] if budget_raw else BudgetType.REGULAR
    except KeyError:
        return jsonify({"error": f"Invalid budget option: {budget_raw}"}), 400

    try:
        inventory_bytes = inventory.read()
        inventory_content = StringIO(inventory_bytes.decode("utf-8"))
    except Exception:
        return jsonify({"error": "Failed to read inventory file"}), 400

    # Start builder in a background thread; it will push messages into session['queue']
    def run_builder():
        try:
            # if cancelled before start, exit early
            if session.get("cancelled"):
                session["queue"].put(("cancelled", {"message": "Build cancelled by user"}))
                session["finished"] = True
                return

            # Choose provider: if client supplied edhrec_data use client provider, else use server-side provider
            provider = None
            if edhrec_data:
                try:
                    payload = json.loads(edhrec_data)
                    provider = ClientProvidedEdhrecProvider(payload)
                except Exception:
                    logging.getLogger(__name__).exception("Invalid edhrec_data JSON in run_builder")
                    session["queue"].put(("error", {"message": "Invalid edhrec_data JSON provided"}))
                    session["finished"] = True
                    return
            else:
                try:
                    provider = ServerEdhrecProvider()
                except Exception as e:
                    logging.getLogger(__name__).exception("Server EDHRec provider initialization failed")
                    session["queue"].put(("error", {"message": f"Server EDHRec provider unavailable: {e}"}))
                    session["finished"] = True
                    return

            def progress_callback(msg: str):
                if session.get("cancelled"):
                    return
                session["queue"].put(("progress", {"message": msg}))

            builder = DeckBuilder(inventory_content, edhrec_provider=provider, progress_callback=progress_callback)
            try:
                result = builder.build(commander, partner, (theme.lower() if theme else None), budget_type)
                if session.get("cancelled"):
                    session["queue"].put(("cancelled", {"message": "Build cancelled by user"}))
                else:
                    session["queue"].put(("result", {"result": result}))
            except Exception as e:
                logging.getLogger(__name__).exception("Builder failed")
                session["queue"].put(("error", {"message": str(e)}))
        finally:
            session["finished"] = True

    Thread(target=run_builder, daemon=True).start()

    # Return build id; client should open an EventSource to /events?build_id=<id>
    return jsonify({"build_id": build_id})


@app.route("/events", methods=["GET"])
def events():
    build_id = request.args.get("build_id")
    if not build_id or build_id not in BUILD_SESSIONS:
        return ("Build not found", 404)

    session = BUILD_SESSIONS[build_id]

    def event_stream():
        q = session["queue"]
        # keep streaming until finished and queue emptied
        while not session["finished"] or not q.empty():
            try:
                ev, data = q.get(timeout=0.5)
                yield sse_format(ev, data)
            except Empty:
                continue
        yield sse_format("closed", {"message": "Build finished"})

    return Response(event_stream(), mimetype="text/event-stream")


@app.route("/update", methods=["POST"])
def update_build():
    # Accept JSON body {build_id:..., edhrec_payload: {...}}
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON payload"}), 400

    build_id = payload.get("build_id")
    if not build_id or build_id not in BUILD_SESSIONS:
        return jsonify({"error": "Invalid or missing build_id"}), 400

    session = BUILD_SESSIONS[build_id]

    provider_payload = payload.get("edhrec_payload")
    if provider_payload:
        # Merge provider payload updates
        session["provider_payload"].update(provider_payload)
        # notify builder thread to resume
        session["update_event"].set()
        return jsonify({"status": "updated"})

    return jsonify({"error": "No recognized update in payload"}), 400


@app.route("/cancel", methods=["POST"])
def cancel_build():
    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "Invalid JSON payload"}), 400

    build_id = payload.get("build_id")
    if not build_id or build_id not in BUILD_SESSIONS:
        return jsonify({"error": "Invalid or missing build_id"}), 400

    session = BUILD_SESSIONS[build_id]
    session["cancelled"] = True
    # wake any waiting builder
    session["update_event"].set()
    # notify client stream
    session["queue"].put(("cancelled", {"message": "Build cancelled by user"}))
    return jsonify({"status": "cancelled"})


@app.route("/proxy", methods=["GET"])
def proxy():
    # Simple server-side proxy only allowing json.edhrec.com to avoid open proxy abuse
    url = request.args.get('url')
    if not url:
        return jsonify({"error": "Missing url parameter"}), 400
    try:
        url = unquote_plus(url)
        parsed = urlparse(url)
        host = parsed.hostname or ''
        allowed_hosts = {"json.edhrec.com", "edhrec.com"}
        if host not in allowed_hosts:
            return jsonify({"error": "Host not allowed"}), 403
        # fetch the URL server-side
        resp = requests.get(url, timeout=10)
        content_type = resp.headers.get('Content-Type', 'application/json')
        if resp.status_code != 200:
            return (resp.text, resp.status_code, {'Content-Type': content_type})
        return (resp.content, 200, {'Content-Type': content_type})
    except requests.RequestException as e:
        logging.getLogger(__name__).exception("Proxy request failed")
        return jsonify({"error": f"Proxy fetch failed: {e}"}), 502


@app.route("/edhrec_build_id", methods=["GET"])
def edhrec_build_id():
    """Return the current edhrec Next.js build id by scraping the homepage's __NEXT_DATA__ script block.
    This matches pyedhrec. Returns JSON { build_id: "..." } or 502 on failure.
    """
    try:
        resp = requests.get("https://edhrec.com", timeout=10)
        resp.raise_for_status()
        text = resp.text
        import re, json as _json
        m = re.search(r"<script id=\"__NEXT_DATA__\" type=\"application/json\">(.*?)</script>", text, re.S)
        if not m:
            return jsonify({"error": "Could not find NEXT_DATA"}), 502
        props_str = m.group(1)
        try:
            props = _json.loads(props_str)
            build_id = props.get("buildId")
            if not build_id:
                return jsonify({"error": "buildId not found in NEXT_DATA"}), 502
            return jsonify({"build_id": build_id})
        except _json.JSONDecodeError:
            return jsonify({"error": "Failed to parse NEXT_DATA"}), 502
    except requests.RequestException as e:
        logging.getLogger(__name__).exception("Failed to fetch edhrec homepage for build id")
        return jsonify({"error": str(e)}), 502


@app.route('/favicon.ico')
def favicon():
    """Serve a tiny SVG favicon to avoid 404s from browsers requesting /favicon.ico."""
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        '<rect width="100%" height="100%" fill="#1f6feb"/>'
        '<text x="32" y="38" font-size="36" text-anchor="middle" fill="white" font-family="Segoe UI, Roboto, Arial">D</text>'
        '</svg>'
    )
    return Response(svg, mimetype='image/svg+xml')


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    # For local development run with: python api.py
    app.run(host="0.0.0.0", port=8000, debug=True)
