"""WebSocket endpoints for real-time streaming."""

import json
import asyncio
import logging
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Query, Header
from fastapi.security import HTTPBearer
import websockets
import httpx

from core.jwt_manager import JWTManager
from core.metrics import metrics
from services.orchestration_service import OrchestrationService
from api.dependencies import get_jwt_manager, get_orchestration_service, get_database_url

router = APIRouter(prefix="/api/ws", tags=["websockets"])
logger = logging.getLogger(__name__)


async def validate_websocket_auth(
    websocket: WebSocket,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None)
) -> Optional[str]:
    """
    Validate WebSocket authentication and return user_id.
    
    Checks for JWT token in:
    1. Query parameter: ?token=<jwt_token> (WebSocket standard)
    2. Authorization header: Authorization: Bearer <jwt_token> (fallback)
    """
    jwt_token = None
    
    # Try query parameter first (WebSocket standard)
    if token:
        jwt_token = token
    # Fallback to Authorization header
    elif authorization and authorization.startswith("Bearer "):
        jwt_token = authorization[7:]
    
    if not jwt_token:
        await websocket.close(code=1008, reason="Missing JWT token")
        return None
    
    try:
        jwt_manager = get_jwt_manager()
        claims = await jwt_manager.validate_token(jwt_token)
        return claims["user_id"]
    except Exception as e:
        logger.error(f"JWT validation failed: {e}")
        await websocket.close(code=1008, reason="Invalid JWT token")
        return None


async def can_access_thread(user_id: str, thread_id: str) -> bool:
    """Check if user can access the specified thread_id."""
    try:
        orchestration_service = get_orchestration_service()
        
        # Check if there's a proposal with this thread_id that the user can access
        # This is a simplified check - in full implementation, we'd check the database
        # For now, we'll allow access if the thread_id follows our format
        if thread_id.startswith("refinement-") or thread_id.startswith("test-thread-"):
            return True
        
        return False
    except Exception as e:
        logger.error(f"Error checking thread access: {e}")
        return False


@router.websocket("/refinements/{thread_id}")
async def stream_refinement(
    websocket: WebSocket,
    thread_id: str,
    token: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None)
):
    """
    WebSocket endpoint to stream real-time progress from deepagents-runtime.
    
    Authentication via:
    - Query parameter: ?token=<jwt_token>
    - Authorization header: Authorization: Bearer <jwt_token>
    """
    await websocket.accept()
    
    # Record WebSocket connection metrics
    metrics.record_websocket_connection(thread_id)
    
    try:
        # Validate authentication
        user_id = await validate_websocket_auth(websocket, token, authorization)
        if not user_id:
            return  # Connection already closed by validate_websocket_auth
        
        logger.info(f"WebSocket connection for thread_id: {thread_id}, user_id: {user_id}")
        
        # Verify user can access this thread_id
        if not await can_access_thread(user_id, thread_id):
            logger.warning(f"Access denied for user {user_id} to thread {thread_id}")
            await websocket.close(code=1008, reason="Access denied to thread")
            return
        
        # Connect to deepagents-runtime WebSocket (mock for now)
        deepagents_url = "ws://deepagents-runtime:8000"  # This would be from config
        mock_deepagents_url = "ws://localhost:8001"  # Mock server URL
        
        try:
            # Try to connect to mock deepagents server
            ws_url = f"{mock_deepagents_url}/stream/{thread_id}"
            
            async with websockets.connect(ws_url) as deepagents_ws:
                logger.info(f"Connected to deepagents-runtime WebSocket for thread: {thread_id}")
                
                # Start bidirectional proxying
                await proxy_websocket_with_state_extraction(
                    websocket, deepagents_ws, thread_id, user_id
                )
                
        except Exception as e:
            logger.error(f"Failed to connect to deepagents-runtime: {e}")
            # Send error to client
            await websocket.send_json({
                "event_type": "error",
                "data": {"error": "Failed to connect to AI service"}
            })
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for thread: {thread_id}")
    except Exception as e:
        logger.error(f"WebSocket error for thread {thread_id}: {e}")
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except:
            pass
    finally:
        # Record WebSocket disconnection metrics
        metrics.record_websocket_disconnection(thread_id)


async def proxy_websocket_with_state_extraction(
    client_ws: WebSocket,
    deepagents_ws,
    thread_id: str,
    user_id: str
):
    """Handle bidirectional WebSocket proxying with state extraction."""
    final_files = {}
    
    async def client_to_deepagents():
        """Forward messages from client to deepagents-runtime."""
        try:
            while True:
                # Receive message from client
                message = await client_ws.receive_text()
                # Forward to deepagents-runtime
                await deepagents_ws.send(message)
                logger.debug(f"Forwarded client message to deepagents-runtime for thread: {thread_id}")
        except WebSocketDisconnect:
            logger.info(f"Client disconnected for thread: {thread_id}")
        except Exception as e:
            logger.error(f"Client->DeepAgents proxy error for thread {thread_id}: {e}")
    
    async def deepagents_to_client():
        """Forward events from deepagents-runtime to client and extract state."""
        nonlocal final_files
        try:
            async for message in deepagents_ws:
                try:
                    event = json.loads(message)
                    logger.debug(f"Received event from deepagents-runtime for thread {thread_id}: {event.get('event_type')}")
                    
                    # Extract files from on_state_update events
                    if event.get("event_type") == "on_state_update":
                        if "files" in event.get("data", {}):
                            final_files = event["data"]["files"]
                            logger.info(f"Extracted {len(final_files)} files from on_state_update for thread: {thread_id}")
                    
                    # Forward event to client
                    await client_ws.send_json(event)
                    
                    # Handle completion
                    if event.get("event_type") == "end":
                        logger.info(f"Received end event for thread: {thread_id}, updating proposal with files")
                        # Update proposal with final files in background
                        asyncio.create_task(update_proposal_with_files(thread_id, final_files))
                        break
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse deepagents message: {e}")
                except Exception as e:
                    logger.error(f"Error processing deepagents message: {e}")
                    
        except Exception as e:
            logger.error(f"DeepAgents->Client proxy error for thread {thread_id}: {e}")
            # Update proposal status to failed
            asyncio.create_task(update_proposal_status_to_failed(thread_id, str(e)))
    
    # Run both proxy directions concurrently
    try:
        await asyncio.gather(
            client_to_deepagents(),
            deepagents_to_client(),
            return_exceptions=True
        )
    except Exception as e:
        logger.error(f"WebSocket proxy error for thread {thread_id}: {e}")
    
    logger.info(f"WebSocket proxy session ended for thread: {thread_id}")


async def update_proposal_with_files(thread_id: str, files: dict):
    """Update the proposal with generated files."""
    try:
        orchestration_service = get_orchestration_service()
        
        # This would update the proposal in the database
        # For now, just log the action
        logger.info(f"Would update proposal for thread {thread_id} with {len(files)} files")
        
        # In full implementation:
        # await orchestration_service.update_proposal_files(thread_id, files)
        
    except Exception as e:
        logger.error(f"Failed to update proposal files for thread {thread_id}: {e}")


async def update_proposal_status_to_failed(thread_id: str, error_message: str):
    """Update the proposal status to failed with error details."""
    try:
        orchestration_service = get_orchestration_service()
        
        # This would update the proposal status in the database
        # For now, just log the action
        logger.info(f"Would update proposal for thread {thread_id} to failed status: {error_message}")
        
        # In full implementation:
        # await orchestration_service.update_proposal_status(thread_id, "failed", error_message)
        
    except Exception as e:
        logger.error(f"Failed to update proposal status for thread {thread_id}: {e}")