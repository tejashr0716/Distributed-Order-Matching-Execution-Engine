import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "ApexMatch - Sub-Microsecond Distributed Order Matching Engine"
    API_V1_PREFIX: str = "/api/v1"
    
    # Database
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL", 
        f"postgresql://{os.getenv('USER', 'postgres')}@localhost:5432/apex_matching_db"
    )
    
    # Redis
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    
    # RabbitMQ
    RABBITMQ_URL: str = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")
    RABBITMQ_EXCHANGE_TRADES: str = "exchange.trades"
    RABBITMQ_QUEUE_SETTLEMENT: str = "clearing.settlement"
    RABBITMQ_QUEUE_AUDIT: str = "risk.audit"
    
    # Cosmos DB / NoSQL
    COSMOS_ENDPOINT: str = os.getenv("COSMOS_ENDPOINT", "")
    COSMOS_KEY: str = os.getenv("COSMOS_KEY", "")
    COSMOS_DATABASE_NAME: str = "ApexMarketAudit"
    COSMOS_CONTAINER_NAME: str = "OrderLifecycleEvents"
    
    # C++ Shared Library
    CPP_LIB_PATH: str = os.getenv(
        "CPP_LIB_PATH", 
        os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../cpp/liborder_matching.dylib"))
    )

    class Config:
        env_file = ".env"

settings = Settings()
