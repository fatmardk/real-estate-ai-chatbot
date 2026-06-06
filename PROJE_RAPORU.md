# 🏠 Emlak GenAI — Akıllı Emlak Öneri Asistanı

## Proje Raporu

---

## 1. Proje Tanıtımı

**Emlak GenAI**, gerçek emlak ilanlarını canlı web sitelerinden toplayıp vektör veritabanında saklayan, kullanıcının doğal dil sorgularıyla semantik arama yapmasını sağlayan ve her ilana özel Türkçe yorum üreten yapay zeka tabanlı bir emlak asistanıdır.

### Kullanılan Teknolojiler

| Bileşen | Teknoloji | Açıklama |
|---------|-----------|----------|
| **Frontend** | Streamlit | İnteraktif web arayüzü |
| **Vektör DB** | Qdrant (Docker) | Semantik ilan araması |
| **Embedding** | `intfloat/multilingual-e5-small` | Çok dilli metin vektörleme (384 boyut) |
| **LLM** | LLaMA-3 8B (LoRA fine-tuned) | Lokal, Ollama üzerinden |
| **Scraping** | requests + BeautifulSoup | Emlakjet & Hepsiemlak |
| **Dil** | Python 3.13 | Tüm backend |

---

## 2. Sistem Mimarisi

```
┌─────────────────────────────────────────────────────────┐
│                    KULLANICI ARAYÜZÜ                     │
│                   (Streamlit - 8501)                      │
│   ┌─────────────┐  ┌──────────────┐  ┌───────────────┐  │
│   │ Filtre Panel │  │ İlan Listesi │  │ LLM Yorumu    │  │
│   │ İlçe/Oda/m²  │  │ Vektör Sonuç │  │ Neden uygun?  │  │
│   │ Fiyat/Sorgu  │  │ Kural Skoru  │  │ Dikkat/Soru   │  │
│   └──────┬──────┘  └──────┬───────┘  └───────┬───────┘  │
│          │                │                   │          │
└──────────┼────────────────┼───────────────────┼──────────┘
           │                │                   │
     ┌─────▼─────┐   ┌─────▼──────┐   ┌───────▼────────┐
     │ Sorgu     │   │  Qdrant    │   │  Ollama LLM    │
     │ Ayrıştırma│   │ Vektör DB  │   │ emlak-ozel     │
     │ (Regex)   │   │ (6333)     │   │ (11434)        │
     └───────────┘   └─────▲──────┘   └────────────────┘
                           │
                    ┌──────┴──────┐
                    │  Embedding  │
                    │  e5-small   │
                    └──────▲──────┘
                           │
              ┌────────────┴────────────┐
              │    VERİ PİPELINE        │
              │                         │
              │  fetch_emlakjet.py       │
              │  fetch_hepsiemlak.py     │
              │      ↓                  │
              │  normalize_listings.py  │
              │      ↓                  │
              │  clean_listings.py      │
              │      ↓                  │
              │  ingest_qdrant.py       │
              └─────────────────────────┘
```

---

## 3. Ekran Görüntüleri

> **Not:** Aşağıdaki ekran görüntülerini çalışan uygulamadan almanız gerekmektedir.
> Streamlit çalışırken tarayıcıda `http://localhost:8501` adresinden alabilirsiniz.

### 3.1 Ana Arayüz — Arama Öncesi

**Alınması gereken ekran görüntüsü:**  
Streamlit açıldığında sol sidebar'da filtre paneli (İlçe, Oda, Fiyat, m²) ve "Ara" butonu görünür.

> 📸 *Buraya uygulamanın ilk açılış ekranının screenshot'ını ekleyin*

---

### 3.2 Arama Sonuçları — İlan Listesi

**Alınması gereken ekran görüntüsü:**  
"Kadıköy'de 3+1, balkonlu, 3 milyon TL altı" gibi bir sorgu yazıp "🔎 Ara" butonuna basıldıktan sonra sol panelde gerçek ilanların listesi.

