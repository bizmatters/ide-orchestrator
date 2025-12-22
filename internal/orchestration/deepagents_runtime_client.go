package orchestration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"time"
	"log"

	"github.com/gorilla/websocket"
	"github.com/sony/gobreaker"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/propagation"
	"go.opentelemetry.io/otel/trace"
)

// DeepAgentsRuntimeClientInterface defines the interface for deepagents-runtime client
type DeepAgentsRuntimeClientInterface interface {
	Invoke(ctx context.Context, req JobRequest) (string, error)
	StreamWebSocket(ctx context.Context, threadID string) (*websocket.Conn, error)
	GetState(ctx context.Context, threadID string) (*ExecutionState, error)
	IsHealthy(ctx context.Context) bool
}

// DeepAgentsRuntimeClient handles communication with the deepagents-runtime service
type DeepAgentsRuntimeClient struct {
	baseURL     string
	httpClient  *http.Client
	tracer      trace.Tracer
	breaker     *gobreaker.CircuitBreaker
}

// JobRequest represents a deepagents-runtime job invocation request
type JobRequest struct {
	TraceID         string                 `json:"trace_id"`
	JobID           string                 `json:"job_id"`
	AgentDefinition map[string]interface{} `json:"agent_definition"`
	InputPayload    InputPayload           `json:"input_payload"`
}

// InputPayload represents the input payload for a job
type InputPayload struct {
	Messages []Message `json:"messages"`
}

// Message represents a message in the input payload
type Message struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

// ExecutionState represents the final execution state
type ExecutionState struct {
	ThreadID       string                 `json:"thread_id"`
	Status         string                 `json:"status"` // "completed", "failed", "running"
	Result         map[string]interface{} `json:"result,omitempty"`
	GeneratedFiles map[string]interface{} `json:"generated_files,omitempty"`
	Error          string                 `json:"error,omitempty"`
}

// DeepAgentsInvokeResponse represents the response from the invoke endpoint
type DeepAgentsInvokeResponse struct {
	ThreadID string `json:"thread_id"`
	Status   string `json:"status"`
}

// StreamEvent represents a WebSocket event from deepagents-runtime
type StreamEvent struct {
	EventType string                 `json:"event_type"`
	Data      map[string]interface{} `json:"data"`
}

// NewDeepAgentsRuntimeClient creates a new deepagents-runtime client
func NewDeepAgentsRuntimeClient() *DeepAgentsRuntimeClient {
	baseURL := os.Getenv("DEEPAGENTS_RUNTIME_URL")
	if baseURL == "" {
		baseURL = "http://deepagents-runtime-service:8000"
		log.Printf("WARN: DEEPAGENTS_RUNTIME_URL not set, defaulting to %s", baseURL)
	}

	// Initialize circuit breaker
	settings := gobreaker.Settings{
		Name:        "deepagents-runtime",
		MaxRequests: 3,
		Interval:    60 * time.Second,
		Timeout:     30 * time.Second,
		ReadyToTrip: func(counts gobreaker.Counts) bool {
			return counts.ConsecutiveFailures > 5
		},
		OnStateChange: func(name string, from gobreaker.State, to gobreaker.State) {
			log.Printf("Circuit breaker %s changed from %s to %s", name, from, to)
		},
	}

	return &DeepAgentsRuntimeClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 30 * time.Second,
		},
		tracer:  otel.Tracer("deepagents-runtime-client"),
		breaker: gobreaker.NewCircuitBreaker(settings),
	}
}

// SetBaseURL sets the base URL for testing purposes
func (c *DeepAgentsRuntimeClient) SetBaseURL(baseURL string) {
	c.baseURL = baseURL
}

// Invoke initiates a job execution in deepagents-runtime
func (c *DeepAgentsRuntimeClient) Invoke(ctx context.Context, req JobRequest) (string, error) {
	ctx, span := c.tracer.Start(ctx, "deepagents_runtime.invoke")
	defer span.End()

	span.SetAttributes(
		attribute.String("job_id", req.JobID),
		attribute.String("trace_id", req.TraceID),
	)

	// Execute with circuit breaker
	result, err := c.breaker.Execute(func() (interface{}, error) {
		return c.invokeInternal(ctx, req)
	})

	if err != nil {
		span.RecordError(err)
		return "", fmt.Errorf("failed to invoke deepagents-runtime: %w", err)
	}

	threadID := result.(string)
	span.SetAttributes(attribute.String("thread_id", threadID))
	
	return threadID, nil
}

// invokeInternal performs the actual HTTP request
func (c *DeepAgentsRuntimeClient) invokeInternal(ctx context.Context, req JobRequest) (string, error) {
	jsonData, err := json.Marshal(req)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request: %w", err)
	}

	url := fmt.Sprintf("%s/deepagents-runtime/invoke", c.baseURL)
	httpReq, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return "", fmt.Errorf("failed to create request: %w", err)
	}

	httpReq.Header.Set("Content-Type", "application/json")
	
	// Inject trace context
	otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(httpReq.Header))

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return "", fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted {
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return "", fmt.Errorf("deepagents-runtime returned status %d (failed to read body: %w)", resp.StatusCode, err)
		}
		return "", fmt.Errorf("deepagents-runtime returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var invokeResp DeepAgentsInvokeResponse
	if err := json.NewDecoder(resp.Body).Decode(&invokeResp); err != nil {
		return "", fmt.Errorf("failed to decode response: %w", err)
	}

	return invokeResp.ThreadID, nil
}

