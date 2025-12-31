"""
DeepAgents mock setup utilities for refinement integration tests.

Provides in-process HTTP and WebSocket mock server for deepagents-runtime endpoints only.
The production WebSocket proxy in ide-orchestrator will connect to this mock.
"""

import time
import json
import asyncio
import os
import threading
from typing import Dict, Any, List, Optional
from pathlib import Path
from aiohttp import web
import websockets


class DeepAgentsMockServer:
    """
    In-process HTTP and WebSocket mock server for deepagents-runtime endpoints only.
    
    Uses websockets library for WebSocket server to match production client.
    Uses aiohttp for HTTP endpoints.
    
    WebSocket server runs in a separate thread to avoid event loop blocking
    when TestClient makes synchronous WebSocket connections.
    """
    
    def __init__(self, scenario: str = "approved", http_port: int = 8000, ws_port: int = 8001):
        self.scenario = scenario
        self.http_server = None
        self.ws_server = None
        self.ws_thread = None
        self.ws_loop = None
        self.http_port = http_port
        self.ws_port = ws_port
        self.test_data = {}
        self.thread_states = {}
        self._load_test_data()
        
    def _load_test_data(self):
        """Load real test data from testdata directory."""
        testdata_dir = Path(__file__).parent.parent.parent.parent / "testdata"
        
        scenario_files = {
            "approved": "thread_state.json",
            "rejected": "rejection_state.json", 
            "isolation_1": "isolation_state_1.json"
        }
        
        if self.scenario in scenario_files:
            state_path = testdata_dir / scenario_files[self.scenario]
            if state_path.exists():
                with open(state_path, 'r') as f:
                    self.test_data = json.load(f)
    
    def _run_ws_server(self):
        """Run WebSocket server in separate thread with its own event loop."""
        self.ws_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.ws_loop)
        
        async def start_ws():
            self.ws_server = await websockets.serve(
                self._handle_websocket,
                '0.0.0.0',
                self.ws_port
            )
            print(f"[DEBUG] WebSocket server started on port {self.ws_port} (separate thread)")
            await self.ws_server.wait_closed()
        
        self.ws_loop.run_until_complete(start_ws())
    
    async def start(self):
        """Start HTTP server on 8000 and WebSocket server on 8001 (in separate thread)."""
        # HTTP server for /invoke endpoint
        app = web.Application()
        app.router.add_post('/invoke', self._handle_invoke)
        app.router.add_get('/state/{thread_id}', self._handle_state)
        
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, '0.0.0.0', self.http_port)
        await site.start()
        self.http_server = runner
        
        # Start WebSocket server in separate thread to avoid event loop blocking
        self.ws_thread = threading.Thread(target=self._run_ws_server, daemon=True)
        self.ws_thread.start()
        
        # Wait for WebSocket server to be ready
        await asyncio.sleep(0.5)
        
        # Set environment variables so production code uses this mock
        mock_url = f"http://127.0.0.1:{self.http_port}"
        mock_ws_url = f"ws://127.0.0.1:{self.ws_port}"
        os.environ["DEEPAGENTS_RUNTIME_URL"] = mock_url
        os.environ["DEEPAGENTS_RUNTIME_WS_URL"] = mock_ws_url
        
        print(f"[DEBUG] Mock deepagents-runtime server started")
        print(f"[DEBUG] HTTP on port {self.http_port}, WebSocket on port {self.ws_port}")
        print(f"[DEBUG] Set DEEPAGENTS_RUNTIME_URL to {mock_url}")
        print(f"[DEBUG] Set DEEPAGENTS_RUNTIME_WS_URL to {mock_ws_url}")
    
    async def _handle_invoke(self, request):
        """Handle POST /invoke requests."""
        thread_id = f"test-thread-{int(time.time() * 1000000)}"
        self.thread_states[thread_id] = {"status": "running", "generated_files": {}}
        print(f"[DEBUG] Mock invoke handler called, created thread_id: {thread_id}")
        return web.json_response({"thread_id": thread_id})
    
    async def _handle_state(self, request):
        """Handle GET /state/{thread_id} requests."""
        thread_id = request.match_info['thread_id']
        if thread_id in self.thread_states:
            return web.json_response(self.thread_states[thread_id])
        return web.json_response({"error": "Not found"}, status=404)
    
    async def _handle_websocket(self, websocket):
        """Handle WebSocket connections using websockets library."""
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
    
    async def stop(self):
        """Stop servers."""
        print(f"[DEBUG] Stopping mock deepagents-runtime server...")
        
        # Stop WebSocket server properly
        if self.ws_server and self.ws_loop:
            print(f"[DEBUG] Closing WebSocket server...")
            # Close the WebSocket server
            self.ws_loop.call_soon_threadsafe(self.ws_server.close)
            
            # Wait for the server to close
            if self.ws_thread and self.ws_thread.is_alive():
                print(f"[DEBUG] Waiting for WebSocket server to close...")
                # Give more time for proper cleanup
                import time
                time.sleep(1.0)
                
                # If thread is still alive, try to stop the loop
                if self.ws_thread.is_alive():
                    print(f"[DEBUG] Stopping WebSocket event loop...")
                    self.ws_loop.call_soon_threadsafe(self.ws_loop.stop)
                    time.sleep(0.5)
        
        # Stop HTTP server
        if self.http_server:
            print(f"[DEBUG] Cleaning up HTTP server...")
            await self.http_server.cleanup()
        
        # Clean up environment variables
        if "DEEPAGENTS_RUNTIME_URL" in os.environ:
            del os.environ["DEEPAGENTS_RUNTIME_URL"]
        if "DEEPAGENTS_RUNTIME_WS_URL" in os.environ:
            del os.environ["DEEPAGENTS_RUNTIME_WS_URL"]
            
        print(f"[DEBUG] Mock deepagents-runtime stopped completely")