> 📸 *Buraya arama sonuçları ekranının screenshot'ını ekleyin*

---

### 3.3 Asistan Yorumu — LLM Çıktısı

**Alınması gereken ekran görüntüsü:**  
Sağ paneldeki "Asistan Yorumu" bölümü: Uygunluk skoru, "Neden uygun?", "Dikkat:", "Kritik soru:" formatında LLM yorumları.

> 📸 *Buraya LLM yorum panelinin screenshot'ını ekleyin*

---

### 3.4 Qdrant Dashboard

**Alınması gereken ekran görüntüsü:**  
`http://localhost:6333/dashboard` adresinden Qdrant koleksiyon bilgisi (listings_demo, nokta sayısı).

> 📸 *Buraya Qdrant dashboard screenshot'ını ekleyin*

---

## 4. Beş Temel Gereksinim (5 Generic Requirements)

### 4.1 🤖 Vibe Coding (No Code, Just Prompt)

Projenin büyük kısmı **AI destekli prompt tabanlı geliştirme** ile oluşturuldu. Temel promptlar:

**Prompt 1 — Proje mimarisi:**
> *"Bu bir emlak projesi. Verileri canlı bir API'den çekmemiz gerekiyor, sonrasında belirli filtreler ile arama yapılıp çıktılar gelecek ve LLM üretecek. Vektör DB kullanıyoruz."*

**Prompt 2 — Scraping stratejisi:**
> *"Hepsiemlak veya Sahibinden hangisi API istemezse onu kullanalım. Bir kere çekip Qdrant'a aktarsa yeterli."*

**Prompt 3 — Skorlama ve LLM entegrasyonu:**
> *"Kullanıcının doğal dil sorgusu regex ile parse edilsin (ilçe, oda, fiyat, m²). Vektör arama sonuçlarına kural tabanlı skor eklensin. Her ilan için LLM 3 satır yorum üretsin: neden uygun, dikkat edilecek, kritik soru."*

**Prompt 4 — Fine-tuning:**
> *"Modelimin tamamen Türkçe yanıt vermesini sağlamak istiyorum. İlanlardan LoRA fine-tuning dataset'i oluştur."*

**Prompt 5 — Veri normalizasyonu:**
> *"Farklı kaynaklardan (Emlakjet + Hepsiemlak) gelen verileri tek formata dönüştür. İlçe, oda, fiyat, m² alanlarını standartlaştır. Eksik ilçeyi başlıktan çıkar."*

---

### 4.2 🗄️ Vector Database (Qdrant)

Projede **Qdrant** açık kaynak vektör veritabanı kullanılmıştır.

**Neden Qdrant?**
- Docker ile tek komutta kurulum
- Cosine similarity ile semantik arama
- Payload filtreleme (ilçe, oda, fiyat aralığı, m²)
- REST API + Python SDK

**Nasıl çalışıyor?**

```python
# 1. İlan metni oluşturulur
text = "Kadıköy Kozyatağı 3+1 130m² | balkon, metro | 2.450.000 TL"

# 2. Embedding modeli ile 384 boyutlu vektöre dönüştürülür
vector = model.encode(text, normalize_embeddings=True)

# 3. Qdrant'a payload ile birlikte yüklenir
client.upsert(collection_name="listings_demo", points=[
    PointStruct(id=1, vector=vector, payload={
        "district": "Kadıköy", "rooms": "3+1", "price_try": 2450000, ...
    })
])

# 4. Kullanıcı sorgusu aynı model ile vektöre çevrilir
query_vec = model.encode("Kadıköy'de 3+1 metroya yakın")

# 5. Cosine similarity ile en yakın ilanlar bulunur
results = client.search(query_vector=query_vec, limit=10,
    query_filter=Filter(must=[
        FieldCondition(key="district", match=MatchValue(value="Kadıköy")),
        FieldCondition(key="price_try", range=Range(lte=3000000))
    ]))
```

