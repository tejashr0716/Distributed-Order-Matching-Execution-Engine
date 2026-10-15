import time
import random
from datetime import datetime
from fastapi import APIRouter, HTTPException, Depends
from typing import List, Dict, Any

from ..schemas.order import OrderCreate, OrderResponse, OrderCancelResponse, ExecutionFill
from ..services.matching_engine_wrapper import matching_engine
from ..services.database_service import db_service
from ..services.redis_service import redis_service
from ..services.rabbitmq_service import rabbitmq_service
from ..services.cosmos_service import cosmos_service
from ..services.websocket_manager import ws_manager

router = APIRouter(prefix="/orders", tags=["Orders"])

# Helper for unique ID generation
def generate_order_id() -> int:
    return int(time.time() * 1000) * 1000 + random.randint(100, 999)

def hash_client_id(client_id: str) -> int:
    return abs(hash(client_id)) % (2**63 - 1)

@router.post("", response_model=OrderResponse)
async def place_order(order_req: OrderCreate):
    # 1. Validate Account & Balance
    account = await db_service.get_account(order_req.client_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Trader account '{order_req.client_id}' not found.")
    
    # Balance Pre-check
    estimated_notional = order_req.price * order_req.quantity
    if order_req.side == "BUY" and order_req.type == "LIMIT":
        if float(account["fiat_balance"]) < estimated_notional:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient fiat balance (${float(account['fiat_balance']):.2f} available, ${estimated_notional:.2f} required)"
            )
    elif order_req.side == "SELL":
        if float(account["asset_balance"]) < order_req.quantity:
            raise HTTPException(
                status_code=400, 
                detail=f"Insufficient asset balance ({float(account['asset_balance']):.4f} available, {order_req.quantity:.4f} required)"
            )

    order_id = generate_order_id()
    client_hash = hash_client_id(order_req.client_id)

    # 2. Submit to Sub-Microsecond C++ Matching Engine
    num_reports, reports = matching_engine.submit_order(
        symbol=order_req.symbol,
        order_id=order_id,
        client_id_hash=client_hash,
        side_str=order_req.side.value,
        type_str=order_req.type.value,
        tif_str=order_req.tif.value,
        price_float=order_req.price,
        qty_float=order_req.quantity
    )

    # 3. Determine Execution Status & Remaining Quantity
    filled_qty = 0.0
    engine_latency_ns = 0
    fills: List[ExecutionFill] = []
    final_status = "ACCEPTED"

    for r in reports:
        engine_latency_ns = max(engine_latency_ns, r["latency_ns"])
        status = r["status"]
        if status in ("FULL_FILL", "PARTIAL_FILL"):
            filled_qty += r["quantity"]
            fills.append(ExecutionFill(**r))
            
            # Record executed trade in database & event streams
            match_id = r["match_id"]
            quote_amount = round(r["price"] * r["quantity"], 4)
            buyer_client = order_req.client_id if order_req.side == "BUY" else "COUNTERPARTY"
            seller_client = order_req.client_id if order_req.side == "SELL" else "COUNTERPARTY"
            buyer_ord = order_id if order_req.side == "BUY" else r["maker_order_id"]
            seller_ord = order_id if order_req.side == "SELL" else r["maker_order_id"]

            trade_record = {
                "match_id": match_id,
                "symbol": order_req.symbol,
                "buyer_order_id": buyer_ord,
                "seller_order_id": seller_ord,
                "buyer_client_id": buyer_client,
                "seller_client_id": seller_client,
                "price": r["price"],
                "quantity": r["quantity"],
                "quote_amount": quote_amount,
                "taker_side": order_req.side.value,
                "latency_ns": r["latency_ns"],
                "executed_at": datetime.utcnow().isoformat()
            }

            # Async DB record
            await db_service.record_trade(
                match_id=match_id,
                symbol=order_req.symbol,
                buyer_order_id=buyer_ord,
                seller_order_id=seller_ord,
                buyer_client_id=buyer_client,
                seller_client_id=seller_client,
                price=r["price"],
                quantity=r["quantity"],
                quote_amount=quote_amount,
                taker_side=order_req.side.value,
                latency_ns=r["latency_ns"]
            )

            # Publish trade to RabbitMQ exchange for async clearing & settlement
            await rabbitmq_service.publish_trade_execution(trade_record)

            # Publish trade to Redis pub/sub and update ticker
            await redis_service.publish_trade(order_req.symbol, trade_record)
            await redis_service.update_ticker(order_req.symbol, r["price"], r["quantity"])

            # Broadcast live trade to WebSockets
            await ws_manager.broadcast_trade(order_req.symbol, trade_record)

        elif status == "NEW_RESTING":
            final_status = "ACCEPTED"
        elif status == "REJECTED":
            final_status = "REJECTED"
        elif status == "CANCELLED":
            final_status = "CANCELLED"

    rem_qty = max(0.0, round(order_req.quantity - filled_qty, 4))
    if filled_qty >= order_req.quantity:
        final_status = "FILLED"
    elif filled_qty > 0:
        final_status = "PARTIALLY_FILLED"

    # 4. Persist Order in PostgreSQL Database
    await db_service.record_order(
        order_id=order_id,
        client_id=order_req.client_id,
        symbol=order_req.symbol,
        side=order_req.side.value,
        order_type=order_req.type.value,
        tif=order_req.tif.value,
        price=order_req.price,
        quantity=order_req.quantity,
        status=final_status,
        remaining_quantity=rem_qty,
        filled_quantity=filled_qty
    )

    # 5. Broadcast Updated L2 Depth
    depth = matching_engine.get_market_depth(order_req.symbol, max_depth=20)
    await redis_service.publish_depth_update(order_req.symbol, depth)
    await ws_manager.broadcast_depth(order_req.symbol, depth)

    # 6. Audit Trail to Cosmos DB / NoSQL
    await cosmos_service.record_audit_event("ORDER_SUBMISSION", {
        "order_id": order_id,
        "client_id": order_req.client_id,
        "symbol": order_req.symbol,
        "side": order_req.side.value,
        "price": order_req.price,
        "quantity": order_req.quantity,
        "status": final_status,
        "filled_quantity": filled_qty,
        "latency_ns": engine_latency_ns
    })

    return OrderResponse(
        order_id=order_id,
        client_id=order_req.client_id,
        symbol=order_req.symbol,
        side=order_req.side.value,
        type=order_req.type.value,
        tif=order_req.tif.value,
        price=order_req.price,
        quantity=order_req.quantity,
        filled_quantity=filled_qty,
        remaining_quantity=rem_qty,
        status=final_status,
        fills=fills,
        engine_latency_ns=engine_latency_ns,
        created_at=datetime.utcnow()
    )

