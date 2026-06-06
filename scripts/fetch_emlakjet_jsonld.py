import json, re
from datetime import datetime
from pathlib import Path
from bs4 import BeautifulSoup

HTML_PATH = Path("data/_debug_page.html")  # requests ile kaydettiğin dosya
OUT = Path("data") / "listings_live.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

def to_int(text: str):
    t = re.sub(r"[^\d]", "", text or "")
    return int(t) if t else None

html = HTML_PATH.read_text(encoding="utf-8", errors="ignore")
soup = BeautifulSoup(html, "html.parser")

scripts = soup.find_all("script", attrs={"type": "application/ld+json"})
print("ld+json script sayısı:", len(scripts))

items = []

def normalize_listing(obj):
    # obj içinde title/price/url/area gibi alanlar farklı isimlerle gelebilir
    title = obj.get("name") or obj.get("title") or "unknown"
    url = obj.get("url") or obj.get("mainEntityOfPage") or ""
    if isinstance(url, dict):
        url = url.get("@id") or ""

    price_try = None
    offers = obj.get("offers")
    if isinstance(offers, dict):
        price_try = to_int(str(offers.get("price") or offers.get("priceSpecification") or ""))
    elif isinstance(offers, list) and offers:
        if isinstance(offers[0], dict):
            price_try = to_int(str(offers[0].get("price") or ""))

    # m² bazen "floorSize": {"value": 120, "unitCode": "MTK"} gibi gelir
    gross_m2 = None
    fs = obj.get("floorSize") or obj.get("floorSizeValue")
    if isinstance(fs, dict):
        gross_m2 = to_int(str(fs.get("value")))
    else:
        gross_m2 = to_int(str(fs)) if fs else None

    return {
        "listing_id": obj.get("@id") or obj.get("sku") or obj.get("productID") or f"live_{len(items)+1}",
        "title": title,
        "district": "unknown",
        "neighborhood": "unknown",
        "rooms": "unknown",
        "gross_m2": gross_m2,
        "price_try": price_try,
        "features": [],
        "description": obj.get("description") or "",
        "description_clean": obj.get("description") or "",
        "source_url": url or "",
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
    }

for s in scripts:
    txt = (s.string or "").strip()
    if not txt:
        continue
    try:
        data = json.loads(txt)
    except:
        continue

    # JSON-LD bazen liste olabilir
    if isinstance(data, list):
        candidates = data
    else:
        candidates = [data]

    for d in candidates:
        # ItemList -> itemListElement
        if isinstance(d, dict) and d.get("@type") == "ItemList" and "itemListElement" in d:
            for el in d["itemListElement"]:
                if isinstance(el, dict) and "item" in el and isinstance(el["item"], dict):
                    items.append(normalize_listing(el["item"]))
        # RealEstateListing / Product benzeri tekil objeler
        elif isinstance(d, dict) and d.get("@type") in ("Product", "RealEstateListing", "Offer", "Apartment"):
            items.append(normalize_listing(d))

OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK: {len(items)} ilan -> {OUT}")