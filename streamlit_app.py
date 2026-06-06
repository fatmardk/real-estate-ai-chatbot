import os
import re
import requests
import streamlit as st
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.http.models import Filter, FieldCondition, MatchValue, Range
from sentence_transformers import SentenceTransformer

# ------------------------------------------------------------
# Yardımcı format fonksiyonları
# ------------------------------------------------------------
def fmt_try(x):
    return f"{int(x):,}".replace(",", ".") + " TL" if isinstance(x, (int, float)) else "unknown"

def fmt_m2(x):
    return f"{int(x)} m²" if isinstance(x, (int, float)) else "unknown"

def tr_sanitize(s: str) -> str:
    """Model çıktısında kaçan bazı İngilizce kalıpları temizler."""
    if not s:
        return s
    repl = {
        "reasons why it's suitable": "uygun olmasının nedenleri",
        "reasons why it is suitable": "uygun olmasının nedenleri",
        "reason why it's suitable": "uygun olmasının nedeni",
        "location": "konum",
        "district": "ilçe",
        "present": "mevcut",
        "reasons": "nedenler",
        "tradeoff": "dikkat edilmesi gereken nokta",
        "red flag": "uyarı",
    }
    out = s
    for k, v in repl.items():
        out = out.replace(k, v).replace(k.title(), v)
    return out.strip()

# ------------------------------------------------------------
# Sorgu ayrıştırma
# ------------------------------------------------------------
DISTRICT_ALIASES = {
    "adalar": "Adalar", "arnavutköy": "Arnavutköy", "ataşehir": "Ataşehir", "avcılar": "Avcılar",
    "bağcılar": "Bağcılar", "bahçelievler": "Bahçelievler", "bakırköy": "Bakırköy", "başakşehir": "Başakşehir",
    "bayrampaşa": "Bayrampaşa", "beşiktaş": "Beşiktaş", "beykoz": "Beykoz", "beylikdüzü": "Beylikdüzü",
    "beyoğlu": "Beyoğlu", "büyükçekmece": "Büyükçekmece", "çekmeköy": "Çekmeköy", "esenler": "Esenler",
    "esenyurt": "Esenyurt", "eyüpsultan": "Eyüpsultan", "fatih": "Fatih", "gaziosmanpaşa": "Gaziosmanpaşa",
    "güngören": "Güngören", "kadıköy": "Kadıköy", "kağıthane": "Kağıthane", "kartal": "Kartal",
    "küçükçekmece": "Küçükçekmece", "maltepe": "Maltepe", "pendik": "Pendik", "sancaktepe": "Sancaktepe",
    "sarıyer": "Sarıyer", "silivri": "Silivri", "sultanbeyli": "Sultanbeyli", "sultangazi": "Sultangazi",
    "şile": "Şile", "şişli": "Şişli", "tuzla": "Tuzla", "ümraniye": "Ümraniye", "üsküdar": "Üsküdar",
    "zeytinburnu": "Zeytinburnu"
}

FEATURE_KEYWORDS = [
    ("metro", 15, "Metroya yakın"),
    ("metrobüs", 15, "Metrobüse yakın"),
    ("metrobus", 15, "Metrobüse yakın"),
    ("balkon", 10, "Balkonlu"),
    ("site", 10, "Site içerisinde"),
    ("otopark", 10, "Otoparklı"),
    ("asansör", 8, "Asansörlü"),
    ("eşyalı", 10, "Eşyalı"),
    ("güvenlik", 10, "Güvenlikli"),
    ("deniz manzarası", 12, "Deniz manzaralı"),
    ("krediye uygun", 10, "Krediye uygun"),
]

