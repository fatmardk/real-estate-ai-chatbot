"""
Emlak ilanlarından LoRA fine-tuning için JSONL veri seti oluşturan script.
Çalıştırmak için: python scripts/generate_finetune_dataset.py
Çıktı: data/finetune_dataset.jsonl
"""

import json
import random
from pathlib import Path
from typing import List, Optional

# Veri dosyasının yolu
DATA_PATH = Path(__file__).parent.parent / "data" / "listings_generated.json"
OUTPUT_PATH = Path(__file__).parent.parent / "data" / "finetune_dataset.jsonl"

# Olası kullanıcı sorgu şablonları
QUERY_TEMPLATES = [
    "{district}'da {rooms} oda, {price_max} TL altında, {m2_min}m² üstü daire arıyorum.",
    "{district} bölgesinde {rooms} tipinde {price_max} TL bütçeyle daire arıyorum.",
    "{m2_min} metrekare üstü, {rooms} oda, {district}'da {price_max} TL'yi geçmesin.",
    "{district}'da en az {m2_min}m², {rooms} yapısında, {price_max} TL ev arıyorum.",
    "Bütçem {price_max} TL, {district} ilçesinde {rooms} istiyorum, {m2_min}m² olsun.",
]

# Özellik tabanlı soru şablonları (LLM'nin üretmesi beklenen kritik sorular)
CRITICAL_QUESTIONS = [
    "Aidat ne kadar ve otopark/güvenlik var mı?",
    "Tapu durumu nedir (kat mülkiyeti/kat irtifakı) ve iskan var mı?",
    "Deprem yönetmeliğine uygunluk ve bina yaşı doğrulanabilir mi?",
    "Dairenin net m²'si kaç ve brüt/net farkı nedir?",
    "Evin ısınma tipi ve aylık ortalama giderler nedir?",
    "Komşu katlar ve binanın genel durumu nasıl?",
    "Kadastral ve tapu kaydı sorunsuz mu?",
    "Okul, hastane gibi sosyal donatılara erişim nasıl?",
]

# Uygunluk nedeni şablonları
MATCH_REASONS = {
    "district": [
        "İlçe kriteri birebir örtüşüyor.",
        "Aradığınız ilçede yer alıyor.",
        "Konum isteğinizle tam uyumlu.",
    ],
    "rooms": [
        "Oda yapısı tam istediğiniz gibi.",
        "Oda sayısı ihtiyacınıza uygun.",
        "İstenen oda tipiyle eşleşiyor.",
    ],
    "price": [
        "Fiyatı bütçenizin içinde.",
        "Belirttiğiniz bütçeyi aşmıyor.",
        "Fiyat açısından beklentinizi karşılıyor.",
    ],
    "m2": [
        "Alan olarak yeterli büyüklükte.",
        "Metrekare isteğinizi karşılıyor.",
        "Kullanım alanı belirttiğiniz ölçütün üzerinde.",
    ],
    "features": [
        "Öne çıkan özellikleri ihtiyacınızla örtüşüyor.",
        "Ek donanım bakımından avantajlı.",
        "Özellikler açısından güçlü bir seçenek.",
    ],
}

# Fedakârlık (trade-off) şablonları
TRADEOFF_TEMPLATES = [
    "Bina yaşı yüksek olabilir, yerinde inceleme önerilir.",
    "Kat konumu beklenenden farklı olabilir.",
    "Fiyat, piyasa ortalamasının biraz üzerinde.",
    "İstenen m² aralığının sınırında yer alıyor.",
    "Oda sayısı dışındaki ayrıntılar ilanla teyit edilmeli.",
]


def fmt_price(price: int) -> str:
    return f"{price:,}".replace(",", ".") + " TL"


