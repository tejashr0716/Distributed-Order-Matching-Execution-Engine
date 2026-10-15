#ifndef ORDER_MATCHING_ENGINE_H
#define ORDER_MATCHING_ENGINE_H

#include <cstdint>
#include <cstddef>

#ifdef __cplusplus
extern "C" {
#endif

// Side
#define SIDE_BUY 1
#define SIDE_SELL 2

// Order Type
#define TYPE_LIMIT 1
#define TYPE_MARKET 2

// Time in Force
#define TIF_GTC 1 // Good-Til-Cancelled
#define TIF_IOC 2 // Immediate-Or-Cancel
#define TIF_FOK 3 // Fill-Or-Kill

// Execution Status
#define EXEC_STATUS_NEW_RESTING 1
#define EXEC_STATUS_PARTIAL_FILL 2
#define EXEC_STATUS_FULL_FILL 3
#define EXEC_STATUS_CANCELLED 4
#define EXEC_STATUS_REJECTED 5

#define MAX_EXECUTIONS_BATCH 64

#pragma pack(push, 8)
typedef struct {
    uint64_t match_id;
    uint64_t taker_order_id;
    uint64_t maker_order_id;
    int64_t  price;            // Price in ticks (cents or 1/10000)
    uint64_t quantity;
    int32_t  side;             // Side of taker (1=BUY, 2=SELL)
    int32_t  status;           // EXEC_STATUS_*
    uint64_t timestamp_ns;     // Nanoseconds timestamp of match
    uint64_t latency_ns;       // Engine internal execution duration (ns)
} ExecutionReport;

typedef struct {
    uint64_t total_orders_processed;
    uint64_t total_trades_matched;
    uint64_t total_volume_traded;
    uint64_t total_cancels;
    uint64_t active_orders_count;
    double   avg_latency_ns;
    uint64_t min_latency_ns;
    uint64_t max_latency_ns;
} EngineMetrics;
#pragma pack(pop)

typedef void* MatchingEngineHandle;

// Engine lifecycle
MatchingEngineHandle create_matching_engine(const char* symbol);
void destroy_matching_engine(MatchingEngineHandle handle);
void reset_matching_engine(MatchingEngineHandle handle);

// Core order operations
// Returns number of execution reports generated (0 if resting, >0 if filled/partially filled)
int32_t submit_order(
    MatchingEngineHandle handle,
    uint64_t order_id,
    uint64_t client_id,
    int32_t  side,
    int32_t  type,
    int32_t  tif,
    int64_t  price,
    uint64_t quantity,
    ExecutionReport* out_reports,
    int32_t  max_reports
);

// Cancel order by ID
// Returns 1 if cancelled successfully, 0 if not found
int32_t cancel_order(
    MatchingEngineHandle handle,
    uint64_t order_id,
    ExecutionReport* out_report
);

// Level 2 Market Depth query
int32_t get_market_depth(
    MatchingEngineHandle handle,
    int32_t max_depth,
    int64_t*  out_bid_prices,
    uint64_t* out_bid_volumes,
    int32_t*  out_bid_counts,
    int32_t*  out_num_bids,
    int64_t*  out_ask_prices,
    uint64_t* out_ask_volumes,
    int32_t*  out_ask_counts,
    int32_t*  out_num_asks
);

// Retrieve real-time engine telemetry
void get_engine_metrics(MatchingEngineHandle handle, EngineMetrics* out_metrics);

#ifdef __cplusplus
}
#endif

#endif // ORDER_MATCHING_ENGINE_H
