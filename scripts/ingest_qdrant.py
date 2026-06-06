"""
ingest_qdrant.py
----------------
Veri kaynağı önceliği:
  1. data/listings_live.json  (fetch_hepsiemlak.py çıktısı)
  2. data/listings_generated.json (generate_listings.py çıktısı)

Kullanım:
    python scripts/ingest_qdrant.py
"""
import json
import os
from pathlib import Path

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv

load_dotenv()

QDRANT_URL  = os.getenv("QDRANT_URL",        "http://localhost:6333")
COLLECTION  = os.getenv("QDRANT_COLLECTION", "listings_demo")
EMBED_MODEL = os.getenv("EMBED_MODEL",       "intfloat/multilingual-e5-small")
RESET_COLLECTION = os.getenv("RESET_COLLECTION", "true").lower() == "true"

# Sadece temizlenmiş gerçek veriyi kullan
DATA_PATH = Path("data") / "listings_clean.json"

if not DATA_PATH.exists():
    raise FileNotFoundError(
        f"Temizlenmiş veri dosyası bulunamadı: {DATA_PATH}\n"
        "Lütfen tüm pipeline'ı çalıştırın:\n"
        "  1. python scripts/fetch_hepsiemlak.py\n"
        "  2. python scripts/fetch_emlakjet.py\n"
        "  3. python scripts/enrich_hepsiemlak_details.py\n"
        "  4. python scripts/enrich_emlakjet_details.py\n"
        "  5. python scripts/normalize_listings.py\n"
        "  6. python scripts/clean_listings.py\n"
    )

print(f"[ingest] Kaynak: TEMİZLENMİŞ gerçek veri → {DATA_PATH}")


def combined_text(l: dict) -> str:
    feats = ", ".join(l.get("features", []) or [])
    desc  = l.get("description_clean") or l.get("description") or ""
    parts = [
        l.get("title", ""),
        f"İlçe: {l.get('district', '')}",
        f"Mahalle: {l.get('neighborhood', '')}",
        f"Oda: {l.get('rooms', '')}",
        f"m²: {l.get('gross_m2', '')}",
        f"Fiyat: {l.get('price_try', '')}",
    ]
    if feats:
        parts.append(f"Özellikler: {feats}")
    if desc:
        parts.append(f"Açıklama: {desc}")
    return " | ".join(p for p in parts if p and p.split(": ", 1)[-1])


def main():
    listings = json.loads(DATA_PATH.read_text(encoding="utf-8"))
    print(f"[ingest] {len(listings)} ilan yüklendi")

    model  = SentenceTransformer(EMBED_MODEL)
    client = QdrantClient(url=QDRANT_URL)

    dim = model.get_sentence_embedding_dimension()
    
    # Koleksiyonu SİL ve YENİDEN OLUŞTUR (Opsiyonel)
    existing = [c.name for c in client.get_collections().collections]
    if RESET_COLLECTION and COLLECTION in existing:
        print(f"[ingest] RESET_COLLECTION=true: Eski koleksiyon siliniyor → {COLLECTION}")
        client.delete_collection(collection_name=COLLECTION)
        existing = [c.name for c in client.get_collections().collections] # Listeyi güncelle
    
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
        )
        print(f"[ingest] Koleksiyon oluşturuldu → {COLLECTION}")
    else:
        print(f"[ingest] Koleksiyon mevcut, üzerine ekleniyor (upsert) → {COLLECTION}")

    texts   = [combined_text(l) for l in listings]
    vectors = model.encode(
        texts,
        normalize_embeddings=True,
        batch_size=64,
        show_progress_bar=True,
    )

    points = []
    for idx, l in enumerate(listings):
        payload = dict(l)
        payload["text"] = texts[idx]
        lid_str = str(l.get("listing_id", idx + 1))
        # Sadece sayısal kısmı al, integer id üret
        digits = "".join(filter(str.isdigit, lid_str))
        pid = int(digits[-9:]) if digits else (idx + 1)
        if pid == 0:
            pid = idx + 1
        points.append(PointStruct(id=pid, vector=vectors[idx].tolist(), payload=payload))

    # Tekrarlı id'leri önlemek için son pid değerini izle
    seen_pids: set[int] = set()
    deduped = []
    for p in points:
        if p.id in seen_pids:
            p = PointStruct(
                id=max(seen_pids) + 1,
                vector=p.vector,
                payload=p.payload,
            )
        seen_pids.add(p.id)
        deduped.append(p)

    client.upsert(collection_name=COLLECTION, points=deduped)
    
    # Final Kontrol
    info = client.get_collection(collection_name=COLLECTION)
    count = info.points_count
    print(f"\n[ingest] ✅ İşlem başarıyla tamamlandı!")
    print(f"[ingest] Toplam Aktarılan : {len(deduped)} ilan")
    print(f"[ingest] Koleksiyon Adı  : {COLLECTION}")
    print(f"[ingest] Güncel Sayı     : {count} nokta")


if __name__ == "__main__":
    main()
