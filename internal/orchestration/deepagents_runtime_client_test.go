package orchestration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gorilla/websocket"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"
)

func TestNewDeepAgentsRuntimeClient(t *testing.T) {
	client := NewDeepAgentsRuntimeClient()
	
	assert.NotNil(t, client)
	assert.NotNil(t, client.httpClient)
	assert.NotNil(t, client.tracer)
	assert.NotNil(t, client.breaker)
	assert.Contains(t, client.baseURL, "deepagents-runtime")
}

func TestDeepAgentsRuntimeClient_Invoke(t *testing.T) {
	tests := []struct {
		name           string
		serverResponse func(w http.ResponseWriter, r *http.Request)
		expectedError  string
		expectedResult string
	}{
		{
			name: "successful_invocation",
			serverResponse: func(w http.ResponseWriter, r *http.Request) {
				assert.Equal(t, "POST", r.Method)
				assert.Equal(t, "/deepagents-runtime/invoke", r.URL.Path)
				assert.Equal(t, "application/json", r.Header.Get("Content-Type"))
				
				// Verify request body
				var req JobRequest
				err := json.NewDecoder(r.Body).Decode(&req)
				assert.NoError(t, err)
				assert.Equal(t, "test-trace-id", req.TraceID)
				assert.Equal(t, "test-job-id", req.JobID)
				
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusOK)
				json.NewEncoder(w).Encode(DeepAgentsInvokeResponse{
					ThreadID: "test-thread-id",
					Status:   "started",
				})
			},
			expectedResult: "test-thread-id",
		},
		{
			name: "server_error",
			serverResponse: func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusInternalServerError)
				w.Write([]byte("Internal server error"))
			},
			expectedError: "deepagents-runtime returned status 500",
		},
		{
			name: "invalid_json_response",
			serverResponse: func(w http.ResponseWriter, r *http.Request) {
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusOK)
				w.Write([]byte("invalid json"))
			},
			expectedError: "failed to decode response",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(tt.serverResponse))
			defer server.Close()

			client := NewDeepAgentsRuntimeClient()
			client.baseURL = server.URL

			req := JobRequest{
				TraceID: "test-trace-id",
				JobID:   "test-job-id",
				AgentDefinition: map[string]interface{}{
					"name": "test-agent",
				},
				InputPayload: InputPayload{
					Messages: []Message{
						{Role: "user", Content: "test prompt"},
					},
				},
			}

			result, err := client.Invoke(context.Background(), req)

			if tt.expectedError != "" {
				assert.Error(t, err)
				assert.Contains(t, err.Error(), tt.expectedError)
			} else {
				assert.NoError(t, err)
				assert.Equal(t, tt.expectedResult, result)
			}
		})
	}
}

func TestDeepAgentsRuntimeClient_GetState(t *testing.T) {
	tests := []struct {
		name           string
		threadID       string
		serverResponse func(w http.ResponseWriter, r *http.Request)
		expectedError  string
		expectedState  *ExecutionState
	}{
		{
			name:     "successful_get_state",
			threadID: "test-thread-id",
			serverResponse: func(w http.ResponseWriter, r *http.Request) {
				assert.Equal(t, "GET", r.Method)
				assert.Equal(t, "/deepagents-runtime/state/test-thread-id", r.URL.Path)
				
				w.Header().Set("Content-Type", "application/json")
				w.WriteHeader(http.StatusOK)
				json.NewEncoder(w).Encode(ExecutionState{
					ThreadID: "test-thread-id",
					Status:   "completed",
					GeneratedFiles: map[string]interface{}{
						"/test.md": map[string]interface{}{
							"content": []string{"# Test", "Content"},
						},
					},
				})
			},
			expectedState: &ExecutionState{
				ThreadID: "test-thread-id",
				Status:   "completed",
				GeneratedFiles: map[string]interface{}{
					"/test.md": map[string]interface{}{
						"content": []interface{}{"# Test", "Content"}, // JSON unmarshals to []interface{}, not []string
					},
				},
			},
		},
		{
			name:     "thread_not_found",
			threadID: "nonexistent-thread",
			serverResponse: func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusNotFound)
				w.Write([]byte("Thread not found"))
			},
			expectedError: "deepagents-runtime returned status 404",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(tt.serverResponse))
			defer server.Close()

			client := NewDeepAgentsRuntimeClient()
			client.baseURL = server.URL

			result, err := client.GetState(context.Background(), tt.threadID)

			if tt.expectedError != "" {
				assert.Error(t, err)
				assert.Contains(t, err.Error(), tt.expectedError)
			} else {
				assert.NoError(t, err)
				assert.Equal(t, tt.expectedState, result)
			}
		})
	}
}

