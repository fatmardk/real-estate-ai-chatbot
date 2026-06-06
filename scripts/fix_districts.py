import json
import re
from pathlib import Path
from collections import Counter

IN_FILE = Path("data") / "listings_clean.json"
OUT_FILE = Path("data") / "listings_clean.json"

DISTRICT_ALIASES = {
    "Kadıköy": ["kadıköy", "kadikoy", "kozyatağı", "kozyatagi", "bostancı", "bostanci", "fenerbahçe", "fenerbahce", "erenköy", "erenkoy", "suadiye", "göztepe", "goztepe", "caddebostan"],
    "Şişli": ["şişli", "sisli", "mecidiyeköy", "mecidiyekoy", "nişantaşı", "nisantasi", "bomonti", "fulya", "okmeydanı", "okmeydani"],
    "Beşiktaş": ["beşiktaş", "besiktas", "levent", "etiler", "bebek", "ortaköy", "ortakoy", "gayrettepe", "akaretler", "dikilitaş", "dikilitas"],
    "Üsküdar": ["üsküdar", "uskudar", "altunizade", "çengelköy", "cengelkoy", "kuzguncuk", "acıbadem", "acibadem", "ünalan", "unalan"],
    "Ataşehir": ["ataşehir", "atasehir", "içerenköy", "icerenkoy", "küçükbakkalköy", "kucukbakkalkoy", "barbaros", "yenişehir", "yenisehir", "kayışdağı", "kayisdagi"],
    "Bakırköy": ["bakırköy", "bakirkoy", "ataköy", "atakoy", "yeşilköy", "yesilkoy", "yeşilyurt", "yesilyurt", "zeytinlik"],
    "Maltepe": ["maltepe", "cevizli", "altayçeşme", "altaycesme", "idealtepe", "zümrütevler", "zumrutevler"],
    "Beylikdüzü": ["beylikdüzü", "beylikduzu", "yakuplu", "adnan kahveci", "cumhuriyet mh", "cumhuriyet mah"],
    "Esenyurt": ["esenyurt", "kıraç", "kirac", "sultaniye", "güzelyurt", "guzelyurt", "haramidere", "bağlarçeşme", "baglarcesme", "üçevler", "ucevler"],
    "Avcılar": ["avcılar", "avcilar", "gümüşpala", "gumuspala", "firuzköy", "firuzkoy"],
    "Pendik": ["pendik", "kurtköy", "kurtkoy", "esenyalı", "esenyali", "harmandere"],
    "Kartal": ["kartal", "kartaltepe", "soğanlık", "soganlik"],
    "Kağıthane": ["kağıthane", "kagithane", "çağlayan", "caglayan", "gültepe", "gultepe"],
    "Eyüpsultan": ["eyüpsultan", "eyupsultan", "çırçır", "circir"],
    "Sultanbeyli": ["sultanbeyli"],
    "Büyükçekmece": ["büyükçekmece", "buyukcekmece", "celaliye"],
    "Bahçelievler": ["bahçelievler", "bahcelievler", "yenibosna", "çobançeşme", "cobancesme"],
    "Küçükçekmece": ["küçükçekmece", "kucukcekmece", "halkalı", "halkali", "sefaköy", "sefakoy"],
    "Bağcılar": ["bağcılar", "bagcilar"],
    "Fatih": ["fatih", "cerrahpaşa", "cerrahpasa"],
    "Sancaktepe": ["sancaktepe"],
    "Ümraniye": ["ümraniye", "umraniye"],
    "Sarıyer": ["sarıyer", "sariyer"],
    "Arnavutköy": ["arnavutköy", "arnavutkoy"],
    "Başakşehir": ["başakşehir", "basaksehir"],
}

FEATURE_KEYWORDS = {
    "metro": ["metro", "metroya yakın"],
    "metrobüs": ["metrobüs", "metrobus", "e-5"],
    "balkon": ["balkon", "balkonlu"],
    "site": ["site", "site içi", "site içerisinde"],
    "otopark": ["otopark"],
    "asansör": ["asansör", "asansorlu", "asansörlü"],
    "eşyalı": ["eşyalı", "esyali"],
    "krediye uygun": ["krediye uygun", "kredi"],
    "sıfır": ["sıfır", "sifir", "yeni bina"],
    "ara kat": ["ara kat", "arakat"],
    "yüksek giriş": ["yüksek giriş"],
    "bahçe katı": ["bahçe katı"],
    "merkezi konum": ["merkezi", "merkezi konum"],
    "lüks": ["lüks", "lux", "lüx"],
    "dubleks": ["dubleks"],
}

def normalize_tr(text: str) -> str:
    text = (text or "").lower()
    replacements = {
        "ı": "i",
        "ğ": "g",
        "ü": "u",
        "ş": "s",
        "ö": "o",
        "ç": "c",
        "İ": "i",
    }
    for a, b in replacements.items():
        text = text.replace(a, b)
    return text

def make_search_text(item: dict) -> str:
    return " ".join([
        str(item.get("title") or ""),
        str(item.get("description") or ""),
        str(item.get("description_clean") or ""),
        str(item.get("source_url") or ""),
    ])

def infer_district(item: dict) -> str:
    raw_text = make_search_text(item)
    text = normalize_tr(raw_text)

    for district, aliases in DISTRICT_ALIASES.items():
        for alias in aliases:
            if normalize_tr(alias) in text:
                return district

    return item.get("district") or "Bilinmiyor"

def infer_features(item: dict) -> list:
    existing = item.get("features") or []
    features = set(str(x).strip() for x in existing if str(x).strip())

    text = normalize_tr(make_search_text(item))

    for feature, aliases in FEATURE_KEYWORDS.items():
        for alias in aliases:
            if normalize_tr(alias) in text:
                features.add(feature)
                break

    return sorted(features)

def main():
    if not IN_FILE.exists():
        print(f"[!] Dosya bulunamadı: {IN_FILE}")
        return

    data = json.loads(IN_FILE.read_text(encoding="utf-8"))
    print(f"[fix_districts] Okunan ilan: {len(data)}")

    changed = 0

    for item in data:
        old_district = item.get("district")
        new_district = infer_district(item)

        if new_district and new_district != old_district:
            item["district"] = new_district
            changed += 1

        item["features"] = infer_features(item)

        if not item.get("description_clean"):
            feats = ", ".join(item.get("features") or [])
            item["description_clean"] = " | ".join([
                str(item.get("title") or ""),
                f"İlçe: {item.get('district') or 'Bilinmiyor'}",
                f"Oda: {item.get('rooms') or 'Bilinmiyor'}",
                f"Özellikler: {feats}" if feats else "",
            ]).strip(" |")

    OUT_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[fix_districts] Güncellenen district sayısı: {changed}")
    print("[fix_districts] İlk 30 ilçe dağılımı:")
    print(Counter([x.get("district") for x in data]).most_common(30))

if __name__ == "__main__":
    main()
