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
