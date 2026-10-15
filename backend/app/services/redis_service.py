import json
import logging
import redis.asyncio as aioredis
from typing import Optional, Dict, Any
from ..config import settings

logger = logging.getLogger("ApexMatch.Redis")

class RedisService:
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None

    async def connect(self):
        if not self.redis:
            try:
                self.redis = aioredis.from_url(
                    settings.REDIS_URL,
                    decode_responses=True,
                    max_connections=20
                )
                await self.redis.ping()
                logger.info("Connected to Redis successfully.")
            except Exception as e:
                logger.warning(f"Redis connection warning: {e}. Running with mock cache.")
                self.redis = None

    async def disconnect(self):
        if self.redis:
            await self.redis.close()
            self.redis = None

    async def publish_depth_update(self, symbol: str, depth_data: Dict[str, Any]):
        if self.redis:
            try:
                payload = json.dumps(depth_data)
                await self.redis.publish(f"depth:{symbol}", payload)
                await self.redis.set(f"snapshot:depth:{symbol}", payload, ex=3600)
            except Exception as e:
                logger.error(f"Error publishing depth to Redis: {e}")

    async def publish_trade(self, symbol: str, trade_data: Dict[str, Any]):
        if self.redis:
            try:
                payload = json.dumps(trade_data, default=str)
                await self.redis.publish(f"trades:{symbol}", payload)
                # Append to recent trades list in Redis
                await self.redis.lpush(f"tape:{symbol}", payload)
                await self.redis.ltrim(f"tape:{symbol}", 0, 199)
            except Exception as e:
                logger.error(f"Error publishing trade to Redis: {e}")

    async def update_ticker(self, symbol: str, price: float, quantity: float):
        if self.redis:
            try:
                key = f"ticker:{symbol}"
                pipe = self.redis.pipeline()
                pipe.hset(key, "last_price", str(price))
                pipe.hincrbyfloat(key, "volume_24h", quantity)
                pipe.hincrby(key, "trades_count", 1)
                await pipe.execute()
            except Exception as e:
                logger.error(f"Error updating ticker in Redis: {e}")

    async def get_depth_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        if self.redis:
            try:
                data = await self.redis.get(f"snapshot:depth:{symbol}")
                if data:
                    return json.loads(data)
            except Exception as e:
                logger.error(f"Error getting depth snapshot from Redis: {e}")
        return None

    async def get_ticker(self, symbol: str) -> Dict[str, Any]:
        if self.redis:
            try:
                key = f"ticker:{symbol}"
                data = await self.redis.hgetall(key)
                if data:
                    return {
                        "symbol": symbol,
                        "last_price": float(data.get("last_price", 0.0)),
                        "volume_24h": float(data.get("volume_24h", 0.0)),
                        "trades_count": int(data.get("trades_count", 0)),
                    }
            except Exception as e:
                logger.error(f"Error getting ticker from Redis: {e}")
        return {"symbol": symbol, "last_price": 0.0, "volume_24h": 0.0, "trades_count": 0}

redis_service = RedisService()