def parse_query_constraints(q: str):
    q = (q or "").lower()
    district = None
    for key, value in DISTRICT_ALIASES.items():
        if key in q:
            district = value
            break
    m = re.search(r"([1-5])\s*\+\s*([01])", q)
    rooms = f"{m.group(1)}+{m.group(2)}" if m else None
    min_m2 = None
    patterns_m2 = [
        r"(?:en az|min(?:imum)?|üstü|üzeri)\s*(\d{2,4})\s*(?:m2|m²|metrekare)?",
        r"(\d{2,4})\s*(?:m2|m²|metrekare)\s*(?:üstü|üzeri|en az)?",
    ]
    for pat in patterns_m2:
        m = re.search(pat, q)
        if m:
            min_m2 = int(m.group(1))
            break
    max_price = None
    m = re.search(r"(\d{1,3})(?:[\.,](\d{1,3}))?\s*(?:milyon|mn|m\b)", q)
    if m:
        whole = int(m.group(1))
        frac = m.group(2) or ""
        max_price = whole * 1_000_000
        if frac:
            max_price += int(frac) * (10 ** (6 - len(frac)))
    else:
        m = re.search(r"(\d[\d\.,]{5,})", q)
        if m:
            raw = m.group(1).replace(".", "").replace(",", "")
            if raw.isdigit() and len(raw) >= 6:
                max_price = int(raw)
    return {"district": district, "rooms": rooms, "min_m2": min_m2, "max_price": max_price}

# ------------------------------------------------------------
# Ortam değişkenleri
# ------------------------------------------------------------
load_dotenv()
QDRANT_MODE = os.getenv("QDRANT_MODE", "local").strip().lower()
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333").strip()
QDRANT_PATH = os.getenv("QDRANT_PATH", "./qdrant_data").strip()
COLLECTION = os.getenv("QDRANT_COLLECTION", "listings_demo").strip()
EMBED_MODEL = os.getenv("EMBED_MODEL", "intfloat/multilingual-e5-small").strip()
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434").strip().rstrip("/")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "emlak-ozel:latest").strip()

@st.cache_resource
def embedder():
    return SentenceTransformer(EMBED_MODEL)

@st.cache_resource
def qdrant():
    if QDRANT_MODE == "memory": return QdrantClient(":memory:")
    if QDRANT_MODE == "local": return QdrantClient(path=QDRANT_PATH)
    return QdrantClient(url=QDRANT_URL)

# ------------------------------------------------------------
# Qdrant ve Skorlama
# ------------------------------------------------------------
def build_filter(district, rooms, price_max, m2_min):
    cond = []
    if district and district != "Hepsi":
        cond.append(FieldCondition(key="district", match=MatchValue(value=district)))
    if rooms and rooms != "Hepsi":
        cond.append(FieldCondition(key="rooms", match=MatchValue(value=rooms)))
    if price_max is not None and price_max != "" and int(price_max) > 0:
        cond.append(FieldCondition(key="price_try", range=Range(lte=int(price_max))))
    if m2_min is not None and m2_min != "" and int(m2_min) > 0:
        cond.append(FieldCondition(key="gross_m2", range=Range(gte=int(m2_min))))
    return Filter(must=cond) if cond else None

def qdrant_search_safe(collection_name, qvec, limit, qfilter):
    client = qdrant()
    try:
        res = client.search(collection_name=collection_name, query_vector=qvec, limit=limit, query_filter=qfilter)
        return res
    except:
        res = client.query_points(collection_name=collection_name, query=qvec, limit=limit, query_filter=qfilter)
        return res.points

def get_qdrant_status():
    try:
        client = qdrant()
        collections = client.get_collections().collections
        exists = any(c.name == COLLECTION for c in collections)
        if not exists: return False, "Koleksiyon yok", 0
        count = client.count(collection_name=COLLECTION).count
        return True, "Bağlı", count
    except Exception as exc:
        return False, f"Bağlantı hatası: {exc}", 0

