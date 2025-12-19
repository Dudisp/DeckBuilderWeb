import json
import logging
from io import StringIO

from flask import Flask, request, render_template, jsonify

from edhrec_provider import ClientProvidedEdhrecProvider
from main import BudgetType, DeckBuilder

app = Flask(__name__, template_folder="templates")


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/build_deck", methods=["POST"])
def build_deck():
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

    if not edhrec_data:
        return jsonify(
            {
                "error": "Missing EDHRec data. Fetch EDHRec data on the client and include it as 'edhrec_data' JSON."
            }
        ), 400

    budget_raw = (budget or "").upper()

    try:
        budget_type = BudgetType[budget_raw] if budget_raw else BudgetType.REGULAR
    except KeyError:
        return jsonify({"error": f"Invalid budget option: {budget_raw}"}), 400

    try:
        inventory_bytes = inventory.read()
        inventory_content = StringIO(inventory_bytes.decode("utf-8"))
        edhrec_payload = json.loads(edhrec_data)
        edhrec_provider = ClientProvidedEdhrecProvider(edhrec_payload)
        builder = DeckBuilder(inventory_content, edhrec_provider=edhrec_provider)
        deck_data = builder.build(
            commander,
            partner,
            theme.lower() if theme else None,
            budget_type,
        )
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).exception("Failed to build deck")
        return jsonify({"error": f"Failed to build deck: {exc}"}), 500

    return jsonify(deck_data)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
    )
    # For local development run with: python api.py
    app.run(host="127.0.0.1", port=8000, debug=True)
