import json
import os
import re
import time
import random
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# -- Ayarlar --
IN_FILE = Path("data") / "listings_emlakjet.json"
OUT_FILE = Path("data") / "listings_emlakjet_enriched.json"
DELAY_MIN = 1.5
DELAY_MAX = 3.0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
}

def fetch_detail(session: requests.Session, url: str) -> dict:
    """Emlakjet ilan detay sayfasından açıklama ve özellikleri çeker."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return {}
        
        soup = BeautifulSoup(resp.text, "html.parser")
        
        # 1) Açıklama
        desc = ""
        # Emlakjet'te genelde id="description" veya h2 altındaki div
        desc_el = soup.find("div", {"id": "description"}) or soup.select_one(".listing-description, [class*='description']")
        if desc_el:
            desc = desc_el.get_text(" ", strip=True)
            
        # 2) Özellikler
        feats = []
        # Detay tablosundaki özellikler
        feat_els = soup.select(".listing-feature-item, [class*='feature-item']")
        for el in feat_els:
            f = el.get_text(strip=True)
            if f: feats.append(f)
            
        # 3) description_clean
        clean_desc = re.sub(r"<[^>]+>", "", desc)
        clean_desc = " ".join(clean_desc.split())

        return {
            "description": desc,
            "description_clean": clean_desc,
            "features": list(set(feats)) if feats else []
        }
    except:
        return {}

def main():
    if not IN_FILE.exists():
        print(f"[!] {IN_FILE} bulunamadı. Önce fetch_emlakjet.py çalıştırın.")
        return

    listings = json.loads(IN_FILE.read_text(encoding="utf-8"))
    print(f"\n[Emlakjet Enrichment] {len(listings)} ilan işlenecek...")

    session = requests.Session()
    stats = {"missing_url": 0, "success": 0, "empty_desc": 0, "total": len(listings)}

    for i, item in enumerate(listings):
        url = item.get("source_url")
        if not url:
            stats["missing_url"] += 1
            continue

        print(f"  [{i+1}/{len(listings)}] {url} ...", end=" ", flush=True)
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        
        detail = fetch_detail(session, url)
        
        if detail:
            item["description"] = detail["description"]
            item["description_clean"] = detail["description_clean"]
            if detail["features"]:
                item["features"] = detail["features"]
            
            if not item.get("description_clean"):
                stats["empty_desc"] += 1
            else:
                stats["success"] += 1
            print("OK")
        else:
            stats["empty_desc"] += 1
            print("Hata")

        if (i+1) % 5 == 0:
            OUT_FILE.write_text(json.dumps(listings, ensure_ascii=False, indent=2), encoding="utf-8")

    OUT_FILE.write_text(json.dumps(listings, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "="*30)
    print("EMLAKJET ENRICH RAPORU")
    print("="*30)
    print(f"Toplam İlan          : {stats['total']}")
    print(f"Başarılı             : {stats['success']}")
    print(f"Açıklaması Boş Kalan : {stats['empty_desc']}")
    print(f"URL'si Olmayan       : {stats['missing_url']}")
    print("="*30)

if __name__ == "__main__":
    main()
