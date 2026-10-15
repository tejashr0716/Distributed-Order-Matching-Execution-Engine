import pytest
from datetime import datetime, timedelta
from spark.market_microstructure_analytics import create_spark_session, analyze_trade_microstructure

def test_spark_vwap_and_microstructure():
    spark = create_spark_session("ApexMatch-Test-Spark")
    try:
        now = datetime.utcnow()
        trades = [
            (9001, "BTC-USD", 1, 2, "ALICE", "BOB", 60000.0, 1.0, 60000.0, "BUY", 150, now),
            (9002, "BTC-USD", 3, 4, "CHARLIE", "BOB", 61000.0, 2.0, 122000.0, "BUY", 180, now),
        ]
        # Weighted avg: (60000*1 + 61000*2) / 3 = 182000 / 3 = 60666.67
        results = analyze_trade_microstructure(spark, trades)
        vwap_rows = results["vwap"].collect()
        assert len(vwap_rows) == 1
        assert vwap_rows[0]["vwap"] == 60666.67
        assert vwap_rows[0]["total_volume"] == 3.0
        assert vwap_rows[0]["trade_count"] == 2

        ofi_rows = results["ofi"].collect()
        assert len(ofi_rows) == 1
        assert ofi_rows[0]["order_flow_imbalance"] == 3.0 # All buy taker
    finally:
        spark.stop()
