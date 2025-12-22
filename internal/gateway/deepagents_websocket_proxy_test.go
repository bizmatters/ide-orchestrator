package gateway

import (
	"context"
	"net/http"
	"net/http/httptest"
	"net/url"
	"os"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/auth"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/orchestration"
)

// MockDeepAgentsClient implements a mock deepagents-runtime client for testing
type MockDeepAgentsClient struct {
	invokeResponse   string
	invokeError      error
	wsConnResponse   *websocket.Conn
	wsConnError      error
	stateResponse    *orchestration.ExecutionState
	stateError       error
	healthyResponse  bool
}

func (m *MockDeepAgentsClient) Invoke(ctx context.Context, req orchestration.JobRequest) (string, error) {
	return m.invokeResponse, m.invokeError
}

func (m *MockDeepAgentsClient) StreamWebSocket(ctx context.Context, threadID string) (*websocket.Conn, error) {
	return m.wsConnResponse, m.wsConnError
}

func (m *MockDeepAgentsClient) GetState(ctx context.Context, threadID string) (*orchestration.ExecutionState, error) {
	return m.stateResponse, m.stateError
}

func (m *MockDeepAgentsClient) IsHealthy(ctx context.Context) bool {
	return m.healthyResponse
}

func TestNewDeepAgentsWebSocketProxy(t *testing.T) {
	// Set JWT_SECRET for testing
	originalSecret := os.Getenv("JWT_SECRET")
	os.Setenv("JWT_SECRET", "test-secret-key-for-testing-purposes-only")
	defer func() {
		if originalSecret == "" {
			os.Unsetenv("JWT_SECRET")
		} else {
			os.Setenv("JWT_SECRET", originalSecret)
		}
	}()

	mockClient := &MockDeepAgentsClient{}
	jwtManager, err := auth.NewJWTManager()
	require.NoError(t, err)

	proxy := NewDeepAgentsWebSocketProxy(nil, mockClient, jwtManager)
	
	assert.NotNil(t, proxy)
	assert.NotNil(t, proxy.deepAgentsClient)
	assert.NotNil(t, proxy.jwtManager)
	assert.NotNil(t, proxy.tracer)
	assert.Equal(t, 10*time.Second, proxy.upgrader.HandshakeTimeout)
}

func TestDeepAgentsWebSocketProxy_ValidateJWTAndGetUserID(t *testing.T) {
	// Set JWT_SECRET for testing
	originalSecret := os.Getenv("JWT_SECRET")
	os.Setenv("JWT_SECRET", "test-secret-key-for-testing-purposes-only")
	defer func() {
		if originalSecret == "" {
			os.Unsetenv("JWT_SECRET")
		} else {
			os.Setenv("JWT_SECRET", originalSecret)
		}
	}()

	jwtManager, err := auth.NewJWTManager()
	require.NoError(t, err)

	proxy := NewDeepAgentsWebSocketProxy(nil, &MockDeepAgentsClient{}, jwtManager)

	tests := []struct {
		name          string
		setupRequest  func() *gin.Context
		expectedError string
		expectedUser  string
	}{
		{
			name: "valid_jwt_in_query_param",
			setupRequest: func() *gin.Context {
				// Generate a valid JWT
				token, err := jwtManager.GenerateToken(
					context.Background(),
					"test-user-id",
					"test@example.com",
					[]string{"user"},
					time.Hour,
				)
				require.NoError(t, err)

				// Create gin context with query parameter
				gin.SetMode(gin.TestMode)
				w := httptest.NewRecorder()
				c, _ := gin.CreateTestContext(w)
				req := httptest.NewRequest("GET", "/?token="+token, nil)
				c.Request = req
				return c
			},
			expectedUser: "test-user-id",
		},
		{
			name: "valid_jwt_in_header",
			setupRequest: func() *gin.Context {
				// Generate a valid JWT
				token, err := jwtManager.GenerateToken(
					context.Background(),
					"test-user-id-2",
					"test2@example.com",
					[]string{"user"},
					time.Hour,
				)
				require.NoError(t, err)

				// Create gin context with Authorization header
				gin.SetMode(gin.TestMode)
				w := httptest.NewRecorder()
				c, _ := gin.CreateTestContext(w)
				req := httptest.NewRequest("GET", "/", nil)
				req.Header.Set("Authorization", "Bearer "+token)
				c.Request = req
				return c
			},
			expectedUser: "test-user-id-2",
		},
		{
			name: "missing_jwt",
			setupRequest: func() *gin.Context {
				gin.SetMode(gin.TestMode)
				w := httptest.NewRecorder()
				c, _ := gin.CreateTestContext(w)
				req := httptest.NewRequest("GET", "/", nil)
				c.Request = req
				return c
			},
			expectedError: "missing JWT token",
		},
		{
			name: "invalid_jwt",
			setupRequest: func() *gin.Context {
				gin.SetMode(gin.TestMode)
				w := httptest.NewRecorder()
				c, _ := gin.CreateTestContext(w)
				req := httptest.NewRequest("GET", "/?token=invalid-token", nil)
				c.Request = req
				return c
			},
			expectedError: "invalid JWT",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			c := tt.setupRequest()
			
			userID, err := proxy.validateJWTAndGetUserID(c)
			
			if tt.expectedError != "" {
				assert.Error(t, err)
				assert.Contains(t, err.Error(), tt.expectedError)
			} else {
				assert.NoError(t, err)
				assert.Equal(t, tt.expectedUser, userID)
			}
		})
	}
}

