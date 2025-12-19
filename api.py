import json
import logging
from io import StringIO

from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates

from edhrec_provider import ClientProvidedEdhrecProvider
from main import BudgetType, DeckBuilder

app = FastAPI()
templates = Jinja2Templates(directory="templates")


@app.get("/", response_class=None)
async def index(request: Request):
    return templates.TemplateResponse('index.html', {"request": request})


@app.post('/build_deck')
async def build_deck(
    request: Request,
    inventory: UploadFile = File(...),
    commander: str = Form(...),
    partner: str | None = Form(None),
    theme: str | None = Form(None),
    budget: str | None = Form(None),
    edhrec_data: str = Form(...),
):
    if not inventory:
        raise HTTPException(status_code=400, detail="No inventory file provided")

    if not commander:
        raise HTTPException(status_code=400, detail="Commander is required")

    if not inventory.filename or not inventory.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file format. Please upload a CSV file.")

    if not edhrec_data:
        raise HTTPException(status_code=400, detail="Missing EDHRec data. Fetch EDHRec data on the client and include it as 'edhrec_data' JSON.")

    budget_raw = (budget or "").upper()

    try:
        budget_type = BudgetType[budget_raw] if budget_raw else BudgetType.REGULAR
    except KeyError:
        raise HTTPException(status_code=400, detail=f"Invalid budget option: {budget_raw}")

    try:
        inventory_bytes = await inventory.read()
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
    except Exception as exc:
        logging.getLogger(__name__).exception("Failed to build deck")
        return JSONResponse({"error": f"Failed to build deck: {exc}"}, status_code=500)

    return JSONResponse(deck_data)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    # For local development run with: python api.py  OR: uvicorn api:app --reload
    import uvicorn

    uvicorn.run(app, host='127.0.0.1', port=8000)
