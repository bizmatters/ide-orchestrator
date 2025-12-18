package orchestration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"time"
	"log"
	"github.com/google/uuid"
)

// SpecEngineClient handles communication with the Spec Engine service
type SpecEngineClient struct {
	baseURL    string
	httpClient *http.Client
}

// NewSpecEngineClient creates a new Spec Engine client
func NewSpecEngineClient(pool interface{}) *SpecEngineClient {
	// ✅ IMPROVED CODE
	baseURL := os.Getenv("SPEC_ENGINE_URL")
	if baseURL == "" {
	    // Default to the local test/dev port, which is more common
	    // for local execution than the Kubernetes service name.
	    baseURL = "http://localhost:8001" 
	    log.Printf("WARN: SPEC_ENGINE_URL not set, defaulting to %s", baseURL)
	}

	return &SpecEngineClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: 60 * time.Second,
		},
	}
}

// InvokeRequest represents a Spec Engine invocation request matching the FastAPI server format
type InvokeRequest struct {
	Input  map[string]interface{} `json:"input"`
	Config map[string]interface{} `json:"config"`
}

// InvokeResponse represents a Spec Engine invocation response
type InvokeResponse struct {
	ThreadID string `json:"thread_id"`
	Status   string `json:"status"`
}

// InvokeAgent invokes the Spec Engine with a user prompt using LangGraph CLI API
func (c *SpecEngineClient) InvokeAgent(ctx context.Context, userPrompt string) (string, error) {
	threadID := uuid.New().String()

	// Step 1: Get or create assistant
	assistantID, err := c.getOrCreateAssistant(ctx)
	if err != nil {
		return "", fmt.Errorf("failed to get or create assistant: %w", err)
	}

	// Step 2: Create thread
	err = c.createThread(ctx, threadID)
	if err != nil {
		return "", fmt.Errorf("failed to create thread: %w", err)
	}

	// Step 3: Create run in the thread using LangGraph CLI API
	reqBody := map[string]interface{}{
		"assistant_id": assistantID,
		"input": map[string]interface{}{
			"user_prompt": userPrompt,
		},
		"config": map[string]interface{}{
			"configurable": map[string]interface{}{
				"thread_id": threadID,
			},
		},
		"stream_mode": []string{"values"}, // Stream values for WebSocket
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("failed to marshal request: %w", err)
	}

	// Use LangGraph CLI endpoint: /threads/{thread_id}/runs
	url := fmt.Sprintf("%s/threads/%s/runs", c.baseURL, threadID)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return "", fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to invoke spec engine: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusAccepted {
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return "", fmt.Errorf("spec engine returned status %d (failed to read body: %w)", resp.StatusCode, err)
		}
		return "", fmt.Errorf("spec engine returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	// LangGraph CLI returns a Run object with run_id
	var runResp map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&runResp); err != nil {
		return "", fmt.Errorf("failed to decode response: %w", err)
	}

	log.Printf("Created run in thread %s: %+v", threadID, runResp)
	return threadID, nil
}

// createThread creates a new thread in LangGraph CLI
func (c *SpecEngineClient) createThread(ctx context.Context, threadID string) error {
	reqBody := map[string]interface{}{
		"thread_id": threadID,
		"metadata": map[string]interface{}{
			"created_by": "ide-orchestrator",
		},
		"if_exists": "do_nothing", // Don't fail if thread already exists
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return fmt.Errorf("failed to marshal thread request: %w", err)
	}

	// Use POST to /threads (not PUT to /threads/{thread_id})
	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/threads", bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create thread request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return fmt.Errorf("failed to create thread: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return fmt.Errorf("thread creation returned status %d (failed to read body: %w)", resp.StatusCode, err)
		}
		return fmt.Errorf("thread creation returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	return nil
}

// getOrCreateAssistant gets or creates an assistant for the spec-engine graph
func (c *SpecEngineClient) getOrCreateAssistant(ctx context.Context) (string, error) {
	// Try to create an assistant (idempotent operation)
	reqBody := map[string]interface{}{
		"graph_id": "spec-engine",
		"config":   map[string]interface{}{},
		"name":     "Builder Agent",
		"description": "Multi-agent system for generating workflow specifications",
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		return "", fmt.Errorf("failed to marshal assistant request: %w", err)
	}

	req, err := http.NewRequestWithContext(ctx, "POST", c.baseURL+"/assistants", bytes.NewBuffer(jsonData))
	if err != nil {
		return "", fmt.Errorf("failed to create assistant request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		return "", fmt.Errorf("failed to create assistant: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK && resp.StatusCode != http.StatusCreated {
		bodyBytes, err := io.ReadAll(resp.Body)
		if err != nil {
			return "", fmt.Errorf("assistant creation returned status %d (failed to read body: %w)", resp.StatusCode, err)
		}
		return "", fmt.Errorf("assistant creation returned status %d: %s", resp.StatusCode, string(bodyBytes))
	}

	var assistantResp map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&assistantResp); err != nil {
		return "", fmt.Errorf("failed to decode assistant response: %w", err)
	}

	assistantID, ok := assistantResp["assistant_id"].(string)
	if !ok {
		return "", fmt.Errorf("invalid assistant_id in response: %+v", assistantResp)
	}

	log.Printf("Using assistant: %s", assistantID)
	return assistantID, nil
}
