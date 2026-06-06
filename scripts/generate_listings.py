import json
import random
from datetime import datetime, timedelta
from pathlib import Path

DISTRICTS = {
    "Kadıköy": ["Kozyatağı", "Bostancı", "Fenerbahçe", "Erenköy", "Suadiye", "Göztepe", "Caddebostan"],
    "Beşiktaş": ["Levent", "Etiler", "Akatlar", "Bebek", "Ortaköy", "Gayrettepe", "Dikilitaş"],
    "Şişli": ["Mecidiyeköy", "Nişantaşı", "Esentepe", "Fulya", "Bomonti", "Okmeydanı"],
    "Üsküdar": ["Altunizade", "Çengelköy", "Kuzguncuk", "Acıbadem", "Ünalan"],
    "Ataşehir": ["Küçükbakkalköy", "İçerenköy", "Barbaros", "Yenişehir", "Kayışdağı"],
    "Bakırköy": ["Ataköy", "Yeşilköy", "Yeşilyurt", "Zeytinlik"],
    "Maltepe": ["Cevizli", "Altayçeşme", "İdealtepe", "Zümrütevler"],
}

ROOMS = ["1+1", "2+1", "3+1", "4+1"]
FEATURE_POOL = [
    "balkon", "site", "metroya yakın", "otopark", "güvenlik", "asansör", "eşyalı",
    "deniz manzarası", "ara kat", "yüksek giriş", "kapalı mutfak", "ebeveyn banyosu",
    "ısı yalıtımı", "doğalgaz", "klima", "fiber internet"
]

TITLE_TEMPLATES = [
    "{district} {neighborhood} {rooms}, {m2}m², {feat1}, {feat2}",
    "{district} {neighborhood}'da {rooms} {m2}m², {feat1} - {feat2}",
    "{district} {neighborhood} {rooms} daire, {m2}m², {feat1}",
]

DESC_TEMPLATES = [
    "{district} {neighborhood} bölgesinde, {rooms} planlı {m2}m² daire. {feat1} ve {feat2} avantajlarıyla öne çıkar. Ulaşıma yakın, günlük yaşam için uygun.",
    "{rooms} dairemiz {district} {neighborhood}'da yer alır. {m2}m² kullanım alanı, {feat1} ve {feat2} özellikleri mevcuttur. Detaylı bilgi için iletişime geçiniz.",
    "{district} {neighborhood} konumunda {rooms} {m2}m². {feat1}, {feat2}. Evin genel durumu iyi, taşınmaya uygundur.",
]

def price_for(district: str, rooms: str, m2: int) -> int:
    base = {
        "Kadıköy": 26000,
        "Beşiktaş": 28000,
        "Şişli": 24000,
        "Üsküdar": 22000,
        "Ataşehir": 21000,
        "Bakırköy": 23000,
        "Maltepe": 18000,
    }.get(district, 20000)

    rooms_mul = {"1+1": 0.95, "2+1": 1.0, "3+1": 1.08, "4+1": 1.15}[rooms]
    noise = random.uniform(0.92, 1.12)

    p = int(base * m2 * rooms_mul * noise)
    p = int(round(p / 5000) * 5000)
    return max(p, 900000)

def make_listing(i: int) -> dict:
    district = random.choice(list(DISTRICTS.keys()))
    neighborhood = random.choice(DISTRICTS[district])
    rooms = random.choices(ROOMS, weights=[20, 35, 30, 15], k=1)[0]

    m2_min = {"1+1": 45, "2+1": 70, "3+1": 95, "4+1": 120}[rooms]
    m2_max = {"1+1": 75, "2+1": 110, "3+1": 145, "4+1": 200}[rooms]
    m2 = random.randint(m2_min, m2_max)

    feats = random.sample(FEATURE_POOL, k=random.randint(3, 6))
    title_tpl = random.choice(TITLE_TEMPLATES)
    desc_tpl = random.choice(DESC_TEMPLATES)

    title = title_tpl.format(
        district=district, neighborhood=neighborhood, rooms=rooms, m2=m2,
        feat1=feats[0], feat2=feats[1]
    )
    description = desc_tpl.format(
        district=district, neighborhood=neighborhood, rooms=rooms, m2=m2,
        feat1=feats[0], feat2=feats[1]
    )

    building_age = random.choice(["0-5", "6-10", "11-15", "16-20", "21+"])
    floor = random.choice(["1", "2", "3", "4", "5+", "yüksek giriş", "bahçe katı"])
    price_try = price_for(district, rooms, m2)

    scraped_at = (datetime.now() - timedelta(minutes=random.randint(0, 60 * 24))).isoformat(timespec="seconds")
    source_url = f"https://example.com/listing/{district.lower()}-{neighborhood.lower()}-{i}"

    return {
        "listing_id": f"L{i}",
        "title": title,
        "district": district,
        "neighborhood": neighborhood,
        "rooms": rooms,
        "gross_m2": m2,
        "price_try": price_try,
        "building_age": building_age,
        "floor": floor,
        "features": feats,
        "description": description,
        "description_clean": description,
        "source_url": source_url,
        "scraped_at": scraped_at,
    }

def main():
    out_dir = Path("data")
    out_dir.mkdir(exist_ok=True, parents=True)

    n = int(input("Kaç ilan üretelim? (örn 500): ").strip() or "500")
    listings = [make_listing(i + 1) for i in range(n)]

    out_path = out_dir / "listings_generated.json"
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(listings, f, ensure_ascii=False, indent=2)

    print(f"OK: {n} ilan üretildi -> {out_path}")

if __name__ == "__main__":
    random.seed(42)
    main()
