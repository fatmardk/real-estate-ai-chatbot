import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2:3b")

def check_ollama():
    print(f"[Ollama Kontrol] URL: {OLLAMA_URL}")
    print(f"[Ollama Kontrol] Hedef Model: {OLLAMA_MODEL}")
    
    # 1. Servis ayakta mı ve model yüklü mü kontrolü
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=15)
        response.raise_for_status()
        data = response.json()
        models = [m["name"] for m in data.get("models", [])]
        
        if not models:
            print("[!] Ollama çalışıyor ama hiç model yüklü değil.")
            return False
            
        print(f"[✓] Yüklü Modeller: {', '.join(models)}")
        
        # Tam eşleşme veya model adı ile başlayan eşleşme ara
        model_found = any(m == OLLAMA_MODEL or m.startswith(f"{OLLAMA_MODEL}:") for m in models)
        
        if not model_found:
            print(f"[!] HATA: Hedef model '{OLLAMA_MODEL}' yüklü değil!")
            print(f"    Lütfen terminalde şu komutu çalıştırın: ollama run {OLLAMA_MODEL}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"[!] HATA: Ollama servisine erişilemiyor ({OLLAMA_URL}).")
        print(f"    Detay: {e}")
        return False

    # 2. Üretim (Generation) Testi
    print("\n[Ollama Kontrol] Üretim testi başlatılıyor...")
    prompt = "Merhaba, sadece 'Sistem çalışıyor' yaz."
    try:
        r = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": "Sadece şu cümleyi yaz: Sistem çalışıyor.",
                "stream": False,
                "options": {
                    "temperature": 0,
                    "num_predict": 20,
                    "top_p": 0.7,
                    "repeat_penalty": 1.35,
                    "stop": [
                        "\n",
                        "1)",
                        "2)",
                        "3)",
                        "İlan bilgileri",
                        "Neden uygun",
                        "Ek belirtisi",
                        "Kritik soru"
                    ]
                }
            },
            timeout=60
        )
        r.raise_for_status()
        result = r.json().get("response", "").strip()
        print(f"[✓] Başarılı! Yanıt: {result}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"[!] HATA: Model yanıt veremedi veya zaman aşımına uğradı.")
        print(f"    Detay: {e}")
        return False

if __name__ == "__main__":
    check_ollama()
