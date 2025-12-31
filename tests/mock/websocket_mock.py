"""
WebSocket mock server for deepagents-runtime using websockets library.
Matches production client protocol for compatibility.
"""

import json
import asyncio
import websockets


class WebSocketMockServer:
    """WebSocket mock server using websockets library."""
    
    def __init__(self, port: int = 8001, test_data: dict = None):
        self.port = port
        self.server = None
        self.test_data = test_data or {}
        self.thread_states = {}
    
    async def start(self):
        """Start WebSocket server."""
        self.server = await websockets.serve(
            self._handle_connection,
            '0.0.0.0',
            self.port
        )
        print(f"[DEBUG] WebSocket mock server started on port: {self.port}")
    
    async def _handle_connection(self, websocket, path):
        """Handle WebSocket connections."""
        print(f"[DEBUG] ===== WebSocket connected =====")
        print(f"[DEBUG] Path: {path}")
        
        if path.startswith('/stream/'):
            thread_id = path.split('/')[-1]
            print(f"[DEBUG] Thread ID: {thread_id}")
            try:
                await self._send_streaming_events(websocket, thread_id)
            except Exception as e:
                print(f"[DEBUG] WebSocket error: {e}")
                import traceback
                print(f"[DEBUG] {traceback.format_exc()}")
        else:
            print(f"[DEBUG] Unknown path: {path}")
    
    async def _send_streaming_events(self, ws, thread_id: str):
        """Send streaming events matching deepagents-runtime format."""
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
        generated_files = self.test_data.get("generated_files", {})
        await ws.send(json.dumps({
            "event_type": "on_state_update",
            "data": {"messages": "Complete", "files": generated_files}
        }))
        print(f"[DEBUG] Event 3 sent")
        
        # Event 4: End
        await ws.send(json.dumps({"event_type": "end", "data": {}}))
        print(f"[DEBUG] End event sent")
        
        self.thread_states[thread_id] = {
            "status": "completed",
            "generated_files": generated_files
        }
        print(f"[DEBUG] Streaming complete for: {thread_id}")
    
    async def stop(self):
        """Stop server."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            print(f"[DEBUG] WebSocket mock server stopped")
