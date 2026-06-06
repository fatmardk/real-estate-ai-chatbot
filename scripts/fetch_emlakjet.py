import json
import re
import os
import time
import random
from datetime import datetime
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# -- Ayarlar --
BASE_URL = "https://www.emlakjet.com"
OUT_PATH = Path("data") / "listings_emlakjet.json"

MAX_PAGES = int(os.getenv("EMLAKJET_MAX_PAGES", "5"))

DISTRICT_ALIASES = {
    "Kadıköy": ["kadıköy", "kadikoy", "kozyatağı", "kozyatagi", "bostancı", "bostanci", "fenerbahçe", "fenerbahce", "erenköy", "erenkoy", "suadiye", "göztepe", "goztepe", "caddebostan"],
    "Şişli": ["şişli", "sisli", "mecidiyeköy", "mecidiyekoy", "nişantaşı", "nisantasi", "bomonti", "fulya", "okmeydanı", "okmeydani"],
    "Beşiktaş": ["beşiktaş", "besiktas", "levent", "etiler", "bebek", "ortaköy", "ortakoy", "gayrettepe", "akaretler", "dikilitaş", "dikilitas"],
    "Üsküdar": ["üsküdar", "uskudar", "altunizade", "çengelköy", "cengelkoy", "kuzguncuk", "acıbadem", "acibadem", "ünalan", "unalan"],
    "Ataşehir": ["ataşehir", "atasehir", "içerenköy", "icerenkoy", "küçükbakkalköy", "kucukbakkalkoy", "barbaros", "yenişehir", "yenisehir", "kayışdağı", "kayisdagi"],
    "Bakırköy": ["bakırköy", "bakirkoy", "ataköy", "atakoy", "yeşilköy", "yesilkoy", "yeşilyurt", "yesilyurt", "zeytinlik"],
    "Maltepe": ["maltepe", "cevizli", "altayçeşme", "altaycesme", "idealtepe", "zümrütevler", "zumrutevler"],
    "Beylikdüzü": ["beylikdüzü", "beylikduzu", "cumhuriyet", "yakuplu", "adnan kahveci"],
    "Esenyurt": ["esenyurt", "kıraç", "kirac", "sultaniye", "güzelyurt", "guzelyurt", "haramidere"],
    "Avcılar": ["avcılar", "avcilar", "gümüşpala", "gumuspala", "firuzköy", "firuzkoy"],
    "Pendik": ["pendik", "kurtköy", "kurtkoy", "esenyalı", "esenyali", "harmandere"],
    "Kartal": ["kartal", "kartaltepe", "soğanlık", "soganlik"],
    "Kağıthane": ["kağıthane", "kagithane", "çağlayan", "caglayan", "gültepe", "gultepe"],
    "Eyüpsultan": ["eyüpsultan", "eyupsultan", "çırçır", "circir"],
    "Sultanbeyli": ["sultanbeyli", "mehmet akif"],
    "Büyükçekmece": ["büyükçekmece", "buyukcekmece", "celaliye"],
    "Bahçelievler": ["bahçelievler", "bahcelievler", "yenibosna", "çobançeşme", "cobancesme"],
    "Küçükçekmece": ["küçükçekmece", "kucukcekmece", "halkalı", "halkali", "sefaköy", "sefakoy"],
    "Bağcılar": ["bağcılar", "bagcilar"],
    "Fatih": ["fatih", "cerrahpaşa", "cerrahpasa"],
}

FEATURE_KEYWORDS = {
    "metro": ["metro", "metroya yakın"],
    "metrobüs": ["metrobüs", "metrobus", "e-5"],
    "balkon": ["balkon", "balkonlu"],
    "site": ["site", "site içi", "site içerisinde"],
    "otopark": ["otopark"],
    "asansör": ["asansör", "asansorlu", "asansörlü"],
    "krediye uygun": ["krediye uygun", "kredi"],
    "sıfır": ["sıfır", "yeni bina"],
    "ara kat": ["ara kat", "arakat"],
    "yüksek giriş": ["yüksek giriş"],
    "bahçe katı": ["bahçe katı"],
    "lüks": ["lüks", "lux", "luxe"],
    "dubleks": ["dubleks"],
}

