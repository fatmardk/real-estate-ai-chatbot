import json
import os
import re
import time
import random
from pathlib import Path
from datetime import datetime
import requests
from bs4 import BeautifulSoup

# -- Ayarlar --
IN_FILE = Path("data") / "listings_hepsiemlak.json"
OUT_FILE = Path("data") / "listings_hepsiemlak_enriched.json"
DELAY_MIN = 2.0
DELAY_MAX = 4.5

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def fetch_detail(session: requests.Session, url: str) -> dict:
    """İlan detay sayfasından açıklama ve özellikleri çeker."""
    try:
        resp = session.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return {}
        
        soup = BeautifulSoup(resp.text, "html.parser")
        tag = soup.find("script", {"id": "__NEXT_DATA__"})
        
        desc = ""
        feats = []
        
        if tag:
            try:
                data = json.loads(tag.string)
                props = data.get("props", {}).get("pageProps", {})
                listing = props.get("listingData") or props.get("data") or {}
                
                desc = listing.get("description") or ""
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
        
        if not desc:
            desc_el = soup.select_one(".description-content, .description-text, [class*='description']")
            if desc_el:
                desc = desc_el.get_text(strip=True)
        
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
        print(f"[!] {IN_FILE} bulunamadı. Önce fetch_hepsiemlak.py çalıştırın.")
        return

    listings = json.loads(IN_FILE.read_text(encoding="utf-8"))
    print(f"\n[Enrichment Başladı] {len(listings)} ilan işlenecek...")

    session = requests.Session()
    stats = {
        "missing_url": 0,
        "success": 0,
        "empty_desc": 0,
        "total": len(listings)
    }

    for i, item in enumerate(listings):
        url = item.get("source_url")
        if not url:
            stats["missing_url"] += 1
            continue

        print(f"  [{i+1}/{len(listings)}] {url} ...", end=" ", flush=True)
        
        # Rate limiting
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
            print("Hata veya Boş")

        # Her 5 ilanda bir ara kaydet (Crash safe)
        if (i + 1) % 5 == 0:
            OUT_FILE.write_text(json.dumps(listings, ensure_ascii=False, indent=2), encoding="utf-8")

    OUT_FILE.write_text(json.dumps(listings, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "="*30)
    print("ZENGİNLEŞTİRME RAPORU")
    print("="*30)
    print(f"Toplam İlan          : {stats['total']}")
    print(f"Başarılı             : {stats['success']}")
    print(f"Açıklaması Boş Kalan : {stats['empty_desc']}")
    print(f"URL'si Olmayan       : {stats['missing_url']}")
    print("="*30)
    print(f"Sonuç kaydedildi: {OUT_FILE}")

if __name__ == "__main__":
    main()
