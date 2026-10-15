import pytest
from backend.app.services.matching_engine_wrapper import matching_engine

def test_resting_limit_order():
    num_reports, reports = matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5001,
        client_id_hash=101,
        side_str="BUY",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=60000.0,
        qty_float=1.5
    )
    assert num_reports == 1
    assert reports[0]["status"] == "NEW_RESTING"
    assert reports[0]["taker_order_id"] == 5001
    assert reports[0]["price"] == 60000.0
    assert reports[0]["quantity"] == 1.5

    depth = matching_engine.get_market_depth("BTC-USD", max_depth=5)
    assert len(depth["bids"]) == 1
    assert depth["bids"][0]["price"] == 60000.0
    assert depth["bids"][0]["volume"] == 1.5

def test_full_fill_crossing_orders():
    # Place resting sell order
    matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5002,
        client_id_hash=102,
        side_str="SELL",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=61000.0,
        qty_float=2.0
    )

    # Incoming crossing buy order
    num_reports, reports = matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5003,
        client_id_hash=103,
        side_str="BUY",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=61000.0,
        qty_float=2.0
    )

    assert num_reports == 1
    fill = reports[0]
    assert fill["status"] == "FULL_FILL"
    assert fill["taker_order_id"] == 5003
    assert fill["maker_order_id"] == 5002
    assert fill["price"] == 61000.0
    assert fill["quantity"] == 2.0

    depth = matching_engine.get_market_depth("BTC-USD", max_depth=5)
    assert len(depth["bids"]) == 0
    assert len(depth["asks"]) == 0

def test_partial_fill_and_resting_remainder():
    # Maker sells 1.0 BTC
    matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5004,
        client_id_hash=104,
        side_str="SELL",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=62000.0,
        qty_float=1.0
    )

    # Taker buys 2.5 BTC (takes 1.0 BTC, 1.5 BTC rests as bid)
    num_reports, reports = matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5005,
        client_id_hash=105,
        side_str="BUY",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=62000.0,
        qty_float=2.5
    )

    assert num_reports == 2
    # Report 1: Partial fill of 1.0 against maker 5004
    assert reports[0]["status"] == "PARTIAL_FILL"
    assert reports[0]["quantity"] == 1.0
    assert reports[0]["maker_order_id"] == 5004

    # Report 2: Remainder 1.5 placed as resting bid
    assert reports[1]["status"] == "NEW_RESTING"
    assert reports[1]["quantity"] == 1.5

    depth = matching_engine.get_market_depth("BTC-USD", max_depth=5)
    assert len(depth["asks"]) == 0
    assert len(depth["bids"]) == 1
    assert depth["bids"][0]["volume"] == 1.5

def test_fifo_price_time_priority():
    # Maker A places 1.0 BTC at 60500 first
    matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5006,
        client_id_hash=106,
        side_str="SELL",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=60500.0,
        qty_float=1.0
    )

    # Maker B places 2.0 BTC at 60500 second
    matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5007,
        client_id_hash=107,
        side_str="SELL",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=60500.0,
        qty_float=2.0
    )

    # Taker buys 1.5 BTC: FIFO mandates Maker A (5006) is filled first!
    num_reports, reports = matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5008,
        client_id_hash=108,
        side_str="BUY",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=60500.0,
        qty_float=1.5
    )

    assert num_reports == 2
    assert reports[0]["maker_order_id"] == 5006
    assert reports[0]["quantity"] == 1.0

    assert reports[1]["maker_order_id"] == 5007
    assert reports[1]["quantity"] == 0.5

def test_cancel_order():
    matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5009,
        client_id_hash=109,
        side_str="BUY",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=59000.0,
        qty_float=3.0
    )

    depth_before = matching_engine.get_market_depth("BTC-USD", max_depth=5)
    assert len(depth_before["bids"]) == 1

    success, report = matching_engine.cancel_order("BTC-USD", 5009)
    assert success is True
    assert report["order_id"] == 5009
    assert report["status"] == "CANCELLED"
    assert report["cancelled_quantity"] == 3.0

    depth_after = matching_engine.get_market_depth("BTC-USD", max_depth=5)
    assert len(depth_after["bids"]) == 0

def test_time_in_force_ioc():
    # Only 0.5 BTC available at 61000
    matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5010,
        client_id_hash=110,
        side_str="SELL",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=61000.0,
        qty_float=0.5
    )

    # Buyer wants 2.0 BTC with IOC: should fill 0.5, and cancel remaining 1.5 immediately
    num_reports, reports = matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5011,
        client_id_hash=111,
        side_str="BUY",
        type_str="LIMIT",
        tif_str="IOC",
        price_float=61000.0,
        qty_float=2.0
    )

    assert num_reports == 2
    assert reports[0]["status"] == "PARTIAL_FILL"
    assert reports[0]["quantity"] == 0.5
    assert reports[1]["status"] == "CANCELLED"
    assert reports[1]["quantity"] == 1.5

    # No resting bid in the book
    depth = matching_engine.get_market_depth("BTC-USD", max_depth=5)
    assert len(depth["bids"]) == 0

def test_time_in_force_fok():
    # Only 1.0 BTC available
    matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5012,
        client_id_hash=112,
        side_str="SELL",
        type_str="LIMIT",
        tif_str="GTC",
        price_float=62000.0,
        qty_float=1.0
    )

    # Buyer requests 3.0 BTC with FOK: Not enough depth -> must REJECT completely
    num_reports, reports = matching_engine.submit_order(
        symbol="BTC-USD",
        order_id=5013,
        client_id_hash=113,
        side_str="BUY",
        type_str="LIMIT",
        tif_str="FOK",
        price_float=62000.0,
        qty_float=3.0
    )

    assert num_reports == 1
    assert reports[0]["status"] == "REJECTED"

    # Maker order 5012 must still be intact in the book
    depth = matching_engine.get_market_depth("BTC-USD", max_depth=5)
    assert len(depth["asks"]) == 1
    assert depth["asks"][0]["volume"] == 1.0
