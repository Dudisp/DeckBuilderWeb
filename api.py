import json
import logging
import uuid
from io import StringIO
from queue import Queue, Empty
from threading import Thread, Event

from flask import Flask, request, render_template, jsonify, Response

from edhrec_provider import ClientProvidedEdhrecProvider
from main import BudgetType, DeckBuilder

app = Flask(__name__, template_folder="templates")

# Simple in-memory session store for builds
# build_id -> {queue: Queue(), provider_payload: dict, finished: bool, update_event: Event}
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
    session = {"queue": Queue(), "provider_payload": {}, "finished": False, "update_event": Event()}
    BUILD_SESSIONS[build_id] = session

    # if client provided edhrec_data upfront, store it
    if edhrec_data:
        try:
            session["provider_payload"] = json.loads(edhrec_data)
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
            attempt = 0
            while True:
                attempt += 1
                provider = ClientProvidedEdhrecProvider(session["provider_payload"])

                def progress_callback(msg: str):
                    session["queue"].put(("progress", {"message": msg}))

                builder = DeckBuilder(inventory_content, edhrec_provider=provider, progress_callback=progress_callback)
                try:
                    result = builder.build(commander, partner, (theme.lower() if theme else None), budget_type)
                    session["queue"].put(("result", {"result": result}))
                    break
                except KeyError as e:
                    # Missing edhrec payload data required by provider, ask client to provide
                    missing_key = str(e).strip("'")
                    session["queue"].put(("request", {"missing_key": missing_key}))
                    # Wait for client to POST /update with the missing data. If timeout, return error.
                    got = session["update_event"].wait(timeout=120)
                    session["update_event"].clear()
                    if not got:
                        session["queue"].put(("error", {"message": f"Timed out waiting for missing data: {missing_key}"}))
                        break
                    # else loop and retry building with updated payload
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


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    # For local development run with: python api.py
    app.run(host="0.0.0.0", port=8000, debug=True)
