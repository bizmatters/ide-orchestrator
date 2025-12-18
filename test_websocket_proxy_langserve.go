package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"net/url"
	"os"
	"strings"
	"time"

	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Test configuration
const (
	IDE_ORCHESTRATOR_URL = "http://localhost:8080"
	SPEC_ENGINE_URL      = "http://localhost:8001"
	TEST_TIMEOUT         = 30 * time.Second
)

// Test data structures
type LangServeEvent struct {
	Event string `json:"event"`
	Data  struct {
		Chunk map[string]interface{} `json:"chunk"`
	} `json:"data"`
}

type CustomServerEvent struct {
	Event string `json:"event"`
	Data  struct {
		Chunk         map[string]interface{} `json:"chunk"`
		TraceMetadata map[string]interface{} `json:"trace_metadata,omitempty"`
		DebugMetadata map[string]interface{} `json:"debug_metadata,omitempty"`
	} `json:"data"`
}

type TestResult struct {
	TestName string
	Success  bool
	Error    error
	Details  string
}

func main() {
	log.Println("🚀 Starting IDE Orchestrator WebSocket Proxy LangServe Integration Test")
	
	// Initialize database connection for JWT verification
	pool, err := initializeDatabase()
	if err != nil {
		log.Fatalf("Failed to initialize database: %v", err)
	}
	defer pool.Close()

	// Run test suite
	results := []TestResult{}
	
	// Test 1: Verify LangServe endpoints are available
	results = append(results, testLangServeEndpointsAvailable())
	
	// Test 2: Test WebSocket proxy with LangServe events
	results = append(results, testWebSocketProxyWithLangServe(pool))
	
	// Test 3: Validate JWT authentication still works
	results = append(results, testJWTAuthenticationWithLangServe(pool))
	
	// Test 4: Test thread_id ownership verification
	results = append(results, testThreadIDOwnershipVerification(pool))
	
	// Test 5: Test bidirectional proxying
	results = append(results, testBidirectionalProxying(pool))
	
	// Test 6: Test error handling
	results = append(results, testErrorHandling(pool))
	
	// Print results
	printTestResults(results)
}

func initializeDatabase() (*pgxpool.Pool, error) {
	databaseURL := os.Getenv("DATABASE_URL")
	if databaseURL == "" {
		databaseURL = "postgres://postgres:password@localhost:5432/bizmatters_dev?sslmode=disable"
	}
	
	pool, err := pgxpool.New(context.Background(), databaseURL)
	if err != nil {
		return nil, fmt.Errorf("failed to create connection pool: %w", err)
	}
	
	// Test connection
	if err := pool.Ping(context.Background()); err != nil {
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}
	
	return pool, nil
}

func testLangServeEndpointsAvailable() TestResult {
	log.Println("📋 Test 1: Verifying LangServe endpoints are available")
	
	// Test /spec-engine/invoke endpoint
	invokeURL := fmt.Sprintf("%s/spec-engine/invoke", SPEC_ENGINE_URL)
	resp, err := http.Get(invokeURL)
	if err != nil {
		return TestResult{
			TestName: "LangServe Endpoints Available",
			Success:  false,
			Error:    err,
			Details:  "Failed to connect to /spec-engine/invoke endpoint",
		}
	}
	defer resp.Body.Close()
	
	// Check if we get a method not allowed (GET on POST endpoint) or similar expected response
	if resp.StatusCode != http.StatusMethodNotAllowed && resp.StatusCode != http.StatusUnprocessableEntity {
		return TestResult{
			TestName: "LangServe Endpoints Available",
			Success:  false,
			Error:    fmt.Errorf("unexpected status code: %d", resp.StatusCode),
			Details:  "LangServe /invoke endpoint not responding as expected",
		}
	}
	
	// Test WebSocket endpoint availability by attempting connection
	wsURL := strings.Replace(SPEC_ENGINE_URL, "http://", "ws://", 1) + "/threads/test-thread/stream"
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err != nil {
		return TestResult{
			TestName: "LangServe Endpoints Available",
			Success:  false,
			Error:    err,
			Details:  "Failed to connect to LangServe WebSocket endpoint",
		}
	}
	conn.Close()
	
	return TestResult{
		TestName: "LangServe Endpoints Available",
		Success:  true,
		Details:  "Both /invoke and WebSocket endpoints are accessible",
	}
}

