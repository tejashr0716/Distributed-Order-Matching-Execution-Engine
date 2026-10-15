import pytest
import pytest_asyncio
from backend.app.services.matching_engine_wrapper import matching_engine
from backend.app.services.database_service import db_service
from backend.app.services.redis_service import redis_service
from backend.app.services.rabbitmq_service import rabbitmq_service

@pytest_asyncio.fixture(autouse=True)
async def setup_services():
    await db_service.connect()
    await redis_service.connect()
    await rabbitmq_service.connect()
    yield
    await db_service.disconnect()
    await redis_service.disconnect()
    await rabbitmq_service.disconnect()

@pytest.fixture(autouse=True)
def reset_engine():
    matching_engine.reset("BTC-USD")
    yield
    matching_engine.reset("BTC-USD")
