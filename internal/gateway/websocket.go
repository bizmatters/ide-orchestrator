package gateway

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

var wsTracer = otel.Tracer("websocket-proxy")

var upgrader = websocket.Upgrader{
	CheckOrigin: func(r *http.Request) bool {
		// TODO: Implement proper origin checking for production
		return true
	},
}

// WebSocketProxy handles WebSocket connections
type WebSocketProxy struct {
	pool            *pgxpool.Pool
	specEngineURL   string
	tracer          trace.Tracer
}

// NewWebSocketProxy creates a new WebSocket proxy
func NewWebSocketProxy(pool *pgxpool.Pool, specEngineURL string) *WebSocketProxy {
	return &WebSocketProxy{
		pool:          pool,
		specEngineURL: specEngineURL,
		tracer:        wsTracer,
	}
}

// StreamRefinement handles WebSocket /api/ws/refinements/:thread_id
// @Summary Stream Builder Agent refinement progress
// @Description WebSocket endpoint to stream real-time progress from Builder Agent
// @Tags refinements
// @Param thread_id path string true "Thread ID"
// @Param Authorization header string true "Bearer token"
// @Success 101 "Switching Protocols"
// @Failure 401 {object} map[string]string
// @Failure 403 {object} map[string]string
// @Failure 404 {object} map[string]string
// @Security BearerAuth
// @Router /ws/refinements/{thread_id} [get]
func (p *WebSocketProxy) StreamRefinement(c *gin.Context) {
	ctx, span := p.tracer.Start(c.Request.Context(), "websocket_proxy.stream_refinement")
	defer span.End()

	threadID := c.Param("thread_id")
	userID, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}

	span.SetAttributes(
		attribute.String("thread.id", threadID),
		attribute.String("user.id", userID.(string)),
	)

	log.Printf("WebSocket connection request for thread_id: %s, user_id: %s", threadID, userID.(string))

	// Verify user owns the proposal with this thread_id
	var proposalID string
	var draftID string
	err := p.pool.QueryRow(ctx, `
		SELECT p.id, p.draft_id
		FROM proposals p
		JOIN drafts d ON p.draft_id = d.id
		WHERE p.thread_id = $1 AND d.created_by_user_id = $2
	`, threadID, userID.(string)).Scan(&proposalID, &draftID)

	if err != nil {
		span.RecordError(err)
		log.Printf("Proposal not found or access denied: %v", err)
		c.JSON(http.StatusForbidden, gin.H{"error": "Proposal not found or access denied"})
		return
	}

	span.SetAttributes(
		attribute.String("proposal.id", proposalID),
		attribute.String("draft.id", draftID),
	)

	log.Printf("Found proposal: %s, draft: %s", proposalID, draftID)

	// Upgrade HTTP connection to WebSocket
	clientConn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to upgrade connection: %v", err)
		return
	}
	defer clientConn.Close()

	log.Printf("WebSocket connection upgraded successfully")

	// Connect to LangGraph CLI's HTTP streaming endpoint
	// LangGraph CLI uses HTTP streaming, not WebSocket, for real-time updates
	// We'll stream from /threads/{thread_id}/stream to get all runs for this thread
	streamURL := fmt.Sprintf("%s/threads/%s/stream", p.specEngineURL, threadID)
	
	span.SetAttributes(attribute.String("spec_engine.stream_url", streamURL))
	log.Printf("Starting HTTP stream from Spec Engine: %s", streamURL)

	// Create HTTP request for streaming
	req, err := http.NewRequestWithContext(ctx, "GET", streamURL, nil)
	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to create stream request: %v", err)
		clientConn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseInternalServerErr, "Failed to create stream request"))
		return
	}

	// Set headers for Server-Sent Events streaming
	req.Header.Set("Accept", "text/event-stream")
	req.Header.Set("Cache-Control", "no-cache")
	req.Header.Set("Connection", "keep-alive")

	// Make the streaming request
	httpClient := &http.Client{}
	resp, err := httpClient.Do(req)
	if err != nil || (resp != nil && resp.StatusCode == http.StatusInternalServerError) {
		// Streaming failed - implement fallback to checkpointer
		span.SetAttributes(attribute.String("fallback.reason", "streaming_failed"))
		log.Printf("HTTP streaming failed (err: %v, status: %d), falling back to checkpointer", err, getStatusCode(resp))
		
		if resp != nil {
			resp.Body.Close()
		}
		
		// Attempt fallback to checkpointer
		if fallbackErr := p.handleCheckpointerFallback(ctx, threadID, clientConn); fallbackErr != nil {
			span.RecordError(fallbackErr)
			log.Printf("Fallback to checkpointer also failed: %v", fallbackErr)
			clientConn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseServiceRestart, "Spec Engine unavailable"))
		} else {
			log.Printf("Successfully provided workflow state via checkpointer fallback")
		}
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		span.RecordError(fmt.Errorf("stream returned status %d", resp.StatusCode))
		log.Printf("Stream returned status %d, attempting fallback", resp.StatusCode)
		
		// Attempt fallback for non-200 responses
		if fallbackErr := p.handleCheckpointerFallback(ctx, threadID, clientConn); fallbackErr != nil {
			span.RecordError(fallbackErr)
			log.Printf("Fallback to checkpointer failed: %v", fallbackErr)
			clientConn.WriteMessage(websocket.CloseMessage, websocket.FormatCloseMessage(websocket.CloseServiceRestart, "Spec Engine unavailable"))
		} else {
			log.Printf("Successfully provided workflow state via checkpointer fallback")
		}
		return
	}

	log.Printf("Connected to Spec Engine HTTP stream successfully - using real-time streaming")

	// Handle streaming response
	errChan := make(chan error, 2)

	// Client -> ignore (one-way stream from agent to client)
	go func() {
		for {
			_, _, err := clientConn.ReadMessage()
			if err != nil {
				log.Printf("Client connection read error: %v", err)
				errChan <- err
				return
			}
			// Ignore client messages - this is a one-way stream from agent to client
		}
	}()

	// HTTP Stream -> Client (forward streaming events)
	go func() {
		scanner := bufio.NewScanner(resp.Body)
		for scanner.Scan() {
			line := scanner.Text()
			
			// Skip empty lines and comments
			if line == "" || strings.HasPrefix(line, ":") {
				continue
			}
			
			// Parse Server-Sent Events format
			if strings.HasPrefix(line, "data: ") {
				data := strings.TrimPrefix(line, "data: ")
				
				// Forward all events since we're already streaming from thread-specific endpoint
				log.Printf("Received event for thread %s, forwarding to client", threadID)
				if err := clientConn.WriteMessage(websocket.TextMessage, []byte(data)); err != nil {
					log.Printf("Client connection write error: %v", err)
					errChan <- err
					return
				}
			}
		}
		
		if err := scanner.Err(); err != nil {
			log.Printf("Stream scanner error: %v", err)
			errChan <- err
		} else {
			log.Printf("Stream ended normally")
			errChan <- fmt.Errorf("stream ended")
		}
	}()

	// Wait for error or completion
	err = <-errChan
	if err != nil && !websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
		span.RecordError(err)
		log.Printf("WebSocket proxy error: %v", err)
	}

	log.Printf("WebSocket connection closed for thread_id: %s", threadID)
}