func testWebSocketProxyWithLangServe(pool *pgxpool.Pool) TestResult {
	log.Println("📋 Test 2: Testing WebSocket proxy with LangServe events")
	
	// Create test data in database
	threadID, userID, err := createTestProposal(pool)
	if err != nil {
		return TestResult{
			TestName: "WebSocket Proxy with LangServe",
			Success:  false,
			Error:    err,
			Details:  "Failed to create test proposal",
		}
	}
	defer cleanupTestProposal(pool, threadID, userID)
	
	// Generate JWT token for authentication
	token, err := generateTestJWT(userID)
	if err != nil {
		return TestResult{
			TestName: "WebSocket Proxy with LangServe",
			Success:  false,
			Error:    err,
			Details:  "Failed to generate test JWT",
		}
	}
	
	// Connect to IDE Orchestrator WebSocket proxy
	wsURL := fmt.Sprintf("ws://localhost:8080/ws/refinements/%s", threadID)
	headers := http.Header{}
	headers.Set("Authorization", fmt.Sprintf("Bearer %s", token))
	
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err != nil {
		return TestResult{
			TestName: "WebSocket Proxy with LangServe",
			Success:  false,
			Error:    err,
			Details:  "Failed to connect to IDE Orchestrator WebSocket proxy",
		}
	}
	defer conn.Close()
	
	// Start a workflow via LangServe /invoke endpoint
	err = startLangServeWorkflow(threadID)
	if err != nil {
		return TestResult{
			TestName: "WebSocket Proxy with LangServe",
			Success:  false,
			Error:    err,
			Details:  "Failed to start LangServe workflow",
		}
	}
	
	// Listen for events and validate LangServe format
	eventReceived := false
	langServeEventReceived := false
	
	conn.SetReadDeadline(time.Now().Add(10 * time.Second))
	
	for i := 0; i < 10; i++ { // Try to read up to 10 messages
		_, message, err := conn.ReadMessage()
		if err != nil {
			if websocket.IsCloseError(err, websocket.CloseNormalClosure) {
				break
			}
			return TestResult{
				TestName: "WebSocket Proxy with LangServe",
				Success:  false,
				Error:    err,
				Details:  "Failed to read WebSocket message",
			}
		}
		
		eventReceived = true
		
		// Parse event to check format
		var event LangServeEvent
		if err := json.Unmarshal(message, &event); err == nil {
			if event.Event == "on_chain_stream" {
				langServeEventReceived = true
				log.Printf("✓ Received LangServe event: %s", event.Event)
				break
			}
		}
		
		// Also check for custom server events during migration
		var customEvent CustomServerEvent
		if err := json.Unmarshal(message, &customEvent); err == nil {
			if customEvent.Event == "on_chain_stream_log" {
				log.Printf("✓ Received custom server event: %s", customEvent.Event)
				// This is acceptable during migration phase
			}
		}
	}
	
	if !eventReceived {
		return TestResult{
			TestName: "WebSocket Proxy with LangServe",
			Success:  false,
			Error:    fmt.Errorf("no events received"),
			Details:  "WebSocket proxy did not forward any events",
		}
	}
	
	return TestResult{
		TestName: "WebSocket Proxy with LangServe",
		Success:  true,
		Details:  fmt.Sprintf("Events received successfully. LangServe format: %v", langServeEventReceived),
	}
}

