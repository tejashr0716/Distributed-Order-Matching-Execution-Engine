import json
import logging
import asyncio
import aio_pika
from typing import Optional, Dict, Any
from ..config import settings

logger = logging.getLogger("ApexMatch.RabbitMQ")

class RabbitMQService:
    def __init__(self):
        self.connection: Optional[aio_pika.RobustConnection] = None
        self.channel: Optional[aio_pika.RobustChannel] = None
        self.exchange: Optional[aio_pika.RobustExchange] = None
        self._fallback_queue: asyncio.Queue = asyncio.Queue()

    async def connect(self):
        try:
            self.connection = await aio_pika.connect_robust(
                settings.RABBITMQ_URL,
                timeout=10.0
            )
            self.channel = await self.connection.channel()
            await self.channel.set_qos(prefetch_count=50)

            # Declare exchange
            self.exchange = await self.channel.declare_exchange(
                settings.RABBITMQ_EXCHANGE_TRADES,
                aio_pika.ExchangeType.TOPIC,
                durable=True
            )

            # Declare queues
            settlement_q = await self.channel.declare_queue(
                settings.RABBITMQ_QUEUE_SETTLEMENT,
                durable=True
            )
            audit_q = await self.channel.declare_queue(
                settings.RABBITMQ_QUEUE_AUDIT,
                durable=True
            )

            # Bind queues
            await settlement_q.bind(self.exchange, routing_key="trade.executed")
            await audit_q.bind(self.exchange, routing_key="trade.#")

            logger.info("Connected to RabbitMQ trade exchange and queues declared.")
        except Exception as e:
            logger.warning(f"RabbitMQ connection failed: {e}. Running with internal memory queue fallback.")
            self.connection = None
            self.channel = None
            self.exchange = None

    async def disconnect(self):
        if self.connection:
            await self.connection.close()
            self.connection = None
            self.channel = None
            self.exchange = None

    async def publish_trade_execution(self, trade_event: Dict[str, Any]):
        payload = json.dumps(trade_event, default=str)
        if self.exchange and self.channel and not self.channel.is_closed:
            try:
                message = aio_pika.Message(
                    body=payload.encode("utf-8"),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type="application/json"
                )
                await self.exchange.publish(message, routing_key="trade.executed")
                return True
            except Exception as e:
                logger.error(f"Error publishing to RabbitMQ: {e}")
        
        # Enqueue to internal fallback
        await self._fallback_queue.put(trade_event)
        return True

    async def get_fallback_queue(self) -> asyncio.Queue:
        return self._fallback_queue

rabbitmq_service = RabbitMQService()