func TestDeepAgentsRuntimeClient_StreamWebSocket(t *testing.T) {
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

		// Send a test event
		event := StreamEvent{
			EventType: "on_state_update",
			Data: map[string]interface{}{
				"files": map[string]interface{}{
					"/test.md": map[string]interface{}{
						"content": []interface{}{"# Test", "Content"}, // JSON unmarshals to []interface{}, not []string
					},
				},
			},
		}
		
		if err := conn.WriteJSON(event); err != nil {
			t.Errorf("Failed to write JSON: %v", err)
			return
		}

		// Send end event
		endEvent := StreamEvent{
			EventType: "end",
			Data:      map[string]interface{}{},
		}
		
		if err := conn.WriteJSON(endEvent); err != nil {
			t.Errorf("Failed to write end event: %v", err)
			return
		}
	}))
	defer server.Close()

	client := NewDeepAgentsRuntimeClient()
	
	// Keep HTTP URL - the client will convert it to WebSocket internally
	client.baseURL = server.URL

	conn, err := client.StreamWebSocket(context.Background(), "test-thread-id")
	require.NoError(t, err)
	defer conn.Close()

	// Read the first event
	var event StreamEvent
	err = conn.ReadJSON(&event)
	require.NoError(t, err)
	assert.Equal(t, "on_state_update", event.EventType)
	assert.Contains(t, event.Data, "files")

	// Read the end event
	var endEvent StreamEvent
	err = conn.ReadJSON(&endEvent)
	require.NoError(t, err)
	assert.Equal(t, "end", endEvent.EventType)
}

func TestDeepAgentsRuntimeClient_IsHealthy(t *testing.T) {
	tests := []struct {
		name           string
		serverResponse func(w http.ResponseWriter, r *http.Request)
		expectedHealth bool
	}{
		{
			name: "healthy_service",
			serverResponse: func(w http.ResponseWriter, r *http.Request) {
				assert.Equal(t, "GET", r.Method)
				assert.Equal(t, "/health", r.URL.Path)
				w.WriteHeader(http.StatusOK)
				w.Write([]byte(`{"status": "healthy"}`))
			},
			expectedHealth: true,
		},
		{
			name: "unhealthy_service",
			serverResponse: func(w http.ResponseWriter, r *http.Request) {
				w.WriteHeader(http.StatusServiceUnavailable)
				w.Write([]byte(`{"status": "unhealthy"}`))
			},
			expectedHealth: false,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			server := httptest.NewServer(http.HandlerFunc(tt.serverResponse))
			defer server.Close()

			client := NewDeepAgentsRuntimeClient()
			client.baseURL = server.URL

			result := client.IsHealthy(context.Background())
			assert.Equal(t, tt.expectedHealth, result)
		})
	}
}

func TestDeepAgentsRuntimeClient_CircuitBreaker(t *testing.T) {
	// Create a server that always fails
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(http.StatusInternalServerError)
		w.Write([]byte("Service unavailable"))
	}))
	defer server.Close()

	client := NewDeepAgentsRuntimeClient()
	client.baseURL = server.URL

	req := JobRequest{
		TraceID: "test-trace-id",
		JobID:   "test-job-id",
		AgentDefinition: map[string]interface{}{
			"name": "test-agent",
		},
		InputPayload: InputPayload{
			Messages: []Message{
				{Role: "user", Content: "test prompt"},
			},
		},
	}

	// Make multiple requests to trigger circuit breaker
	for i := 0; i < 10; i++ {
		_, err := client.Invoke(context.Background(), req)
		assert.Error(t, err)
		
		// After enough failures, circuit breaker should open
		if i > 5 {
			// The error should indicate circuit breaker is open
			if strings.Contains(err.Error(), "circuit breaker is open") {
				break
			}
		}
	}
}

func TestDeepAgentsRuntimeClient_ContextCancellation(t *testing.T) {
	// Create a server with delay
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		time.Sleep(100 * time.Millisecond)
		w.WriteHeader(http.StatusOK)
		json.NewEncoder(w).Encode(DeepAgentsInvokeResponse{
			ThreadID: "test-thread-id",
			Status:   "started",
		})
	}))
	defer server.Close()

	client := NewDeepAgentsRuntimeClient()
	client.baseURL = server.URL

	// Create context with short timeout
	ctx, cancel := context.WithTimeout(context.Background(), 50*time.Millisecond)
	defer cancel()

	req := JobRequest{
		TraceID: "test-trace-id",
		JobID:   "test-job-id",
		AgentDefinition: map[string]interface{}{
			"name": "test-agent",
		},
		InputPayload: InputPayload{
			Messages: []Message{
				{Role: "user", Content: "test prompt"},
			},
		},
	}

	_, err := client.Invoke(ctx, req)
	assert.Error(t, err)
	assert.Contains(t, err.Error(), "context deadline exceeded")
}