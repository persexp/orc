Proje Özeti
Kullanıcı doğal dille yazıyor → API metni import / transaction / query / other olarak sınıflandırıp yapılandırılmış JSON döndürüyor.
“Mevcut değer ne?”, “kaç para?” gibi kısa Türkçe sorular emniyet kemeri regex’leriyle query.topic="portfolio_value" olarak yakalanıyor.
Backend: FastAPI (Python)
LLM: OpenAI (gpt-4o-mini) — JSON moduyla katı JSON üretimi.
Çalıştırma: Uvicorn
Geliştirme: Cursor ile otomatik kurulum & koşturma.
🧭 Cursor’a Talimat (yüksek seviye plan)
Cursor, aşağıdaki adımları sırasıyla uygula:
Projeyi oluştur: portfolio-intent/ klasörü.
Aşağıdaki dosyaları ve içerikleri oluştur (birebir).
Sanal ortam kur, bağımlılıkları yükle.
.env dosyası oluştur; anahtarları kullanıcı girecek.
Uvicorn ile lokalde çalıştır (http://localhost:8080).
Aşağıdaki curl testlerini çalıştır ve çıktıları göster.
Hata olursa düzeltme öner ve tekrar dene.
📁 Proje Yapısı (hedef)
portfolio-intent/
├─ app.py
├─ prompts.py
├─ schemas.py
├─ requirements.txt
├─ .env.example
├─ run.sh
└─ README.md
📄 Dosyalar ve İçerikleri
Cursor, aşağıdaki içerikleri aynen ilgili dosyalara yaz.
requirements.txt
fastapi==0.115.0
uvicorn[standard]==0.30.6
python-dotenv==1.0.1
openai==1.47.0
pydantic==2.8.2
pytz==2024.2
.env.example
# .env dosyasına kopyalayın ve doldurun
OPENAI_API_KEY=sk-...
PORT=8080
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
prompts.py
SYSTEM_PROMPT = """
You are an API intent router for a portfolio app.
Output ONLY valid JSON, no additional prose.

Decide if user's message is one of:
- "import": bulk portfolio transfer (list of holdings/cash)
- "transaction": single action (BUY/SELL/ADD/REMOVE)
- "query": asking current state/value/positions/P&L/allocation
- "other": smalltalk or unsupported

Normalize but NEVER hallucinate. If unsure, leave fields empty.
Units: share | coin | gram | ounce | lot. Currency like USD, TRY, EUR.
Timezone: Europe/Istanbul. Timestamps must be ISO-8601.
Always include a confidence in [0,1].
"""

USER_GUIDE = """
Examples:

"Mevcut değerim ne?":
{
  "intent":"query",
  "confidence":0.92,
  "query":{"topic":"portfolio_value","asOf":"now"}
}

"Şu an toplam portföy değeri (TL bazında) nedir?":
{
  "intent":"query",
  "confidence":0.92,
  "query":{"topic":"portfolio_value","asOf":"now","currencyHint":"TRY"}
}

"Bugün portföyüm kaç para eder?":
{
  "intent":"query",
  "confidence":0.90,
  "query":{"topic":"portfolio_value","asOf":"now"}
}

"Portföyüme 10 AAPL ekle 182.35'ten":
{
  "intent":"transaction",
  "confidence":0.86,
  "transaction":{"op":"ADD","symbol":"AAPL","qty":10,"price":182.35,"currency":"USD","unit":"share","ts":"<now-iso>"}
}

"3 gram altın ekle 3500 TL/gram":
{
  "intent":"transaction",
  "confidence":0.84,
  "transaction":{"op":"ADD","symbol":"XAU","qty":3,"price":3500,"currency":"TRY","unit":"gram","ts":"<now-iso>"}
}

"Aşağıdaki portföyümü içeri aktar: 5 AAPL, 0.2 BTC, 2000 USD nakit":
{
  "intent":"import",
  "confidence":0.90,
  "importPayload":{
    "items":[
      {"symbol":"AAPL","qty":5,"unit":"share","currency":"USD"},
      {"symbol":"BTC","qty":0.2,"unit":"coin","currency":"USD"}
    ],
    "cash":[{"currency":"USD","amount":2000}]
  }
}
"""
schemas.py
from pydantic import BaseModel, Field
from typing import Optional, List, Literal

Intent = Literal["import", "transaction", "query", "other"]
Op = Literal["BUY", "SELL", "ADD", "REMOVE"]

class Transaction(BaseModel):
    op: Optional[Op] = None
    symbol: Optional[str] = None
    qty: Optional[float] = None
    price: Optional[float] = None
    currency: Optional[str] = None
    unit: Optional[str] = None  # share | coin | gram | ounce | lot
    ts: Optional[str] = None     # ISO-8601

class ImportItem(BaseModel):
    symbol: Optional[str] = None
    qty: Optional[float] = None
    avgPrice: Optional[float] = None
    currency: Optional[str] = None
    unit: Optional[str] = None

class ImportCash(BaseModel):
    currency: str
    amount: float

class ImportPayload(BaseModel):
    items: Optional[List[ImportItem]] = None
    cash: Optional[List[ImportCash]] = None

class QueryPayload(BaseModel):
    topic: Optional[str] = None        # portfolio_value | positions | pnl | allocation | ...
    asOf: Optional[str] = None         # now | ISO-8601 | last_close
    currencyHint: Optional[str] = None # TRY | USD | ...

class IntentResult(BaseModel):
    intent: Intent = "other"
    confidence: float = Field(0, ge=0, le=1)
    transaction: Optional[Transaction] = None
    importPayload: Optional[ImportPayload] = None
    query: Optional[QueryPayload] = None
    notes: Optional[str] = None

class RouteRequest(BaseModel):
    message: str

class RouteResponse(BaseModel):
    ok: bool
    result: Optional[IntentResult] = None
    error: Optional[str] = None
app.py
import json
import os
import re
from datetime import datetime
import pytz
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from schemas import RouteRequest, RouteResponse, IntentResult, QueryPayload
from prompts import SYSTEM_PROMPT, USER_GUIDE

load_dotenv()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY missing in environment")

client = OpenAI(api_key=OPENAI_API_KEY)

IST = pytz.timezone("Europe/Istanbul")

app = FastAPI(title="Portfolio Intent Router")

# CORS
allowed_origins = os.getenv("ALLOWED_ORIGINS", "*")
origins = [o.strip() for o in allowed_origins.split(",")] if allowed_origins else ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def now_iso_istanbul() -> str:
    return datetime.now(IST).isoformat(timespec="seconds")

def force_json(text: str) -> dict:
    try:
        return json.loads(text)
    except Exception:
        start = text.find("{"); end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(text[start:end+1])
        raise ValueError("Model did not return valid JSON")

# Kısa TR sorular için emniyet kemeri (portfolio_value)
VALUE_PATTERNS = [
    r"\bmevcut değer(im)?\b",
    r"\btoplam (portföy )?değer(i|im)?\b",
    r"\bkaç para\b",
    r"\bşu an (portföy )?ne kadar\b",
    r"\bbugün (portföy )?değer(i|im)?\b",
]

def maybe_force_portfolio_value(user_text: str, result: IntentResult) -> IntentResult:
    txt = user_text.lower()
    if any(re.search(p, txt) for p in VALUE_PATTERNS):
        if result.intent != "query" or not result.query or not result.query.topic:
            result.intent = "query"
            qp = (result.query.model_dump() if result.query else {})
            qp = {**qp, "topic": "portfolio_value", "asOf": qp.get("asOf") or "now"}
            if " tl" in txt or " tl?" in txt or "tl " in txt or "tl?" in txt:
                qp["currencyHint"] = "TRY"
            result.query = QueryPayload(**qp)
        if result.confidence < 0.75:
            result.confidence = 0.85
    return result

@app.post("/route-intent", response_model=RouteResponse)
def route_intent(payload: RouteRequest):
    user_text = payload.message.strip()
    if not user_text:
        raise HTTPException(status_code=400, detail="message required")

    model_name = "gpt-4o-mini"  # kalite/maliyet dengesi

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_GUIDE},
        {"role": "user", "content": (
            "Now, the user's message is:\n"
            f"{user_text}\n"
            f"- If time is needed, use this ISO now (Europe/Istanbul): {now_iso_istanbul()}.\n"
            "Return ONLY JSON."
        )},
    ]

    try:
        completion = client.chat.completions.create(
            model=model_name,
            messages=messages,
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        raw = completion.choices[0].message.content or "{}"
        data = force_json(raw)

        result = IntentResult.model_validate(data)
        result = maybe_force_portfolio_value(user_text, result)

        return RouteResponse(ok=True, result=result)

    except Exception as e:
        return RouteResponse(ok=False, error=str(e))
run.sh
#!/usr/bin/env bash
set -e
export PYTHONUNBUFFERED=1
export PORT=${PORT:-8080}
uvicorn app:app --host 0.0.0.0 --port $PORT --reload
README.md
# Portfolio Intent Router (FastAPI + OpenAI)

Doğal dil mesajlarını "import | transaction | query | other" olarak sınıflandırıp yapılandırılmış JSON döndürür.

## Kurulum

1) .env oluştur
cp .env.example .env
OPENAI_API_KEY değerini gir