// getStatusCode safely extracts status code from response
func getStatusCode(resp *http.Response) int {
	if resp == nil {
		return 0
	}
	return resp.StatusCode
}

// handleCheckpointerFallback queries the checkpointer database for final workflow state
// and sends it to the client as LangServe-compatible events
func (p *WebSocketProxy) handleCheckpointerFallback(ctx context.Context, threadID string, clientConn *websocket.Conn) error {
	span := trace.SpanFromContext(ctx)
	span.SetAttributes(
		attribute.String("fallback.mode", "checkpointer"),
		attribute.String("thread_id", threadID),
	)
	
	log.Printf("Attempting checkpointer fallback for thread: %s", threadID)
	
	// Query checkpointer for the latest checkpoint
	finalState, err := p.queryCheckpointerState(ctx, threadID)
	if err != nil {
		return fmt.Errorf("failed to query checkpointer: %w", err)
	}
	
	if finalState == nil {
		return fmt.Errorf("no checkpoint data found for thread %s", threadID)
	}
	
	// Format as LangServe-compatible event
	event := map[string]interface{}{
		"event": "on_chain_stream",
		"data": map[string]interface{}{
			"chunk": finalState,
		},
		"metadata": map[string]interface{}{
			"thread_id": threadID,
			"source": "checkpointer_fallback",
			"timestamp": "now", // Could be more precise
		},
	}
	
	// Send event to client
	eventBytes, err := json.Marshal(event)
	if err != nil {
		return fmt.Errorf("failed to marshal fallback event: %w", err)
	}
	
	if err := clientConn.WriteMessage(websocket.TextMessage, eventBytes); err != nil {
		return fmt.Errorf("failed to send fallback event: %w", err)
	}
	
	log.Printf("Successfully sent checkpointer fallback data for thread: %s", threadID)
	return nil
}

