import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .services.database_service import db_service
from .services.redis_service import redis_service
from .services.rabbitmq_service import rabbitmq_service
from .services.cosmos_service import cosmos_service
from .services.matching_engine_wrapper import matching_engine

from .routers import orders, market_data, accounts, telemetry, websocket

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] [ApexMatch] %(message)s")
logger = logging.getLogger("ApexMatch")

def seed_initial_liquidity():
    """
    Seeds initial resting orders into the C++ orderbook so the depth ladder
    has active two-sided liquidity immediately on boot.
    """
    logger.info("Seeding initial resting liquidity into C++ order book...")
    base_price = 64250.00
    
    # Bids (Buy orders below base price)
    for i in range(1, 15):
        price = base_price - (i * 2.50)
        qty = 0.25 + (i % 5) * 0.15
        matching_engine.submit_order(
            symbol="BTC-USD",
            order_id=100000 + i,
            client_id_hash=1001,
            side_str="BUY",
            type_str="LIMIT",
            tif_str="GTC",
            price_float=price,
            qty_float=qty
        )

    # Asks (Sell orders above base price)
    for i in range(1, 15):
        price = base_price + (i * 2.50)
        qty = 0.20 + (i % 4) * 0.18
        matching_engine.submit_order(
            symbol="BTC-USD",
            order_id=200000 + i,
            client_id_hash=1002,
            side_str="SELL",
            type_str="LIMIT",
            tif_str="GTC",
            price_float=price,
            qty_float=qty
        )

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Booting ApexMatch Distributed Order Matching Engine...")
    await db_service.connect()
    await redis_service.connect()
    await rabbitmq_service.connect()
    await cosmos_service.connect()
    seed_initial_liquidity()
    logger.info("ApexMatch Engine is ready to process sub-microsecond orders.")
    yield
    logger.info("Shutting down ApexMatch Engine...")
    await db_service.disconnect()
    await redis_service.disconnect()
    await rabbitmq_service.disconnect()
    await cosmos_service.disconnect()

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Sub-microsecond Price-Time Priority deterministic matching engine wrapped in FastAPI async microservices.",
    version="1.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(orders.router, prefix=settings.API_V1_PREFIX)
app.include_router(market_data.router, prefix=settings.API_V1_PREFIX)
app.include_router(accounts.router, prefix=settings.API_V1_PREFIX)
app.include_router(telemetry.router, prefix=settings.API_V1_PREFIX)
app.include_router(websocket.router)

@app.get("/", response_class=HTMLResponse)
async def serve_trading_terminal():
    template_path = os.path.join(os.path.dirname(__file__), "templates", "index.html")
    with open(template_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())
