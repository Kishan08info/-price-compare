"""Filter irrelevant / suspicious offers and rank the rest by price."""
import re
from statistics import median

from .providers import Offer

STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "of", "in", "to", "by", "new", "latest",
    "buy", "online", "best", "price", "edition", "version", "pack", "inch", "black", "white",
}
ACCESSORY_WORDS = {
    "case", "cover", "protector", "skin", "sleeve", "strap", "charger", "cable",
    "adapter", "stand", "mount", "holder", "sticker", "tempered", "replacement",
}
USED_WORDS = {"refurbished", "renewed", "used", "pre-owned", "open-box", "open box"}

MIN_RELEVANCE = 0.45
MIN_PRICE_RATIO = 0.35  # anything below 35% of the median is probably an accessory or scam


def tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower())
    return {w for w in words if w not in STOPWORDS and len(w) > 1}


def relevance(query: str, title: str) -> float:
    """Share of the query's important words found in the offer title.
    Words with digits (model numbers, storage sizes) count double."""
    q, t = tokens(query), tokens(title)
    if not q:
        return 0.0
    weight = lambda w: 2.0 if any(c.isdigit() for c in w) else 1.0
    total = sum(weight(w) for w in q)
    hit = sum(weight(w) for w in q if w in t)
    return round(hit / total, 3)


def rank_offers(query: str, offers: list[Offer], reference_price: float | None = None) -> tuple[list[Offer], list[Offer]]:
    """Returns (kept offers sorted cheapest first, removed offers)."""
    query_tokens = tokens(query)
    wants_accessory = bool(query_tokens & ACCESSORY_WORDS)
    kept, removed = [], []

    for o in offers:
        o.relevance = relevance(query, o.title)
        o.flags = []
        title_tokens = tokens(o.title)
        if o.relevance < MIN_RELEVANCE:
            o.flags.append("not the same product")
        if not wants_accessory and title_tokens & ACCESSORY_WORDS:
            o.flags.append("accessory")
        if any(w in o.title.lower() for w in USED_WORDS):
            o.flags.append("refurbished/used")  # informational, not removed
        if o.original_price and o.original_price > o.price:
            o.discount_pct = round((o.original_price - o.price) / o.original_price * 100, 1)
        hard = {"not the same product", "accessory"}
        (removed if hard & set(o.flags) else kept).append(o)

    # Price outliers: compare against the median of what's left (or the price on the pasted page)
    if kept:
        anchor = reference_price or median(o.price for o in kept)
        still = []
        for o in kept:
            if o.price < anchor * MIN_PRICE_RATIO:
                o.flags.append("suspiciously cheap")
                removed.append(o)
            else:
                still.append(o)
        kept = still

    # Cheapest first; new beats refurbished at equal price; then relevance
    kept.sort(key=lambda o: (o.price, "refurbished/used" in o.flags, -o.relevance))
    return kept, removed
