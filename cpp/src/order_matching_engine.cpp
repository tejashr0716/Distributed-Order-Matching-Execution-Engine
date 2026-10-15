#include "order_matching_engine.h"
#include <string>
#include <vector>
#include <map>
#include <unordered_map>
#include <chrono>
#include <algorithm>
#include <cstring>
#include <atomic>
#include <memory>
#include <iostream>

namespace {

inline uint64_t get_now_ns() {
    return std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()
    ).count();
}

struct Order {
    uint64_t order_id;
    uint64_t client_id;
    int32_t  side;
    int32_t  type;
    int32_t  tif;
    int64_t  price;
    uint64_t total_qty;
    uint64_t remaining_qty;
    uint64_t timestamp_ns;
    
    Order* prev;
    Order* next;
    void*  level_ptr; // PriceLevel*
};

struct PriceLevel {
    int64_t  price;
    uint64_t total_volume;
    int32_t  order_count;
    Order*   head;
    Order*   tail;

    PriceLevel(int64_t p = 0) 
        : price(p), total_volume(0), order_count(0), head(nullptr), tail(nullptr) {}

    void append_order(Order* order) {
        order->level_ptr = this;
        order->prev = tail;
        order->next = nullptr;
        if (tail) {
            tail->next = order;
        } else {
            head = order;
        }
        tail = order;
        total_volume += order->remaining_qty;
        order_count++;
    }

    void remove_order(Order* order) {
        if (order->prev) {
            order->prev->next = order->next;
        } else {
            head = order->next;
        }
        if (order->next) {
            order->next->prev = order->prev;
        } else {
            tail = order->prev;
        }
        total_volume -= order->remaining_qty;
        order_count--;
        order->prev = nullptr;
        order->next = nullptr;
        order->level_ptr = nullptr;
    }
};

// Memory Pool for ultra low latency zero-allocation performance
class OrderPool {
private:
    std::vector<Order*> free_orders_;
    std::vector<std::vector<Order>> chunks_;
    const size_t chunk_size_ = 32768;

public:
    OrderPool() {
        grow();
    }

    ~OrderPool() = default;

    void grow() {
        chunks_.emplace_back(chunk_size_);
        auto& chunk = chunks_.back();
        free_orders_.reserve(free_orders_.size() + chunk_size_);
        for (size_t i = 0; i < chunk_size_; ++i) {
            free_orders_.push_back(&chunk[i]);
        }
    }

    Order* allocate() {
        if (free_orders_.empty()) {
            grow();
        }
        Order* ord = free_orders_.back();
        free_orders_.pop_back();
        std::memset(ord, 0, sizeof(Order));
        return ord;
    }

    void deallocate(Order* ord) {
        if (ord) {
            free_orders_.push_back(ord);
        }
    }

    void reset() {
        free_orders_.clear();
        for (auto& chunk : chunks_) {
            for (size_t i = 0; i < chunk.size(); ++i) {
                free_orders_.push_back(&chunk[i]);
            }
        }
    }
};

class OrderBookImpl {
private:
    std::string symbol_;
    std::map<int64_t, PriceLevel*, std::greater<int64_t>> bids_;
    std::map<int64_t, PriceLevel*, std::less<int64_t>> asks_;
    
    std::unordered_map<uint64_t, Order*> order_map_;
    std::unordered_map<int64_t, PriceLevel*> bid_levels_;
    std::unordered_map<int64_t, PriceLevel*> ask_levels_;

    OrderPool order_pool_;
    std::atomic<uint64_t> match_counter_{1};

    // Telemetry & Metrics
    uint64_t total_orders_{0};
    uint64_t total_trades_{0};
    uint64_t total_volume_{0};
    uint64_t total_cancels_{0};
    uint64_t latency_sum_ns_{0};
    uint64_t min_latency_ns_{UINT64_MAX};
    uint64_t max_latency_ns_{0};

    PriceLevel* get_or_create_level(int32_t side, int64_t price) {
        if (side == SIDE_BUY) {
            auto it = bid_levels_.find(price);
            if (it != bid_levels_.end()) {
                return it->second;
            }
            PriceLevel* level = new PriceLevel(price);
            bid_levels_[price] = level;
            bids_[price] = level;
            return level;
        } else {
            auto it = ask_levels_.find(price);
            if (it != ask_levels_.end()) {
                return it->second;
            }
            PriceLevel* level = new PriceLevel(price);
            ask_levels_[price] = level;
            asks_[price] = level;
            return level;
        }
    }

