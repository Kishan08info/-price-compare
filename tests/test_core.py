import asyncio

from app.extractor import detect_store, parse_page, title_from_slug
from app.providers import DemoProvider, Offer
from app.ranking import rank_offers, relevance


def test_detect_store():
    assert detect_store("https://www.amazon.in/x/dp/B0ABC") == ("Amazon India", "in", "INR")
    assert detect_store("https://www.flipkart.com/x/p/itm1") == ("Flipkart", "in", "INR")
    assert detect_store("https://smile.amazon.com/x")[0] == "Amazon"


def test_title_from_slug():
    assert title_from_slug(
        "https://www.amazon.com/Apple-AirPods-Pro-2nd-Generation/dp/B0BDHWDR12?th=1"
    ) == "Apple AirPods Pro 2nd Generation"
    assert title_from_slug(
        "https://www.flipkart.com/samsung-galaxy-s24-ultra-titanium-256-gb/p/itm12345"
    ) == "samsung galaxy s24 ultra titanium 256 gb"
    assert title_from_slug(
        "https://www.walmart.com/ip/Sony-WH-1000XM5-Wireless-Headphones/123456"
    ) == "Sony WH 1000XM5 Wireless Headphones"


def test_parse_page_jsonld():
    html = """<html><head><script type="application/ld+json">
    {"@type":"Product","name":"Sony WH-1000XM5","offers":{"price":"348.00"}}
    </script></head></html>"""
    assert parse_page(html) == {"title": "Sony WH-1000XM5", "price": 348.0}


def test_relevance_weights_model_numbers():
    q = "Sony WH-1000XM5 headphones"
    assert relevance(q, "Sony WH-1000XM5 Wireless Noise Canceling Headphones") == 1.0
    assert relevance(q, "Sony WH-1000XM4 Wireless Headphones") < relevance(q, "Sony WH-1000XM5")


def test_rank_filters_and_sorts():
    q = "Apple AirPods Pro 2"
    offers = [
        Offer("Apple AirPods Pro 2", "A", 249, "USD", "x", original_price=279),
        Offer("Apple AirPods Pro 2 USB-C", "B", 199, "USD", "x"),
        Offer("Case cover for Apple AirPods Pro 2", "C", 9.99, "USD", "x"),
        Offer("Samsung Galaxy Buds", "D", 99, "USD", "x"),
        Offer("Apple AirPods Pro 2 knockoff", "E", 30, "USD", "x"),
    ]
    kept, removed = rank_offers(q, offers)
    assert [o.store for o in kept] == ["B", "A"]
    assert kept[1].discount_pct == 10.8
    assert {o.store for o in removed} == {"C", "D", "E"}


def test_demo_provider_end_to_end():
    offers = asyncio.run(DemoProvider().search("Apple AirPods Pro 2", "us", "USD"))
    kept, removed = rank_offers("Apple AirPods Pro 2", offers)
    assert len(kept) == 6 and len(removed) == 2
    assert kept == sorted(kept, key=lambda o: o.price)