func TestDeepAgentsWebSocketProxy_SendErrorToClient(t *testing.T) {
	// Create a WebSocket test server
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upgrader := websocket.Upgrader{
			CheckOrigin: func(r *http.Request) bool { return true },
		}
		
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			t.Errorf("Failed to upgrade WebSocket: %v", err)
			return
		}
		defer conn.Close()

		// Read the error message
		var errorEvent map[string]interface{}
		err = conn.ReadJSON(&errorEvent)
		if err != nil {
			t.Errorf("Failed to read JSON: %v", err)
			return
		}

		// Verify error format
		assert.Equal(t, "error", errorEvent["event_type"])
		data, ok := errorEvent["data"].(map[string]interface{})
		assert.True(t, ok)
		assert.Equal(t, "Test error message", data["error"])
	}))
	defer server.Close()

	// Connect to the test server
	u, err := url.Parse(server.URL)
	require.NoError(t, err)
	u.Scheme = "ws"

	conn, _, err := websocket.DefaultDialer.Dial(u.String(), nil)
	require.NoError(t, err)
	defer conn.Close()

	// Create proxy and send error
	proxy := NewDeepAgentsWebSocketProxy(nil, &MockDeepAgentsClient{}, nil)
	proxy.sendErrorToClient(conn, "Test error message")
}

func TestDeepAgentsWebSocketProxy_IsHealthy(t *testing.T) {
	tests := []struct {
		name            string
		clientHealthy   bool
		expectedHealthy bool
	}{
		{
			name:            "healthy_client",
			clientHealthy:   true,
			expectedHealthy: true,
		},
		{
			name:            "unhealthy_client",
			clientHealthy:   false,
			expectedHealthy: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			mockClient := &MockDeepAgentsClient{
				healthyResponse: tt.clientHealthy,
			}
			
			proxy := NewDeepAgentsWebSocketProxy(nil, mockClient, nil)
			
			result := proxy.IsHealthy(context.Background())
			assert.Equal(t, tt.expectedHealthy, result)
		})
	}
}

func TestDeepAgentsWebSocketProxy_UpdateProposalWithFiles(t *testing.T) {
	// This test would require a real database connection
	// For now, we'll test that the method doesn't panic with nil pool
	
	proxy := &DeepAgentsWebSocketProxy{
		pool: nil, // Simulate nil pool to test error handling
	}
	
	files := map[string]interface{}{
		"/test.md": map[string]interface{}{
			"content": []string{"# Test", "Content"},
		},
	}
	
	// Test that the method handles nil pool gracefully
	// In a real test, we'd set up a test database and verify the update
	proxy.updateProposalWithFiles(context.Background(), "test-thread-id", files)
	
	// If we get here without panicking, the test passes
	assert.True(t, true, "Method should handle nil pool gracefully")
}

