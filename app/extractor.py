"""Turn a pasted product URL into a product name, store, country and (if possible) current price."""
import json
import re
from dataclasses import dataclass, asdict
from urllib.parse import urlparse, unquote

import httpx
from bs4 import BeautifulSoup

# domain fragment -> (store name, country code, currency)
STORES = {
    "amazon.in": ("Amazon India", "in", "INR"),
    "amazon.co.uk": ("Amazon UK", "uk", "GBP"),
    "amazon.ca": ("Amazon Canada", "ca", "CAD"),
    "amazon.com": ("Amazon", "us", "USD"),
    "flipkart.com": ("Flipkart", "in", "INR"),
    "myntra.com": ("Myntra", "in", "INR"),
    "croma.com": ("Croma", "in", "INR"),
    "reliancedigital.in": ("Reliance Digital", "in", "INR"),
    "walmart.com": ("Walmart", "us", "USD"),
    "bestbuy.com": ("Best Buy", "us", "USD"),
    "target.com": ("Target", "us", "USD"),
    "ebay.com": ("eBay", "us", "USD"),
    "costco.com": ("Costco", "us", "USD"),
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Words that stores add to page titles but aren't part of the product name
TITLE_NOISE = re.compile(
    r"\s*[:|\-–]\s*(amazon\.[a-z.]+|flipkart\.com|walmart\.com|best buy|target|ebay|"
    r"buy online.*|online at best price.*|electronics|computers? & accessories).*$",
    re.IGNORECASE,
)


@dataclass
class ProductInfo:
    url: str
    store: str
    country: str
    currency: str
    title: str
    price: float | None = None
    image: str | None = None

    def to_dict(self):
        return asdict(self)


def detect_store(url: str) -> tuple[str, str, str]:
    host = urlparse(url).netloc.lower().removeprefix("www.")
    for domain, info in STORES.items():
        if host == domain or host.endswith("." + domain):
            return info
    # Unknown store: guess the country from the TLD
    country = "in" if host.endswith(".in") else "uk" if host.endswith(".uk") else "us"
    currency = {"in": "INR", "uk": "GBP"}.get(country, "USD")
    return host or "Unknown store", country, currency


def title_from_slug(url: str) -> str | None:
    """Most stores put a readable product slug in the URL — use it when the page can't be fetched."""
    path = unquote(urlparse(url).path)
    parts = [p for p in path.split("/") if p]
    slug = None

    for marker in ("dp", "gp", "p", "ip", "product"):
        if marker in parts:
            i = parts.index(marker)
            if marker == "ip" and i + 1 < len(parts):  # walmart: /ip/<slug>/<id>
                slug = parts[i + 1]
            elif i > 0:  # amazon /<slug>/dp/<asin>, flipkart /<slug>/p/<id>
                slug = parts[i - 1]
            if slug:
                break

    if not slug:  # fallback: the segment with the most hyphens
        candidates = [p for p in parts if p.count("-") >= 2]
        slug = max(candidates, key=lambda p: p.count("-"), default=None)

    if not slug:
        return None
    slug = re.sub(r"\.(p|html?)$", "", slug)
    words = re.split(r"[-_+]+", slug)
    words = [w for w in words if w and not re.fullmatch(r"[A-Z0-9]{10}", w)]  # drop ASIN-like ids
    return " ".join(words).strip() or None


def clean_title(title: str) -> str:
    title = TITLE_NOISE.sub("", title).strip()
    title = re.sub(r"\s+", " ", title)
    return title[:150]


def _parse_price(value) -> float | None:
    if value is None:
        return None
    m = re.search(r"\d[\d,]*\.?\d*", str(value))
    if not m:
        return None
    try:
        return float(m.group().replace(",", ""))
    except ValueError:
        return None


def parse_page(html: str) -> dict:
    """Pull title / price / image from JSON-LD, Open Graph or <title>."""
    soup = BeautifulSoup(html, "html.parser")
    out: dict = {}

    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (json.JSONDecodeError, TypeError):
            continue
        items = data if isinstance(data, list) else data.get("@graph", [data])
        for item in items:
            if not isinstance(item, dict) or "Product" not in str(item.get("@type")):
                continue
            out.setdefault("title", item.get("name"))
            img = item.get("image")
            out.setdefault("image", img[0] if isinstance(img, list) and img else img)
            offers = item.get("offers") or {}
            if isinstance(offers, list) and offers:
                offers = offers[0]
            if isinstance(offers, dict):
                price = _parse_price(offers.get("price") or offers.get("lowPrice"))
                if price:
                    out.setdefault("price", price)

    def meta(*names):
        for n in names:
            tag = soup.find("meta", property=n) or soup.find("meta", attrs={"name": n})
            if tag and tag.get("content"):
                return tag["content"]
        return None

    out.setdefault("title", meta("og:title", "twitter:title"))
    out.setdefault("image", meta("og:image"))
    if not out.get("price"):
        out["price"] = _parse_price(meta("product:price:amount", "og:price:amount"))
    if not out.get("title") and soup.title:
        out["title"] = soup.title.get_text()
    return {k: v for k, v in out.items() if v}


async def extract_product(url: str) -> ProductInfo:
    if not re.match(r"^https?://", url):
        url = "https://" + url
    store, country, currency = detect_store(url)
    page: dict = {}
    try:
        async with httpx.AsyncClient(headers=HEADERS, follow_redirects=True, timeout=10) as client:
            resp = await client.get(url)
        if resp.status_code == 200:
            page = parse_page(resp.text)
            # Short links (amzn.to etc.) redirect — re-detect on the final URL
            if str(resp.url) != url:
                url = str(resp.url)
                store, country, currency = detect_store(url)
    except httpx.HTTPError:
        pass  # many stores block bots; fall back to the URL slug

    title = page.get("title")
    # Captcha / robot pages have useless titles
    if title and re.search(r"robot|captcha|access denied|page not found", title, re.I):
        title = None
    title = clean_title(title) if title else title_from_slug(url)
    if not title:
        raise ValueError("Couldn't work out the product name from this link.")

    return ProductInfo(
        url=url, store=store, country=country, currency=currency,
        title=title, price=page.get("price"), image=page.get("image"),
    )
