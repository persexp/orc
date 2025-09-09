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
