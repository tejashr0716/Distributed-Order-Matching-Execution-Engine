from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum
from datetime import datetime

class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    LIMIT = "LIMIT"
    MARKET = "MARKET"

class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    FOK = "FOK"

class OrderStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"

class OrderCreate(BaseModel):
    client_id: str = Field(..., example="TRADER_ALICE")
    symbol: str = Field(default="BTC-USD", example="BTC-USD")
    side: OrderSide = Field(..., example=OrderSide.BUY)
    type: OrderType = Field(default=OrderType.LIMIT, example=OrderType.LIMIT)
    tif: TimeInForce = Field(default=TimeInForce.GTC, example=TimeInForce.GTC)
    price: float = Field(..., gt=0, example=65000.50)
    quantity: float = Field(..., gt=0, example=0.5)

class ExecutionFill(BaseModel):
    match_id: int
    maker_order_id: int
    taker_order_id: int
    price: float
    quantity: float
    side: str
    status: str
    latency_ns: int
    timestamp_ns: int

class OrderResponse(BaseModel):
    order_id: int
    client_id: str
    symbol: str
    side: str
    type: str
    tif: str
    price: float
    quantity: float
    filled_quantity: float
    remaining_quantity: float
    status: str
    fills: List[ExecutionFill] = []
    engine_latency_ns: int
    created_at: datetime

class OrderCancelResponse(BaseModel):
    order_id: int
    success: bool
    status: str
    cancelled_quantity: float
    latency_ns: int
    message: str