def calc_score(user_query: str, payload: dict, district_eff: str, rooms_eff: str, price_eff: int, m2_eff: int):
    score = 0
    why, tradeoffs, red_flags = [], [], []
    district, rooms, m2, price = payload.get("district"), payload.get("rooms"), payload.get("gross_m2"), payload.get("price_try")
    feats_text = " ".join(str(x) for x in payload.get("features") or []).lower()
    text = f"{payload.get('title','')} {payload.get('description_clean','')}".lower()
    q = (user_query or "").lower()

    if district_eff != "Hepsi":
        if (district or "").lower() == district_eff.lower(): score += 25; why.append("İlçe uygun")
        else: tradeoffs.append("İlçe farklı")
    elif district and district.lower() in q: score += 15; why.append("İlçe sorguda")

    if rooms_eff != "Hepsi":
        if (rooms or "").lower() == rooms_eff.lower(): score += 20; why.append("Oda sayısı uygun")
        else: tradeoffs.append("Oda sayısı farklı")
    elif rooms and rooms.lower() in q: score += 10; why.append("Oda sorguda")

    # m²
    if isinstance(m2, (int, float)) and m2_eff:
        if m2 >= m2_eff:
            score += 15
            why.append(f"m² uygun ({fmt_m2(m2)})")
        else:
            tradeoffs.append(f"m² kriterin altında ({fmt_m2(m2)})")
    elif m2 is None:
        red_flags.append("m² bilgisi eksik")

    # Fiyat
    if isinstance(price, (int, float)) and price_eff:
        if price <= price_eff:
            score += 30
            why.append(f"Bütçenize uygun ({fmt_try(price)})")
        else:
            tradeoffs.append(f"Bütçenizi aşıyor ({fmt_try(price)})")
    elif price is None:
        red_flags.append("Fiyat bilgisi eksik")

    for kw, pts, label in FEATURE_KEYWORDS:
        if kw in q and (kw in feats_text or kw in text):
            score += pts; why.append(f"{label} var")
    
    if str(district or "").lower() in {"istanbul", "unknown", "bilinmiyor"}:
        red_flags.append("İlçe alanı temizlenmemiş")

    return max(0, min(100, score)), why[:3], tradeoffs[:2], red_flags[:2]

# ------------------------------------------------------------
# Ollama İşlemleri
# ------------------------------------------------------------
def clean_llm_output(text: str) -> str:
    """Model çıktısını 1-2-3 maddelerine ayırır ve gürültüyü temizler."""
    if not text: return "Açıklama üretilemedi."
    
    # Madde yapılarını (1., 2., 3. veya 1), 2), 3)) yakala
    # Model bazen her şeyi tek satıra koyuyor veya aralara gürültü ekliyor.
    pattern = r"([123][\)\.]\s*[^123\)\|\n]+)"
    matches = re.findall(pattern, text)
    
    if matches:
        cleaned_matches = []
        for m in matches[:3]:
            # Boru işareti (|) ve gereksiz parantezli açıklamaları temizle
            m = m.replace("|", "").strip()
            # Modelin sonuna eklediği "(Bu soruyu Türkçe belirt)" gibi gürültüleri at
            m = re.sub(r"\s*\(.*?\)\s*$", "", m).strip()
            # Eğer madde numarası ile başlamıyorsa (regex bazen tam yakalayamayabilir) ekle
            if cleaned_matches:
                idx = len(cleaned_matches) + 1
                if not m.startswith(str(idx)):
                    m = f"{idx}) {m}"
            cleaned_matches.append(m)
        return "\n".join(cleaned_matches)
    
    # Eğer regex ile madde bulamadıysa klasik satır bazlı temizliğe dön
    text = text.replace("```", "").strip()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines[:3])

