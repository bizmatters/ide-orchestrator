package gateway

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"

	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/auth"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/orchestration"
)

// DeepAgentsWebSocketProxy handles WebSocket connections to deepagents-runtime
type DeepAgentsWebSocketProxy struct {
	pool                    *pgxpool.Pool
	deepAgentsClient        orchestration.DeepAgentsRuntimeClientInterface
	jwtManager              *auth.JWTManager
	tracer                  trace.Tracer
	upgrader                websocket.Upgrader
}

// NewDeepAgentsWebSocketProxy creates a new deepagents-runtime WebSocket proxy
func NewDeepAgentsWebSocketProxy(pool *pgxpool.Pool, deepAgentsClient orchestration.DeepAgentsRuntimeClientInterface, jwtManager *auth.JWTManager) *DeepAgentsWebSocketProxy {
	return &DeepAgentsWebSocketProxy{
		pool:             pool,
		deepAgentsClient: deepAgentsClient,
		jwtManager:       jwtManager,
		tracer:           otel.Tracer("deepagents-websocket-proxy"),
		upgrader: websocket.Upgrader{
			CheckOrigin: func(r *http.Request) bool {
				// TODO: Implement proper CORS origin checking for production
				origin := r.Header.Get("Origin")
				// For now, allow all origins - should be restricted in production
				log.Printf("WebSocket connection from origin: %s", origin)
				return true
			},
			HandshakeTimeout: 10 * time.Second,
		},
	}
}

// StreamRefinement handles WebSocket /api/ws/refinements/:thread_id for deepagents-runtime
// @Summary Stream deepagents-runtime refinement progress
// @Description WebSocket endpoint to stream real-time progress from deepagents-runtime
// @Tags refinements
// @Param thread_id path string true "Thread ID"
// @Param Authorization header string true "Bearer token" 
// @Success 101 "Switching Protocols"
// @Failure 401 {object} map[string]string
// @Failure 403 {object} map[string]string
// @Failure 404 {object} map[string]string
// @Security BearerAuth
// @Router /ws/refinements/{thread_id} [get]
func (p *DeepAgentsWebSocketProxy) StreamRefinement(c *gin.Context) {
	ctx, span := p.tracer.Start(c.Request.Context(), "deepagents_websocket_proxy.stream_refinement")
	defer span.End()

	threadID := c.Param("thread_id")
	span.SetAttributes(attribute.String("thread_id", threadID))

	// Validate JWT and get user ID
	userID, err := p.validateJWTAndGetUserID(c)
	if err != nil {
		span.RecordError(err)
		log.Printf("JWT validation failed: %v", err)
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	span.SetAttributes(attribute.String("user_id", userID))

	// Verify user can access this thread_id
	if !p.canAccessThread(ctx, userID, threadID) {
		span.SetAttributes(attribute.Bool("access_denied", true))
		log.Printf("Access denied for user %s to thread %s", userID, threadID)
		c.JSON(http.StatusForbidden, gin.H{"error": "Forbidden"})
		return
	}

	log.Printf("WebSocket connection request for thread_id: %s, user_id: %s", threadID, userID)

	// Upgrade HTTP connection to WebSocket
	clientConn, err := p.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to upgrade connection: %v", err)
		return
	}
	defer clientConn.Close()

	log.Printf("WebSocket connection upgraded successfully for thread: %s", threadID)

	// Connect to deepagents-runtime WebSocket
	deepAgentsConn, err := p.deepAgentsClient.StreamWebSocket(ctx, threadID)
	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to connect to deepagents-runtime WebSocket: %v", err)
		p.sendErrorToClient(clientConn, "Failed to connect to deepagents-runtime")
		return
	}
	defer deepAgentsConn.Close()

	log.Printf("Connected to deepagents-runtime WebSocket for thread: %s", threadID)

	// Start hybrid event processing with bidirectional proxying
	p.proxyWebSocketWithStateExtraction(ctx, clientConn, deepAgentsConn, threadID)
}

