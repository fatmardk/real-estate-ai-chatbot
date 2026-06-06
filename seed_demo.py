from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
from sentence_transformers import SentenceTransformer

QDRANT_URL = "http://localhost:6333"
COLLECTION = "listings_demo"

model = SentenceTransformer("intfloat/multilingual-e5-small")
client = QdrantClient(url=QDRANT_URL)

dim = model.get_sentence_embedding_dimension()
existing = [c.name for c in client.get_collections().collections]
if COLLECTION not in existing:
    client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
    )

now = datetime.now().isoformat(timespec="seconds")

listings = [
    {
        "listing_id": "L1",
        "title": "Kadıköy Kozyatağı 3+1, metroya 5 dk, balkonlu, site içi",
        "district": "Kadıköy",
        "rooms": "3+1",
        "gross_m2": 130,
        "price_try": 2450000,
        "features": ["balkon", "site", "metroya yakın"],
        "description_clean": "Metroya yürüyüş mesafesinde, aileye uygun site içinde, balkonlu 3+1 daire.",
        "source_url": "https://example.com/L1",
        "scraped_at": now,
    },
    {
        "listing_id": "L2",
        "title": "Beşiktaş 2+1, merkezi, manzaralı",
        "district": "Beşiktaş",
        "rooms": "2+1",
        "gross_m2": 95,
        "price_try": 3200000,
        "features": ["merkezi", "manzara"],
        "description_clean": "Merkezi konum, toplu ulaşıma yakın, 2+1 daire.",
        "source_url": "https://example.com/L2",
        "scraped_at": now,
    },
    {
        "listing_id": "L3",
        "title": "Ataşehir 3+1, yeni bina, otoparklı site",
        "district": "Ataşehir",
        "rooms": "3+1",
        "gross_m2": 125,
        "price_try": 2600000,
        "features": ["site", "otopark", "yeni bina"],
        "description_clean": "Yeni bina, otoparklı site içinde, geniş 3+1.",
        "source_url": "https://example.com/L3",
        "scraped_at": now,
    },
]

def combined_text(x: dict) -> str:
    feats = ", ".join(x.get("features", []))
    return f"{x.get('title','')} | İlçe: {x.get('district','')} | Oda: {x.get('rooms','')} | m²: {x.get('gross_m2','')} | Fiyat: {x.get('price_try','')} | Özellikler: {feats} | Açıklama: {x.get('description_clean','')}"

texts = [combined_text(l) for l in listings]
vectors = model.encode(texts, normalize_embeddings=True)

points = []
for i, l in enumerate(listings):
    payload = dict(l)
    payload["text"] = texts[i]
    # "L1" -> 1 gibi
    pid = int(l["listing_id"].replace("L",""))
    points.append(PointStruct(id=pid, vector=vectors[i].tolist(), payload=payload))

client.upsert(collection_name=COLLECTION, points=points)
print("OK: Demo ilanlar Qdrant'a yüklendi ->", COLLECTION)
