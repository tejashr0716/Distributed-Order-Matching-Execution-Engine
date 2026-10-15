import pytest
import time
from backend.app.services.database_service import db_service
from backend.app.services.rabbitmq_service import rabbitmq_service
from backend.app.services.redis_service import redis_service

@pytest.mark.asyncio
async def test_atomic_trade_clearing_settlement():
    # Check initial balances
    alice_before = await db_service.get_account("TRADER_ALICE")
    bob_before = await db_service.get_account("TRADER_BOB")

    match_id = int(time.time() * 1000)
    quote_amt = 32000.0  # $32,000 USD
    btc_qty = 0.5        # 0.5 BTC

    # Record trade first to satisfy relational integrity
    await db_service.record_trade(
        match_id=match_id,
        symbol="BTC-USD",
        buyer_order_id=8801,
        seller_order_id=8802,
        buyer_client_id="TRADER_ALICE",
        seller_client_id="TRADER_BOB",
        price=64000.0,
        quantity=btc_qty,
        quote_amount=quote_amt,
        taker_side="BUY",
        latency_ns=185
    )

    # Buyer: ALICE (-32,000 USD, +0.5 BTC)
    # Seller: BOB (+32,000 USD, -0.5 BTC)
    success = await db_service.atomic_settle_trade(
        match_id=match_id,
        buyer_account_id="TRADER_ALICE",
        seller_account_id="TRADER_BOB",
        quote_amount=quote_amt,
        asset_quantity=btc_qty,
        fee=0.0
    )
    assert success is True

    alice_after = await db_service.get_account("TRADER_ALICE")
    bob_after = await db_service.get_account("TRADER_BOB")

    assert float(alice_after["fiat_balance"]) == pytest.approx(float(alice_before["fiat_balance"]) - quote_amt, 0.01)
    assert float(alice_after["asset_balance"]) == pytest.approx(float(alice_before["asset_balance"]) + btc_qty, 0.0001)

    assert float(bob_after["fiat_balance"]) == pytest.approx(float(bob_before["fiat_balance"]) + quote_amt, 0.01)
    assert float(bob_after["asset_balance"]) == pytest.approx(float(bob_before["asset_balance"]) - btc_qty, 0.0001)

@pytest.mark.asyncio
async def test_redis_depth_and_ticker_caching():
    test_depth = {
        "symbol": "BTC-USD",
        "best_bid": 64100.0,
        "best_ask": 64102.5,
        "spread": 2.5
    }
    await redis_service.publish_depth_update("BTC-USD", test_depth)
    cached = await redis_service.get_depth_snapshot("BTC-USD")
    assert cached is not None
    assert cached["spread"] == 2.5

    await redis_service.update_ticker("BTC-USD", 64101.0, 1.25)
    ticker = await redis_service.get_ticker("BTC-USD")
    assert ticker["last_price"] == 64101.0
    assert ticker["volume_24h"] >= 1.25
