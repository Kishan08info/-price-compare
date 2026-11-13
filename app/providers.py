"""Price sources. SerpAPI (Google Shopping) when a key is set, otherwise demo data."""
import hashlib
import os
import random
from dataclasses import dataclass, asdict

import httpx


@dataclass
class Offer:
    title: str
    store: str
    price: float
    currency: str
    link: str
    original_price: float | None = None
    shipping: str | None = None
    rating: float | None = None
    reviews: int | None = None
    thumbnail: str | None = None
    # filled in by ranking
    relevance: float = 0.0
    discount_pct: float | None = None
    flags: list[str] | None = None

    def to_dict(self):
        return asdict(self)


class SerpApiProvider:
    name = "Google Shopping (SerpAPI)"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, country: str, currency: str) -> list[Offer]:
        params = {
            "engine": "google_shopping",
            "q": query,
            "gl": country,
            "hl": "en",
            "num": 40,
            "api_key": self.api_key,
        }
        async with httpx.AsyncClient(timeout=25) as client:
            resp = await client.get("https://serpapi.com/search.json", params=params)
        resp.raise_for_status()
        data = resp.json()
        if "error" in data:
            raise RuntimeError(f"SerpAPI: {data['error']}")

        offers = []
        for r in data.get("shopping_results", []):
            price = r.get("extracted_price")
            if not price:
                continue
            offers.append(Offer(
                title=r.get("title", ""),
                store=r.get("source", "Unknown"),
                price=float(price),
                currency=currency,
                link=r.get("link") or r.get("product_link") or "",
                original_price=r.get("extracted_old_price"),
                shipping=r.get("delivery"),
                rating=r.get("rating"),
                reviews=r.get("reviews"),
                thumbnail=r.get("thumbnail"),
            ))
        return offers


class DemoProvider:
    """Deterministic fake offers so the app works without an API key."""
    name = "Demo data (set SERPAPI_KEY for real prices)"

    STORES = {
        "in": ["Amazon India", "Flipkart", "Croma", "Reliance Digital", "Vijay Sales", "Tata CLiQ"],
        "us": ["Amazon", "Walmart", "Best Buy", "Target", "eBay", "Costco"],
        "uk": ["Amazon UK", "Argos", "Currys", "John Lewis", "eBay UK"],
        "ca": ["Amazon Canada", "Best Buy Canada", "Walmart Canada", "Costco Canada"],
    }

    async def search(self, query: str, country: str, currency: str) -> list[Offer]:
        seed = int(hashlib.md5(query.lower().encode()).hexdigest(), 16)
        rng = random.Random(seed)
        base = rng.choice([25, 60, 150, 400, 900]) * (83 if currency == "INR" else 1)
        offers = []
        for store in self.STORES.get(country, self.STORES["us"]):
            mrp = round(base * rng.uniform(1.05, 1.3), 2)
            price = round(mrp * rng.uniform(0.7, 0.98), 2)
            offers.append(Offer(
                title=query, store=store, price=price, currency=currency,
                link=f"https://www.google.com/search?tbm=shop&q={query.replace(' ', '+')}",
                original_price=mrp,
                shipping=rng.choice(["Free delivery", "Free delivery", "+ shipping"]),
                rating=round(rng.uniform(3.6, 4.8), 1),
                reviews=rng.randint(20, 5000),
            ))
        # a couple of junk results the filter should remove
        offers.append(Offer(title=f"Case cover for {query}", store="eBay", price=round(base * 0.05, 2),
                            currency=currency, link="https://example.com"))
        offers.append(Offer(title="Unrelated wireless mouse", store="Walmart", price=round(base * 0.4, 2),
                            currency=currency, link="https://example.com"))
        return offers


def get_provider():
    key = os.getenv("SERPAPI_KEY", "").strip()
    return SerpApiProvider(key) if key else DemoProvider()