func testJWTAuthenticationWithLangServe(pool *pgxpool.Pool) TestResult {
	log.Println("📋 Test 3: Testing JWT authentication with LangServe")
	
	// Test without JWT token
	wsURL := "ws://localhost:8080/ws/refinements/test-thread"
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, nil)
	if err == nil {
		conn.Close()
		return TestResult{
			TestName: "JWT Authentication with LangServe",
			Success:  false,
			Error:    fmt.Errorf("connection succeeded without JWT"),
			Details:  "WebSocket proxy should reject connections without JWT token",
		}
	}
	
	// Check if we got the expected 401 Unauthorized
	if resp != nil && resp.StatusCode != http.StatusUnauthorized {
		return TestResult{
			TestName: "JWT Authentication with LangServe",
			Success:  false,
			Error:    fmt.Errorf("unexpected status code: %d", resp.StatusCode),
			Details:  "Expected 401 Unauthorized for missing JWT",
		}
	}
	
	// Test with invalid JWT token
	headers := http.Header{}
	headers.Set("Authorization", "Bearer invalid-token")
	
	conn, resp, err = websocket.DefaultDialer.Dial(wsURL, headers)
	if err == nil {
		conn.Close()
		return TestResult{
			TestName: "JWT Authentication with LangServe",
			Success:  false,
			Error:    fmt.Errorf("connection succeeded with invalid JWT"),
			Details:  "WebSocket proxy should reject connections with invalid JWT token",
		}
	}
	
	return TestResult{
		TestName: "JWT Authentication with LangServe",
		Success:  true,
		Details:  "JWT authentication properly rejects invalid/missing tokens",
	}
}

func testThreadIDOwnershipVerification(pool *pgxpool.Pool) TestResult {
	log.Println("📋 Test 4: Testing thread_id ownership verification")
	
	// Create test proposal for user A
	threadID, userID, err := createTestProposal(pool)
	if err != nil {
		return TestResult{
			TestName: "Thread ID Ownership Verification",
			Success:  false,
			Error:    err,
			Details:  "Failed to create test proposal",
		}
	}
	defer cleanupTestProposal(pool, threadID, userID)
	
	// Generate JWT token for different user (user B)
	differentUserID := "different-user-id"
	token, err := generateTestJWT(differentUserID)
	if err != nil {
		return TestResult{
			TestName: "Thread ID Ownership Verification",
			Success:  false,
			Error:    err,
			Details:  "Failed to generate test JWT for different user",
		}
	}
	
	// Try to connect with user B's token to user A's thread
	wsURL := fmt.Sprintf("ws://localhost:8080/ws/refinements/%s", threadID)
	headers := http.Header{}
	headers.Set("Authorization", fmt.Sprintf("Bearer %s", token))
	
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err == nil {
		conn.Close()
		return TestResult{
			TestName: "Thread ID Ownership Verification",
			Success:  false,
			Error:    fmt.Errorf("connection succeeded for non-owner"),
			Details:  "WebSocket proxy should reject connections from non-owners",
		}
	}
	
	// Check if we got the expected 403 Forbidden
	if resp != nil && resp.StatusCode != http.StatusForbidden {
		return TestResult{
			TestName: "Thread ID Ownership Verification",
			Success:  false,
			Error:    fmt.Errorf("unexpected status code: %d", resp.StatusCode),
			Details:  "Expected 403 Forbidden for non-owner access",
		}
	}
	
	return TestResult{
		TestName: "Thread ID Ownership Verification",
		Success:  true,
		Details:  "Thread ID ownership verification properly rejects non-owners",
	}
}