def create_mock_deepagents_server(scenario: str = "approved", http_port: int = 8000, ws_port: int = 8001) -> DeepAgentsMockServer:
    """
    Create in-process HTTP and WebSocket mock server for deepagents-runtime.
    
    This follows the integration testing pattern by mocking only the external
    deepagents-runtime HTTP and WebSocket endpoints. The production WebSocket proxy will
    connect to this mock server.
    
    Args:
        scenario: Test scenario to load data for
        http_port: Port for HTTP server (default 8000)
        ws_port: Port for WebSocket server (default 8001)
        
    Returns:
        DeepAgentsMockServer instance
    """
    print(f"[DEBUG] Creating mock deepagents server for scenario: {scenario} on ports {http_port}/{ws_port}")
    return DeepAgentsMockServer(scenario, http_port, ws_port)


async def wait_for_proposal_completion_via_orchestration(
    proposal_service,
    proposal_id: str,
    timeout: int = 30
):
    """
    Wait for proposal completion via the actual production orchestration service.
    
    This follows the integration testing pattern by using the real production
    orchestration service. The WebSocket connection has already been driven
    by the test, so we just need to wait for the database update to complete.
    
    Args:
        proposal_service: ProposalService instance (production service)
        proposal_id: Proposal ID to monitor
        timeout: Maximum wait time in seconds
    """
    print(f"[DEBUG] Waiting for proposal completion via production orchestration service for proposal_id: {proposal_id}")
    
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            # Use production service to check status
            from .database_helpers import get_proposal_by_id
            
            proposal = await get_proposal_by_id(proposal_id)
            if proposal and proposal["status"] == "completed":
                print(f"[DEBUG] Proposal {proposal_id} completed via production orchestration service")
                return proposal
            elif proposal and proposal["status"] == "failed":
                print(f"[DEBUG] Proposal {proposal_id} failed")
                raise Exception(f"Proposal processing failed")
                
        except Exception as e:
            print(f"[DEBUG] Error checking proposal status: {e}")
        
        # Wait before next check
        await asyncio.sleep(0.5)
    
    raise TimeoutError(f"Proposal {proposal_id} did not complete within {timeout} seconds")


# Cleanup tracking for testing requirement 4.5
class RuntimeCleanupTracker:
    """
    Tracks calls to deepagents-runtime cleanup to verify Requirement 4.5.
    """
    
    def __init__(self):
        self.cleanup_calls = []
    
    def record_cleanup_call(self, thread_id: str, success: bool = True):
        """Record a cleanup call for verification."""
        self.cleanup_calls.append({
            "thread_id": thread_id,
            "success": success,
            "timestamp": time.time()
        })
    
    def was_cleanup_called(self, thread_id: str) -> bool:
        """Check if cleanup was called for specific thread_id."""
        return any(call["thread_id"] == thread_id for call in self.cleanup_calls)
    
    def get_cleanup_calls_for_thread(self, thread_id: str) -> list:
        """Get all cleanup calls for specific thread_id."""
        return [call for call in self.cleanup_calls if call["thread_id"] == thread_id]


# Global cleanup tracker instance
_cleanup_tracker = RuntimeCleanupTracker()


def get_cleanup_tracker() -> RuntimeCleanupTracker:
    """Get the global cleanup tracker instance."""
    return _cleanup_tracker


def mock_deepagents_cleanup_call(thread_id: str, success: bool = True):
    """Mock a deepagents-runtime cleanup call."""
    print(f"[DEBUG] Mock cleanup called for thread_id: {thread_id}, success: {success}")
    _cleanup_tracker.record_cleanup_call(thread_id, success)
    return success


def setup_cleanup_tracking():
    """Set up cleanup tracking by patching the cleanup method."""
    from unittest.mock import patch
    
    async def mock_cleanup(self, thread_id: str):
        print(f"[DEBUG] Mock async cleanup called for thread_id: {thread_id}")
        result = mock_deepagents_cleanup_call(thread_id, True)
        print(f"[DEBUG] Mock cleanup result: {result}")
        return result
    
    # Patch the real client to ensure cleanup tracking works
    from services.deepagents_client import DeepAgentsRuntimeClient
    print("[DEBUG] Setting up cleanup tracking patch for real DeepAgentsRuntimeClient")
    return patch.object(DeepAgentsRuntimeClient, 'cleanup_thread_data', mock_cleanup)