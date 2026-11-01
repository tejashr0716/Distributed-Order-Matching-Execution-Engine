import pytest
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.services.database_service import db_service

@pytest.mark.asyncio
async def test_health_check_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/telemetry/health")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "UP"
        assert "cpp_matching_core" in data["components"]

@pytest.mark.asyncio
async def test_get_account_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/accounts/TRADER_ALICE")
        assert res.status_code == 200
        data = res.json()
        assert data["account_id"] == "TRADER_ALICE"
        assert data["fiat_balance"] >= 0
        assert data["asset_balance"] >= 0

@pytest.mark.asyncio
async def test_place_order_api_success():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        order_payload = {
            "client_id": "TRADER_ALICE",
            "symbol": "BTC-USD",
            "side": "BUY",
            "type": "LIMIT",
            "tif": "GTC",
            "price": 63500.0,
            "quantity": 0.25
        }
        res = await ac.post("/api/v1/orders", json=order_payload)
        assert res.status_code == 200
        data = res.json()
        assert data["order_id"] > 0
        assert data["status"] in ("ACCEPTED", "FILLED", "PARTIALLY_FILLED")
        assert data["engine_latency_ns"] >= 0

@pytest.mark.asyncio
async def test_place_order_insufficient_funds_rejected():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Alice only has $250,000; placing a $50,000,000 order must fail
        order_payload = {
            "client_id": "TRADER_ALICE",
            "symbol": "BTC-USD",
            "side": "BUY",
            "type": "LIMIT",
            "tif": "GTC",
            "price": 100000.0,
            "quantity": 500.0 # $50M notional
        }
        res = await ac.post("/api/v1/orders", json=order_payload)
        assert res.status_code == 400
        assert "Insufficient fiat balance" in res.json()["detail"]

@pytest.mark.asyncio
async def test_market_depth_and_ticker_api():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/api/v1/depth/BTC-USD")
        assert res.status_code == 200
        depth = res.json()
        assert "bids" in depth
        assert "asks" in depth

        ticker_res = await ac.get("/api/v1/ticker/BTC-USD")
        assert ticker_res.status_code == 200
        ticker = ticker_res.json()
        assert ticker["symbol"] == "BTC-USD"

@pytest.mark.asyncio
async def test_serve_trading_terminal():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        res = await ac.get("/")
        assert res.status_code == 200
        assert "text/html" in res.headers.get("content-type", "")
        assert "ApexMatch Pro" in res.text
        assert "Order Matching & Execution Engine" in res.text
