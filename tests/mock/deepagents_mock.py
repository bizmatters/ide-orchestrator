"""
Mock DeepAgents Runtime Server and Client for testing.

Provides HTTP and WebSocket endpoints that simulate the deepagents-runtime service
using test data from testdata/ directory, plus a mock client that can be used
in integration tests.
"""

import json
import asyncio
import time
from pathlib import Path
from typing import Dict, Any, List, Optional
from unittest.mock import AsyncMock
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import uvicorn


class MockDeepAgentsRuntimeClient:
    """
    Mock implementation of DeepAgentsRuntimeClient for testing.
    
    This mock simulates the behavior of the real DeepAgentsRuntimeClient
    without making actual HTTP calls to deepagents-runtime.
    """
    
    def __init__(self, base_url: str = "http://mock-deepagents"):
        self.base_url = base_url
        self.mock_responses = {}
        self.call_count = 0
        
        # Load test data from testdata directory
        self.testdata_dir = Path(__file__).parent.parent / "testdata"
        self.test_events = []
        self.test_state = {}
        self._load_test_data()
    
    def _load_test_data(self):
        """Load test data from JSON files."""
        # Load all_events.json
        events_path = self.testdata_dir / "all_events.json"
        with open(events_path, 'r') as f:
            self.test_events = json.load(f)
        
        # Load thread_state.json
        state_path = self.testdata_dir / "thread_state.json"
        with open(state_path, 'r') as f:
            self.test_state = json.load(f)
    
    def set_mock_response(self, method: str, response: Dict[str, Any]):
        """Set mock response for a specific method."""
        self.mock_responses[method] = response
    
    async def invoke_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Mock implementation of invoke_job method.
        
        Args:
            payload: Job payload with job_id, trace_id, agent_definition, input_payload
            
        Returns:
            Mock response with thread_id from test data
        """
        self.call_count += 1
        
        # Return mock response if set, otherwise use test data
        if "invoke_job" in self.mock_responses:
            return self.mock_responses["invoke_job"]
        
        # Use real test data
        return {
            "thread_id": self.test_state["thread_id"],
            "status": "started"
        }
    
    async def get_execution_state(self, thread_id: str) -> Dict[str, Any]:
        """
        Mock implementation of get_execution_state method.
        
        Args:
            thread_id: Thread ID from deepagents-runtime
            
        Returns:
            Mock execution state using test data
        """
        if "get_execution_state" in self.mock_responses:
            return self.mock_responses["get_execution_state"]
        
        # Use real test data, update thread_id to match the requested one
        state = self.test_state.copy()
        state["thread_id"] = thread_id
        return state
    
    async def cleanup_thread_data(self, thread_id: str) -> bool:
        """
        Mock implementation of cleanup_thread_data method.
        
        Args:
            thread_id: Thread ID to clean up
            
        Returns:
            True (always succeeds in mock)
        """
        return True
    
    async def process_refinement_job(
        self,
        proposal_id: str,
        thread_id: str,
        user_prompt: str,
        current_specification: Dict[str, Any],
        context_file_path: Optional[str] = None,
        context_selection: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Mock implementation of process_refinement_job method.
        
        Returns mock final execution state using real test data.
        """
        if "process_refinement_job" in self.mock_responses:
            return self.mock_responses["process_refinement_job"]
        
        # Use real test data
        state = self.test_state.copy()
        state["thread_id"] = thread_id
        return state


class MockDeepAgentsServer:
    """Mock implementation of deepagents-runtime service."""
    
    def __init__(self, testdata_dir: Path = None):
        """
        Initialize mock server with test data.
        
        Args:
            testdata_dir: Path to testdata directory containing all_events.json and thread_state.json
        """
        if testdata_dir is None:
            testdata_dir = Path(__file__).parent.parent / "testdata"
        
        self.testdata_dir = testdata_dir
        self.all_events: List[Dict[str, Any]] = []
        self.thread_state: Dict[str, Any] = {}
        
        # Load test data
        self._load_test_data()
        
        # Create FastAPI app
        self.app = FastAPI()
        self._setup_routes()
    
    def _load_test_data(self):
        """Load test data from JSON files."""
        # Load all_events.json
        events_path = self.testdata_dir / "all_events.json"
        with open(events_path, 'r') as f:
            self.all_events = json.load(f)
        
        # Load thread_state.json
        state_path = self.testdata_dir / "thread_state.json"
        with open(state_path, 'r') as f:
            self.thread_state = json.load(f)
    
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.post("/invoke")
        async def invoke():
            """Handle POST /invoke requests."""
            return JSONResponse({
                "thread_id": self.thread_state["thread_id"],
                "status": "started"
            })
        
        @self.app.get("/state/{thread_id}")
        async def get_state(thread_id: str):
            """Handle GET /state/{thread_id} requests."""
            state = self.thread_state.copy()
            state["thread_id"] = thread_id
            return JSONResponse(state)
        
        @self.app.websocket("/stream/{thread_id}")
        async def stream_events(websocket: WebSocket, thread_id: str):
            """Handle WebSocket /stream/{thread_id} requests."""
            await websocket.accept()
            
            try:
                # Stream all events sequentially
                for event in self.all_events:
                    await websocket.send_json(event)
                
                # Close connection after streaming all events
                await websocket.close()
            except WebSocketDisconnect:
                pass
    
    def run(self, host: str = "127.0.0.1", port: int = 8000):
        """
        Run the mock server.
        
        Args:
            host: Host to bind to
            port: Port to bind to
        """
        uvicorn.run(self.app, host=host, port=port)
    
    def get_app(self) -> FastAPI:
        """Get the FastAPI application instance."""
        return self.app


def create_mock_server(testdata_dir: Path = None) -> MockDeepAgentsServer:
    """
    Create a mock deepagents server instance.
    
    Args:
        testdata_dir: Path to testdata directory
        
    Returns:
        MockDeepAgentsServer instance
    """
    return MockDeepAgentsServer(testdata_dir)
