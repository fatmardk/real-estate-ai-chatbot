import json
from pathlib import Path

# -- Ayarlar --
IN_FILE = Path("data") / "listings_normalized.json"
OUT_FILE = Path("data") / "listings_clean.json"

# -- İlan dışı (junk) URL kelimeleri --
JUNK_KEYWORDS = [
    "/fiyat-bilgisi/", "/emlak-endeksi/", "/haberler/", 
    "/kayit/", "/giris/", "emlakjet.com/projeler", 
    "hepsiemlak.com/emlak-yasam"
]

def is_valid_url(url: str) -> bool:
    if not url: return False
    url_lower = url.lower()
    for kw in JUNK_KEYWORDS:
        if kw in url_lower: return False
    return True

def main():
    if not IN_FILE.exists():
        print(f"[!] {IN_FILE} bulunamadı. Önce normalize_listings.py çalıştırın.")
        return

    raw_listings = json.loads(IN_FILE.read_text(encoding="utf-8"))
    print(f"\n[Cleaning Başladı] {len(raw_listings)} kayıt inceleniyor...")

    clean_listings = []
    
    stats = {
        "total": len(raw_listings),
        "clean": 0,
        "with_desc": 0,
        "valid_price": 0,
        "valid_m2": 0,
        "valid_url": 0
    }

    for item in raw_listings:
        item = enrich_item_from_text(item)
        # 1. URL Kontrolü
        if not is_valid_url(item.get("source_url")):
            continue
        stats["valid_url"] += 1

        # 2. Kritik Veri Kontrolü (Boş olmamalı)
        price = item.get("price_try")
        m2 = item.get("gross_m2")
        rooms = item.get("rooms")
        
        has_price = (price is not None and price > 0)
        has_m2 = (m2 is not None and m2 > 0)
        has_rooms = (rooms and rooms != "unknown")

        if has_price: stats["valid_price"] += 1
        if has_m2: stats["valid_m2"] += 1

        # Filtreleme: Fiyat veya M2 veya Oda bilgisi olmayan çöp verileri atalım
        if not (has_price and (has_m2 or has_rooms)):
            continue
            
        # 3. Açıklama Kontrolü (Kalite için, ama kaydı atmıyoruz)
        if item.get("description_clean") and len(item["description_clean"]) > 10:
            stats["with_desc"] += 1

        clean_listings.append(item)
        stats["clean"] += 1

    OUT_FILE.write_text(json.dumps(clean_listings, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "="*30)
    print("TEMİZLİK VE KALİTE RAPORU")
    print("="*30)
    print(f"Toplam Ham Kayıt      : {stats['total']}")
    print(f"Geçerli İlan URL'si   : {stats['valid_url']}")
    print(f"Fiyatı Dolu Kayıt     : {stats['valid_price']}")
    print(f"m²'si Dolu Kayıt      : {stats['valid_m2']}")
    print(f"Açıklaması Dolu Kayıt : {stats['with_desc']}")
    print("-"*30)
    print(f"TEMİZ/HAZIR İLAN      : {stats['clean']}")
    print("="*30)
    print(f"Sonuç kaydedildi      : {OUT_FILE}")

if __name__ == "__main__":
    main()
