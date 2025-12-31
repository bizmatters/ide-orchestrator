#!/usr/bin/env python3
"""
Local WebSocket handshake test script.
Tests the mock WebSocket server without Docker/Kubernetes overhead.
"""

import asyncio
import websockets
import json
import threading
import time


class SimpleWebSocketMockServer:
    """Simplified WebSocket mock server for local testing."""
    
    def __init__(self, port=8001):
        self.port = port
        self.ws_server = None
        self.ws_loop = None
        self.ws_thread = None
    
    def _run_ws_server(self):
        """Run WebSocket server in separate thread with its own event loop."""
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)
        
        async def start_ws():
            self.ws_server = await websockets.serve(
                self._handle_websocket,
                '0.0.0.0',
                self.port
            )
            print(f"[DEBUG] WebSocket server started on port {self.port} (separate thread)")
            await self.ws_server.wait_closed()
        
        self.ws_loop.run_until_complete(start_ws())
    
    async def _handle_websocket(self, websocket):
        """Handle WebSocket connections."""
        path = websocket.request.path
        thread_id = path.split('/')[-1]
        print(f"[DEBUG] ===== WebSocket connected =====")
        print(f"[DEBUG] Thread ID: {thread_id}")
        print(f"[DEBUG] Path: {path}")
        
        try:
            await self._send_streaming_events(websocket, thread_id)
        except Exception as e:
            print(f"[DEBUG] WebSocket error: {e}")
            import traceback
            print(f"[DEBUG] {traceback.format_exc()}")
    
    async def _send_streaming_events(self, ws, thread_id: str):
        """Send streaming events."""
        print(f"[DEBUG] Starting streaming events for: {thread_id}")
        
        # Event 1: Initial state
        await ws.send(json.dumps({
            "event_type": "on_state_update",
            "data": {"messages": "Starting processing...", "files": {}}
        }))
        print(f"[DEBUG] Event 1 sent")
        
        await asyncio.sleep(0.5)
        
        # Event 2: Progress
        await ws.send(json.dumps({
            "event_type": "on_llm_stream",
            "data": {"messages": "Processing..."}
        }))
        print(f"[DEBUG] Event 2 sent")
        
        await asyncio.sleep(0.5)
        
        # Event 3: Final state with files
        await ws.send(json.dumps({
            "event_type": "on_state_update",
            "data": {"messages": "Complete", "files": {"test.py": {"content": "print('hello')"}}}
        }))
        print(f"[DEBUG] Event 3 sent")
        
        # Event 4: End
        await ws.send(json.dumps({"event_type": "end", "data": {}}))
        print(f"[DEBUG] End event sent")
        
        print(f"[DEBUG] Streaming complete for: {thread_id}")
    
    async def start(self):
        """Start WebSocket server in separate thread."""
        self.ws_thread = threading.Thread(target=self._run_ws_server, daemon=True)
        self.ws_thread.start()
        
        # Wait for server to be ready
        await asyncio.sleep(0.5)
        print(f"[DEBUG] Mock WebSocket server started on port {self.port}")
    
    async def stop(self):
        """Stop server."""
        if self.ws_server and self.ws_loop:
            self.ws_loop.call_soon_threadsafe(self.ws_server.close)
        print(f"[DEBUG] Mock WebSocket server stopped")


async def test_websocket_client():
    """Test WebSocket client connection."""
    print("[TEST] Testing WebSocket client connection...")
    
    try:
        # Connect to WebSocket server
        ws_url = "ws://127.0.0.1:8001/stream/test-thread-123"
        print(f"[TEST] Connecting to: {ws_url}")
        
        async with websockets.connect(ws_url) as websocket:
            print("[TEST] ✅ WebSocket connection successful!")
            
            # Receive events
            event_count = 0
            while True:
                try:
                    message = await websocket.recv()
                    event = json.loads(message)
                    event_count += 1
                    print(f"[TEST] Received event {event_count}: {event.get('event_type')}")
                    
                    if event.get("event_type") == "end":
                        print("[TEST] ✅ Received end event, test complete!")
                        break
                        
                except Exception as e:
                    print(f"[TEST] ❌ Error receiving message: {e}")
                    break
                    
    except Exception as e:
        print(f"[TEST] ❌ WebSocket connection failed: {e}")
        import traceback
        print(f"[TEST] {traceback.format_exc()}")


async def main():
    """Main test function."""
    print("=" * 60)
    print("LOCAL WEBSOCKET HANDSHAKE TEST")
    print("=" * 60)
    
    # Start mock server
    mock_server = SimpleWebSocketMockServer()
    await mock_server.start()
    
    try:
        # Wait a bit for server to fully start
        await asyncio.sleep(1)
        
        # Test client connection
        await test_websocket_client()
        
    finally:
        # Stop server
        await mock_server.stop()
    
    print("=" * 60)
    print("TEST COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())