    void remove_level_if_empty(int32_t side, int64_t price, PriceLevel* level) {
        if (level->order_count <= 0) {
            if (side == SIDE_BUY) {
                bids_.erase(price);
                bid_levels_.erase(price);
            } else {
                asks_.erase(price);
                ask_levels_.erase(price);
            }
            delete level;
        }
    }

public:
    explicit OrderBookImpl(std::string symbol) : symbol_(std::move(symbol)) {}

    ~OrderBookImpl() {
        reset();
    }

    void reset() {
        for (auto& pair : bid_levels_) delete pair.second;
        for (auto& pair : ask_levels_) delete pair.second;
        bid_levels_.clear();
        ask_levels_.clear();
        bids_.clear();
        asks_.clear();
        order_map_.clear();
        order_pool_.reset();
        
        total_orders_ = 0;
        total_trades_ = 0;
        total_volume_ = 0;
        total_cancels_ = 0;
        latency_sum_ns_ = 0;
        min_latency_ns_ = UINT64_MAX;
        max_latency_ns_ = 0;
    }

    bool check_fok_fillable(int32_t side, int32_t type, int64_t price, uint64_t target_qty) {
        uint64_t accumulated = 0;
        if (side == SIDE_BUY) {
            for (auto const& [ask_price, level] : asks_) {
                if (type == TYPE_LIMIT && ask_price > price) break;
                accumulated += level->total_volume;
                if (accumulated >= target_qty) return true;
            }
        } else {
            for (auto const& [bid_price, level] : bids_) {
                if (type == TYPE_LIMIT && bid_price < price) break;
                accumulated += level->total_volume;
                if (accumulated >= target_qty) return true;
            }
        }
        return false;
    }

