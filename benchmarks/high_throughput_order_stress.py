import asyncio
import time
import statistics
import random
from httpx import AsyncClient, ASGITransport
from backend.app.main import app
from backend.app.services.database_service import db_service
from backend.app.services.redis_service import redis_service
from backend.app.services.rabbitmq_service import rabbitmq_service

TOTAL_ORDERS = 2000
CONCURRENT_WORKERS = 40

async def worker_task(worker_id: int, orders_per_worker: int, latencies: list, fills_count: list):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test", timeout=30.0) as client:
        clients_pool = ["TRADER_ALICE", "TRADER_BOB", "WHALE_01", "MM_BOT_01"]
        base_price = 64250.0

        for i in range(orders_per_worker):
            side = "BUY" if (i % 2 == 0) else "SELL"
            # Slightly vary price around base
            price_offset = ((i % 20) - 10) * 1.50
            price = round(base_price + price_offset, 2)
            qty = round(0.05 + (i % 10) * 0.05, 4)
            trader = clients_pool[worker_id % len(clients_pool)]

            payload = {
                "client_id": trader,
                "symbol": "BTC-USD",
                "side": side,
                "type": "LIMIT",
                "tif": "GTC",
                "price": price,
                "quantity": qty
            }

            t0 = time.perf_counter()
            try:
                res = await client.post("/api/v1/orders", json=payload)
                t1 = time.perf_counter()
                dur_ms = (t1 - t0) * 1000.0
                latencies.append(dur_ms)
                if res.status_code == 200:
                    data = res.json()
                    fills_count.append(len(data.get("fills", [])))
            except Exception as e:
                pass

async def run_benchmark():
    print("=====================================================================")
    print("  APEXMATCH CONCURRENT END-TO-END PIPELINE STRESS BENCHMARK          ")
    print("=====================================================================")
    print(f"[*] Target Orders      : {TOTAL_ORDERS}")
    print(f"[*] Concurrent Workers : {CONCURRENT_WORKERS}")
    print("[*] Connecting services (Postgres, Redis, RabbitMQ, C++ Core)...")

    await db_service.connect()
    await redis_service.connect()
    await rabbitmq_service.connect()

    latencies = []
    fills_count = []
    orders_per_worker = TOTAL_ORDERS // CONCURRENT_WORKERS

    start_wall = time.perf_counter()
    tasks = [
        asyncio.create_task(worker_task(w_id, orders_per_worker, latencies, fills_count))
        for w_id in range(CONCURRENT_WORKERS)
    ]
    await asyncio.gather(*tasks)
    end_wall = time.perf_counter()

    total_sec = end_wall - start_wall
    throughput = len(latencies) / total_sec
    total_fills = sum(fills_count)

    latencies.sort()
    p50 = statistics.median(latencies)
    p90 = latencies[int(len(latencies) * 0.90)]
    p95 = latencies[int(len(latencies) * 0.95)]
    p99 = latencies[int(len(latencies) * 0.99)]
    mean_lat = statistics.mean(latencies)

    print("\n======================= BENCHMARK RESULTS =======================")
    print(f" Total Orders Ingested   : {len(latencies):,}")
    print(f" Executed Fills Matched  : {total_fills:,}")
    print(f" Total Elapsed Time      : {total_sec:.3f} seconds")
    print(f" Pipeline Throughput     : {throughput:,.2f} orders/sec")
    print("-----------------------------------------------------------------")
    print(f" Mean Latency            : {mean_lat:.2f} ms")
    print(f" p50 Latency             : {p50:.2f} ms")
    print(f" p90 Latency             : {p90:.2f} ms")
    print(f" p95 Latency             : {p95:.2f} ms")
    print(f" p99 Latency             : {p99:.2f} ms")
    print("=================================================================\n")

    await db_service.disconnect()
    await redis_service.disconnect()
    await rabbitmq_service.disconnect()

if __name__ == "__main__":
    asyncio.run(run_benchmark())
