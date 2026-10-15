import asyncio
import json
import logging
import os
import signal
from backend.app.config import settings
from backend.app.services.database_service import db_service
from backend.app.services.rabbitmq_service import rabbitmq_service

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [SettlementWorker] %(message)s")
logger = logging.getLogger("SettlementWorker")

class SettlementWorker:
    def __init__(self):
        self.running = True

    async def start(self):
        logger.info("Initializing ApexMatch Clearing & Settlement Worker...")
        await db_service.connect()
        await rabbitmq_service.connect()

        # If RabbitMQ connection is available, consume from the queue
        if rabbitmq_service.channel:
            queue = await rabbitmq_service.channel.get_queue(settings.RABBITMQ_QUEUE_SETTLEMENT)
            logger.info(f"Consuming trade executions from RabbitMQ queue: {settings.RABBITMQ_QUEUE_SETTLEMENT}")
            
            async with queue.iterator() as queue_iter:
                async for message in queue_iter:
                    if not self.running:
                        break
                    async with message.process():
                        try:
                            payload = json.loads(message.body.decode("utf-8"))
                            await self.process_trade_settlement(payload)
                        except Exception as e:
                            logger.error(f"Error processing settlement message: {e}")
        else:
            # Fallback queue consumer loop
            logger.info("RabbitMQ not connected; running internal memory queue worker loop...")
            fallback_q = await rabbitmq_service.get_fallback_queue()
            while self.running:
                try:
                    payload = await asyncio.wait_for(fallback_q.get(), timeout=1.0)
                    await self.process_trade_settlement(payload)
                    fallback_q.task_done()
                except asyncio.TimeoutError:
                    continue
                except Exception as e:
                    logger.error(f"Error processing fallback settlement message: {e}")

    async def process_trade_settlement(self, trade: dict):
        match_id = trade.get("match_id")
        buyer = trade.get("buyer_client_id")
        seller = trade.get("seller_client_id")
        quote_amount = float(trade.get("quote_amount", 0.0))
        asset_qty = float(trade.get("quantity", 0.0))

        # Skip settlement if counterparty is simulated market maker bot without internal DB record
        buyer_acc = await db_service.get_account(buyer)
        seller_acc = await db_service.get_account(seller)

        if not buyer_acc or not seller_acc:
            logger.debug(f"Trade #{match_id}: One counterparty is an external/bot account. Settle for available internal accounts.")
            if buyer_acc:
                await db_service.adjust_balance(buyer, -quote_amount, asset_qty)
            if seller_acc:
                await db_service.adjust_balance(seller, quote_amount, -asset_qty)
            return

        logger.info(f"Settling Trade #{match_id}: Buyer={buyer} (-${quote_amount:.2f}, +{asset_qty:.4f} BTC), Seller={seller} (+${quote_amount:.2f}, -{asset_qty:.4f} BTC)")
        success = await db_service.atomic_settle_trade(
            match_id=match_id,
            buyer_account_id=buyer,
            seller_account_id=seller,
            quote_amount=quote_amount,
            asset_quantity=asset_qty,
            fee=0.0
        )
        if success:
            logger.info(f"Trade #{match_id} cleared & settled atomically.")
        else:
            logger.warning(f"Trade #{match_id} settlement failed due to balance limits.")

    def stop(self):
        self.running = False

async def main():
    worker = SettlementWorker()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.stop)
        except NotImplementedError:
            pass

    try:
        await worker.start()
    finally:
        await db_service.disconnect()
        await rabbitmq_service.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