    int32_t submit_order(
        uint64_t order_id,
        uint64_t client_id,
        int32_t  side,
        int32_t  type,
        int32_t  tif,
        int64_t  price,
        uint64_t quantity,
        ExecutionReport* out_reports,
        int32_t  max_reports
    ) {
        uint64_t start_time = get_now_ns();
        total_orders_++;

        if (order_map_.find(order_id) != order_map_.end() || quantity == 0) {
            if (max_reports > 0 && out_reports) {
                out_reports[0].match_id = match_counter_.fetch_add(1);
                out_reports[0].taker_order_id = order_id;
                out_reports[0].maker_order_id = 0;
                out_reports[0].price = price;
                out_reports[0].quantity = 0;
                out_reports[0].side = side;
                out_reports[0].status = EXEC_STATUS_REJECTED;
                out_reports[0].timestamp_ns = get_now_ns();
                out_reports[0].latency_ns = out_reports[0].timestamp_ns - start_time;
                return 1;
            }
            return 0;
        }

        // Handle FOK upfront liquidity check
        if (tif == TIF_FOK && !check_fok_fillable(side, type, price, quantity)) {
            if (max_reports > 0 && out_reports) {
                out_reports[0].match_id = match_counter_.fetch_add(1);
                out_reports[0].taker_order_id = order_id;
                out_reports[0].maker_order_id = 0;
                out_reports[0].price = price;
                out_reports[0].quantity = 0;
                out_reports[0].side = side;
                out_reports[0].status = EXEC_STATUS_REJECTED;
                out_reports[0].timestamp_ns = get_now_ns();
                out_reports[0].latency_ns = out_reports[0].timestamp_ns - start_time;
                return 1;
            }
            return 0;
        }

        int32_t reports_generated = 0;
        uint64_t remaining = quantity;

        // Matching Engine Execution Loop
        if (side == SIDE_BUY) {
            while (remaining > 0 && !asks_.empty()) {
                auto it = asks_.begin();
                int64_t best_ask_price = it->first;
                PriceLevel* best_level = it->second;

                if (type == TYPE_LIMIT && best_ask_price > price) {
                    break; // Price does not cross
                }

                while (remaining > 0 && best_level->head != nullptr) {
                    Order* maker_order = best_level->head;
                    uint64_t match_qty = std::min(remaining, maker_order->remaining_qty);
                    remaining -= match_qty;
                    maker_order->remaining_qty -= match_qty;
                    best_level->total_volume -= match_qty;

                    total_trades_++;
                    total_volume_ += match_qty;

                    if (reports_generated < max_reports && out_reports) {
                        ExecutionReport& rep = out_reports[reports_generated++];
                        rep.match_id = match_counter_.fetch_add(1);
                        rep.taker_order_id = order_id;
                        rep.maker_order_id = maker_order->order_id;
                        rep.price = best_ask_price;
                        rep.quantity = match_qty;
                        rep.side = side;
                        rep.status = (remaining == 0) ? EXEC_STATUS_FULL_FILL : EXEC_STATUS_PARTIAL_FILL;
                        rep.timestamp_ns = get_now_ns();
                        rep.latency_ns = rep.timestamp_ns - start_time;
                    }

                    if (maker_order->remaining_qty == 0) {
                        best_level->remove_order(maker_order);
                        order_map_.erase(maker_order->order_id);
                        order_pool_.deallocate(maker_order);
                    }
                }

                if (best_level->order_count <= 0) {
                    remove_level_if_empty(SIDE_SELL, best_ask_price, best_level);
                }
            }
        } else { // SELL
            while (remaining > 0 && !bids_.empty()) {
                auto it = bids_.begin();
                int64_t best_bid_price = it->first;
                PriceLevel* best_level = it->second;

                if (type == TYPE_LIMIT && best_bid_price < price) {
                    break; // Price does not cross
                }

                while (remaining > 0 && best_level->head != nullptr) {
                    Order* maker_order = best_level->head;
                    uint64_t match_qty = std::min(remaining, maker_order->remaining_qty);
                    remaining -= match_qty;
                    maker_order->remaining_qty -= match_qty;
                    best_level->total_volume -= match_qty;

                    total_trades_++;
                    total_volume_ += match_qty;

                    if (reports_generated < max_reports && out_reports) {
                        ExecutionReport& rep = out_reports[reports_generated++];
                        rep.match_id = match_counter_.fetch_add(1);
                        rep.taker_order_id = order_id;
                        rep.maker_order_id = maker_order->order_id;
                        rep.price = best_bid_price;
                        rep.quantity = match_qty;
                        rep.side = side;
                        rep.status = (remaining == 0) ? EXEC_STATUS_FULL_FILL : EXEC_STATUS_PARTIAL_FILL;
                        rep.timestamp_ns = get_now_ns();
                        rep.latency_ns = rep.timestamp_ns - start_time;
                    }

                    if (maker_order->remaining_qty == 0) {
                        best_level->remove_order(maker_order);
                        order_map_.erase(maker_order->order_id);
                        order_pool_.deallocate(maker_order);
                    }
                }

                if (best_level->order_count <= 0) {
                    remove_level_if_empty(SIDE_BUY, best_bid_price, best_level);
                }
            }
        }

        // Post-match lifecycle: Resting order or IOC cancellation
        if (remaining > 0) {
            if (type == TYPE_LIMIT && tif == TIF_GTC) {
                Order* resting = order_pool_.allocate();
                resting->order_id = order_id;
                resting->client_id = client_id;
                resting->side = side;
                resting->type = type;
                resting->tif = tif;
                resting->price = price;
                resting->total_qty = quantity;
                resting->remaining_qty = remaining;
                resting->timestamp_ns = start_time;

                PriceLevel* level = get_or_create_level(side, price);
                level->append_order(resting);
                order_map_[order_id] = resting;

                if (reports_generated < max_reports && out_reports) {
                    ExecutionReport& rep = out_reports[reports_generated++];
                    rep.match_id = match_counter_.fetch_add(1);
                    rep.taker_order_id = order_id;
                    rep.maker_order_id = 0;
                    rep.price = price;
                    rep.quantity = remaining;
                    rep.side = side;
                    rep.status = EXEC_STATUS_NEW_RESTING;
                    rep.timestamp_ns = get_now_ns();
                    rep.latency_ns = rep.timestamp_ns - start_time;
                }
            } else if (tif == TIF_IOC) {
                // Remainder is cancelled
                if (reports_generated < max_reports && out_reports) {
                    ExecutionReport& rep = out_reports[reports_generated++];
                    rep.match_id = match_counter_.fetch_add(1);
                    rep.taker_order_id = order_id;
                    rep.maker_order_id = 0;
                    rep.price = price;
                    rep.quantity = remaining;
                    rep.side = side;
                    rep.status = EXEC_STATUS_CANCELLED;
                    rep.timestamp_ns = get_now_ns();
                    rep.latency_ns = rep.timestamp_ns - start_time;
                }
            }
        }

        uint64_t end_time = get_now_ns();
        uint64_t elapsed = end_time - start_time;
        latency_sum_ns_ += elapsed;
        if (elapsed < min_latency_ns_) min_latency_ns_ = elapsed;
        if (elapsed > max_latency_ns_) max_latency_ns_ = elapsed;

        return reports_generated;
    }

