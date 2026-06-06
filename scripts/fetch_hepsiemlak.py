"""
fetch_hepsiemlak.py
-------------------
Hepsiemlak'tan requests + BeautifulSoup ile ilan çeker.

Hepsiemlak Next.js kullandığından sayfa HTML'sinde
  <script id="__NEXT_DATA__">...</script>
bloğu içinde tüm ilan verisi JSON olarak gömülüdür.
Bu yüzden JavaScript çalıştırmaya gerek yoktur.

Kullanım:
    python scripts/fetch_hepsiemlak.py

Çıktı:
    data/listings_live.json
"""

import json
import os
import re
import time
import random
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

# ── Ayarlar ──────────────────────────────────────────────────────────────────
CITY            = os.getenv("HEPSIEMLAK_CITY", "istanbul")
LISTING_TYPE    = os.getenv("HEPSIEMLAK_LISTING_TYPE", "kiralik")  # kiralik | satilik
MAX_PAGES       = int(os.getenv("HEPSIEMLAK_MAX_PAGES", "8"))
OUT_PATH        = Path("data") / "listings_hepsiemlak.json"
DELAY_MIN       = 2.0   # saniye
DELAY_MAX       = 4.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

BASE_URL = "https://www.hepsiemlak.com"


# ── Yardımcı fonksiyonlar ─────────────────────────────────────────────────────

def clean_price(raw: str) -> int | None:
    """'2.450.000 TL' veya '12.500 TL/ay' → int"""
    if not raw:
        return None
    digits = re.sub(r"[^\d]", "", raw.split("TL")[0].split("/")[0])
    return int(digits) if digits else None


def clean_m2(raw: str) -> int | None:
    """'130 m²' veya '130m2' → int"""
    if not raw:
        return None
    m = re.search(r"(\d+)", raw.replace(".", ""))
    return int(m.group(1)) if m else None


def normalize_rooms(raw: str) -> str | None:
    """'3+1', '3 + 1', 'Stüdyo' gibi → standart format"""
    if not raw:
        return None
    raw = raw.strip()
    m = re.search(r"(\d)\s*\+\s*1", raw)
    if m:
        return f"{m.group(1)}+1"
    if "stüdyo" in raw.lower():
        return "1+0"
    return raw


def district_from_location(location: str) -> str | None:
    """'Kadıköy / Kozyatağı' → 'Kadıköy'"""
    if not location:
        return None
    parts = [p.strip() for p in location.split("/")]
    return parts[0] if parts else None


def neighborhood_from_location(location: str) -> str | None:
    parts = [p.strip() for p in (location or "").split("/")]
    return parts[1] if len(parts) > 1 else None


# ── __NEXT_DATA__ parse stratejisi ────────────────────────────────────────────