def clean_llm_output_strict(text: str, why2=None, trade1=None, payload=None, user_query="") -> str:
    """
    Ollama cevabını temizler.
    Tekrarlanan başlıkları, İngilizce notları, tablo kalıntılarını ve fazla uzayan kısımları keser.
    Kritik soru eksik kalırsa kural tabanlı fallback kullanır.
    """
    if not text:
        text = ""

    text = text.replace("```", "").replace('""', "").strip()
    text = re.sub(r"\s+", " ", text)

    # İngilizce/meta notlardan sonrasını kes
    cut_markers = [
        "# Note to user",
        "Note to user",
        "automated response",
        "generated by an AI",
        "may not",
        "This is",
        "This answer",
        "|",
        "---",
        "Ek belirtisi",
        "4)",
        "5)",
        "6)",
        "##",
    ]

    lower_text = text.lower()
    cut_positions = []

    for marker in cut_markers:
        idx = lower_text.find(marker.lower())
        if idx != -1:
            cut_positions.append(idx)

    if cut_positions:
        text = text[:min(cut_positions)].strip()

    # 1), 2), 3) formatını sadeleştir
    text = re.sub(r"\b1[\).]\s*", "Neden uygun? ", text)
    text = re.sub(r"\b2[\).]\s*", "Dikkat: ", text)
    text = re.sub(r"\b3[\).]\s*", "Kritik soru: ", text)

    # Tekrar eden başlıkları düzelt
    text = text.replace("Neden uygun? Neden uygun?", "Neden uygun?")
    text = text.replace("Dikkat: Dikkat:", "Dikkat:")
    text = text.replace("Kritik soru: Kritik soru:", "Kritik soru:")

    def extract_between(label, next_labels):
        pattern_next = "|".join([re.escape(x) for x in next_labels])
        pattern = rf"{re.escape(label)}\s*(.*?)(?={pattern_next}|$)"
        m = re.search(pattern, text, flags=re.IGNORECASE)
        if not m:
            return None
        value = m.group(1).strip()
        return value if value else None

    neden_val = extract_between("Neden uygun?", ["Dikkat:", "Kritik soru:"])
    dikkat_val = extract_between("Dikkat:", ["Kritik soru:"])
    kritik_val = extract_between("Kritik soru:", [])

    # Kritik soru satırında soru işaretinden sonrasını kes
    if kritik_val:
        q_idx = kritik_val.find("?")
        if q_idx != -1:
            kritik_val = kritik_val[:q_idx + 1].strip()

    # Kritik soru eksik/kırpılmışsa fallback kullan
    if not kritik_val or len(kritik_val) < 15 or "?" not in kritik_val:
        kritik_val = pick_critical_question(payload or {}, user_query)

    # Neden uygun eksikse kural tabanlı fallback
    if not neden_val or len(neden_val) < 5:
        neden_val = " / ".join(why2 or ["Bu ilan bazı temel kriterlerle eşleşiyor."])

    # Dikkat eksikse kural tabanlı fallback
    if not dikkat_val or len(dikkat_val) < 5:
        dikkat_val = " / ".join(trade1 or ["İlan detayları yerinde teyit edilmeli."])

    # Başlık tekrarlarını temizle
    neden_val = neden_val.replace("Neden uygun?", "").strip()
    dikkat_val = dikkat_val.replace("Dikkat:", "").strip()
    kritik_val = kritik_val.replace("Kritik soru:", "").strip()

    return (
        f"Neden uygun? {neden_val}\n"
        f"Dikkat: {dikkat_val}\n"
        f"Kritik soru: {kritik_val}"
    )

def pick_critical_question(payload: dict, user_query: str = "") -> str:
    title = str(payload.get("title") or "").lower()
    desc = str(payload.get("description_clean") or payload.get("description") or "").lower()
    features = " ".join(map(str, payload.get("features") or [])).lower()
    text = f"{title} {desc} {features}"
    q = (user_query or "").lower()

    if "dubleks" in text or "teras" in text:
        return "Terasın tapuya işli olup olmadığı ve dubleks kullanım alanının ruhsata uygunluğu doğrulanabilir mi?"

    if "kredi" in text or "krediye uygun" in text:
        return "Krediye uygunluk banka ekspertiziyle doğrulanmış mı?"

    if "bahçe katı" in text or "giriş" in text or "zemin" in text:
        return "Dairenin rutubet, yalıtım ve güvenlik durumu yerinde kontrol edildi mi?"

    if "site" in text or "güvenlik" in text or "otopark" in text:
        return "Aidat ne kadar ve otopark/güvenlik hizmetleri aktif mi?"

    if "metro" in text or "metrobüs" in text or "ulaşım" in text:
        return "Toplu taşıma mesafesi gerçekten yürüyüş mesafesinde mi?"

    if "sıfır" in text or "yeni" in text or "iskan" in text:
        return "İskan durumu, tapu tipi ve yapı kullanım izin belgesi net mi?"

    if "yatırım" in text or "kiracılı" in text or "kira" in text:
        return "Mevcut kira getirisi ve kiracı durumu resmi belgelerle doğrulanabilir mi?"

    if "2+1" in text or "3+1" in text:
        return "Dairenin net m²’si kaç ve oda kullanımı ilandaki bilgilerle uyumlu mu?"

    return "Tapu durumu, iskan ve bina yaşı net olarak doğrulanabilir mi?"