// validateJWTAndGetUserID validates JWT token and returns user ID
func (p *DeepAgentsWebSocketProxy) validateJWTAndGetUserID(c *gin.Context) (string, error) {
	// Try to get JWT from query parameter first (WebSocket standard)
	token := c.Query("token")
	if token == "" {
		// Fallback to Authorization header
		authHeader := c.GetHeader("Authorization")
		if authHeader != "" && len(authHeader) > 7 && authHeader[:7] == "Bearer " {
			token = authHeader[7:]
		}
	}

	if token == "" {
		return "", fmt.Errorf("missing JWT token")
	}

	// Validate JWT
	claims, err := p.jwtManager.ValidateToken(c.Request.Context(), token)
	if err != nil {
		return "", fmt.Errorf("invalid JWT: %w", err)
	}

	return claims.UserID, nil
}

// canAccessThread checks if user can access the specified thread_id
func (p *DeepAgentsWebSocketProxy) canAccessThread(ctx context.Context, userID, threadID string) bool {
	// Handle nil pool gracefully (for testing)
	if p.pool == nil {
		log.Printf("Pool is nil, denying access for thread: %s", threadID)
		return false
	}

	var proposalID string
	err := p.pool.QueryRow(ctx, `
		SELECT p.id
		FROM proposals p
		JOIN drafts d ON p.draft_id = d.id
		WHERE p.thread_id = $1 AND d.created_by_user_id = $2
	`, threadID, userID).Scan(&proposalID)

	return err == nil
}

// proxyWebSocketWithStateExtraction handles bidirectional WebSocket proxying with state extraction
func (p *DeepAgentsWebSocketProxy) proxyWebSocketWithStateExtraction(
	ctx context.Context,
	clientConn, deepAgentsConn *websocket.Conn,
	threadID string,
) {
	var span trace.Span
	if p.tracer != nil {
		ctx, span = p.tracer.Start(ctx, "deepagents_websocket_proxy.proxy_with_state_extraction")
		defer span.End()
		span.SetAttributes(attribute.String("thread_id", threadID))
	}

	var finalFiles map[string]interface{}
	errChan := make(chan error, 2)

	// Client -> deepagents-runtime (forward client messages)
	go func() {
		defer func() {
			log.Printf("Client->DeepAgents goroutine ended for thread: %s", threadID)
		}()

		for {
			messageType, message, err := clientConn.ReadMessage()
			if err != nil {
				if websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
					log.Printf("Client connection closed normally for thread: %s", threadID)
				} else {
					log.Printf("Client connection read error for thread %s: %v", threadID, err)
				}
				errChan <- err
				return
			}

			// Forward message to deepagents-runtime
			if err := deepAgentsConn.WriteMessage(messageType, message); err != nil {
				log.Printf("Failed to forward message to deepagents-runtime for thread %s: %v", threadID, err)
				errChan <- err
				return
			}

			log.Printf("Forwarded client message to deepagents-runtime for thread: %s", threadID)
		}
	}()

	// deepagents-runtime -> Client (forward events and extract state)
	go func() {
		defer func() {
			log.Printf("DeepAgents->Client goroutine ended for thread: %s", threadID)
		}()

		for {
			var event orchestration.StreamEvent
			if err := deepAgentsConn.ReadJSON(&event); err != nil {
				if websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
					log.Printf("DeepAgents connection closed normally for thread: %s", threadID)
				} else {
					log.Printf("DeepAgents connection read error for thread %s: %v", threadID, err)
				}
				errChan <- err
				return
			}

			log.Printf("Received event from deepagents-runtime for thread %s: %s", threadID, event.EventType)

			// Extract files from on_state_update events
			if event.EventType == "on_state_update" {
				if files, ok := event.Data["files"]; ok {
					if filesMap, ok := files.(map[string]interface{}); ok {
						finalFiles = filesMap
						log.Printf("Extracted %d files from on_state_update for thread: %s", len(finalFiles), threadID)
					}
				}
			}

			// Forward event to client
			if err := clientConn.WriteJSON(event); err != nil {
				log.Printf("Failed to forward event to client for thread %s: %v", threadID, err)
				errChan <- err
				return
			}

			// Handle completion
			if event.EventType == "end" {
				log.Printf("Received end event for thread: %s, updating proposal with files", threadID)
				// Update proposal with final files in background
				go p.updateProposalWithFiles(context.Background(), threadID, finalFiles)
				
				// End the proxy session
				errChan <- fmt.Errorf("execution completed")
				return
			}
		}
	}()

	// Wait for error or completion
	err := <-errChan
	if err != nil && !websocket.IsCloseError(err, websocket.CloseNormalClosure, websocket.CloseGoingAway) {
		if err.Error() != "execution completed" {
			if span != nil {
				span.RecordError(err)
			}
			log.Printf("WebSocket proxy error for thread %s: %v", threadID, err)
			
			// Update proposal status to failed on error
			go p.updateProposalStatusToFailed(context.Background(), threadID, err.Error())
		}
	}

	log.Printf("WebSocket proxy session ended for thread: %s", threadID)
}