// StreamWebSocket establishes a WebSocket connection to stream events
func (c *DeepAgentsRuntimeClient) StreamWebSocket(ctx context.Context, threadID string) (*websocket.Conn, error) {
	ctx, span := c.tracer.Start(ctx, "deepagents_runtime.stream_websocket")
	defer span.End()

	span.SetAttributes(attribute.String("thread_id", threadID))

	// Execute with circuit breaker
	result, err := c.breaker.Execute(func() (interface{}, error) {
		return c.streamWebSocketInternal(ctx, threadID)
	})

	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to establish WebSocket connection: %w", err)
	}

	return result.(*websocket.Conn), nil
}

// streamWebSocketInternal performs the actual WebSocket connection
func (c *DeepAgentsRuntimeClient) streamWebSocketInternal(ctx context.Context, threadID string) (*websocket.Conn, error) {
	// Parse base URL and convert to WebSocket URL
	u, err := url.Parse(c.baseURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse base URL: %w", err)
	}

	// Convert HTTP scheme to WebSocket scheme
	switch u.Scheme {
	case "http":
		u.Scheme = "ws"
	case "https":
		u.Scheme = "wss"
	default:
		return nil, fmt.Errorf("unsupported URL scheme: %s", u.Scheme)
	}

	u.Path = fmt.Sprintf("/deepagents-runtime/stream/%s", threadID)

	// Create WebSocket dialer with timeout
	dialer := websocket.Dialer{
		HandshakeTimeout: 10 * time.Second,
	}

	// Create headers for trace propagation
	headers := http.Header{}
	otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(headers))

	conn, resp, err := dialer.DialContext(ctx, u.String(), headers)
	if err != nil {
		if resp != nil {
			bodyBytes, _ := io.ReadAll(resp.Body)
			return nil, fmt.Errorf("failed to dial WebSocket (status %d): %s, error: %w", resp.StatusCode, string(bodyBytes), err)
		}
		return nil, fmt.Errorf("failed to dial WebSocket: %w", err)
	}

	return conn, nil
}

// GetState retrieves the final execution state (fallback method)
func (c *DeepAgentsRuntimeClient) GetState(ctx context.Context, threadID string) (*ExecutionState, error) {
	ctx, span := c.tracer.Start(ctx, "deepagents_runtime.get_state")
	defer span.End()

	span.SetAttributes(attribute.String("thread_id", threadID))

	// Execute with circuit breaker
	result, err := c.breaker.Execute(func() (interface{}, error) {
		return c.getStateInternal(ctx, threadID)
	})

	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to get state: %w", err)
	}

	return result.(*ExecutionState), nil
}

// getStateInternal performs the actual HTTP request
func (c *DeepAgentsRuntimeClient) getStateInternal(ctx context.Context, threadID string) (*ExecutionState, error) {
	url := fmt.Sprintf("%s/deepagents-runtime/state/%s", c.baseURL, threadID)
	httpReq, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	// Inject trace context
	otel.GetTextMapPropagator().Inject(ctx, propagation.HeaderCarrier(httpReq.Header))

	resp, err := c.httpClient.Do(httpReq)
	if err != nil {
		return nil, fmt.Errorf("failed to make request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return nil, fmt.Errorf("deepagents-runtime returned status %d (failed to read body: %w)", resp.StatusCode, err)
		}
		return nil, fmt.Errorf("deepagents-runtime returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var state ExecutionState
	if err := json.NewDecoder(resp.Body).Decode(&state); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &state, nil
}

// IsHealthy checks if the deepagents-runtime service is healthy
func (c *DeepAgentsRuntimeClient) IsHealthy(ctx context.Context) bool {
	ctx, span := c.tracer.Start(ctx, "deepagents_runtime.health_check")
	defer span.End()

	// Use circuit breaker state as a quick health indicator
	if c.breaker.State() == gobreaker.StateOpen {
		span.SetAttributes(attribute.Bool("healthy", false), attribute.String("reason", "circuit_breaker_open"))
		return false
	}

	// Perform actual health check
	url := fmt.Sprintf("%s/health", c.baseURL)
	httpReq, err := http.NewRequestWithContext(ctx, "GET", url, nil)
	if err != nil {
		span.RecordError(err)
		return false
	}

	// Short timeout for health checks
	client := &http.Client{Timeout: 5 * time.Second}
	resp, err := client.Do(httpReq)
	if err != nil {
		span.RecordError(err)
		return false
	}
	defer resp.Body.Close()

	healthy := resp.StatusCode == http.StatusOK
	span.SetAttributes(attribute.Bool("healthy", healthy))
	
	return healthy
}