def build_smart_reason(payload: dict, why2=None) -> str:
    title = str(payload.get("title") or "").lower()
    desc = str(payload.get("description_clean") or payload.get("description") or "").lower()
    features = " ".join(map(str, payload.get("features") or [])).lower()
    text = f"{title} {desc} {features}"

    district = payload.get("district") or "belirtilen bölge"
    rooms = payload.get("rooms") or "belirtilen oda tipi"
    m2 = payload.get("gross_m2")
    price = payload.get("price_try")

    reasons = []

    if "metro" in text or "metrobüs" in text:
        reasons.append("ulaşıma yakın olması günlük kullanım açısından güçlü bir avantaj sağlıyor")

    if "balkon" in text:
        reasons.append("balkon detayı daireyi yaşam konforu açısından daha kullanışlı hale getiriyor")

    if "güney cephe" in text or "ön cephe" in text or "önü açık" in text:
        reasons.append("cephe ve açıklık bilgisi aydınlık/ferah kullanım beklentisi açısından olumlu görünüyor")

    if "içi yenilenmiş" in text or "yenilenmiş" in text or "yeni" in text:
        reasons.append("yenilenmiş/yeni durumu ekstra masraf ihtimalini azaltabilecek olumlu bir detay olarak öne çıkıyor")

    if "iskanlı" in text or "iskan" in text:
        reasons.append("iskan bilgisinin belirtilmiş olması tapu ve kullanım süreci açısından önemli bir avantaj olabilir")

    if "ebeveyn" in text or "ebv" in text:
        reasons.append("ebeveyn banyosu gibi ek kullanım alanları aile yaşamı için pratiklik sağlayabilir")

    if "teras" in text or "dubleks" in text:
        reasons.append("teras/dubleks yapısı standart dairelere göre daha geniş ve farklı kullanım imkânı sunabilir")

    if "site" in text:
        reasons.append("site içerisinde olması güvenlik, düzen ve sosyal kullanım açısından avantaj sağlayabilir")

    if "otopark" in text:
        reasons.append("otopark bilgisinin bulunması araç kullananlar için önemli bir kolaylık sağlar")

    if "merkezi" in text or "merkezi konum" in text:
        reasons.append("merkezi konumu günlük ulaşım ve çevre olanaklarına erişim açısından güçlü bir artı oluşturuyor")

    if "hastane" in text or "okul" in text or "central" in text:
        reasons.append("sosyal donatılara yakınlık günlük yaşamı kolaylaştırabilecek bir unsur olarak görünüyor")

    # Kural tabanlı eşleşmeleri daha doğal hale getir
    rule_text = " / ".join(why2 or [])

    if "İlçe uygun" in rule_text:
        reasons.insert(0, f"{district} konumunda olması kullanıcının bölge beklentisiyle uyumlu görünüyor")

    if "Oda sayısı uygun" in rule_text:
        reasons.append(f"{rooms} oda yapısı kullanıcının aradığı daire tipiyle örtüşüyor")

    if "m² uygun" in rule_text and m2:
        reasons.append(f"{m2} m² büyüklüğü belirtilen minimum alan beklentisini karşılıyor")

    if "Bütçenize uygun" in rule_text and price:
        reasons.append(f"fiyatının belirlenen bütçe sınırında kalması seçeneği daha erişilebilir hale getiriyor")

    if not reasons:
        reasons = ["ilan, kullanıcının temel arama kriterleriyle genel olarak uyumlu görünüyor"]

    # Aynı tarz tekrarları engelle ve en fazla 3 güçlü nedeni kullan
    unique_reasons = []
    for r in reasons:
        if r not in unique_reasons:
            unique_reasons.append(r)

    selected = unique_reasons[:3]

    if len(selected) == 1:
        return selected[0]

    if len(selected) == 2:
        return f"{selected[0]}. Ayrıca {selected[1]}"

    return f"{selected[0]}. Ayrıca {selected[1]}. Bunun yanında {selected[2]}"

