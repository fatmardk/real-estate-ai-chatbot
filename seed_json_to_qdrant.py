import argparse
import json
import os
from pathlib import Path
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

load_dotenv()

QDRANT_MODE = os.getenv("QDRANT_MODE", "local")
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_data")
COLLECTION_NAME = os.getenv("QDRANT_COLLECTION", "listings_demo")
EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small")

def main():
    parser = argparse.ArgumentParser(description="Seed normalized JSON data into Qdrant.")
    parser.add_argument("--input", required=True, help="Path to the JSON file (e.g., data/listings_normalized.json)")
    parser.add_argument("--recreate", action="store_true", help="Recreate the collection if it exists")
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"[!] HATA: Girdi dosyası bulunamadı: {input_path}")
        return

    # 1. Veriyi Oku
    print(f"[*] Veri okunuyor: {input_path}")
    with open(input_path, "r", encoding="utf-8") as f:
        listings = json.load(f)
    print(f"[*] Toplam ilan: {len(listings)}")

    if not listings:
        print("[!] Dosya boş.")
        return

    # 2. Qdrant ve Embedding Model Hazırlığı
    print(f"[*] Qdrant ({QDRANT_MODE}) başlatılıyor...")
    try:
        if QDRANT_MODE == "server":
            client = QdrantClient(url=QDRANT_URL, timeout=10)
        else:
            client = QdrantClient(path=QDRANT_PATH)
        # Sadece bağlantıyı test etmek için
        client.get_collections()
    except Exception as e:
        print(f"[!] HATA: Qdrant başlatılamadı. Mod: {QDRANT_MODE}")
        print(f"    Detay: {e}")
        return

    print(f"[*] Embedding modeli yükleniyor: {EMBED_MODEL}")
    model = SentenceTransformer(EMBED_MODEL)
    
    # 3. Koleksiyon Yönetimi
    if args.recreate:
        print(f"[*] Koleksiyon siliniyor/yeniden oluşturuluyor: {COLLECTION_NAME}")
        client.recreate_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=384, distance=Distance.COSINE),
        )
    else:
        collections = client.get_collections().collections
        if not any(c.name == COLLECTION_NAME for c in collections):
            print(f"[*] Koleksiyon bulunamadı. Yeni oluşturuluyor: {COLLECTION_NAME}")
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )
        else:
            print(f"[*] Koleksiyon bulundu: {COLLECTION_NAME}")

    # 4. Verileri Hazırlama ve Basma
    print("[*] İlanlar vektörleştiriliyor ve veritabanına ekleniyor...")
    
    points = []
    for i, item in enumerate(listings):
        listing_id = item.get("listing_id") or str(i)
        title = item.get("title", "")
        district = item.get("district", "")
        neighborhood = item.get("neighborhood", "")
        rooms = item.get("rooms", "")
        gross_m2 = item.get("gross_m2", "")
        price = item.get("price_try", "")
        features = ", ".join(item.get("features") or [])
        desc_clean = item.get("description_clean", "")
        
        # Metin birleştirme
        text_for_embedding = f"Başlık: {title}. Konum: {district}, {neighborhood}. Oda: {rooms}. Alan: {gross_m2}m2. Fiyat: {price} TL. Özellikler: {features}. Açıklama: {desc_clean}"
        
        vector = model.encode(text_for_embedding, normalize_embeddings=True).tolist()
        
        payload = {
            "listing_id": listing_id,
            "title": title,
            "district": district,
            "neighborhood": neighborhood,
            "rooms": rooms,
            "gross_m2": gross_m2,
            "price_try": price,
            "features": item.get("features") or [],
            "description_clean": desc_clean,
            "source_url": item.get("source_url", ""),
            "scraped_at": item.get("scraped_at", ""),
            "text": text_for_embedding
        }
        
        # Qdrant için benzersiz ve geçerli bir UUID ya da INT ID gerekiyor.
        # String bir listing_id'yi integer'a hashliyoruz veya sıradaki index'i kullanıyoruz.
        point_id = abs(hash(listing_id)) % (10 ** 15)
        
        points.append(PointStruct(id=point_id, vector=vector, payload=payload))
        
        if len(points) >= 100 or i == len(listings) - 1:
            client.upsert(
                collection_name=COLLECTION_NAME,
                points=points
            )
            print(f"    - {i + 1}/{len(listings)} ilan eklendi.")
            points = []

    print("[✓] İşlem tamamlandı.")

if __name__ == "__main__":
    main()
