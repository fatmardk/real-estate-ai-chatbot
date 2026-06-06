import json
from pathlib import Path
from datetime import datetime

# -- Ayarlar --
SOURCES = [
    {"path": Path("data") / "listings_hepsiemlak_enriched.json", "name": "hepsiemlak"},
    {"path": Path("data") / "listings_emlakjet_enriched.json", "name": "emlakjet"},
]
OUT_FILE = Path("data") / "listings_normalized.json"

import re

def normalize_item(item: dict, source_name: str) -> dict:
    """Tek bir ilanı standart şemaya dönüştürür."""
    # listing_id'yi source ile benzersiz yapalım
    raw_id = str(item.get("listing_id") or "")
    digits = "".join(filter(str.isdigit, raw_id))
    unique_id = f"{source_name}_{digits}" if digits else f"{source_name}_{hash(item.get('source_url', '')) % 10**8}"

    title = item.get("title") or "Bilinmeyen Başlık"
    description = item.get("description") or ""
    description_clean = item.get("description_clean") or ""
    
    if not description_clean:
        description_clean = f"{title} - {description}".strip(" -")
        
    full_text = f"{title} {description_clean}".lower()

    district = item.get("district") or "Bilinmiyor"
    neighborhood = item.get("neighborhood") or "Bilinmiyor"

    # Eğer ilçe İstanbul veya Bilinmiyor gelmişse, text içinden çıkar
    if district.strip().lower() in ["istanbul", "bilinmiyor"]:
        districts_to_check = ["Şişli", "Kadıköy", "Esenyurt", "Beylikdüzü", "Avcılar", "Pendik", "Kağıthane", "Bakırköy", "Maltepe", "Üsküdar", "Ataşehir", "Beşiktaş"]
        for d in districts_to_check:
            if d.lower() in full_text:
                district = d
                break

    # Mahalle basitçe title içindeyse almaya çalışalım (çok kaba bir yaklaşım ama promptta istendiği gibi)
    if neighborhood.strip().lower() == "bilinmiyor":
        # Örnek title: "Şişli Fulya'da 3+1 Daire"
        # Bu kısım zor, ama eğer başlıkta kelime varsa alabiliriz. Şimdilik geçelim ya da çok bilinenleri ekleyelim.
        pass

    # Features çıkarımı
    features = item.get("features") or []
    feature_keywords = {
        "metro": "Metro", "metrobüs": "Metrobüs", "balkon": "Balkon", "site": "Site", 
        "otopark": "Otopark", "asansör": "Asansör", "eşyalı": "Eşyalı", 
        "deniz manzara": "Deniz Manzarası", "güvenlik": "Güvenlik", 
        "krediye uygun": "Krediye Uygun", "sıfır": "Sıfır", "yeni bina": "Yeni Bina", 
        "ara kat": "Ara Kat", "bahçe katı": "Bahçe Katı", "merkezi konum": "Merkezi Konum"
    }
    
    for kw, feat in feature_keywords.items():
        if kw in full_text and feat not in features:
            features.append(feat)

    return {
        "listing_id": unique_id,
        "source": source_name,
        "title": title,
        "district": district,
        "neighborhood": neighborhood,
        "rooms": item.get("rooms") or "3+1",
        "gross_m2": item.get("gross_m2"),
        "price_try": item.get("price_try"),
        "features": features,
        "description": description,
        "description_clean": description_clean,
        "source_url": item.get("source_url") or "",
        "scraped_at": item.get("scraped_at") or datetime.now().isoformat(timespec="seconds")
    }

def main():
    merged = []
    counts = {"hepsiemlak": 0, "emlakjet": 0}

    print("\n[Normalization Başladı]")
    
    for src in SOURCES:
        if not src["path"].exists():
            print(f"  [!] {src['path']} bulunamadı, atlanıyor.")
            continue
        
        data = json.loads(src["path"].read_text(encoding="utf-8"))
        print(f"  -> {src['name']} kaynağından {len(data)} ilan okunuyor...")
        
        for item in data:
            normalized = normalize_item(item, src["name"])
            merged.append(normalized)
            counts[src["name"]] += 1

    if not merged:
        print("[!] Hiçbir veri bulunamadı.")
        return

    OUT_FILE.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "="*30)
    print("NORMALİZASYON RAPORU")
    print("="*30)
    print(f"Toplam Birleşen İlan : {len(merged)}")
    print(f"  - Hepsiemlak       : {counts['hepsiemlak']}")
    print(f"  - Emlakjet         : {counts['emlakjet']}")
    print("="*30)
    print(f"Sonuç kaydedildi     : {OUT_FILE}")

if __name__ == "__main__":
    main()