def ollama_short_explain(user_query: str, payload: dict, rule_score: int, why2, trade1, red1):
    questions = [
        "Aidat ne kadar ve otopark/güvenlik var mı?",
        "Tapu durumu nedir (kat mülkiyeti/kat irtifakı) ve iskan var mı?",
        "Deprem yönetmeliğine uygunluk ve bina yaşı doğrulanabilir mi?",
        "Dairenin net m²’si kaç ve brüt/net farkı nedir?",
        "Evin ısınma tipi ve aylık ortalama giderler nedir?"
    ]
    feats = ", ".join(payload.get("features") or []) or "Belirtilmemiş"
    smart_reason = build_smart_reason(payload, why2)
    critical_question = pick_critical_question(payload, user_query)

    if trade1:
        dikkat_text = " / ".join(trade1)
    else:
        dikkat_text = "İlan detayları yerinde teyit edilmeli."
    prompt = f"""
    Sen profesyonel bir emlak danışmanısın.
    Aşağıdaki ilana özel, kısa ve doğal bir Türkçe yorum yaz.

    Kullanıcı isteği:
    {user_query}

    İlan başlığı:
    {payload.get('title')}

    Konum:
    {payload.get('district')}

    Oda:
    {payload.get('rooms')}

    m²:
    {payload.get('gross_m2')}

    Öne çıkarılacak özel neden:
    {smart_reason}

    Dikkat edilmesi gereken nokta:
    {dikkat_text}

    Kritik soru:
    {critical_question}

    Kesin format:
    1) Neden uygun? {smart_reason}.
    2) Dikkat: {dikkat_text}
    3) Kritik soru: {critical_question}

    Sadece bu 3 satırı yaz. Başka hiçbir şey ekleme.
    """.strip()

    options = {
        "temperature": 0,
        "num_predict": 90,
        "repeat_penalty": 1.35,
        "top_p": 0.7,
        "stop": [
            "\n4)",
            "4)",
            "Ek belirtisi",
            "```",
            "# Note to user",
            "Note to user",
            "automated response",
            "generated by an AI",
            "may not",
            "##",
            "\n\n\n"
        ]
    }





    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "options": options
            },
            timeout=180
        )
        r.raise_for_status()

        raw_response = r.json().get("response", "").strip()

        cleaned = clean_llm_output_strict(
            raw_response,
            why2=[smart_reason],
            trade1=[dikkat_text],
            payload=payload,
            user_query=user_query
        )

        # Model yine genel cevap üretirse 1. ve 3. satırı ilanın gerçek içeriğine göre zorla
        lines = cleaned.splitlines()

        neden_line = f"Neden uygun? {smart_reason}"
        dikkat_line = f"Dikkat: {dikkat_text}"
        kritik_line = f"Kritik soru: {critical_question}"

        return "\n".join([neden_line, dikkat_line, kritik_line])

    except Exception as e:
        return f"Açıklama şu an üretilemiyor: {type(e).__name__}: {e}"
# ------------------------------------------------------------
# UI
# ------------------------------------------------------------
st.set_page_config(page_title="Emlak Öneri Asistanı", page_icon="🏠", layout="wide")
st.title("🏠 Gerçek Zamanlı Emlak Öneri Asistanı")

with st.sidebar:
    st.header("Sistem Durumu")
    q_ok, q_msg, q_count = get_qdrant_status()
    if q_ok: st.success(f"Qdrant: {q_msg} ({q_count} ilan)")
    else: st.error(f"Qdrant: {q_msg}")
    
    if st.button("Ollama Test Et"):
        with st.spinner("Test ediliyor..."):
            try:
                res = requests.post(f"{OLLAMA_URL}/api/generate", json={"model": OLLAMA_MODEL, "prompt": "Merhaba, sadece 'Bağlantı başarılı' yaz.", "stream": False, "options": {"num_predict": 10}}, timeout=30)
                st.success(res.json().get("response").strip())
            except: st.error("Ollama bağlantı hatası!")

    st.divider()
    user_query = st.text_area("İsteğinizi yazın", "Kadıköy'de 3+1, balkonlu, 3 milyon TL altı.", height=100)
    district = st.selectbox("İlçe", ["Hepsi", "Kadıköy", "Beşiktaş", "Şişli", "Üsküdar", "Ataşehir", "Bakırköy", "Maltepe"])
    rooms = st.selectbox("Oda", ["Hepsi", "1+1", "2+1", "3+1", "4+1"])
    price_max = st.number_input("Maks Fiyat (TL)", value=3000000, step=100000)
    m2_min = st.number_input("Min m²", value=100, step=10)
    use_llm = st.checkbox("LLM Açıklaması", value=True)
    go = st.button("🔎 Ara")