2) Sanal ortam & bağımlılıklar
python -m venv .venv
source .venv/bin/activate # Windows: .venv\Scripts\activate
pip install -r requirements.txt

3) Çalıştır
bash run.sh
Varsayılan: http://localhost:8080

## Test

curl -s http://localhost:8080/route-intent
-H "Content-Type: application/json"
-d '{"message":"mevcut değer ne?"}' | jq

Beklenen: `intent=query`, `query.topic=portfolio_value`.

curl -s http://localhost:8080/route-intent
-H "Content-Type: application/json"
-d '{"message":"Portföyüme 3 gram altın ekle 3500 TL/gram"}' | jq

Beklenen: `intent=transaction`, op=ADD, symbol=XAU, unit=gram, currency=TRY.

## Notlar
- JSON zorlaması aktif (`response_format`) + Pydantic doğrulama.
- Europe/Istanbul ISO zaman biçimi sağlanır.
- Kısa TR sorular regex fallback ile `portfolio_value`'a yönlendirilir.
▶️ Kurulum & Çalıştırma (Cursor uygulasın)
Cursor, terminalde şu komutları çalıştır:
# 1) .env dosyası
cp .env.example .env
# .env içindeki OPENAI_API_KEY=... değerini düzenle

# 2) Sanal ortam & bağımlılıklar
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3) Sunucuyu çalıştır
bash run.sh
# Uvicorn running on http://0.0.0.0:8080
Testler:
curl -s http://localhost:8080/route-intent \
 -H "Content-Type: application/json" \
 -d '{"message":"mevcut değer ne?"}' | jq

curl -s http://localhost:8080/route-intent \
 -H "Content-Type: application/json" \
 -d '{"message":"Portföyüme 10 AAPL ekle 182.35ten"}' | jq
🧩 Sorun Giderme
401 / API Key: .env içinde OPENAI_API_KEY dolu mu? Terminalde echo $OPENAI_API_KEY ile doğrula (Windows: echo %OPENAI_API_KEY%).
CORS: Frontend’ten istek atacaksan ALLOWED_ORIGINS’e domain’i ekle.
Bağımlılık hatası: pip install -r requirements.txt tekrar çalıştır; Python sürümü 3.10+ olmalı.
Windows’ta run.sh: PowerShell’de uvicorn app:app --host 0.0.0.0 --port 8080 --reload çalıştır.
🚀 Sonraki Adımlar (isteğe bağlı)
POST /apply-transaction (Firestore’a yaz)
GET /portfolio-snapshot (holdings/transactions oku)
GET /prices?symbols=... (Alpha Vantage/Finnhub/CoinGecko)
POST /answer (snapshot + prices → toplam değer; LLM’ye doğal özetlettir)
OpenAI function calling ile applyTransaction/getPortfolio gibi araç çağrıları