# Price Compare

Paste a product link from Amazon, Flipkart, Walmart, Best Buy, etc. and get the lowest price across stores, with discounts and savings.

## How it works

1. **Extract** (`app/extractor.py`): detects the store and country from the domain, fetches the page and reads the product name/price from JSON-LD or Open Graph tags. If the store blocks the request (Amazon often does), it falls back to the product slug in the URL.
2. **Search** (`app/providers.py`): looks the product up on Google Shopping via SerpAPI, which covers hundreds of stores in one call. Without a key it uses demo data.
3. **Filter & rank** (`app/ranking.py`):
   - drops results that aren't the same product (word-match score; model numbers like `1000XM5` or `256gb` count double)
   - drops accessories (cases, chargers...) unless you searched for one
   - drops suspiciously cheap listings (< 35% of the median or of your link's price)
   - flags refurbished/used items
   - sorts by price and computes discount % and savings vs. the pasted link

## Run

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env      # then add your SERPAPI_KEY (optional)
uvicorn app.main:app --reload
```

Open http://localhost:8000.

Tests: `pytest -q`

## API

`POST /api/compare` with `{"url": "<product link>"}` returns `product`, `best`, `savings_vs_link`, `offers` (sorted), `filtered_out` (with reasons).

## Ideas for next steps

- Price history + alerts (store results in SQLite, cron job, email when price drops)
- Coupon/bank-offer detection
- Browser extension that sends the current tab's URL to the API
- Add more providers (Amazon PA-API, eBay Browse API, Flipkart Affiliate API) behind the same `search()` interface