**Koleksiyon:** `listings_demo` — Temizlenmiş gerçek ilan verileri  
**Embedding boyutu:** 384 (intfloat/multilingual-e5-small)  
**Metrik:** Cosine Similarity

---

### 4.3 🌐 Web Scraping (Gerçek Zamanlı Veri)

İki farklı emlak sitesinden **requests + BeautifulSoup** ile gerçek ilan verisi çekilmiştir:

#### Emlakjet Scraper (`scripts/fetch_emlakjet.py`)
- **Yöntem:** HTTP GET + HTML parse
- **Veri:** Satılık daire ilanları, çoklu ilçe ve sayfa desteği
- **Çıkarılan alanlar:** Başlık, fiyat, m², oda sayısı, ilçe, mahalle, özellikler, ilan URL'si
- **Rate limiting:** Her sayfa arasında 1.5-3 saniye rastgele bekleme
- **Anti-bot:** Gerçekçi User-Agent header'ı

```python
# Temel scraping akışı
session = requests.Session()
resp = session.get(url, headers={"User-Agent": "Mozilla/5.0 ..."}, timeout=25)
soup = BeautifulSoup(resp.text, "html.parser")
cards = soup.select(".listing-card")  # İlan kartları
```

#### Hepsiemlak Scraper (`scripts/fetch_hepsiemlak.py`)
- **Yöntem:** Next.js `__NEXT_DATA__` JSON bloğu parse
- **Fallback:** HTML kart parse (site yapısı değişirse)

#### Veri Pipeline

```
fetch_emlakjet.py  →  listings_emlakjet.json (ham veri)
fetch_hepsiemlak.py →  listings_live.json (ham veri)
        ↓
enrich_*_details.py  →  enriched JSON (zenginleştirilmiş)
        ↓
normalize_listings.py →  listings_normalized.json (standart format)
        ↓
clean_listings.py     →  listings_clean.json (temiz, kullanıma hazır)
        ↓
ingest_qdrant.py      →  Qdrant koleksiyonu (vektör + payload)
```

---

### 4.4 🧠 Large Language Model (Açık Kaynak LLM — Lokal)

Projede **LLaMA-3 8B Instruct** modeli, **Ollama** üzerinden tamamen lokal olarak çalıştırılmaktadır.

**Model detayları:**

| Parametre | Değer |
|-----------|-------|
| Temel Model | `llama-3-8b-instruct` |
| Nicemleme | Q4_K_M (4-bit, 4.9 GB) |
| Çalıştırma | Ollama (`localhost:11434`) |
| Özel Ad | `emlak-ozel:latest` |
| Sistem Promptu | *"Sen bir Türk emlak danışmanı asistanısın. Yalnızca Türkçe yaz."* |

**Modelfile (Ollama konfigürasyonu):**
```
FROM ./llama-3-8b-instruct.Q4_K_M.gguf
SYSTEM "Sen bir Türk emlak danışmanı asistanısın. Yalnızca Türkçe yaz.
       İngilizce kelime kullanma. Kısa, net ve bilgilendirici ol."
PARAMETER temperature 0.1
PARAMETER stop "<|start_header_id|>"
PARAMETER stop "<|end_header_id|>"
PARAMETER stop "<|eot_id|>"
```

**API Çağrısı:**
```python
response = requests.post(
    "http://127.0.0.1:11434/api/generate",
    json={
        "model": "emlak-ozel:latest",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0,
            "num_predict": 90,
            "repeat_penalty": 1.35,
        }
    }
)
```

---

### 4.5 💡 LLM-Powered Intelligent Decision / Output

LLM, ham vektör arama sonuçlarının üzerine **akıllı karar ve yorum katmanı** ekler:

#### Kural Tabanlı Skorlama (Hybrid Search)