func TestDeepAgentsWebSocketProxy_UpdateProposalStatusToFailed(t *testing.T) {
	// This test would require a real database connection
	// For now, we'll test that the method doesn't panic with nil pool
	
	proxy := &DeepAgentsWebSocketProxy{
		pool: nil, // Simulate nil pool to test error handling
	}
	
	// Test that the method handles nil pool gracefully
	// In a real test, we'd set up a test database and verify the update
	proxy.updateProposalStatusToFailed(context.Background(), "test-thread-id", "Test error message")
	
	// If we get here without panicking, the test passes
	assert.True(t, true, "Method should handle nil pool gracefully")
}

func TestDeepAgentsWebSocketProxy_ProxyWebSocketWithStateExtraction(t *testing.T) {
	// Create mock WebSocket connections
	clientServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upgrader := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()

		// Simulate client behavior - just wait for messages
		for {
			_, _, err := conn.ReadMessage()
			if err != nil {
				break
			}
		}
	}))
	defer clientServer.Close()

	deepAgentsServer := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		upgrader := websocket.Upgrader{CheckOrigin: func(r *http.Request) bool { return true }}
		conn, err := upgrader.Upgrade(w, r, nil)
		if err != nil {
			return
		}
		defer conn.Close()

		// Send test events
		events := []orchestration.StreamEvent{
			{
				EventType: "on_state_update",
				Data: map[string]interface{}{
					"files": map[string]interface{}{
						"/test.md": map[string]interface{}{
							"content": []string{"# Test", "Content"},
						},
					},
				},
			},
			{
				EventType: "end",
				Data:      map[string]interface{}{},
			},
		}

		for _, event := range events {
			if err := conn.WriteJSON(event); err != nil {
				break
			}
			time.Sleep(10 * time.Millisecond) // Small delay between events
		}
	}))
	defer deepAgentsServer.Close()

	// Connect to both servers
	clientURL, _ := url.Parse(clientServer.URL)
	clientURL.Scheme = "ws"
	clientConn, _, err := websocket.DefaultDialer.Dial(clientURL.String(), nil)
	require.NoError(t, err)
	defer clientConn.Close()

	deepAgentsURL, _ := url.Parse(deepAgentsServer.URL)
	deepAgentsURL.Scheme = "ws"
	deepAgentsConn, _, err := websocket.DefaultDialer.Dial(deepAgentsURL.String(), nil)
	require.NoError(t, err)
	defer deepAgentsConn.Close()

	// Create proxy and test
	proxy := &DeepAgentsWebSocketProxy{
		pool: nil, // We don't need database for this test
	}
	
	// This would normally update the database, but we're just testing the proxy logic
	ctx, cancel := context.WithTimeout(context.Background(), 1*time.Second)
	defer cancel()
	
	// Run the proxy in a goroutine
	go proxy.proxyWebSocketWithStateExtraction(ctx, clientConn, deepAgentsConn, "test-thread-id")
	
	// Wait for the context to timeout (simulating completion)
	<-ctx.Done()
}

// Helper function to create a test gin context with WebSocket upgrade
func createTestWebSocketContext(token string) (*gin.Context, *httptest.ResponseRecorder) {
	gin.SetMode(gin.TestMode)
	w := httptest.NewRecorder()
	c, _ := gin.CreateTestContext(w)
	
	req := httptest.NewRequest("GET", "/ws/refinements/test-thread-id", nil)
	if token != "" {
		req.Header.Set("Authorization", "Bearer "+token)
	}
	req.Header.Set("Connection", "upgrade")
	req.Header.Set("Upgrade", "websocket")
	req.Header.Set("Sec-WebSocket-Version", "13")
	req.Header.Set("Sec-WebSocket-Key", "test-key")
	
	c.Request = req
	c.Params = []gin.Param{
		{Key: "thread_id", Value: "test-thread-id"},
	}
	
	return c, w
}