def build_user_query(listing: dict) -> str:
    template = random.choice(QUERY_TEMPLATES)
    district = listing.get("district", "İstanbul")
    rooms = listing.get("rooms", "3+1")
    price_try = listing.get("price_try", 3000000)
    gross_m2 = listing.get("gross_m2", 100)

    # Bütçeyi %10-20 yukarı ayarla ki ilan eşleşsin
    price_max = int(price_try * random.uniform(1.05, 1.25))
    price_max = (price_max // 50000) * 50000  # 50.000 TL yuvarlama

    m2_min = max(50, int(gross_m2) - random.randint(10, 20))

    return template.format(
        district=district,
        rooms=rooms,
        price_max=fmt_price(price_max),
        m2_min=m2_min,
    )


def build_match_reasons(listing: dict) -> List[str]:
    reasons = []
    reasons.append(random.choice(MATCH_REASONS["district"]))
    reasons.append(random.choice(MATCH_REASONS["rooms"]))

    if listing.get("price_try"):
        reasons.append(random.choice(MATCH_REASONS["price"]))

    if listing.get("gross_m2"):
        reasons.append(random.choice(MATCH_REASONS["m2"]))

    feats = listing.get("features") or []
    if feats:
        reasons.append(random.choice(MATCH_REASONS["features"]))

    random.shuffle(reasons)
    return reasons[:2]


def build_response(listing: dict, reasons: List[str], tradeoff: str, question: str) -> str:
    """Tamamen Türkçe, temiz bir LLM yanıtı üretir."""
    neden = " ".join(reasons)
    response = (
        f"1) Neden uygun? {neden}\n"
        f"2) Dikkat: {tradeoff}\n"
        f"3) Kritik soru: {question}"
    )
    return response


def build_system_prompt() -> str:
    return (
        "Sen bir Türk emlak danışmanı asistanısın. "
        "Yalnızca Türkçe yaz. "
        "Asla İngilizce kelime kullanma. "
        "Fiyat değerlendirmesi yapma. "
        "Kısa, net ve bilgilendirici ol."
    )


def listing_to_instruction(listing: dict) -> Optional[dict]:
    """Her ilan için bir instruction-response çifti oluşturur."""
    try:
        user_query = build_user_query(listing)
        reasons = build_match_reasons(listing)
        tradeoff = random.choice(TRADEOFF_TEMPLATES)
        question = random.choice(CRITICAL_QUESTIONS)

        feats_str = ", ".join(listing.get("features") or [])
        district = listing.get("district", "")
        rooms = listing.get("rooms", "")
        price = listing.get("price_try", "")
        m2 = listing.get("gross_m2", "")

        instruction = (
            f"Kullanıcı isteği: {user_query}\n\n"
            f"İlan bilgileri:\n"
            f"- İlçe: {district}\n"
            f"- Oda: {rooms}\n"
            f"- Brüt m²: {m2}\n"
            f"- Fiyat: {fmt_price(price) if price else 'Belirtilmemiş'}\n"
            f"- Özellikler: {feats_str if feats_str else 'Belirtilmemiş'}\n\n"
            f"Bu ilan kullanıcıya uygun mu? "
            f"Neden uygun, dikkat edilmesi gereken bir husus ve en önemli kritik soruyu Türkçe olarak belirt."
        )

        response = build_response(listing, reasons, tradeoff, question)

        return {
            "messages": [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": instruction},
                {"role": "assistant", "content": response},
            ]
        }
    except Exception as e:
        print(f"[UYARI] İlan atlandı (hata: {e})")
        return None


def main():
    random.seed(42)

    print(f"[BİLGİ] Veri yükleniyor: {DATA_PATH}")
    with open(DATA_PATH, encoding="utf-8") as f:
        listings = json.load(f)

    print(f"[BİLGİ] {len(listings)} ilan bulundu.")

    records = []
    for listing in listings:
        # Her ilandan 2 farklı örnek üret (farklı kullanıcı sorgusu)
        for _ in range(2):
            rec = listing_to_instruction(listing)
            if rec:
                records.append(rec)

    # Karıştır
    random.shuffle(records)

    print(f"[BİLGİ] {len(records)} eğitim örneği oluşturuldu.")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    print(f"[BAŞARILI] Veri seti kaydedildi: {OUTPUT_PATH}")

    # Örnek göster
    print("\n--- Örnek Kayıt ---")
    sample = records[0]
    for msg in sample["messages"]:
        print(f"\n[{msg['role'].upper()}]\n{msg['content']}")


if __name__ == "__main__":
    main()
