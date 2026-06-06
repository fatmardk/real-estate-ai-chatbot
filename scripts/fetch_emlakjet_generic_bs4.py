import json, re
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

URL = "https://www.emlakjet.com/satilik-daire/istanbul"
OUT = Path("data") / "listings_live.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
}

def to_int(text: str):
    t = re.sub(r"[^\d]", "", text or "")
    return int(t) if t else None

def find_card(tag):
    """TL içeren node'dan yukarı çıkıp 'kart' olabilecek bir container bulmaya çalışır."""
    cur = tag
    for _ in range(8):
        if cur is None:
            break
        # kart gibi duran container: içinde link/h2/h3 barındırır
        if hasattr(cur, "find") and cur.find("a", href=True):
            txt = cur.get_text(" ", strip=True)
            if "TL" in txt and (re.search(r"\b[1-9]\s*\+\s*1\b", txt) or re.search(r"\b\d{2,3}\s*(m2|m²)\b", txt, re.I)):
                return cur
        cur = cur.parent
    return None

resp = requests.get(URL, headers=HEADERS, timeout=25)
print("STATUS:", resp.status_code, "LEN:", len(resp.text))
resp.raise_for_status()

# Debug kaydı
Path("data/_debug_page.html").write_text(resp.text, encoding="utf-8", errors="ignore")

soup = BeautifulSoup(resp.text, "html.parser")

# 1) Sayfada TL geçen parçaları bul
price_nodes = soup.find_all(string=re.compile(r"\bTL\b"))
seen_urls = set()
items = []

for node in price_nodes:
    card = find_card(node.parent)
    if not card:
        continue

    text = card.get_text(" ", strip=True)

    # fiyat
    m_price = re.search(r"(\d[\d\.\,]+)\s*TL", text)
    price_try = to_int(m_price.group(1)) if m_price else None
    if not price_try:
        continue

    # oda
    m_rooms = re.search(r"([1-9])\s*\+\s*1", text)
    rooms = f"{m_rooms.group(1)}+1" if m_rooms else "unknown"

    # m²
    m_m2 = re.search(r"(\d{2,3})\s*(m2|m²)", text, re.IGNORECASE)
    gross_m2 = int(m_m2.group(1)) if m_m2 else None

    # başlık (kart içinde h2/h3 dene)
    h = card.find(["h2", "h3"])
    title = h.get_text(strip=True) if h else "unknown"

    # url (kart içindeki ilk link)
    a = card.find("a", href=True)
    href = a["href"] if a else URL
    if href.startswith("/"):
        href = "https://www.emlakjet.com" + href

    # duplicate engelle
    if href in seen_urls:
        continue
    seen_urls.add(href)

    items.append({
        "listing_id": f"live_{len(items)+1}",
        "title": title,
        "district": "İstanbul",
        "neighborhood": "unknown",
        "rooms": rooms,
        "gross_m2": gross_m2,
        "price_try": price_try,
        "features": [],
        "description": "",
        "description_clean": "",
        "source_url": href,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
    })

# ilk 50 yeter (tek sayfa demo)
items = items[:50]

OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK: {len(items)} ilan -> {OUT}")