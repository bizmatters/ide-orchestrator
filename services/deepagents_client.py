"""
DeepAgents Runtime client for external service communication.

This module handles all communication with the deepagents-runtime service,
including HTTP calls, WebSocket connections, and cleanup operations.
"""

import asyncio
import httpx
import pybreaker
from typing import Dict, Any, Optional
from opentelemetry import trace
from opentelemetry.propagate import inject
from core.metrics import metrics

tracer = trace.get_tracer(__name__)

# Circuit breaker for deepagents-runtime calls
deepagents_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    exclude=[httpx.HTTPStatusError]  # Don't break on HTTP errors, only on connection issues
)


class DeepAgentsRuntimeClient:
    """Client for communicating with deepagents-runtime service."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
    
    @deepagents_breaker
    async def invoke_job(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Invoke a job on deepagents-runtime.
        
        Args:
            payload: Job payload with job_id, trace_id, agent_definition, input_payload
            
        Returns:
            Response from deepagents-runtime with thread_id
            
        Raises:
            Exception: If the request fails
        """
        with tracer.start_as_current_span("deepagents_invoke") as span:
            span.set_attributes({
                "job_id": payload.get("job_id", "unknown"),
                "trace_id": payload.get("trace_id", "unknown")
            })
            
            headers = {}
            inject(headers)  # Inject OpenTelemetry trace context
            
            try:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    response = await client.post(
                        f"{self.base_url}/invoke",
                        json=payload,
                        headers=headers
                    )
                    
                    metrics.record_deepagents_request("invoke", str(response.status_code))
                    span.set_attributes({"http.status_code": response.status_code})
                    
                    if response.status_code != 200:
                        error_msg = f"Deepagents-runtime invoke failed: {response.status_code}"
                        span.record_exception(Exception(error_msg))
                        raise Exception(error_msg)
                    
                    return response.json()
                    
            except httpx.RequestError as e:
                metrics.record_deepagents_request("invoke", "error")
                span.record_exception(e)
                raise Exception(f"Network error calling deepagents-runtime: {str(e)}")
    
    @deepagents_breaker
    async def get_execution_state(self, thread_id: str) -> Dict[str, Any]:
        """
        Get execution state for a thread.
        
        Args:
            thread_id: Thread ID from deepagents-runtime
            
        Returns:
            Execution state with status, result, generated_files
            
        Raises:
            Exception: If the request fails
        """
        with tracer.start_as_current_span("deepagents_get_state") as span:
            span.set_attributes({"thread_id": thread_id})
            
            headers = {}
            inject(headers)
            
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.get(
                        f"{self.base_url}/state/{thread_id}",
                        headers=headers
                    )
                    
                    metrics.record_deepagents_request("state", str(response.status_code))
                    span.set_attributes({"http.status_code": response.status_code})
                    
                    if response.status_code == 200:
                        return response.json()
                    else:
                        error_msg = f"Failed to get execution state: {response.status_code}"
                        span.record_exception(Exception(error_msg))
                        raise Exception(error_msg)
                        
            except httpx.RequestError as e:
                metrics.record_deepagents_request("state", "error")
                span.record_exception(e)
                raise Exception(f"Network error getting execution state: {str(e)}")
    
    async def cleanup_thread_data(self, thread_id: str) -> bool:
        """
        Clean up deepagents-runtime checkpointer data for a thread.
        
        This is a best-effort operation that won't raise exceptions.
        
        Args:
            thread_id: Thread ID to clean up
            
        Returns:
            True if cleanup succeeded, False otherwise
        """
        with tracer.start_as_current_span("deepagents_cleanup") as span:
            span.set_attributes({"thread_id": thread_id})
            
            try:
                headers = {}
                inject(headers)
                
                async with httpx.AsyncClient(timeout=10.0) as client:
                    response = await client.delete(
                        f"{self.base_url}/cleanup/{thread_id}",
                        headers=headers
                    )
                    
                    metrics.record_deepagents_request("cleanup", str(response.status_code))
                    span.set_attributes({"http.status_code": response.status_code})
                    
                    if response.status_code in [200, 204, 404]:
                        return True
                    else:
                        span.record_exception(Exception(f"Cleanup failed: {response.status_code}"))
                        return False
                        
            except Exception as e:
                metrics.record_deepagents_request("cleanup", "error")
                span.record_exception(e)
                return False
    
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
        Process a complete refinement job from invoke to completion.
        
        Args:
            proposal_id: Proposal ID
            thread_id: Thread ID for tracking
            user_prompt: User's refinement instructions
            current_specification: Current agent specification
            context_file_path: Optional file path for context
            context_selection: Optional text selection for context
            
        Returns:
            Final execution state with generated files
            
        Raises:
            Exception: If processing fails
        """
        # Prepare payload for deepagents-runtime
        payload = {
            "job_id": f"refinement-{proposal_id}",
            "trace_id": f"trace-{proposal_id}",
            "agent_definition": current_specification,
            "input_payload": {
                "instructions": user_prompt,
                "context": context_selection or "",
                "context_file_path": context_file_path
            }
        }
        
        # Invoke the job
        invoke_result = await self.invoke_job(payload)
        runtime_thread_id = invoke_result.get("thread_id", thread_id)
        
        # Poll for completion (in real implementation, this would use WebSocket)
        await asyncio.sleep(2)  # Give it time to process
        
        # Get final state
        return await self.get_execution_state(runtime_thread_id)