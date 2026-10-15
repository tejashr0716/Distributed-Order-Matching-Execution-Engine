# ApexMatch: Sub-Microsecond Distributed Order Matching & Execution Engine

[![CI/CD Pipeline](https://github.com/tejashr0716/Distributed-Order-Matching-Execution-Engine/actions/workflows/ci.yml/badge.svg)](https://github.com/tejashr0716/Distributed-Order-Matching-Execution-Engine/actions)
[![Language: C++17](https://img.shields.io/badge/Language-C%2B%2B17-blue.svg)](https://en.cppreference.com/w/cpp/17)
[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-brightgreen.svg)](https://www.python.org/)
[![Apache Spark](https://img.shields.io/badge/Apache%20Spark-3.5%2F4.2-E25A1C.svg)](https://spark.apache.org/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-336791.svg)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-7.0-DC382D.svg)](https://redis.io/)
[![RabbitMQ](https://img.shields.io/badge/RabbitMQ-3.13-FF6600.svg)](https://www.rabbitmq.com/)

**ApexMatch** is an institutional-grade, ultra-low-latency distributed order matching and clearing engine designed for high-frequency algorithmic financial exchanges. It couples a **sub-microsecond C++ Price-Time Priority (FIFO) matching core** with an asynchronous **FastAPI** telemetry layer, **Redis** Level 2/3 depth pub/sub caching, a durable **RabbitMQ** clearing event bus, atomic multi-asset **PostgreSQL / Azure SQL** settlement ledger, and **Apache Spark** market microstructure analytics.

---

## Architecture Overview

```mermaid
flowchart TD
    subgraph Clients["Trader Clients & Algorithmic Market Makers"]
        C1["Institutional Trading APIs (REST)"]
        C2["High-Frequency WebSocket Feed"]
        C3["Market Maker Quant Bots"]
    end

    subgraph Gateway["Async API & WebSockets Gateway (FastAPI)"]
        FW["FastAPI Gateway Router"]
        WSM["WebSocket Connection Hub (L2 Depth & Trades)"]
        FFI["Ctypes FFI Zero-Copy Bridge"]
    end

    subgraph CoreEngine["Sub-Microsecond Matching Core (C++17)"]
        BOOK["Deterministic Price-Time (FIFO) Order Book"]
        POOL["Pre-Allocated Slab Memory Pool (Zero Allocation)"]
        MATCH["Crossing Engine (LIMIT, MARKET, GTC, IOC, FOK)"]
        BENCH["Hardware Nanosecond Benchmark Core"]
        BOOK <--> POOL
        BOOK <--> MATCH
    end

    subgraph EventStream["High-Throughput Streaming & Caching"]
        REDIS["Redis 7 (L2 Snapshot Cache & Pub/Sub)"]
        RMQ["RabbitMQ (exchange.trades & clearing.settlement)"]
        COSMOS["Azure Cosmos DB / NoSQL (Order Lifecycle Audit)"]
    end

    subgraph Persistence["Atomic Relational Clearing & Analytics"]
        PG["PostgreSQL / Azure SQL (Orders, Trades, Accounts)"]
        WORKER["Asynchronous Settlement Worker"]
        SPARK["Apache Spark (VWAP, OFI, Spread Profiler)"]
    end

    C1 -->|Order Placement| FW
    C2 <-->|Depth / Trades Stream| WSM
    C3 -->|Liquidity Injection| FW
    FW --> FFI
    FFI <--> CoreEngine
    FFI -->|L2 Depth Update| REDIS
    FFI -->|Trade Execution| RMQ
    FFI -->|Audit Event| COSMOS
    REDIS --> WSM
    RMQ --> WORKER
    WORKER -->|Atomic Multi-Asset Balance Settlement| PG
    PG --> SPARK
```

---

## Key Performance Benchmarks

### 1. C++ Matching Core Micro-Benchmark (Apple Silicon / Clang -O3)
| Metric | Benchmark Result | Unit |
| :--- | :--- | :--- |
| **System Throughput** | **4,589,392.77** | **Orders / Second (4.59M ops/s)** |
| **Min Latency** | **41** | **Nanoseconds (0.04 µs)** |
| **Mean Latency** | **194.01** | **Nanoseconds (0.19 µs)** |
| **p50 Median Latency** | **167** | **Nanoseconds (0.17 µs)** |
| **p90 Latency** | **291** | **Nanoseconds (0.29 µs)** |
| **p99 Tail Latency** | **583** | **Nanoseconds (0.58 µs)** |
| **p99.9 Tail Latency** | **1,500** | **Nanoseconds (1.50 µs)** |

### 2. End-to-End Async Pipeline Stress Test (FastAPI + C++ FFI + Redis + RabbitMQ)
- **Concurrent Workers**: 40 parallel client sessions
- **Total Orders Processed**: 2,000 orders
- **Pipeline Throughput**: **674.47 orders/sec**
- **p50 Latency**: **34.89 ms** (including network, database verification, and message serialization)

---

## Core Systems & Distributed Capabilities

- **Zero-Allocation Hot Path**: The C++ core utilizes a custom pre-allocated chunk memory pool (`OrderPool`) for `Order` and `PriceLevel` nodes, eliminating memory fragmentation and heap allocation jitter.
- **Price-Time Priority (FIFO)**: Strict price level ordering with doubly linked order queues ensuring constant time $O(1)$ order placement, cancellation, and execution matching.
- **Advanced Order Types & TIF**:
  - `LIMIT` orders (Good-Til-Cancelled).
  - `MARKET` orders (immediate liquidity sweeps).
  - `IOC` (Immediate-Or-Cancel) with partial fill and immediate remainder cancellation.
  - `FOK` (Fill-Or-Kill) with upfront order book depth liquidity verification.
- **Atomic Multi-Asset Clearing**: Settlement worker consumes trade executions from RabbitMQ and runs serialized two-party accounting in PostgreSQL (`UPDATE trader_accounts ... FOR UPDATE`), preventing double-spends and race conditions.
- **Apache Spark Market Microstructure**:
  - Volume-Weighted Average Price (VWAP) calculation: $\text{VWAP} = \frac{\sum (P_i \times Q_i)}{\sum Q_i}$.
  - Order Flow Imbalance (OFI) tracking institutional order aggression.

---

## Quickstart & Local Execution

### 1. Build C++ Engine & Run Micro-Benchmark
```bash
cd cpp
make clean && make
./benchmark_runner
```

### 2. Run Database Schema & Start Backend
```bash
# Setup PostgreSQL database
psql -U postgres -d postgres -c "CREATE DATABASE apex_matching_db;"
psql -U postgres -d apex_matching_db -f schema.sql

# Install Python requirements
pip install -r backend/requirements.txt

# Start Backend API & Trading Terminal
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Run Pytest Test Suite
```bash
python3 -m pytest backend/tests/ -v
```

### 4. Run Apache Spark Analytics
```bash
python3 spark/market_microstructure_analytics.py
```

### 5. Launch with Docker Compose
```bash
docker-compose up --build
```

---

## Live Interactive Terminal

Access the live dark-mode institutional trading terminal at `http://localhost:8000` to interact with:
- Real-time Level 2 Order Book Depth Ladder with live bid/ask volume bars.
- Live Canvas Price Microstructure Chart.
- Direct Limit & Market Order Placement.
- Algorithmic Market Maker Bot toggle for live streaming order book liquidity.
- Active Open Orders table with 1-click cancellation.
- Nanosecond engine performance telemetry panel.
