#include "order_matching_engine.h"
#include <iostream>
#include <vector>
#include <numeric>
#include <algorithm>
#include <chrono>
#include <iomanip>

int main() {
    std::cout << "========================================================\n";
    std::cout << "  APEXMATCH C++ SUB-MICROSECOND ORDER MATCHING BENCHMARK \n";
    std::cout << "========================================================\n";

    MatchingEngineHandle engine = create_matching_engine("BTC-USD");

    const int WARMUP_ORDERS = 10000;
    const int BENCH_ORDERS = 500000;
    std::vector<ExecutionReport> reports(MAX_EXECUTIONS_BATCH);

    std::cout << "[*] Warming up CPU caches with " << WARMUP_ORDERS << " orders...\n";
    for (int i = 1; i <= WARMUP_ORDERS; ++i) {
        int side = (i % 2 == 0) ? SIDE_BUY : SIDE_SELL;
        int64_t price = 6000000 + (i % 200) * 10; // $60,000.00
        submit_order(engine, i, 1001, side, TYPE_LIMIT, TIF_GTC, price, 10, reports.data(), MAX_EXECUTIONS_BATCH);
    }
    reset_matching_engine(engine);

    std::cout << "[*] Running High-Frequency Matching Benchmark (" << BENCH_ORDERS << " orders)...\n";

    std::vector<uint64_t> latencies;
    latencies.reserve(BENCH_ORDERS);

    auto start_wall = std::chrono::high_resolution_clock::now();

    for (int i = 1; i <= BENCH_ORDERS; ++i) {
        int side = (i % 2 == 0) ? SIDE_BUY : SIDE_SELL;
        // Bids: 59,950.00 to 60,000.00; Asks: 60,000.00 to 60,050.00
        int64_t price = 6000000 + ((i % 100) - 50) * 10;
        uint64_t qty = 5 + (i % 20);

        auto t0 = std::chrono::high_resolution_clock::now();
        int n = submit_order(engine, i, 1000 + (i % 50), side, TYPE_LIMIT, TIF_GTC, price, qty, reports.data(), MAX_EXECUTIONS_BATCH);
        auto t1 = std::chrono::high_resolution_clock::now();

        uint64_t dur_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(t1 - t0).count();
        latencies.push_back(dur_ns);
    }

    auto end_wall = std::chrono::high_resolution_clock::now();
    double total_sec = std::chrono::duration<double>(end_wall - start_wall).count();
    double throughput = BENCH_ORDERS / total_sec;

    std::sort(latencies.begin(), latencies.end());

    double sum = std::accumulate(latencies.begin(), latencies.end(), 0.0);
    double avg = sum / latencies.size();
    uint64_t p50 = latencies[latencies.size() * 0.50];
    uint64_t p90 = latencies[latencies.size() * 0.90];
    uint64_t p99 = latencies[latencies.size() * 0.99];
    uint64_t p999 = latencies[latencies.size() * 0.999];
    uint64_t min_lat = latencies.front();
    uint64_t max_lat = latencies.back();

    EngineMetrics metrics;
    get_engine_metrics(engine, &metrics);

    std::cout << "\n================ BENCHMARK RESULTS ================\n";
    std::cout << std::fixed << std::setprecision(2);
    std::cout << " Total Orders Processed : " << metrics.total_orders_processed << "\n";
    std::cout << " Trades Executed        : " << metrics.total_trades_matched << "\n";
    std::cout << " Volume Executed        : " << metrics.total_volume_traded << " units\n";
    std::cout << " Active Orders in Book  : " << metrics.active_orders_count << "\n";
    std::cout << " Total Elapsed Time     : " << total_sec << " seconds\n";
    std::cout << " System Throughput      : " << throughput << " orders/sec (" << (throughput / 1e6) << " M ops/s)\n";
    std::cout << "---------------------------------------------------\n";
    std::cout << " Min Latency            : " << min_lat << " ns (" << (min_lat / 1000.0) << " µs)\n";
    std::cout << " Mean Latency           : " << avg << " ns (" << (avg / 1000.0) << " µs)\n";
    std::cout << " p50 Latency            : " << p50 << " ns (" << (p50 / 1000.0) << " µs)\n";
    std::cout << " p90 Latency            : " << p90 << " ns (" << (p90 / 1000.0) << " µs)\n";
    std::cout << " p99 Latency            : " << p99 << " ns (" << (p99 / 1000.0) << " µs)\n";
    std::cout << " p99.9 Latency          : " << p999 << " ns (" << (p999 / 1000.0) << " µs)\n";
    std::cout << " Max Latency            : " << max_lat << " ns (" << (max_lat / 1000.0) << " µs)\n";
    std::cout << "===================================================\n";

    destroy_matching_engine(engine);
    return 0;
}