Her ilan için 0–100 arası uygunluk skoru hesaplanır:

| Kriter | Puan |
|--------|------|
| İlçe uyumu | +25 |
| Oda sayısı uyumu | +20 |
| Bütçeye uygunluk | +30 |
| m² yeterliliği | +15 |
| Özellik eşleşmesi (metro, balkon, site...) | +5–15 |

#### LLM Yorum Formatı

Her ilan için LLM üç yapılandırılmış çıktı üretir:

```
1) Neden uygun? Kadıköy konumunda olması kullanıcının bölge beklentisiyle
   uyumlu görünüyor. Ayrıca ulaşıma yakın olması güçlü bir avantaj sağlıyor.

2) Dikkat: Bütçenizi aşıyor (3.200.000 TL)

3) Kritik soru: Aidat ne kadar ve otopark/güvenlik hizmetleri aktif mi?
```

#### Akıllı Neden Üretimi (`build_smart_reason`)

İlan başlığı ve özelliklerinden bağlama duyarlı nedenler çıkarılır:
- "metro" → *"ulaşıma yakın olması günlük kullanım açısından güçlü bir avantaj sağlıyor"*
- "site" → *"site içerisinde olması güvenlik ve düzen açısından avantaj sağlayabilir"*
- "dubleks" → *"standart dairelere göre daha geniş kullanım imkânı sunabilir"*

#### Kritik Soru Seçimi (`pick_critical_question`)

İlan içeriğine göre en alakalı soru otomatik seçilir:
- Dubleks/teras ilan → *"Terasın tapuya işli olup olmadığı doğrulanabilir mi?"*
- Site/güvenlik ilan → *"Aidat ne kadar ve otopark/güvenlik hizmetleri aktif mi?"*
- Sıfır/yeni bina → *"İskan durumu ve yapı kullanım izin belgesi net mi?"*

---

## 5. Improvement / Refinement (Fine-Tuning)

### V1 → V2 İyileştirmeleri

#### 5.1 LoRA Fine-Tuning

Temel LLaMA-3 modeli Türkçe emlak bağlamında zayıf performans gösteriyordu:
- İngilizce kelimeler karışıyordu
- Çıktı formatı tutarsızdı
- Emlak terminolojisi eksikti

**Çözüm: LoRA (Low-Rank Adaptation) ile ince ayar**

**Eğitim veri seti oluşturma** (`scripts/generate_finetune_dataset.py`):
- 500 sentetik ilandan her biri için 2 farklı kullanıcı sorgusu üretildi
- Toplam ~1000 eğitim örneği (`data/finetune_dataset.jsonl`)
- Her örnek: `system + user instruction + assistant response` formatında (ChatML)

**Eğitim örneği:**
```json
{
  "messages": [
    {"role": "system", "content": "Sen bir Türk emlak danışmanı asistanısın..."},
    {"role": "user", "content": "Kullanıcı isteği: Kadıköy'de 3+1..."},
    {"role": "assistant", "content": "1) Neden uygun? İlçe kriteri birebir..."}
  ]
}
```

**Eğitim konfigürasyonu** (Google Colab, T4 GPU):

| Parametre | Değer |
|-----------|-------|
| LoRA rank (r) | 16 |
| LoRA alpha | 32 |
| Dropout | 0.05 |
| Batch size | 2 (gradient acc: 8 → efektif 16) |
| Epoch | 3 |
| Learning rate | 2e-4 |
| Niceleme | 4-bit (QLoRA) |
| Max sequence length | 512 |
| Framework | Unsloth + SFTTrainer (TRL) |

**Hedef modüller:** `q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj`

#### 5.2 Çıktı Temizleme Katmanı

Fine-tuned model hâlâ bazen İngilizce kalıntılar veya fazla uzun yanıtlar ürettiğinden, **post-processing** katmanı eklendi:

