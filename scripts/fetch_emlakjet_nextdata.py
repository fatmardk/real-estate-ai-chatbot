import json
import re
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

def pick_first(d: dict, keys: list[str], default=None):
    for k in keys:
        if isinstance(d, dict) and k in d and d[k] not in (None, ""):
            return d[k]
    return default

def to_int(x):
    if x is None:
        return None
    if isinstance(x, (int, float)):
        return int(x)
    s = str(x)
    s = re.sub(r"[^\d]", "", s)
    return int(s) if s else None

resp = requests.get(URL, headers=HEADERS, timeout=25)
print("STATUS:", resp.status_code, "LEN:", len(resp.text))
resp.raise_for_status()

# Debug kaydı (istersen)
Path("data/_debug_page.html").write_text(resp.text, encoding="utf-8")

soup = BeautifulSoup(resp.text, "html.parser")

# 1) Next.js verisi var mı?
next_data = soup.find("script", id="__NEXT_DATA__")
if not next_data or not next_data.string:
    raise RuntimeError("Bu sayfada __NEXT_DATA__ bulunamadı. (Site farklı mimari kullanıyor olabilir.)")

data = json.loads(next_data.string)

# Next.js yapısı siteye göre değişir, bu yüzden güvenli gezelim
# Sıklıkla: props -> pageProps içinde arama sonuçları bulunur.
page_props = (((data.get("props") or {}).get("pageProps")) or {})

# Olası alan adları (siteye göre değişebilir)
candidates = []

# pageProps içindeki dict’leri dolaş, içinde “listings / results / items” benzeri listeler var mı bak
def find_listing_lists(obj):
    found = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                # liste çok büyükse ve içinde title/price gibi alanlar geçiyorsa ilan listesi olabilir
                sample_keys = set(v[0].keys())
                if {"title", "price"}.intersection(sample_keys) or {"listingId", "id"}.intersection(sample_keys):
                    found.append(v)
            else:
                found.extend(find_listing_lists(v))
    elif isinstance(obj, list):
        for it in obj:
            found.extend(find_listing_lists(it))
    return found

lists = find_listing_lists(page_props)
if not lists:
    raise RuntimeError("pageProps içinde ilan listesi bulunamadı. Debug için data/_debug_page.html dosyasını kontrol et.")

# En olası ilk listeyi al
raw_listings = lists[0]

items = []
for i, l in enumerate(raw_listings, start=1):
    title = pick_first(l, ["title", "name", "heading"], "unknown")
    price_try = to_int(pick_first(l, ["price", "amount", "priceTL", "priceTry"]))
    gross_m2 = to_int(pick_first(l, ["grossArea", "gross_m2", "area", "m2"]))
    rooms = pick_first(l, ["room", "rooms", "roomCount", "roomText"], "unknown")
    district = pick_first(l, ["district", "town", "ilce"], "unknown")
    neighborhood = pick_first(l, ["neighborhood", "mahalle", "quarter"], "unknown")

    url_part = pick_first(l, ["url", "detailUrl", "link"], None)
    if url_part and isinstance(url_part, str) and url_part.startswith("http"):
        source_url = url_part
    elif url_part and isinstance(url_part, str) and url_part.startswith("/"):
        source_url = "https://www.emlakjet.com" + url_part
    else:
        source_url = URL

    items.append({
        "listing_id": str(pick_first(l, ["listingId", "id"], f"live_{i}")),
        "title": str(title),
        "district": str(district),
        "neighborhood": str(neighborhood),
        "rooms": str(rooms),
        "gross_m2": gross_m2,
        "price_try": price_try,
        "features": [],
        "description": "",
        "description_clean": "",
        "source_url": source_url,
        "scraped_at": datetime.now().isoformat(timespec="seconds"),
    })

OUT.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"OK: {len(items)} ilan -> {OUT}")