// updateProposalWithFiles updates the proposal with generated files
func (p *DeepAgentsWebSocketProxy) updateProposalWithFiles(ctx context.Context, threadID string, files map[string]interface{}) {
	// Handle nil pool gracefully (for testing)
	if p.pool == nil {
		log.Printf("Pool is nil, skipping database update for thread: %s", threadID)
		return
	}

	var span trace.Span
	if p.tracer != nil {
		ctx, span = p.tracer.Start(ctx, "deepagents_websocket_proxy.update_proposal_files")
		defer span.End()
		span.SetAttributes(
			attribute.String("thread_id", threadID),
			attribute.Int("files_count", len(files)),
		)
	}

	// Find proposal by thread_id
	var proposalID string
	err := p.pool.QueryRow(ctx, `
		SELECT id FROM proposals WHERE thread_id = $1
	`, threadID).Scan(&proposalID)

	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to find proposal for thread_id %s: %v", threadID, err)
		return
	}

	// Convert files to JSONB
	filesJSON, err := json.Marshal(files)
	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to marshal files for proposal %s: %v", proposalID, err)
		return
	}

	// Update proposal with generated files and mark as completed
	_, err = p.pool.Exec(ctx, `
		UPDATE proposals 
		SET generated_files = $1, 
		    status = 'completed',
		    completed_at = NOW()
		WHERE id = $2
	`, filesJSON, proposalID)

	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to update proposal %s with files: %v", proposalID, err)
		return
	}

	span.SetAttributes(attribute.String("proposal_id", proposalID))
	log.Printf("Successfully updated proposal %s with %d files", proposalID, len(files))
}

// updateProposalStatusToFailed updates the proposal status to failed with error details
func (p *DeepAgentsWebSocketProxy) updateProposalStatusToFailed(ctx context.Context, threadID string, errorMessage string) {
	// Handle nil pool gracefully (for testing)
	if p.pool == nil {
		log.Printf("Pool is nil, skipping database update for thread: %s", threadID)
		return
	}

	var span trace.Span
	if p.tracer != nil {
		ctx, span = p.tracer.Start(ctx, "deepagents_websocket_proxy.update_proposal_failed")
		defer span.End()
		span.SetAttributes(
			attribute.String("thread_id", threadID),
			attribute.String("error_message", errorMessage),
		)
	}

	// Find proposal by thread_id
	var proposalID string
	err := p.pool.QueryRow(ctx, `
		SELECT id FROM proposals WHERE thread_id = $1
	`, threadID).Scan(&proposalID)

	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to find proposal for thread_id %s: %v", threadID, err)
		return
	}

	// Update proposal status to failed with error details
	_, err = p.pool.Exec(ctx, `
		UPDATE proposals 
		SET status = 'failed',
		    completed_at = NOW(),
		    ai_generated_content = jsonb_set(
		        COALESCE(ai_generated_content, '{}'),
		        '{error}',
		        to_jsonb($1::text)
		    )
		WHERE id = $2
	`, errorMessage, proposalID)

	if err != nil {
		span.RecordError(err)
		log.Printf("Failed to update proposal %s to failed status: %v", proposalID, err)
		return
	}

	span.SetAttributes(attribute.String("proposal_id", proposalID))
	log.Printf("Successfully updated proposal %s to failed status with error: %s", proposalID, errorMessage)
}

// sendErrorToClient sends an error message to the WebSocket client
func (p *DeepAgentsWebSocketProxy) sendErrorToClient(conn *websocket.Conn, message string) {
	errorEvent := map[string]interface{}{
		"event_type": "error",
		"data": map[string]interface{}{
			"error": message,
		},
	}

	if err := conn.WriteJSON(errorEvent); err != nil {
		log.Printf("Failed to send error to client: %v", err)
	}
}

// IsHealthy checks if the deepagents-runtime service is healthy
func (p *DeepAgentsWebSocketProxy) IsHealthy(ctx context.Context) bool {
	return p.deepAgentsClient.IsHealthy(ctx)
}