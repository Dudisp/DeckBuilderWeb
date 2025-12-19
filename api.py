import json
import logging
from io import StringIO

from flask import Flask, jsonify, render_template, request

from edhrec_provider import ClientProvidedEdhrecProvider
from main import BudgetType, DeckBuilder

app = Flask(__name__)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/build_deck', methods=['POST'])
def build_deck():
    if 'inventory' not in request.files:
        return jsonify({"error": "No inventory file provided"}), 400

    inventory_file = request.files['inventory']
    if inventory_file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    commander = request.form.get('commander')
    partner = request.form.get('partner') or None
    theme = request.form.get('theme') or None
    budget_raw = (request.form.get('budget') or "").upper()
    edhrec_payload_raw = request.form.get('edhrec_data')

    if not commander:
        return jsonify({"error": "Commander is required"}), 400

    if not inventory_file.filename.endswith('.csv'):
        return jsonify({"error": "Invalid file format. Please upload a CSV file."}), 400

    if not edhrec_payload_raw:
        return jsonify({"error": "Missing EDHRec data. Fetch EDHRec data on the client and include it as 'edhrec_data' JSON."}), 400

    try:
        budget = BudgetType[budget_raw] if budget_raw else BudgetType.REGULAR
    except KeyError:
        return jsonify({"error": f"Invalid budget option: {budget_raw}"}), 400

    try:
        inventory_content = StringIO(inventory_file.read().decode("utf-8"))
        edhrec_payload = json.loads(edhrec_payload_raw)
        edhrec_provider = ClientProvidedEdhrecProvider(edhrec_payload)
        builder = DeckBuilder(inventory_content, edhrec_provider=edhrec_provider)
        deck_data = builder.build(
            commander,
            partner,
            theme.lower() if theme else None,
            budget,
        )
    except Exception as exc:
        app.logger.exception("Failed to build deck")
        return jsonify({"error": f"Failed to build deck: {exc}"}), 500

    return jsonify(deck_data)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    app.run(debug=True)