def parse_nextdata(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """__NEXT_DATA__ JSON bloğunu parse eder, ilan listesini döner."""
    tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not tag:
        return []

    try:
        data = json.loads(tag.string)
    except Exception as e:
        print(f"  [!] __NEXT_DATA__ parse hatası: {e}")
        return []

    # Ağaç içinde ilan listesini bul: pageProps → birkaç olası konum
    props = data.get("props", {}).get("pageProps", {})

    listings_raw = (
        props.get("listings")
        or props.get("data", {}).get("listings")
        or props.get("searchResult", {}).get("listings")
        or props.get("result", {}).get("listings")
        or []
    )

    # Bazen tek bir "items" altında gelir
    if not listings_raw:
        for key in ("items", "results", "listingList", "housingList"):
            candidate = props.get(key) or props.get("data", {}).get(key, [])
            if candidate:
                listings_raw = candidate
                break

    if not listings_raw:
        print(f"  [!] __NEXT_DATA__ içinde listings bulunamadı (keys: {list(props.keys())})")
        return []

    results = []
    for item in listings_raw:
        try:
            raw_loc   = item.get("location") or item.get("locationName") or ""
            raw_price = item.get("price") or item.get("formattedPrice") or ""
            raw_m2    = item.get("squareMeter") or item.get("usableSquareMeter") or ""
            raw_rooms = item.get("roomCount") or item.get("room") or ""
            listing_id = str(item.get("id") or item.get("listingId") or "")
            title     = item.get("title") or item.get("name") or ""
            url_path  = item.get("detailUrl") or item.get("url") or ""
            features_raw = item.get("features") or item.get("attributes") or []
            if isinstance(features_raw, dict):
                features_raw = list(features_raw.values())

            results.append({
                "listing_id":       listing_id,
                "title":            title,
                "district":         district_from_location(raw_loc),
                "neighborhood":     neighborhood_from_location(raw_loc),
                "rooms":            normalize_rooms(str(raw_rooms)),
                "gross_m2":         clean_m2(str(raw_m2)),
                "price_try":        clean_price(str(raw_price)),
                "building_age":     item.get("buildingAge") or item.get("age"),
                "floor":            item.get("floor") or item.get("floorNumber"),
                "features":         [str(f) for f in features_raw[:8]],
                "description":      item.get("description") or "",
                "description_clean": item.get("description") or "",
                "source_url":       BASE_URL + url_path if url_path.startswith("/") else url_path,
                "scraped_at":       datetime.now().isoformat(timespec="seconds"),
            })
        except Exception as ex:
            print(f"  [!] İlan parse hatası: {ex}")
            continue

    return results


# ── HTML kart parse stratejisi (fallback) ────────────────────────────────────

def parse_html_cards(soup: BeautifulSoup, page_url: str) -> list[dict]:
    """__NEXT_DATA__ yoksa HTML kartlarını parse etmeyi dener."""
    # Hepsiemlak'ta ilan kartı seçiciler (yıla göre değişebilir)
    selectors = [
        "li.listing-item",
        "li[data-v-id]",
        "div.list-view-content",
        "article.hs-listing-card",
    ]
    cards = []
    for sel in selectors:
        cards = soup.select(sel)
        if cards:
            print(f"  [i] HTML kart seçici: '{sel}' → {len(cards)} kart")
            break

    if not cards:
        print("  [!] HTML kartı bulunamadı")
        return []

    results = []
    for c in cards:
        try:
            title_el  = c.select_one("h3, .title, [class*='title']")
            price_el  = c.select_one(".price, [class*='price']")
            m2_el     = c.select_one("[class*='squaremeter'], [class*='m2'], [class*='m²']")
            rooms_el  = c.select_one("[class*='room'], [class*='oda']")
            loc_el    = c.select_one("[class*='location'], [class*='district']")
            link_el   = c.select_one("a[href]")

            title  = title_el.get_text(strip=True) if title_el else ""
            price  = clean_price(price_el.get_text(strip=True) if price_el else "")
            m2     = clean_m2(m2_el.get_text(strip=True) if m2_el else "")
            rooms  = normalize_rooms(rooms_el.get_text(strip=True) if rooms_el else "")
            loc    = loc_el.get_text(strip=True).replace("\n", " / ") if loc_el else ""
            href   = link_el["href"] if link_el else ""
            lid    = re.sub(r"[^0-9]", "", href)[-10:] or str(random.randint(10000, 99999))

            if not title:
                continue

            results.append({
                "listing_id":        lid,
                "title":             title,
                "district":          district_from_location(loc),
                "neighborhood":      neighborhood_from_location(loc),
                "rooms":             rooms,
                "gross_m2":          m2,
                "price_try":         price,
                "building_age":      None,
                "floor":             None,
                "features":          [],
                "description":       "",
                "description_clean": "",
                "source_url":        BASE_URL + href if href.startswith("/") else href,
                "scraped_at":        datetime.now().isoformat(timespec="seconds"),
            })
        except Exception as ex:
            print(f"  [!] Kart parse hatası: {ex}")
            continue

    return results


# ── Sayfa çekici ──────────────────────────────────────────────────────────────

def fetch_page(session: requests.Session, page_num: int) -> list[dict]:
    """Tek bir liste sayfasını çek ve parse et."""
    # Hepsiemlak paginasyon parametresi: ?page=N (1-tabanlı)
    params: dict[str, str | int] = {}
    if LISTING_TYPE == "kiralik":
        base_path = f"/{CITY}-kiralik-daire"
    else:
        base_path = f"/{CITY}-satilik-daire"

    if page_num > 1:
        params["page"] = page_num

    url = BASE_URL + base_path
    print(f"  → GET {url}  page={page_num} ...", end=" ", flush=True)

    try:
        resp = session.get(url, params=params, headers=HEADERS, timeout=25)
        print(f"HTTP {resp.status_code}")
        if resp.status_code != 200:
            print(f"  [!] Atlandı (status {resp.status_code})")
            return []
    except Exception as e:
        print(f"\n  [!] Bağlantı hatası: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    listings = parse_nextdata(soup, url)
    if listings:
        print(f"     __NEXT_DATA__ → {len(listings)} ilan")
        return listings

    listings = parse_html_cards(soup, url)
    if listings:
        return listings

    return []


# ── Detay sayfa çekici ──────────────────────────────────────────────────────────

def fetch_detail(session: requests.Session, url: str) -> dict:
    """İlan detay sayfasından açıklama ve özellikleri çeker."""
    print(f"    ↳ Detay çekiliyor: {url} ...", end=" ", flush=True)
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            print(f"Hata ({resp.status_code})")
            return {}
        
        print("OK")
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find("script", {"id": "__NEXT_DATA__"})
        
        desc = ""
        feats = []
        
        if tag:
            try:
                data = json.loads(tag.string)
                props = data.get("props", {}).get("pageProps", {})
                listing = props.get("listingData") or props.get("data") or {}
                
                # Açıklama
                desc = listing.get("description") or ""
                
                # Özellikler (Categorized features)
                categories = listing.get("featureCategories") or []
                for cat in categories:
                    f_list = cat.get("features") or []
                    for f in f_list:
                        if isinstance(f, dict):
                            fname = f.get("name")
                            if fname: feats.append(fname)
                        else:
                            feats.append(str(f))
            except:
                pass
        
        # Fallback (HTML selector)
        if not desc:
            desc_el = soup.select_one(".description-content, .description-text, [class*='description']")
            if desc_el:
                desc = desc_el.get_text(strip=True)
        
        # description_clean (HTML tag temizliği)
        clean_desc = re.sub(r"<[^>]+>", "", desc)
        clean_desc = " ".join(clean_desc.split())

        return {
            "description": desc,
            "description_clean": clean_desc,
            "features": list(set(feats)) if feats else []
        }
    except Exception as e:
        print(f"Hata: {e}")
        return {}


# ── Ana akış ─────────────────────────────────────────────────────────────────

def main():
    Out_path = Path(OUT_PATH)
    Out_path.parent.mkdir(exist_ok=True, parents=True)

    all_listings: list[dict] = []
    seen_ids: set[str] = set()

    session = requests.Session()

    print(f"\n[Hepsiemlak Fetcher - Detaylı Mod]")
    print(f"  Şehir       : {CITY}")
    print(f"  Tip         : {LISTING_TYPE}")
    print(f"  Max sayfa   : {MAX_PAGES}")
    print(f"  Çıktı       : {Out_path}\n")

    for page in range(1, MAX_PAGES + 1):
        items = fetch_page(session, page)

        if not items:
            # Sayfa boş veya 403 döndü
            if page == 1:
                print("\n[!] Hepsiemlak erişimi engelledi (HTTP 403) veya hiç ilan bulunamadı.")
                print("    → Site şu an requests erişimine izin vermiyor.")
                print("    → Eğer elinizde 'data/listings_live.json' varsa enrich_hepsiemlak_details.py ile devam edebilirsiniz.")
            else:
                print(f"  [i] Sayfa {page} boş veya engelli → duruyoruz.")
            break

        new_count = 0
        for item in items:
            lid = item["listing_id"] or str(random.randint(100_000, 999_999))
            item["listing_id"] = lid
            if lid not in seen_ids:
                seen_ids.add(lid)
                all_listings.append(item)
                new_count += 1

        print(f"  ✓ Sayfa {page}: +{new_count} yeni ilan (toplam: {len(all_listings)})")

        if page < MAX_PAGES:
            sleep_sec = random.uniform(DELAY_MIN, DELAY_MAX)
            print(f"  ⏳ {sleep_sec:.1f}s bekleniyor...")
            time.sleep(sleep_sec)

    if not all_listings:
        return

    Out_path.write_text(
        json.dumps(all_listings, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    
    print("\n" + "="*30)
    print("HEPSIEMLAK FETCH RAPORU")
    print("="*30)
    print(f"Toplam İlan        : {len(all_listings)}")
    print(f"Kaydedilen Dosya   : {Out_path}")
    print("="*30)
    print("Bir sonraki adım: python scripts/enrich_hepsiemlak_details.py")


if __name__ == "__main__":
    main()
