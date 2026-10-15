from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class TradeExecutionSchema(BaseModel):
    match_id: int
    symbol: str
    buyer_order_id: int
    seller_order_id: int
    buyer_client_id: str
    seller_client_id: str
    price: float
    quantity: float
    quote_amount: float
    taker_side: str
    latency_ns: int
    executed_at: datetime

class DepthLevel(BaseModel):
    price: float
    volume: float
    order_count: int

class Level2DepthResponse(BaseModel):
    symbol: str
    mid_price: float
    spread: float
    bids: List[DepthLevel]
    asks: List[DepthLevel]
    timestamp: datetime

class MarketStatsResponse(BaseModel):
    symbol: str
    last_price: float
    high_24h: float
    low_24h: float
    volume_24h: float
    trades_count: int
    timestamp: datetime
