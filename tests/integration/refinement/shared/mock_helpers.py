"""
DeepAgents mock setup utilities for refinement integration tests.

Provides in-process HTTP and WebSocket mock server for deepagents-runtime endpoints only.
The production WebSocket proxy in ide-orchestrator will connect to this mock.
"""

import time
import json
import asyncio
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
from aiohttp import web, WSMsgType
import aiohttp


class DeepAgentsMockServer:
    """
    In-process HTTP and WebSocket mock server for deepagents-runtime endpoints only.
    
    This follows the integration testing pattern by mocking only the external
    deepagents-runtime HTTP and WebSocket endpoints. The production WebSocket proxy in
    ide-orchestrator will connect to this mock server.
    """
    
    def __init__(self, scenario: str = "approved"):
        self.scenario = scenario
        self.server = None
        self.port = None
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
    
    async def start(self):
        """Start the combined HTTP and WebSocket mock server."""
        app = web.Application()
        
        # Add HTTP routes
        app.router.add_post('/invoke', self._handle_invoke)
        app.router.add_get('/state/{thread_id}', self._handle_state)
        app.router.add_get('/stream/{thread_id}', self._handle_websocket)
        
        # Start server on random port, bind to all interfaces for cluster access
        runner = web.AppRunner(app)
        await runner.setup()
        
        site = web.TCPSite(runner, '0.0.0.0', 0)
        await site.start()
        
        # Get the actual port
        self.port = site._server.sockets[0].getsockname()[1]
        self.server = runner
        
        print(f"[DEBUG] Mock deepagents-runtime server started on port: {self.port}")
        
        # Set environment variable for WebSocket proxy to use mock
        # Since app runs in-process with test (ASGITransport), use localhost
        mock_url = f"http://127.0.0.1:{self.port}"
        os.environ["DEEPAGENTS_RUNTIME_URL"] = mock_url
        print(f"[DEBUG] Set DEEPAGENTS_RUNTIME_URL to: {mock_url}")
    
    async def _handle_invoke(self, request):
        """Handle POST /invoke requests."""
        thread_id = f"test-thread-{int(time.time() * 1000000)}"
        self.thread_states[thread_id] = {
            "status": "running",
            "generated_files": {}
        }
        
        print(f"[DEBUG] Mock invoke handler called, created thread_id: {thread_id}")
        
        return web.json_response({"thread_id": thread_id})
    
    async def _handle_state(self, request):
        """Handle GET /state/{thread_id} requests."""
        thread_id = request.match_info['thread_id']
        
        print(f"[DEBUG] Mock state handler called for thread_id: {thread_id}")
        
        if thread_id in self.thread_states:
            state = self.thread_states[thread_id]
            print(f"[DEBUG] Returning state for {thread_id}: {state['status']}")
            return web.json_response(state)
        else:
            print(f"[DEBUG] Thread {thread_id} not found in states")
            return web.json_response({"error": "Not found"}, status=404)
    
    async def _handle_websocket(self, request):
        """Handle WebSocket upgrade requests from production proxy."""
        thread_id = request.match_info['thread_id']
        print(f"[DEBUG] WebSocket connection received for thread_id: {thread_id}")
        
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        
        try:
            # Send streaming events to simulate deepagents-runtime behavior
            await self._send_streaming_events(ws, thread_id)
        except Exception as e:
            print(f"[DEBUG] WebSocket error for thread {thread_id}: {e}")
        finally:
            await ws.close()
        
        return ws
    
    async def _send_streaming_events(self, ws, thread_id: str):
        """Send streaming events that match deepagents-runtime format."""
        print(f"[DEBUG] Starting streaming events for thread_id: {thread_id}")
        
        # Send initial state update
        await ws.send_str(json.dumps({
            "event_type": "on_state_update",
            "data": {
                "messages": "Starting processing...",
                "files": {}
            }
        }))
        
        # Simulate processing time
        await asyncio.sleep(1)
        
        # Send progress update
        await ws.send_str(json.dumps({
            "event_type": "on_llm_stream",
            "data": {
                "messages": "Processing refinement request..."
            }
        }))
        
        # Simulate more processing time
        await asyncio.sleep(1)
        
        # Send final state update with generated files
        generated_files = self.test_data.get("generated_files", {})
        await ws.send_str(json.dumps({
            "event_type": "on_state_update",
            "data": {
                "messages": "Processing complete",
                "files": generated_files
            }
        }))
        
        # Send end event to signal completion
        await ws.send_str(json.dumps({
            "event_type": "end",
            "data": {}
        }))
        
        print(f"[DEBUG] Completed streaming events for thread_id: {thread_id}")
        
        # Update thread state for HTTP state endpoint
        self.thread_states[thread_id] = {
            "status": "completed",
            "generated_files": generated_files,
            "result": "Processing completed successfully"
        }
    
    async def stop(self):
        """Stop the server and cleanup."""
        if self.server:
            await self.server.cleanup()
            print(f"[DEBUG] Mock server stopped")
        
        # Clean up environment variable
        if "DEEPAGENTS_RUNTIME_URL" in os.environ:
            del os.environ["DEEPAGENTS_RUNTIME_URL"]
            print(f"[DEBUG] Cleaned up DEEPAGENTS_RUNTIME_URL environment variable")
        
        print(f"[DEBUG] Mock deepagents-runtime stopped")


def create_mock_deepagents_server(scenario: str = "approved") -> DeepAgentsMockServer:
    """
    Create in-process HTTP and WebSocket mock server for deepagents-runtime.
    
    This follows the integration testing pattern by mocking only the external
    deepagents-runtime HTTP and WebSocket endpoints. The production WebSocket proxy will
    connect to this mock server.
    
    Args:
        scenario: Test scenario to load data for
        
    Returns:
        DeepAgentsMockServer instance
    """
    print(f"[DEBUG] Creating mock deepagents server for scenario: {scenario}")
    return DeepAgentsMockServer(scenario)


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