@router.delete("/{order_id}", response_model=OrderCancelResponse)
async def cancel_order(order_id: int, symbol: str = "BTC-USD"):
    success, report = matching_engine.cancel_order(symbol, order_id)
    if not success or not report:
        raise HTTPException(status_code=404, detail=f"Order {order_id} not found in active order book or already filled.")

    # Update database
    await db_service.update_order_fill(order_id, 0.0, 0.0, "CANCELLED")

    # Broadcast updated depth
    depth = matching_engine.get_market_depth(symbol, max_depth=20)
    await redis_service.publish_depth_update(symbol, depth)
    await ws_manager.broadcast_depth(symbol, depth)

    # Audit event
    await cosmos_service.record_audit_event("ORDER_CANCELLED", {
        "order_id": order_id,
        "symbol": symbol,
        "latency_ns": report["latency_ns"]
    })

    return OrderCancelResponse(
        order_id=order_id,
        success=True,
        status="CANCELLED",
        cancelled_quantity=report["cancelled_quantity"],
        latency_ns=report["latency_ns"],
        message=f"Order {order_id} cancelled successfully in {report['latency_ns']} ns."
    )

@router.get("/client/{client_id}")
async def get_client_orders(client_id: str, limit: int = 50):
    orders = await db_service.get_client_orders(client_id, limit)
    return {"client_id": client_id, "orders": orders}