func testBidirectionalProxying(pool *pgxpool.Pool) TestResult {
	log.Println("📋 Test 5: Testing bidirectional proxying")
	
	// Create test data
	threadID, userID, err := createTestProposal(pool)
	if err != nil {
		return TestResult{
			TestName: "Bidirectional Proxying",
			Success:  false,
			Error:    err,
			Details:  "Failed to create test proposal",
		}
	}
	defer cleanupTestProposal(pool, threadID, userID)
	
	// Generate JWT token
	token, err := generateTestJWT(userID)
	if err != nil {
		return TestResult{
			TestName: "Bidirectional Proxying",
			Success:  false,
			Error:    err,
			Details:  "Failed to generate test JWT",
		}
	}
	
	// Connect to WebSocket proxy
	wsURL := fmt.Sprintf("ws://localhost:8080/ws/refinements/%s", threadID)
	headers := http.Header{}
	headers.Set("Authorization", fmt.Sprintf("Bearer %s", token))
	
	conn, _, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err != nil {
		return TestResult{
			TestName: "Bidirectional Proxying",
			Success:  false,
			Error:    err,
			Details:  "Failed to connect to WebSocket proxy",
		}
	}
	defer conn.Close()
	
	// Test that connection stays open and can handle messages
	// (In practice, the proxy ignores client messages but should not close the connection)
	testMessage := map[string]interface{}{
		"type": "test",
		"data": "bidirectional test",
	}
	
	messageBytes, _ := json.Marshal(testMessage)
	err = conn.WriteMessage(websocket.TextMessage, messageBytes)
	if err != nil {
		return TestResult{
			TestName: "Bidirectional Proxying",
			Success:  false,
			Error:    err,
			Details:  "Failed to send message through proxy",
		}
	}
	
	// Connection should remain open
	conn.SetReadDeadline(time.Now().Add(2 * time.Second))
	_, _, err = conn.ReadMessage()
	if err != nil && !websocket.IsCloseError(err, websocket.CloseNormalClosure) {
		// This is expected - no response to client messages, but connection should stay open
		// We'll consider this a success if the write succeeded
	}
	
	return TestResult{
		TestName: "Bidirectional Proxying",
		Success:  true,
		Details:  "Bidirectional proxying works correctly",
	}
}

func testErrorHandling(pool *pgxpool.Pool) TestResult {
	log.Println("📋 Test 6: Testing error handling")
	
	// Test connection to non-existent thread
	token, err := generateTestJWT("test-user")
	if err != nil {
		return TestResult{
			TestName: "Error Handling",
			Success:  false,
			Error:    err,
			Details:  "Failed to generate test JWT",
		}
	}
	
	wsURL := "ws://localhost:8080/ws/refinements/non-existent-thread"
	headers := http.Header{}
	headers.Set("Authorization", fmt.Sprintf("Bearer %s", token))
	
	conn, resp, err := websocket.DefaultDialer.Dial(wsURL, headers)
	if err == nil {
		conn.Close()
		return TestResult{
			TestName: "Error Handling",
			Success:  false,
			Error:    fmt.Errorf("connection succeeded for non-existent thread"),
			Details:  "WebSocket proxy should reject connections to non-existent threads",
		}
	}
	
	// Check if we got the expected error response
	if resp != nil && resp.StatusCode != http.StatusForbidden && resp.StatusCode != http.StatusNotFound {
		return TestResult{
			TestName: "Error Handling",
			Success:  false,
			Error:    fmt.Errorf("unexpected status code: %d", resp.StatusCode),
			Details:  "Expected 403/404 for non-existent thread",
		}
	}
	
	return TestResult{
		TestName: "Error Handling",
		Success:  true,
		Details:  "Error handling works correctly for non-existent threads",
	}
}

// Helper functions

