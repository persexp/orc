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