- `clean_llm_output_strict()`: Tekrarlayan başlıkları, İngilizce notları, tablo kalıntılarını temizler
- `tr_sanitize()`: İngilizce kalıp sözcükleri Türkçe'ye çevirir
- Kritik soru eksik kalırsa `pick_critical_question()` ile kural tabanlı fallback

#### 5.3 Hybrid Scoring (Vektör + Kural)

V1'de sadece vektör benzerlik skoru vardı. V2'de **kural tabanlı skorlama** eklendi:

```
Final Skor = Vektör Benzerlik (Qdrant) + Kural Skoru (Python)
```

Bu sayede:
- Semantik olarak yakın ama fiyatı aşan ilanlar düşük skor alır
- İlçe/oda tam eşleşen ilanlar öne çıkar
- Özellik bazlı bonus puanlar (metro, balkon, site) uygulanır

#### 5.4 Veri Kalitesi İyileştirmeleri

- **İlçe çıkarımı:** Başlık/açıklamadan regex ile ilçe tespiti (`infer_district`)
- **Özellik zenginleştirme:** Metin analizi ile eksik özellikler otomatik eklenir
- **Veri temizleme:** Junk URL'ler, eksik fiyat/m² verileri filtrelenir
- **Çift kaynak birleştirme:** Emlakjet + Hepsiemlak verileri tek formatta normalize

---

## 6. Proje Dosya Yapısı

```
c:\emlak-genai\
│
├── streamlit_app.py              # Ana uygulama (666 satır)
├── check_ollama.py               # Ollama bağlantı testi
├── seed_json_to_qdrant.py        # Alternatif ingest aracı
├── Modelfile                     # Ollama model tanımı
├── llama-3-8b-instruct.Q4_K_M.gguf  # LLM model dosyası (4.9 GB)
├── lora_finetuning_colab.ipynb   # LoRA eğitim notebook'u
├── .env                          # Yapılandırma
│
├── data/
│   ├── listings_clean.json       # Temiz veri (kullanıma hazır)
│   ├── listings_normalized.json  # Normalize edilmiş veri
│   ├── listings_emlakjet.json    # Emlakjet ham verisi
│   ├── listings_live.json        # Hepsiemlak ham verisi
│   └── finetune_dataset.jsonl    # LoRA eğitim veri seti
│
└── scripts/
    ├── fetch_emlakjet.py          # Emlakjet scraper
    ├── fetch_hepsiemlak.py        # Hepsiemlak scraper
    ├── enrich_emlakjet_details.py # Veri zenginleştirme
    ├── enrich_hepsiemlak_details.py
    ├── normalize_listings.py      # Çift kaynak normalizasyon
    ├── clean_listings.py          # Veri temizleme & kalite kontrol
    ├── ingest_qdrant.py           # Qdrant'a vektör yükleme
    ├── generate_listings.py       # Sentetik veri üreteci
    └── generate_finetune_dataset.py  # LoRA eğitim verisi üreteci
```

---

## 7. Çalıştırma Talimatları

```powershell
# 1. Sanal ortamı aktif et
cd C:\emlak-genai
.venv\Scripts\activate

# 2. Qdrant'ı başlat (Docker)
docker run -d -p 6333:6333 -v C:\emlak-genai\qdrant_data:/qdrant/storage qdrant/qdrant

# 3. Ollama'nın çalıştığını kontrol et
ollama list

# 4. Uygulamayı başlat
streamlit run streamlit_app.py
```

---

## 8. Sonuç

Emlak GenAI projesi, modern yapay zeka tekniklerini (vektör veritabanı, LLM, LoRA fine-tuning) gerçek dünya verileriyle birleştirerek, kullanıcıya doğal dilde emlak araması yapma ve her ilan hakkında akıllı yorum alma imkanı sunan uçtan uca bir sistemdir. Tüm bileşenler lokal olarak çalışmakta olup herhangi bir ücretli API'ye bağımlılık bulunmamaktadır.
