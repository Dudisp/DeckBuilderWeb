EDHRec Deck Builder

This small app builds Commander (EDH) decks using an inventory CSV uploaded by the user and EDHRec data fetched in the browser (client-side) to avoid server-side scraping/requests.

What changed (migration to FastAPI)
- The project was converted from Flask to FastAPI. The API entrypoint is `api.py` which exposes:
  - GET / -> serves `templates/index.html` (Jinja2 template)
  - POST /build_deck -> accepts a form with the uploaded CSV (`inventory`), `commander`, optional `partner`, optional `theme`, optional `budget` and `edhrec_data` (a JSON payload fetched from EDHRec on the client).

Requirements
- Python 3.10+ recommended
- See `requirements.txt` for pinned dependencies. Install with:

```bash
pip install -r requirements.txt
```

Running locally
- Development using Uvicorn (recommended):

```bash
uvicorn api:app --reload
```

- Or run `python api.py` which will start uvicorn programmatically.

PythonAnywhere deployment notes
- PythonAnywhere supports WSGI apps. FastAPI is ASGI. Two options:
  1) Use an ASGI server (recommended) by running Uvicorn in a background process on your PythonAnywhere account and pointing a web app to use a "manual configuration" (you will need to use the paid plan to allow long-running processes). This is more complex.
  2) Use an ASGI-to-WSGI adapter (e.g., `asgi2wsgi`) and expose the app via WSGI in the normal PythonAnywhere web app settings. The repo includes `asgi2wsgi` in `requirements.txt`; below is an example `wsgi.py` to place on PythonAnywhere:

```python
# wsgi.py
from asgi2wsgi import asgi2wsgi
import api

application = asgi2wsgi(api.app)
```

Then configure the PythonAnywhere web app to use this `wsgi.py` as its WSGI configuration file.

Client-side EDHRec fetching
- EDHRec blocks server requests. The app expects the client/browser to fetch EDHRec data (via fetch/XHR) and submit it with the `edhrec_data` form field. `edhrec_provider.ClientProvidedEdhrecProvider` accepts the payload and is used by the builder.
- Keep the client-side code (JS) to fetch EDHRec JSON and send it with the form. The server never makes outbound EDHRec calls.

Security and file size
- Limit upload size in production. PythonAnywhere will enforce quotas. Consider validating CSV fields and sanitizing values.

Next steps / suggestions
- Add a small client-side JS module to fetch EDHRec JSON (with user consent) and auto-populate `edhrec_data` before submitting the form.
- Add unit tests for `DeckBuilder` with a mocked `ClientProvidedEdhrecProvider`.


