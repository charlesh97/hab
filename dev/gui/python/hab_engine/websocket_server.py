"""WebSocket Server — broadcasts engine status to macOS dashboard clients."""

import asyncio
import json
import logging
import threading
from typing import Optional, Set, Any, Dict
from .models import WSMessageType

logger = logging.getLogger(__name__)

try:
    import websockets
    HAS_WEBSOCKETS = True
except ImportError:
    HAS_WEBSOCKETS = False


class WebSocketServer:
    """
    Lightweight WebSocket server for macOS app communication.
    Runs on localhost:8765 by default.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self.host = host
        self.port = port
        self._server = None
        self._thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._clients: Set[Any] = set()
        self._running = False
        self._command_handler: Optional[callable] = None
        self._message_queue: asyncio.Queue = None

    def set_command_handler(self, handler: callable):
        """Set callback for incoming commands from clients."""
        self._command_handler = handler

    def start(self):
        """Start the WebSocket server in a background thread."""
        if not HAS_WEBSOCKETS:
            logger.warning("websockets not installed — WebSocket server disabled")
            return
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        logger.info(f"WebSocket server starting on ws://{self.host}:{self.port}")

    def _run_server(self):
        """Run the asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._message_queue = asyncio.Queue()

        async def handler(websocket):
            self._clients.add(websocket)
            logger.info(f"WebSocket client connected ({len(self._clients)} total)")
            try:
                async for raw in websocket:
                    try:
                        msg = json.loads(raw)
                        if self._command_handler:
                            await self._command_handler(msg)
                    except json.JSONDecodeError:
                        logger.warning(f"Invalid WS message: {raw[:100]}")
            except Exception as e:
                logger.debug(f"WebSocket client disconnected: {e}")
            finally:
                self._clients.discard(websocket)

        async def main():
            self._server = await websockets.serve(
                handler, self.host, self.port,
                ping_interval=30, ping_timeout=10,
            )
            logger.info(f"WebSocket server listening on {self.host}:{self.port}")
            await self._server.wait_closed()

        try:
            self._loop.run_until_complete(main())
        except Exception as e:
            logger.error(f"WebSocket server error: {e}")
        finally:
            self._running = False
            self._loop.close()

    def broadcast(self, message: Dict[str, Any]):
        """Send a JSON message to all connected clients."""
        if not self._running or not self._loop or not self._clients:
            return

        payload = json.dumps(message)

        async def _send():
            if not self._clients:
                return
            dead = set()
            for ws in self._clients:
                try:
                    await ws.send(payload)
                except Exception:
                    dead.add(ws)
            self._clients -= dead

        asyncio.run_coroutine_threadsafe(_send(), self._loop)

    def broadcast_spectrum(self, frequencies: list, power_db: list,
                           center_freq: float, span_hz: float):
        """Broadcast spectrum frame to all clients."""
        step = max(1, len(frequencies) // 256)
        self.broadcast({
            "type": WSMessageType.SPECTRUM.value,
            "data": {
                "f": list(frequencies[::step]),
                "p": list(power_db[::step]),
                "fc": center_freq,
                "span": span_hz,
            }
        })

    def broadcast_status(self, status: Dict[str, Any]):
        """Broadcast engine status."""
        self.broadcast({
            "type": WSMessageType.STATUS.value,
            "data": status,
        })

    def stop(self):
        """Stop the WebSocket server."""
        self._running = False
        if self._server and self._loop:
            self._server.close()
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread:
            self._thread.join(timeout=3)
        logger.info("WebSocket server stopped")
