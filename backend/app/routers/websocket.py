import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..services.websocket_manager import ws_manager
from ..services.matching_engine_wrapper import matching_engine

router = APIRouter(prefix="/ws", tags=["WebSockets"])

@router.websocket("/depth/{symbol}")
async def websocket_depth_endpoint(websocket: WebSocket, symbol: str = "BTC-USD"):
    await ws_manager.connect_depth(symbol, websocket)
    try:
        # Send initial snapshot immediately upon connection
        initial_depth = matching_engine.get_market_depth(symbol, max_depth=20)
        await websocket.send_text(json.dumps(initial_depth))

        while True:
            # Keep connection alive & handle incoming pings
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect_depth(symbol, websocket)
    except Exception:
        ws_manager.disconnect_depth(symbol, websocket)

@router.websocket("/trades/{symbol}")
async def websocket_trades_endpoint(websocket: WebSocket, symbol: str = "BTC-USD"):
    await ws_manager.connect_trades(symbol, websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        ws_manager.disconnect_trades(symbol, websocket)
    except Exception:
        ws_manager.disconnect_trades(symbol, websocket)
