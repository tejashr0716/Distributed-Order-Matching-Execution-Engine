import asyncpg
import logging
from typing import Optional, Dict, Any, List
from ..config import settings

logger = logging.getLogger("ApexMatch.Database")

class DatabaseService:
    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        if not self.pool:
            try:
                self.pool = await asyncpg.create_pool(
                    dsn=settings.DATABASE_URL,
                    min_size=2,
                    max_size=20,
                    command_timeout=30.0
                )
                logger.info("Connected to PostgreSQL/Azure SQL database pool successfully.")
            except Exception as e:
                logger.error(f"Database connection error: {e}")
                raise

    async def disconnect(self):
        if self.pool:
            await self.pool.close()
            self.pool = None
            logger.info("Closed database connection pool.")

    async def get_account(self, account_id: str) -> Optional[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT account_id, username, fiat_balance, asset_balance, locked_fiat, locked_asset, updated_at
                FROM trader_accounts
                WHERE account_id = $1
                """,
                account_id
            )
            return dict(row) if row else None

    async def adjust_balance(self, account_id: str, fiat_delta: float, asset_delta: float) -> bool:
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Check sufficient funds
                acc = await conn.fetchrow(
                    "SELECT fiat_balance, asset_balance FROM trader_accounts WHERE account_id = $1 FOR UPDATE",
                    account_id
                )
                if not acc:
                    return False
                if acc["fiat_balance"] + fiat_delta < 0 or acc["asset_balance"] + asset_delta < 0:
                    return False
                
                await conn.execute(
                    """
                    UPDATE trader_accounts
                    SET fiat_balance = fiat_balance + $2,
                        asset_balance = asset_balance + $3,
                        updated_at = NOW()
                    WHERE account_id = $1
                    """,
                    account_id, fiat_delta, asset_delta
                )
                return True

    async def record_order(
        self,
        order_id: int,
        client_id: str,
        symbol: str,
        side: str,
        order_type: str,
        tif: str,
        price: float,
        quantity: float,
        status: str,
        remaining_quantity: float,
        filled_quantity: float = 0.0
    ):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO orders (
                    order_id, client_id, symbol, side, type, tif, price, quantity, 
                    filled_quantity, remaining_quantity, status, created_at, updated_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW(), NOW())
                ON CONFLICT (order_id) DO UPDATE SET
                    filled_quantity = EXCLUDED.filled_quantity,
                    remaining_quantity = EXCLUDED.remaining_quantity,
                    status = EXCLUDED.status,
                    updated_at = NOW()
                """,
                order_id, client_id, symbol, side, order_type, tif, price, quantity,
                filled_quantity, remaining_quantity, status
            )

    async def update_order_fill(self, order_id: int, filled_qty: float, remaining_qty: float, status: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE orders
                SET filled_quantity = filled_quantity + $2,
                    remaining_quantity = $3,
                    status = $4,
                    updated_at = NOW()
                WHERE order_id = $1
                """,
                order_id, filled_qty, remaining_qty, status
            )

    async def record_trade(
        self,
        match_id: int,
        symbol: str,
        buyer_order_id: int,
        seller_order_id: int,
        buyer_client_id: str,
        seller_client_id: str,
        price: float,
        quantity: float,
        quote_amount: float,
        taker_side: str,
        latency_ns: int
    ):
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO trades (
                    match_id, symbol, buyer_order_id, seller_order_id, buyer_client_id, seller_client_id,
                    price, quantity, quote_amount, taker_side, latency_ns, executed_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, NOW())
                ON CONFLICT (match_id) DO NOTHING
                """,
                match_id, symbol, buyer_order_id, seller_order_id, buyer_client_id, seller_client_id,
                price, quantity, quote_amount, taker_side, latency_ns
            )

    async def atomic_settle_trade(
        self,
        match_id: int,
        buyer_account_id: str,
        seller_account_id: str,
        quote_amount: float,
        asset_quantity: float,
        fee: float = 0.0
    ) -> bool:
        """
        Executes zero-race-condition multi-asset clearing and settlement.
        Buyer: -quote_amount fiat, +asset_quantity crypto
        Seller: +quote_amount fiat, -asset_quantity crypto
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Lock both accounts in deterministic order to prevent deadlock
                accounts = sorted([buyer_account_id, seller_account_id])
                for acc_id in accounts:
                    await conn.execute(
                        "SELECT account_id FROM trader_accounts WHERE account_id = $1 FOR UPDATE",
                        acc_id
                    )

                # Debit buyer fiat, credit buyer asset
                await conn.execute(
                    """
                    UPDATE trader_accounts
                    SET fiat_balance = fiat_balance - $2,
                        asset_balance = asset_balance + $3,
                        updated_at = NOW()
                    WHERE account_id = $1
                    """,
                    buyer_account_id, quote_amount, asset_quantity
                )

                # Credit seller fiat, debit seller asset
                await conn.execute(
                    """
                    UPDATE trader_accounts
                    SET fiat_balance = fiat_balance + $2,
                        asset_balance = asset_balance - $3,
                        updated_at = NOW()
                    WHERE account_id = $1
                    """,
                    seller_account_id, (quote_amount - fee), asset_quantity
                )

                # Record clearing settlement audit
                await conn.execute(
                    """
                    INSERT INTO clearing_settlements (
                        match_id, buyer_account_id, seller_account_id, settled_fiat, settled_asset, clearing_fee, settlement_status
                    ) VALUES ($1, $2, $3, $4, $5, $6, 'SETTLED')
                    """,
                    match_id, buyer_account_id, seller_account_id, quote_amount, asset_quantity, fee
                )

                return True

    async def get_recent_trades(self, symbol: str, limit: int = 50) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT match_id, symbol, buyer_order_id, seller_order_id, buyer_client_id, seller_client_id,
                       price, quantity, quote_amount, taker_side, latency_ns, executed_at
                FROM trades
                WHERE symbol = $1
                ORDER BY executed_at DESC
                LIMIT $2
                """,
                symbol, limit
            )
            return [dict(r) for r in rows]

    async def get_client_orders(self, client_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT order_id, client_id, symbol, side, type, tif, price, quantity, filled_quantity,
                       remaining_quantity, status, created_at, updated_at
                FROM orders
                WHERE client_id = $1
                ORDER BY created_at DESC
                LIMIT $2
                """,
                client_id, limit
            )
            return [dict(r) for r in rows]

db_service = DatabaseService()