// queryCheckpointerState queries the LangGraph CLI thread state as fallback
// when streaming fails (e.g., workflow already completed)
func (p *WebSocketProxy) queryCheckpointerState(ctx context.Context, threadID string) (map[string]interface{}, error) {
	// Instead of querying PostgreSQL checkpoints (which LangGraph CLI doesn't use),
	// query the LangGraph CLI's thread state directly
	threadURL := fmt.Sprintf("%s/threads/%s", p.specEngineURL, threadID)
	
	// Retry logic for workflows that might still be completing
	maxRetries := 5
	retryDelay := 3 // seconds
	
	for attempt := 1; attempt <= maxRetries; attempt++ {
		req, err := http.NewRequestWithContext(ctx, "GET", threadURL, nil)
		if err != nil {
			return nil, fmt.Errorf("failed to create thread request: %w", err)
		}
		
		httpClient := &http.Client{}
		resp, err := httpClient.Do(req)
		if err != nil {
			log.Printf("Failed to query thread state for %s (attempt %d/%d): %v", threadID, attempt, maxRetries, err)
			if attempt < maxRetries {
				time.Sleep(time.Duration(retryDelay) * time.Second)
				continue
			}
			return nil, fmt.Errorf("failed to query thread state after %d attempts: %w", attempt, err)
		}
		defer resp.Body.Close()
		
		if resp.StatusCode != http.StatusOK {
			log.Printf("Thread state query returned status %d for %s (attempt %d/%d)", resp.StatusCode, threadID, attempt, maxRetries)
			if attempt < maxRetries {
				time.Sleep(time.Duration(retryDelay) * time.Second)
				continue
			}
			return nil, fmt.Errorf("thread state query returned status %d after %d attempts", resp.StatusCode, attempt)
		}
		
		var threadState map[string]interface{}
		if err := json.NewDecoder(resp.Body).Decode(&threadState); err != nil {
			return nil, fmt.Errorf("failed to parse thread state: %w", err)
		}
		
		// Check if thread has values (completed workflow state)
		values, hasValues := threadState["values"]
		if !hasValues || values == nil {
			log.Printf("Thread %s has no values yet (attempt %d/%d), waiting %d seconds...", threadID, attempt, maxRetries, retryDelay)
			if attempt < maxRetries {
				time.Sleep(time.Duration(retryDelay) * time.Second)
				continue
			}
			return nil, fmt.Errorf("thread %s has no completed state after %d attempts", threadID, maxRetries)
		}
		
		// Successfully got thread state with values
		valuesMap, ok := values.(map[string]interface{})
		if !ok {
			return nil, fmt.Errorf("thread values is not a map: %T", values)
		}
		
		log.Printf("Retrieved thread state for %s: %d keys (attempt %d)", threadID, len(valuesMap), attempt)
		return valuesMap, nil
	}
	
	return nil, fmt.Errorf("failed to get thread state after %d attempts", maxRetries)
}
