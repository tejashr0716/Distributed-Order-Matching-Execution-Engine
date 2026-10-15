from fastapi import APIRouter, HTTPException
from datetime import datetime
from ..services.matching_engine_wrapper import matching_engine
from ..services.database_service import db_service
from ..services.redis_service import redis_service

router = APIRouter(prefix="", tags=["Market Data"])

@router.get("/depth/{symbol}")
async def get_orderbook_depth(symbol: str = "BTC-USD", limit: int = 20):
    # Try Redis cached snapshot first
    cached = await redis_service.get_depth_snapshot(symbol)
    if cached:
        return cached
    
    # Read from in-memory C++ engine
    depth = matching_engine.get_market_depth(symbol, max_depth=limit)
    depth["timestamp"] = datetime.utcnow().isoformat()
    return depth

@router.get("/trades/{symbol}")
async def get_recent_trades(symbol: str = "BTC-USD", limit: int = 50):
    trades = await db_service.get_recent_trades(symbol, limit)
    return {"symbol": symbol, "count": len(trades), "trades": trades}

@router.get("/ticker/{symbol}")
async def get_market_ticker(symbol: str = "BTC-USD"):
    ticker = await redis_service.get_ticker(symbol)
    depth = matching_engine.get_market_depth(symbol, max_depth=1)
    ticker["best_bid"] = depth["best_bid"]
    ticker["best_ask"] = depth["best_ask"]
    ticker["mid_price"] = depth["mid_price"]
    ticker["spread"] = depth["spread"]
    ticker["timestamp"] = datetime.utcnow().isoformat()
    return ticker
