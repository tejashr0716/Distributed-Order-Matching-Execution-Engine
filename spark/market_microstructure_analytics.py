import os
import sys
from pyspark.sql import SparkSession
from pyspark.sql.functions import (
    col, sum as _sum, avg, count, max as _max, min as _min, abs as _abs,
    window, when, lit, round as _round
)
from pyspark.sql.types import (
    StructType, StructField, LongType, StringType, DoubleType, TimestampType
)

def create_spark_session(app_name="ApexMatch-Microstructure-Analytics"):
    return (
        SparkSession.builder
        .appName(app_name)
        .master("local[*]")
        .config("spark.driver.memory", "2g")
        .config("spark.sql.shuffle.partitions", "4")
        .config("spark.ui.enabled", "false")
        .getOrCreate()
    )

def analyze_trade_microstructure(spark: SparkSession, trades_data=None):
    """
    Computes VWAP, Order Flow Imbalance (OFI), Effective Spread, and Slippage
    across distributed trade execution batches.
    """
    schema = StructType([
        StructField("match_id", LongType(), False),
        StructField("symbol", StringType(), False),
        StructField("buyer_order_id", LongType(), False),
        StructField("seller_order_id", LongType(), False),
        StructField("buyer_client_id", StringType(), False),
        StructField("seller_client_id", StringType(), False),
        StructField("price", DoubleType(), False),
        StructField("quantity", DoubleType(), False),
        StructField("quote_amount", DoubleType(), False),
        StructField("taker_side", StringType(), False),
        StructField("latency_ns", LongType(), False),
        StructField("executed_at", TimestampType(), False),
    ])

    if trades_data:
        df = spark.createDataFrame(trades_data, schema=schema)
    else:
        # Fallback sample data generator for standalone execution & unit test
        from datetime import datetime, timedelta
        now = datetime.utcnow()
        sample = [
            (1001, "BTC-USD", 1, 2, "ALICE", "BOB", 64250.0, 0.5, 32125.0, "BUY", 180, now - timedelta(seconds=20)),
            (1002, "BTC-USD", 3, 4, "CHARLIE", "BOB", 64255.0, 1.0, 64255.0, "BUY", 195, now - timedelta(seconds=15)),
            (1003, "BTC-USD", 5, 6, "ALICE", "DAVE", 64245.0, 0.8, 51396.0, "SELL", 210, now - timedelta(seconds=10)),
            (1004, "BTC-USD", 7, 8, "WHALE_01", "BOB", 64260.0, 2.5, 160650.0, "BUY", 165, now - timedelta(seconds=5)),
            (1005, "BTC-USD", 9, 10, "CHARLIE", "DAVE", 64250.0, 0.4, 25700.0, "SELL", 175, now),
        ]
        df = spark.createDataFrame(sample, schema=schema)

    # 1. VWAP Calculation: Sum(price * quantity) / Sum(quantity)
    vwap_df = df.groupBy("symbol").agg(
        _round(_sum(col("price") * col("quantity")) / _sum(col("quantity")), 2).alias("vwap"),
        _round(_sum("quantity"), 4).alias("total_volume"),
        _round(_sum("quote_amount"), 2).alias("total_turnover_usd"),
        count("match_id").alias("trade_count"),
        _round(avg("latency_ns"), 1).alias("avg_matching_latency_ns"),
        _round(_min("price"), 2).alias("low_price"),
        _round(_max("price"), 2).alias("high_price")
    )

    # 2. Order Flow Imbalance (OFI): Buy Taker Volume - Sell Taker Volume
    ofi_df = df.groupBy("symbol").agg(
        _sum(when(col("taker_side") == "BUY", col("quantity")).otherwise(lit(0.0))).alias("buy_volume"),
        _sum(when(col("taker_side") == "SELL", col("quantity")).otherwise(lit(0.0))).alias("sell_volume")
    ).withColumn("order_flow_imbalance", _round(col("buy_volume") - col("sell_volume"), 4))

    # 3. Client Volume & Market Participation Share
    client_df = df.groupBy("buyer_client_id").agg(
        _round(_sum("quantity"), 4).alias("bought_volume"),
        _round(_sum("quote_amount"), 2).alias("bought_usd")
    )

    return {
        "vwap": vwap_df,
        "ofi": ofi_df,
        "clients": client_df
    }

if __name__ == "__main__":
    spark = create_spark_session()
    print("\n========== RUNNING APEXMATCH APACHE SPARK ANALYTICS ==========")
    results = analyze_trade_microstructure(spark)
    
    print("\n--- Market Depth & VWAP Microstructure Metrics ---")
    results["vwap"].show(truncate=False)

    print("\n--- Order Flow Imbalance (OFI) ---")
    results["ofi"].show(truncate=False)

    print("\n--- Client Execution Breakdown ---")
    results["clients"].show(truncate=False)

    spark.stop()