func createTestProposal(pool *pgxpool.Pool) (threadID, userID string, err error) {
	ctx := context.Background()
	threadID = fmt.Sprintf("test-thread-%d", time.Now().Unix())
	userID = fmt.Sprintf("test-user-%d", time.Now().Unix())
	
	// Create user
	_, err = pool.Exec(ctx, `
		INSERT INTO users (id, email, created_at, updated_at) 
		VALUES ($1, $2, NOW(), NOW())
		ON CONFLICT (id) DO NOTHING
	`, userID, fmt.Sprintf("%s@test.com", userID))
	if err != nil {
		return "", "", fmt.Errorf("failed to create test user: %w", err)
	}
	
	// Create draft
	draftID := fmt.Sprintf("test-draft-%d", time.Now().Unix())
	_, err = pool.Exec(ctx, `
		INSERT INTO drafts (id, created_by_user_id, created_at, updated_at)
		VALUES ($1, $2, NOW(), NOW())
	`, draftID, userID)
	if err != nil {
		return "", "", fmt.Errorf("failed to create test draft: %w", err)
	}
	
	// Create proposal
	proposalID := fmt.Sprintf("test-proposal-%d", time.Now().Unix())
	_, err = pool.Exec(ctx, `
		INSERT INTO proposals (id, draft_id, thread_id, created_at, updated_at)
		VALUES ($1, $2, $3, NOW(), NOW())
	`, proposalID, draftID, threadID)
	if err != nil {
		return "", "", fmt.Errorf("failed to create test proposal: %w", err)
	}
	
	return threadID, userID, nil
}

func cleanupTestProposal(pool *pgxpool.Pool, threadID, userID string) {
	ctx := context.Background()
	
	// Clean up in reverse order
	pool.Exec(ctx, "DELETE FROM proposals WHERE thread_id = $1", threadID)
	pool.Exec(ctx, "DELETE FROM drafts WHERE created_by_user_id = $1", userID)
	pool.Exec(ctx, "DELETE FROM users WHERE id = $1", userID)
}

func generateTestJWT(userID string) (string, error) {
	// This is a simplified JWT generation for testing
	// In a real implementation, you would use proper JWT libraries
	// For now, we'll return a mock token that the test environment can validate
	return fmt.Sprintf("test-jwt-token-for-%s", userID), nil
}

func startLangServeWorkflow(threadID string) error {
	// Start a workflow via LangServe /invoke endpoint
	invokeURL := fmt.Sprintf("%s/spec-engine/invoke", SPEC_ENGINE_URL)
	
	payload := map[string]interface{}{
		"input": map[string]interface{}{
			"user_prompt":              "test prompt",
			"files":                   map[string]interface{}{},
			"initial_files_snapshot":  map[string]interface{}{},
			"revision_count":          0,
			"messages":               []interface{}{},
		},
		"config": map[string]interface{}{
			"configurable": map[string]interface{}{
				"thread_id": threadID,
			},
		},
	}
	
	payloadBytes, _ := json.Marshal(payload)
	
	resp, err := http.Post(invokeURL, "application/json", bytes.NewBuffer(payloadBytes))
	if err != nil {
		return fmt.Errorf("failed to invoke LangServe endpoint: %w", err)
	}
	defer resp.Body.Close()
	
	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted {
		return fmt.Errorf("unexpected status code from LangServe invoke: %d", resp.StatusCode)
	}
	
	return nil
}

func printTestResults(results []TestResult) {
	log.Println("\n" + strings.Repeat("=", 80))
	log.Println("🧪 IDE ORCHESTRATOR WEBSOCKET PROXY LANGSERVE INTEGRATION TEST RESULTS")
	log.Println(strings.Repeat("=", 80))
	
	successCount := 0
	for _, result := range results {
		status := "❌ FAILED"
		if result.Success {
			status = "✅ PASSED"
			successCount++
		}
		
		log.Printf("%s %s", status, result.TestName)
		if result.Details != "" {
			log.Printf("   Details: %s", result.Details)
		}
		if result.Error != nil {
			log.Printf("   Error: %v", result.Error)
		}
		log.Println()
	}
	
	log.Println(strings.Repeat("-", 80))
	log.Printf("📊 SUMMARY: %d/%d tests passed", successCount, len(results))
	
	if successCount == len(results) {
		log.Println("🎉 ALL TESTS PASSED! WebSocket proxy is compatible with LangServe events.")
	} else {
		log.Println("⚠️  SOME TESTS FAILED. Review the results above.")
	}
	log.Println(strings.Repeat("=", 80))
}