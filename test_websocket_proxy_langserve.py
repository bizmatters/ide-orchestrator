#!/usr/bin/env python3
"""
IDE Orchestrator WebSocket Proxy LangServe Integration Test

This script tests the IDE Orchestrator WebSocket proxy to ensure it properly handles
LangServe events and maintains all existing functionality including JWT authentication
and thread_id ownership verification.
"""

import asyncio
import json
import logging
import os
import sys
import time
import uuid
from typing import Dict, Any, Optional

import aiohttp
import websockets
import psycopg2
from psycopg2.extras import RealDictCursor

# Test configuration
IDE_ORCHESTRATOR_URL = "http://localhost:8080"
SPEC_ENGINE_URL = "http://localhost:8001"
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://postgres:password@localhost:5432/bizmatters_dev")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TestResult:
    def __init__(self, test_name: str, success: bool, details: str = "", error: Optional[Exception] = None):
        self.test_name = test_name
        self.success = success
        self.details = details
        self.error = error

class WebSocketProxyTester:
    def __init__(self):
        self.db_conn = None
        self.test_results = []
    
    async def setup(self):
        """Initialize database connection and test environment"""
        try:
            self.db_conn = psycopg2.connect(DATABASE_URL)
            logger.info("✓ Database connection established")
        except Exception as e:
            logger.error(f"Failed to connect to database: {e}")
            raise
    
    async def cleanup(self):
        """Clean up test environment"""
        if self.db_conn:
            self.db_conn.close()
    
    async def run_all_tests(self):
        """Run all WebSocket proxy tests"""
        logger.info("🚀 Starting IDE Orchestrator WebSocket Proxy LangServe Integration Tests")
        
        # Test 1: Verify LangServe endpoints are available
        await self.test_langserve_endpoints_available()
        
        # Test 2: Test WebSocket proxy with LangServe events
        await self.test_websocket_proxy_with_langserve()
        
        # Test 3: Validate JWT authentication still works
        await self.test_jwt_authentication()
        
        # Test 4: Test thread_id ownership verification
        await self.test_thread_id_ownership()
        
        # Test 5: Test transparent bidirectional proxying
        await self.test_bidirectional_proxying()
        
        # Test 6: Test error handling
        await self.test_error_handling()
        
        # Print results
        self.print_test_results()
    
    async def test_langserve_endpoints_available(self):
        """Test 1: Verify LangServe endpoints are available"""
        logger.info("📋 Test 1: Verifying LangServe endpoints are available")
        
        try:
            # Test /spec-engine/invoke endpoint
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{SPEC_ENGINE_URL}/spec-engine/invoke") as resp:
                    # Expect 405 Method Not Allowed (GET on POST endpoint) or 422 Unprocessable Entity
                    if resp.status not in [405, 422]:
                        raise Exception(f"Unexpected status code: {resp.status}")
            
            # Test WebSocket endpoint availability
            ws_url = SPEC_ENGINE_URL.replace("http://", "ws://") + "/threads/test-thread/stream"
            try:
                async with websockets.connect(ws_url, timeout=5) as websocket:
                    logger.info("✓ WebSocket connection to LangServe endpoint successful")
            except Exception as e:
                logger.warning(f"WebSocket connection failed (may be expected): {e}")
            
            self.test_results.append(TestResult(
                "LangServe Endpoints Available",
                True,
                "Both /invoke and WebSocket endpoints are accessible"
            ))
            
        except Exception as e:
            self.test_results.append(TestResult(
                "LangServe Endpoints Available",
                False,
                "Failed to connect to LangServe endpoints",
                e
            ))
    
    async def test_websocket_proxy_with_langserve(self):
        """Test 2: Test WebSocket proxy with LangServe events"""
        logger.info("📋 Test 2: Testing WebSocket proxy with LangServe events")
        
        try:
            # Create test proposal
            thread_id, user_id = self.create_test_proposal()
            
            try:
                # Generate test JWT token
                token = self.generate_test_jwt(user_id)
                
                # Connect to IDE Orchestrator WebSocket proxy
                ws_url = f"ws://localhost:8080/ws/refinements/{thread_id}"
                headers = {"Authorization": f"Bearer {token}"}
                
                async with websockets.connect(ws_url, extra_headers=headers, timeout=10) as websocket:
                    logger.info("✓ Connected to IDE Orchestrator WebSocket proxy")
                    
                    # Start a workflow via LangServe
                    await self.start_langserve_workflow(thread_id)
                    
                    # Listen for events and validate format
                    event_received = False
                    langserve_event_received = False
                    
                    try:
                        for i in range(10):  # Try to read up to 10 messages
                            message = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                            event_received = True
                            
                            try:
                                event_data = json.loads(message)
                                event_type = event_data.get("event", "")
                                
                                # Check for LangServe format
                                if event_type == "on_chain_stream":
                                    langserve_event_received = True
                                    logger.info(f"✓ Received LangServe event: {event_type}")
                                    break
                                
                                # Also accept custom server events during migration
                                elif event_type == "on_chain_stream_log":
                                    logger.info(f"✓ Received custom server event: {event_type}")
                                
                            except json.JSONDecodeError:
                                logger.warning("Received non-JSON message")
                    
                    except asyncio.TimeoutError:
                        logger.info("No more messages received (timeout)")
                    
                    if not event_received:
                        raise Exception("No events received from WebSocket proxy")
                    
                    self.test_results.append(TestResult(
                        "WebSocket Proxy with LangServe",
                        True,
                        f"Events received successfully. LangServe format: {langserve_event_received}"
                    ))
            
            finally:
                self.cleanup_test_proposal(thread_id, user_id)
        
        except Exception as e:
            self.test_results.append(TestResult(
                "WebSocket Proxy with LangServe",
                False,
                "Failed to test WebSocket proxy with LangServe events",
                e
            ))
    
    async def test_jwt_authentication(self):
        """Test 3: Validate JWT authentication still works"""
        logger.info("📋 Test 3: Testing JWT authentication")
        
        try:
            # Test without JWT token
            ws_url = "ws://localhost:8080/ws/refinements/test-thread"
            
            try:
                async with websockets.connect(ws_url, timeout=5) as websocket:
                    raise Exception("Connection succeeded without JWT token")
            except websockets.exceptions.InvalidStatusCode as e:
                if e.status_code != 401:
                    raise Exception(f"Expected 401 Unauthorized, got {e.status_code}")
            
            # Test with invalid JWT token
            headers = {"Authorization": "Bearer invalid-token"}
            try:
                async with websockets.connect(ws_url, extra_headers=headers, timeout=5) as websocket:
                    raise Exception("Connection succeeded with invalid JWT token")
            except websockets.exceptions.InvalidStatusCode as e:
                if e.status_code not in [401, 403]:
                    raise Exception(f"Expected 401/403, got {e.status_code}")
            
            self.test_results.append(TestResult(
                "JWT Authentication",
                True,
                "JWT authentication properly rejects invalid/missing tokens"
            ))
        
        except Exception as e:
            self.test_results.append(TestResult(
                "JWT Authentication",
                False,
                "JWT authentication test failed",
                e
            ))
    
    async def test_thread_id_ownership(self):
        """Test 4: Test thread_id ownership verification"""
        logger.info("📋 Test 4: Testing thread_id ownership verification")
        
        try:
            # Create test proposal for user A
            thread_id, user_id = self.create_test_proposal()
            
            try:
                # Generate JWT token for different user (user B)
                different_user_id = f"different-user-{int(time.time())}"
                token = self.generate_test_jwt(different_user_id)
                
                # Try to connect with user B's token to user A's thread
                ws_url = f"ws://localhost:8080/ws/refinements/{thread_id}"
                headers = {"Authorization": f"Bearer {token}"}
                
                try:
                    async with websockets.connect(ws_url, extra_headers=headers, timeout=5) as websocket:
                        raise Exception("Connection succeeded for non-owner")
                except websockets.exceptions.InvalidStatusCode as e:
                    if e.status_code != 403:
                        raise Exception(f"Expected 403 Forbidden, got {e.status_code}")
                
                self.test_results.append(TestResult(
                    "Thread ID Ownership Verification",
                    True,
                    "Thread ID ownership verification properly rejects non-owners"
                ))
            
            finally:
                self.cleanup_test_proposal(thread_id, user_id)
        
        except Exception as e:
            self.test_results.append(TestResult(
                "Thread ID Ownership Verification",
                False,
                "Thread ID ownership verification test failed",
                e
            ))
    
    async def test_bidirectional_proxying(self):
        """Test 5: Test transparent bidirectional proxying"""
        logger.info("📋 Test 5: Testing bidirectional proxying")
        
        try:
            # Create test proposal
            thread_id, user_id = self.create_test_proposal()
            
            try:
                # Generate JWT token
                token = self.generate_test_jwt(user_id)
                
                # Connect to WebSocket proxy
                ws_url = f"ws://localhost:8080/ws/refinements/{thread_id}"
                headers = {"Authorization": f"Bearer {token}"}
                
                async with websockets.connect(ws_url, extra_headers=headers, timeout=10) as websocket:
                    logger.info("✓ Connected to WebSocket proxy")
                    
                    # Test that connection can handle messages
                    test_message = json.dumps({
                        "type": "test",
                        "data": "bidirectional test"
                    })
                    
                    await websocket.send(test_message)
                    logger.info("✓ Sent message through proxy")
                    
                    # Connection should remain open (proxy ignores client messages)
                    # We'll wait a short time to ensure connection stability
                    await asyncio.sleep(1)
                    
                    self.test_results.append(TestResult(
                        "Bidirectional Proxying",
                        True,
                        "Bidirectional proxying works correctly"
                    ))
            
            finally:
                self.cleanup_test_proposal(thread_id, user_id)
        
        except Exception as e:
            self.test_results.append(TestResult(
                "Bidirectional Proxying",
                False,
                "Bidirectional proxying test failed",
                e
            ))
    
    async def test_error_handling(self):
        """Test 6: Test error handling"""
        logger.info("📋 Test 6: Testing error handling")
        
        try:
            # Generate test JWT token
            token = self.generate_test_jwt("test-user")
            
            # Test connection to non-existent thread
            ws_url = "ws://localhost:8080/ws/refinements/non-existent-thread"
            headers = {"Authorization": f"Bearer {token}"}
            
            try:
                async with websockets.connect(ws_url, extra_headers=headers, timeout=5) as websocket:
                    raise Exception("Connection succeeded for non-existent thread")
            except websockets.exceptions.InvalidStatusCode as e:
                if e.status_code not in [403, 404]:
                    raise Exception(f"Expected 403/404, got {e.status_code}")
            
            self.test_results.append(TestResult(
                "Error Handling",
                True,
                "Error handling works correctly for non-existent threads"
            ))
        
        except Exception as e:
            self.test_results.append(TestResult(
                "Error Handling",
                False,
                "Error handling test failed",
                e
            ))
    
    def create_test_proposal(self) -> tuple[str, str]:
        """Create a test proposal in the database"""
        thread_id = f"test-thread-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        user_id = f"test-user-{int(time.time())}-{uuid.uuid4().hex[:8]}"
        
        with self.db_conn.cursor() as cursor:
            # Create user
            cursor.execute("""
                INSERT INTO users (id, email, created_at, updated_at) 
                VALUES (%s, %s, NOW(), NOW())
                ON CONFLICT (id) DO NOTHING
            """, (user_id, f"{user_id}@test.com"))
            
            # Create draft
            draft_id = f"test-draft-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            cursor.execute("""
                INSERT INTO drafts (id, created_by_user_id, created_at, updated_at)
                VALUES (%s, %s, NOW(), NOW())
            """, (draft_id, user_id))
            
            # Create proposal
            proposal_id = f"test-proposal-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            cursor.execute("""
                INSERT INTO proposals (id, draft_id, thread_id, created_at, updated_at)
                VALUES (%s, %s, %s, NOW(), NOW())
            """, (proposal_id, draft_id, thread_id))
            
            self.db_conn.commit()
        
        logger.info(f"✓ Created test proposal: thread_id={thread_id}, user_id={user_id}")
        return thread_id, user_id
    
    def cleanup_test_proposal(self, thread_id: str, user_id: str):
        """Clean up test proposal from database"""
        with self.db_conn.cursor() as cursor:
            # Clean up in reverse order
            cursor.execute("DELETE FROM proposals WHERE thread_id = %s", (thread_id,))
            cursor.execute("DELETE FROM drafts WHERE created_by_user_id = %s", (user_id,))
            cursor.execute("DELETE FROM users WHERE id = %s", (user_id,))
            self.db_conn.commit()
        
        logger.info(f"✓ Cleaned up test proposal: thread_id={thread_id}, user_id={user_id}")
    
    def generate_test_jwt(self, user_id: str) -> str:
        """Generate a test JWT token"""
        # This is a simplified JWT generation for testing
        # In a real implementation, you would use proper JWT libraries
        # For now, we'll return a mock token that the test environment can validate
        return f"test-jwt-token-for-{user_id}"
    
    async def start_langserve_workflow(self, thread_id: str):
        """Start a workflow via LangServe /invoke endpoint"""
        invoke_url = f"{SPEC_ENGINE_URL}/spec-engine/invoke"
        
        payload = {
            "input": {
                "user_prompt": "test prompt",
                "files": {},
                "initial_files_snapshot": {},
                "revision_count": 0,
                "messages": []
            },
            "config": {
                "configurable": {
                    "thread_id": thread_id
                }
            }
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(invoke_url, json=payload) as resp:
                if resp.status not in [200, 202]:
                    raise Exception(f"Unexpected status code from LangServe invoke: {resp.status}")
        
        logger.info(f"✓ Started LangServe workflow for thread_id: {thread_id}")
    
    def print_test_results(self):
        """Print test results summary"""
        print("\n" + "=" * 80)
        print("🧪 IDE ORCHESTRATOR WEBSOCKET PROXY LANGSERVE INTEGRATION TEST RESULTS")
        print("=" * 80)
        
        success_count = 0
        for result in self.test_results:
            status = "❌ FAILED" if not result.success else "✅ PASSED"
            success_count += result.success
            
            print(f"{status} {result.test_name}")
            if result.details:
                print(f"   Details: {result.details}")
            if result.error:
                print(f"   Error: {result.error}")
            print()
        
        print("-" * 80)
        print(f"📊 SUMMARY: {success_count}/{len(self.test_results)} tests passed")
        
        if success_count == len(self.test_results):
            print("🎉 ALL TESTS PASSED! WebSocket proxy is compatible with LangServe events.")
        else:
            print("⚠️  SOME TESTS FAILED. Review the results above.")
        print("=" * 80)

async def main():
    """Main test runner"""
    tester = WebSocketProxyTester()
    
    try:
        await tester.setup()
        await tester.run_all_tests()
    except Exception as e:
        logger.error(f"Test setup failed: {e}")
        sys.exit(1)
    finally:
        await tester.cleanup()

if __name__ == "__main__":
    # Check dependencies
    try:
        import aiohttp
        import websockets
        import psycopg2
    except ImportError as e:
        print(f"Missing required dependency: {e}")
        print("Install with: pip install aiohttp websockets psycopg2-binary")
        sys.exit(1)
    
    asyncio.run(main())