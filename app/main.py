from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

load_dotenv()

from .extractor import extract_product  # noqa: E402
from .providers import get_provider  # noqa: E402
from .ranking import rank_offers  # noqa: E402

STATIC = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(title="Price Compare")
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class CompareRequest(BaseModel):
    url: str


@app.get("/")
def index():
    return FileResponse(STATIC / "index.html")


@app.post("/api/compare")
async def compare(req: CompareRequest):
    url = req.url.strip()
    if not url:
        raise HTTPException(400, "Paste a product link.")
    try:
        product = await extract_product(url)
    except ValueError as e:
        raise HTTPException(422, str(e))

    provider = get_provider()
    try:
        offers = await provider.search(product.title, product.country, product.currency)
    except Exception as e:  # network / quota errors from the price source
        raise HTTPException(502, f"Price lookup failed: {e}")

    kept, removed = rank_offers(product.title, offers, product.price)
    best = kept[0] if kept else None

    savings = None
    if best and product.price and product.price > best.price:
        savings = {
            "amount": round(product.price - best.price, 2),
            "pct": round((product.price - best.price) / product.price * 100, 1),
        }

    return {
        "source": provider.name,
        "product": product.to_dict(),
        "best": best.to_dict() if best else None,
        "savings_vs_link": savings,
        "offers": [o.to_dict() for o in kept],
        "filtered_out": [o.to_dict() for o in removed],
    }
