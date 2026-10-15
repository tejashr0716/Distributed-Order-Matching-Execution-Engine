import ctypes
import os
import threading
from typing import List, Tuple, Dict, Any, Optional
from ..config import settings

class ExecutionReportC(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ("match_id", ctypes.c_uint64),
        ("taker_order_id", ctypes.c_uint64),
        ("maker_order_id", ctypes.c_uint64),
        ("price", ctypes.c_int64),
        ("quantity", ctypes.c_uint64),
        ("side", ctypes.c_int32),
        ("status", ctypes.c_int32),
        ("timestamp_ns", ctypes.c_uint64),
        ("latency_ns", ctypes.c_uint64),
    ]

class EngineMetricsC(ctypes.Structure):
    _pack_ = 8
    _fields_ = [
        ("total_orders_processed", ctypes.c_uint64),
        ("total_trades_matched", ctypes.c_uint64),
        ("total_volume_traded", ctypes.c_uint64),
        ("total_cancels", ctypes.c_uint64),
        ("active_orders_count", ctypes.c_uint64),
        ("avg_latency_ns", ctypes.c_double),
        ("min_latency_ns", ctypes.c_uint64),
        ("max_latency_ns", ctypes.c_uint64),
    ]

class MatchingEngineWrapper:
    PRICE_SCALE = 100.0       # Cents ($1.00 = 100)
    QTY_SCALE = 10000.0       # 4 decimal places (0.0001 = 1)
    MAX_REPORTS = 64

    # Execution Status Constants
    STATUS_NEW_RESTING = 1
    STATUS_PARTIAL_FILL = 2
    STATUS_FULL_FILL = 3
    STATUS_CANCELLED = 4
    STATUS_REJECTED = 5

    def __init__(self, lib_path: Optional[str] = None):
        self.lib_path = lib_path or settings.CPP_LIB_PATH
        if not os.path.isabs(self.lib_path):
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.lib_path = os.path.join(base_dir, "cpp", "liborder_matching.dylib")
        
        if not os.path.exists(self.lib_path):
            # Check alternative relative path
            fallback = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../cpp/liborder_matching.dylib"))
            if os.path.exists(fallback):
                self.lib_path = fallback
            else:
                raise FileNotFoundError(f"C++ shared library not found at: {self.lib_path}")

        self._lib = ctypes.CDLL(self.lib_path)
        self._lock = threading.Lock()
        self._setup_bindings()
        
        # Symbol -> EngineHandle
        self._handles: Dict[str, ctypes.c_void_p] = {}

    def _setup_bindings(self):
        # create_matching_engine
        self._lib.create_matching_engine.argtypes = [ctypes.c_char_p]
        self._lib.create_matching_engine.restype = ctypes.c_void_p

        # destroy_matching_engine
        self._lib.destroy_matching_engine.argtypes = [ctypes.c_void_p]
        self._lib.destroy_matching_engine.restype = None

        # reset_matching_engine
        self._lib.reset_matching_engine.argtypes = [ctypes.c_void_p]
        self._lib.reset_matching_engine.restype = None

        # submit_order
        self._lib.submit_order.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.c_uint64,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int32,
            ctypes.c_int64,
            ctypes.c_uint64,
            ctypes.POINTER(ExecutionReportC),
            ctypes.c_int32
        ]
        self._lib.submit_order.restype = ctypes.c_int32

        # cancel_order
        self._lib.cancel_order.argtypes = [
            ctypes.c_void_p,
            ctypes.c_uint64,
            ctypes.POINTER(ExecutionReportC)
        ]
        self._lib.cancel_order.restype = ctypes.c_int32

        # get_market_depth
        self._lib.get_market_depth.argtypes = [
            ctypes.c_void_p,
            ctypes.c_int32,
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int64),
            ctypes.POINTER(ctypes.c_uint64),
            ctypes.POINTER(ctypes.c_int32),
            ctypes.POINTER(ctypes.c_int32)
        ]
        self._lib.get_market_depth.restype = ctypes.c_int32

        # get_engine_metrics
        self._lib.get_engine_metrics.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(EngineMetricsC)
        ]
        self._lib.get_engine_metrics.restype = None

    def get_handle(self, symbol: str) -> ctypes.c_void_p:
        with self._lock:
            if symbol not in self._handles:
                handle = self._lib.create_matching_engine(symbol.encode("utf-8"))
                self._handles[symbol] = handle
            return self._handles[symbol]

    def submit_order(
        self,
        symbol: str,
        order_id: int,
        client_id_hash: int,
        side_str: str,
        type_str: str,
        tif_str: str,
        price_float: float,
        qty_float: float
    ) -> Tuple[int, List[Dict[str, Any]]]:
        handle = self.get_handle(symbol)
        
        side = 1 if side_str.upper() == "BUY" else 2
        order_type = 1 if type_str.upper() == "LIMIT" else 2
        tif_map = {"GTC": 1, "IOC": 2, "FOK": 3}
        tif = tif_map.get(tif_str.upper(), 1)
        
        price_ticks = int(round(price_float * self.PRICE_SCALE))
        qty_units = int(round(qty_float * self.QTY_SCALE))

        reports_arr = (ExecutionReportC * self.MAX_REPORTS)()
        
        with self._lock:
            num_reports = self._lib.submit_order(
                handle,
                ctypes.c_uint64(order_id),
                ctypes.c_uint64(client_id_hash),
                ctypes.c_int32(side),
                ctypes.c_int32(order_type),
                ctypes.c_int32(tif),
                ctypes.c_int64(price_ticks),
                ctypes.c_uint64(qty_units),
                reports_arr,
                ctypes.c_int32(self.MAX_REPORTS)
            )

        status_names = {
            1: "NEW_RESTING",
            2: "PARTIAL_FILL",
            3: "FULL_FILL",
            4: "CANCELLED",
            5: "REJECTED"
        }

        results = []
        for i in range(num_reports):
            r = reports_arr[i]
            results.append({
                "match_id": r.match_id,
                "taker_order_id": r.taker_order_id,
                "maker_order_id": r.maker_order_id,
                "price": round(r.price / self.PRICE_SCALE, 2),
                "quantity": round(r.quantity / self.QTY_SCALE, 4),
                "side": "BUY" if r.side == 1 else "SELL",
                "status": status_names.get(r.status, "UNKNOWN"),
                "timestamp_ns": r.timestamp_ns,
                "latency_ns": r.latency_ns,
            })

        return num_reports, results

    def cancel_order(self, symbol: str, order_id: int) -> Tuple[bool, Optional[Dict[str, Any]]]:
        handle = self.get_handle(symbol)
        report = ExecutionReportC()

        with self._lock:
            success = self._lib.cancel_order(
                handle,
                ctypes.c_uint64(order_id),
                ctypes.byref(report)
            )

        if success == 1:
            return True, {
                "match_id": report.match_id,
                "order_id": report.taker_order_id,
                "price": round(report.price / self.PRICE_SCALE, 2),
                "cancelled_quantity": round(report.quantity / self.QTY_SCALE, 4),
                "side": "BUY" if report.side == 1 else "SELL",
                "latency_ns": report.latency_ns,
                "status": "CANCELLED"
            }
        return False, None

    def get_market_depth(self, symbol: str, max_depth: int = 20) -> Dict[str, Any]:
        handle = self.get_handle(symbol)
        
        bid_prices = (ctypes.c_int64 * max_depth)()
        bid_volumes = (ctypes.c_uint64 * max_depth)()
        bid_counts = (ctypes.c_int32 * max_depth)()
        num_bids = ctypes.c_int32(0)

        ask_prices = (ctypes.c_int64 * max_depth)()
        ask_volumes = (ctypes.c_uint64 * max_depth)()
        ask_counts = (ctypes.c_int32 * max_depth)()
        num_asks = ctypes.c_int32(0)

        with self._lock:
            self._lib.get_market_depth(
                handle,
                ctypes.c_int32(max_depth),
                bid_prices, bid_volumes, bid_counts, ctypes.byref(num_bids),
                ask_prices, ask_volumes, ask_counts, ctypes.byref(num_asks)
            )

        bids = []
        for i in range(num_bids.value):
            bids.append({
                "price": round(bid_prices[i] / self.PRICE_SCALE, 2),
                "volume": round(bid_volumes[i] / self.QTY_SCALE, 4),
                "order_count": bid_counts[i]
            })

        asks = []
        for i in range(num_asks.value):
            asks.append({
                "price": round(ask_prices[i] / self.PRICE_SCALE, 2),
                "volume": round(ask_volumes[i] / self.QTY_SCALE, 4),
                "order_count": ask_counts[i]
            })

        best_bid = bids[0]["price"] if bids else 0.0
        best_ask = asks[0]["price"] if asks else 0.0
        spread = round(best_ask - best_bid, 2) if (best_bid > 0 and best_ask > 0) else 0.0
        mid_price = round((best_bid + best_ask) / 2.0, 2) if (best_bid > 0 and best_ask > 0) else (best_bid or best_ask)

        return {
            "symbol": symbol,
            "bids": bids,
            "asks": asks,
            "best_bid": best_bid,
            "best_ask": best_ask,
            "mid_price": mid_price,
            "spread": spread
        }

    def get_metrics(self, symbol: str) -> Dict[str, Any]:
        handle = self.get_handle(symbol)
        m = EngineMetricsC()
        with self._lock:
            self._lib.get_engine_metrics(handle, ctypes.byref(m))

        return {
            "symbol": symbol,
            "total_orders_processed": m.total_orders_processed,
            "total_trades_matched": m.total_trades_matched,
            "total_volume_traded": round(m.total_volume_traded / self.QTY_SCALE, 4),
            "total_cancels": m.total_cancels,
            "active_orders_count": m.active_orders_count,
            "avg_latency_ns": round(m.avg_latency_ns, 2),
            "min_latency_ns": m.min_latency_ns,
            "max_latency_ns": m.max_latency_ns
        }

    def reset(self, symbol: str):
        handle = self.get_handle(symbol)
        with self._lock:
            self._lib.reset_matching_engine(handle)

# Global singleton
matching_engine = MatchingEngineWrapper()