def infer_district(item: dict) -> str:
    current = item.get("district")

    # Zaten İstanbul dışında temiz ilçe varsa dokunma
    if current and current not in ["İstanbul", "unknown", "Bilinmiyor", None]:
        return current

    text = " ".join([
        str(item.get("title") or ""),
        str(item.get("description") or ""),
        str(item.get("description_clean") or ""),
        str(item.get("source_url") or ""),
    ]).lower()

    for district, aliases in DISTRICT_ALIASES.items():
        for alias in aliases:
            if alias in text:
                return district

    return current or "Bilinmiyor"

def enrich_features_from_text(item: dict) -> list:
    existing = item.get("features") or []
    features = set(str(x).strip() for x in existing if str(x).strip())

    text = " ".join([
        str(item.get("title") or ""),
        str(item.get("description") or ""),
        str(item.get("description_clean") or ""),
        str(item.get("source_url") or ""),
    ]).lower()

    for feature, aliases in FEATURE_KEYWORDS.items():
        if any(alias in text for alias in aliases):
            features.add(feature)

    return sorted(features)

def enrich_item_from_text(item: dict) -> dict:
    item["district"] = infer_district(item)
    item["features"] = enrich_features_from_text(item)

    if not item.get("description_clean"):
        feats = ", ".join(item.get("features") or [])
        item["description_clean"] = " | ".join([
            str(item.get("title") or ""),
            f"İlçe: {item.get('district') or 'Bilinmiyor'}",
            f"Oda: {item.get('rooms') or 'Bilinmiyor'}",
            f"Özellikler: {feats}" if feats else "",
        ]).strip(" |")

    return item

def build_page_urls(district_slug: str, page: int) -> list[str]:
    base = f"{BASE_URL}/satilik-daire/{district_slug}"

    if page == 1:
        return [base]

    # Emlakjet sayfalama yapısı değişebildiği için iki formatı da deniyoruz.
    return [
        f"{base}/{page}/",
        f"{base}?page={page}",
    ]


def main():
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    print("\n[Emlakjet Fetcher - Çoklu İlçe/Sayfa Modu]")
    print(f"  İlçe sayısı : {len(DISTRICT_SLUGS)}")
    print(f"  Max sayfa   : {MAX_PAGES}")
    print(f"  Çıktı       : {OUT_PATH}")

    session = requests.Session()
    seen_urls = set()
    all_items = []

    for district_slug in DISTRICT_SLUGS:
        print(f"\n[İlçe] {district_slug}")

        for page in range(1, MAX_PAGES + 1):
            page_items = []

            for url in build_page_urls(district_slug, page):
                print(f"  → GET {url} ...", end=" ", flush=True)

                try:
                    resp = session.get(url, headers=HEADERS, timeout=25)
                    print(f"HTTP {resp.status_code}")

                    if resp.status_code != 200:
                        continue

                    items = parse_page(resp.text, district_slug, seen_urls)

                    if items:
                        page_items = items
                        break

                except Exception as e:
                    print(f"Hata: {e}")

            if not page_items:
                print(f"  [i] Sayfa {page} boş veya aynı ilanlar geldi, bu ilçe için duruyoruz.")
                break

            all_items.extend(page_items)
            print(f"  ✓ Sayfa {page}: +{len(page_items)} ilan | Toplam: {len(all_items)}")

            # Ara kayıt
            OUT_PATH.write_text(
                json.dumps(all_items, ensure_ascii=False, indent=2),
                encoding="utf-8"
            )

            time.sleep(random.uniform(1.5, 3.0))

    OUT_PATH.write_text(
        json.dumps(all_items, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    print("\n" + "=" * 30)
    print("EMLAKJET FETCH RAPORU")
    print("=" * 30)
    print(f"Toplam İlan      : {len(all_items)}")
    print(f"Kaydedilen Dosya : {OUT_PATH}")
    print("=" * 30)
    print("Bir sonraki adım: python scripts/enrich_emlakjet_details.py")
if __name__ == "__main__":
    main()