    int32_t cancel_order(uint64_t order_id, ExecutionReport* out_report) {
        uint64_t start_time = get_now_ns();
        auto it = order_map_.find(order_id);
        if (it == order_map_.end()) {
            return 0;
        }

        Order* ord = it->second;
        PriceLevel* level = static_cast<PriceLevel*>(ord->level_ptr);
        int32_t side = ord->side;
        int64_t price = ord->price;
        uint64_t rem_qty = ord->remaining_qty;

        if (level) {
            level->remove_order(ord);
            remove_level_if_empty(side, price, level);
        }

        order_map_.erase(it);
        order_pool_.deallocate(ord);
        total_cancels_++;

        uint64_t end_time = get_now_ns();
        uint64_t elapsed = end_time - start_time;

        if (out_report) {
            out_report->match_id = match_counter_.fetch_add(1);
            out_report->taker_order_id = order_id;
            out_report->maker_order_id = 0;
            out_report->price = price;
            out_report->quantity = rem_qty;
            out_report->side = side;
            out_report->status = EXEC_STATUS_CANCELLED;
            out_report->timestamp_ns = end_time;
            out_report->latency_ns = elapsed;
        }

        return 1;
    }

    int32_t get_market_depth(
        int32_t max_depth,
        int64_t*  out_bid_prices,
        uint64_t* out_bid_volumes,
        int32_t*  out_bid_counts,
        int32_t*  out_num_bids,
        int64_t*  out_ask_prices,
        uint64_t* out_ask_volumes,
        int32_t*  out_ask_counts,
        int32_t*  out_num_asks
    ) {
        int32_t b_idx = 0;
        for (auto const& [price, level] : bids_) {
            if (b_idx >= max_depth) break;
            out_bid_prices[b_idx] = price;
            out_bid_volumes[b_idx] = level->total_volume;
            out_bid_counts[b_idx] = level->order_count;
            b_idx++;
        }
        *out_num_bids = b_idx;

        int32_t a_idx = 0;
        for (auto const& [price, level] : asks_) {
            if (a_idx >= max_depth) break;
            out_ask_prices[a_idx] = price;
            out_ask_volumes[a_idx] = level->total_volume;
            out_ask_counts[a_idx] = level->order_count;
            a_idx++;
        }
        *out_num_asks = a_idx;

        return 0;
    }

    void get_metrics(EngineMetrics* out) {
        if (!out) return;
        out->total_orders_processed = total_orders_;
        out->total_trades_matched = total_trades_;
        out->total_volume_traded = total_volume_;
        out->total_cancels = total_cancels_;
        out->active_orders_count = order_map_.size();
        out->avg_latency_ns = (total_orders_ > 0) ? (static_cast<double>(latency_sum_ns_) / total_orders_) : 0.0;
        out->min_latency_ns = (min_latency_ns_ == UINT64_MAX) ? 0 : min_latency_ns_;
        out->max_latency_ns = max_latency_ns_;
    }
};

} // namespace

extern "C" {

MatchingEngineHandle create_matching_engine(const char* symbol) {
    std::string s = symbol ? symbol : "BTC-USD";
    return reinterpret_cast<MatchingEngineHandle>(new OrderBookImpl(s));
}

void destroy_matching_engine(MatchingEngineHandle handle) {
    if (handle) {
        delete reinterpret_cast<OrderBookImpl*>(handle);
    }
}

void reset_matching_engine(MatchingEngineHandle handle) {
    if (handle) {
        reinterpret_cast<OrderBookImpl*>(handle)->reset();
    }
}

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
) {
    if (!handle) return -1;
    return reinterpret_cast<OrderBookImpl*>(handle)->submit_order(
        order_id, client_id, side, type, tif, price, quantity, out_reports, max_reports
    );
}

int32_t cancel_order(
    MatchingEngineHandle handle,
    uint64_t order_id,
    ExecutionReport* out_report
) {
    if (!handle) return 0;
    return reinterpret_cast<OrderBookImpl*>(handle)->cancel_order(order_id, out_report);
}

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
) {
    if (!handle) return -1;
    return reinterpret_cast<OrderBookImpl*>(handle)->get_market_depth(
        max_depth, out_bid_prices, out_bid_volumes, out_bid_counts, out_num_bids,
        out_ask_prices, out_ask_volumes, out_ask_counts, out_num_asks
    );
}

void get_engine_metrics(MatchingEngineHandle handle, EngineMetrics* out_metrics) {
    if (handle && out_metrics) {
        reinterpret_cast<OrderBookImpl*>(handle)->get_metrics(out_metrics);
    }
}

}
