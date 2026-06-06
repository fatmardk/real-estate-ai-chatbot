import json, re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

URL = "https://www.emlakjet.com/satilik-daire/istanbul"  # ör: bir ilçenin ilan listesi sayfası
OUT = Path("data") / "listings_live.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {"User-Agent": "Mozilla/5.0"}

def to_int(text: str):
    t = re.sub(r"[^\d]", "", text or "")
    return int(t) if t else None

resp = requests.get(URL, headers=HEADERS, timeout=25)
print("STATUS:", resp.status_code, "LEN:", len(resp.text))

Path("data").mkdir(exist_ok=True)
Path("data/_debug_page.html").write_text(resp.text, encoding="utf-8")
print("Saved: data/_debug_page.html")

html = resp.text
soup = BeautifulSoup(html, "html.parser")

items = []
cards = soup.select("CARD_SELECTOR")  # ör: ".listing-item"
for i, c in enumerate(cards, start=1):
    title_el = c.select_one("TITLE_SELECTOR")   # ör: ".title"
    price_el = c.select_one("PRICE_SELECTOR")   # ör: ".price"
    m2_el    = c.select_one("M2_SELECTOR")      # ör: ".m2"
    rooms_el = c.select_one("ROOMS_SELECTOR")   # ör: ".rooms"
    link_el  = c.select_one("a")

    title = title_el.get_text(strip=True) if title_el else "unknown"
    price_try = to_int(price_el.get_text(strip=True)) if price_el else None
    gross_m2  = to_int(m2_el.get_text(strip=True)) if m2_el else None
    rooms     = rooms_el.get_text(strip=True) if rooms_el else "unknown"
    href      = link_el["href"] if (link_el and link_el.has_attr("href")) else URL
    if href.startswith("/"):
        # relative link ise domain ekle (istersen)
        pass

    items.append({
        "listing_id": f"live_{i}",
        "title": title,
        "district": "unknown",
        "neighborhood": "unknown",
        "rooms": rooms,
        "gross_m2": gross_m2,
        "price_try": price_try,
        "features": [],
        "description": "",
        "description_clean": "",
        "source_url": href,
        "scraped_at": datetime.now().isoformat(timespec="seconds")
    })

OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK: {len(items)} ilan -> {OUT}")