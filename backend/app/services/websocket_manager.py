import json
import logging
from typing import Dict, Set
from fastapi import WebSocket

logger = logging.getLogger("ApexMatch.WebSocket")

class WebSocketManager:
    def __init__(self):
        # symbol -> set of WebSockets
        self.depth_subscribers: Dict[str, Set[WebSocket]] = {}
        self.trades_subscribers: Dict[str, Set[WebSocket]] = {}

    async def connect_depth(self, symbol: str, websocket: WebSocket):
        await websocket.accept()
        if symbol not in self.depth_subscribers:
            self.depth_subscribers[symbol] = set()
        self.depth_subscribers[symbol].add(websocket)
        logger.info(f"WebSocket client connected to depth feed for {symbol}")

    def disconnect_depth(self, symbol: str, websocket: WebSocket):
        if symbol in self.depth_subscribers:
            self.depth_subscribers[symbol].discard(websocket)

    async def connect_trades(self, symbol: str, websocket: WebSocket):
        await websocket.accept()
        if symbol not in self.trades_subscribers:
            self.trades_subscribers[symbol] = set()
        self.trades_subscribers[symbol].add(websocket)
        logger.info(f"WebSocket client connected to trades feed for {symbol}")

    def disconnect_trades(self, symbol: str, websocket: WebSocket):
        if symbol in self.trades_subscribers:
            self.trades_subscribers[symbol].discard(websocket)

    async def broadcast_depth(self, symbol: str, data: dict):
        if symbol in self.depth_subscribers:
            payload = json.dumps(data)
            dead_sockets = set()
            for ws in self.depth_subscribers[symbol]:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead_sockets.add(ws)
            for ws in dead_sockets:
                self.depth_subscribers[symbol].discard(ws)

    async def broadcast_trade(self, symbol: str, data: dict):
        if symbol in self.trades_subscribers:
            payload = json.dumps(data, default=str)
            dead_sockets = set()
            for ws in self.trades_subscribers[symbol]:
                try:
                    await ws.send_text(payload)
                except Exception:
                    dead_sockets.add(ws)
            for ws in dead_sockets:
                self.trades_subscribers[symbol].discard(ws)

ws_manager = WebSocketManager()