if go:
    parsed = parse_query_constraints(user_query)
    d_eff = district if district != "Hepsi" else (parsed["district"] or "Hepsi")
    r_eff = rooms if rooms != "Hepsi" else (parsed["rooms"] or "Hepsi")
    p_eff = price_max if price_max > 0 else (parsed["max_price"] or 0)
    m_eff = m2_min if m2_min > 0 else (parsed["min_m2"] or 0)

    with st.spinner("Vektör araması yapılıyor..."):
        qvec = embedder().encode([user_query], normalize_embeddings=True)[0].tolist()
        qf = build_filter(d_eff, r_eff, p_eff, m_eff)
        hits = qdrant_search_safe(COLLECTION, qvec, 10, qf)

    if not hits:
        st.warning("Sonuç bulunamadı. Filtreleri gevşetmeyi deneyin.")
        st.stop()

    candidates = []
    for h in hits:
        p = h.payload or {}
        rule_score, why, trade, red = calc_score(user_query, p, d_eff, r_eff, p_eff, m_eff)
        candidates.append({"payload": p, "score": rule_score, "why": why, "trade": trade, "red": red})
    
    candidates = sorted(candidates, key=lambda x: x["score"], reverse=True)

    col1, col2 = st.columns([1, 1], gap="medium")
    with col1:
        st.subheader("İlan Listesi")
        for c in candidates[:10]:
            p = c["payload"]
            title = p.get('title')
            if not title or str(title).lower() == "unknown":
                title = "İsimsiz İlan"
            
            st.markdown(f"**{title}**")
            
            # Konum ve Temel Bilgiler
            district = p.get("district") or "Bilinmiyor"
            neighborhood = p.get("neighborhood")

            loc_str = f"📍 İstanbul / {district}"

            if neighborhood and str(neighborhood).lower() not in ["unknown", "bilinmiyor", "none", "null", ""]:
                loc_str += f" / {neighborhood}"

            st.write(loc_str)
            
            st.write(f"🏠 {p.get('rooms', '?-?')} | 📐 {fmt_m2(p.get('gross_m2'))} | 💰 **{fmt_try(p.get('price_try'))}**")
            
            # Özellikler (Mini liste)
            feats = p.get('features') or []
            source_url = p.get("source_url")
            if source_url and str(source_url).strip().lower() not in ["unknown", "none", "null", ""]:
                st.markdown(f"[🔗 İlanı Aç]({source_url})")

            # Özellikler (Mini liste)
            feats = p.get('features') or []
            if feats:
                st.caption("✨ " + " • ".join(map(str, feats[:5])))
            st.divider()

    with col2:
        st.subheader("Asistan Yorumu")
        for c in candidates[:5]:
            p = c["payload"]
            title = p.get('title')
            if not title or str(title).lower() == "unknown":
                title = "İsimsiz İlan"
            st.markdown(f"**{title}**")
            st.write(f"Uygunluk Skoru: %{c['score']}")
            
            if use_llm:
                with st.spinner("Yapay zeka yorumluyor..."):
                    text = ollama_short_explain(user_query, p, c["score"], c["why"], c["trade"], c["red"])
                    if text and text.strip():
                        st.info(text)
                    else:
                        st.warning("Model anlamlı bir yanıt üretemedi.")
            else:
                st.write("**Nedenler:**")
                for w in c["why"]:
                    st.write(f"- {w}")
            st.divider()
