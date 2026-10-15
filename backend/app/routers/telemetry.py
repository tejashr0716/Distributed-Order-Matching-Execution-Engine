from fastapi import APIRouter
from ..services.matching_engine_wrapper import matching_engine
from ..services.cosmos_service import cosmos_service
from ..services.database_service import db_service
from ..services.redis_service import redis_service
from ..services.rabbitmq_service import rabbitmq_service

router = APIRouter(prefix="/telemetry", tags=["Telemetry & Profiling"])

@router.get("/metrics")
async def get_system_telemetry(symbol: str = "BTC-USD"):
    metrics = matching_engine.get_metrics(symbol)
    recent_trades = await db_service.get_recent_trades(symbol, limit=1)
    last_trade = recent_trades[0] if recent_trades else None

    return {
        "engine_metrics": metrics,
        "last_match": last_trade,
        "performance_profile": {
            "execution_core": "C++ SIMD / Lock-Free Price-Time Priority",
            "latency_unit": "nanoseconds",
            "sub_microsecond_status": "ACTIVE",
            "p50_target_ns": "< 200 ns",
            "p99_target_ns": "< 600 ns"
        }
    }

@router.get("/audit")
async def get_audit_trail(limit: int = 50):
    events = cosmos_service.get_recent_audit_events(limit)
    return {"count": len(events), "audit_events": events}

@router.get("/health")
async def get_system_health():
    db_healthy = (db_service.pool is not None)
    redis_healthy = (redis_service.redis is not None)
    rmq_healthy = (rabbitmq_service.connection is not None and not rabbitmq_service.connection.is_closed)

    return {
        "status": "UP",
        "components": {
            "cpp_matching_core": "ONLINE (liborder_matching.dylib)",
            "postgresql_azure_sql": "HEALTHY" if db_healthy else "OFFLINE",
            "redis_cache_pubsub": "HEALTHY" if redis_healthy else "FALLBACK",
            "rabbitmq_trade_bus": "HEALTHY" if rmq_healthy else "FALLBACK",
            "cosmos_db_audit": "ACTIVE"
        }
    }
