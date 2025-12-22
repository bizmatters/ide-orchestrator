package gateway

import (
	"log"
	"net/http"
	"time"
	"fmt"
	"context"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/crypto/bcrypt"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/auth"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/orchestration"
)

// Handler handles HTTP requests for the gateway layer
type Handler struct {
	orchestrationService *orchestration.Service
	jwtManager           *auth.JWTManager
	pool                 *pgxpool.Pool
}

// NewHandler creates a new gateway handler
func NewHandler(orchestrationService *orchestration.Service, jwtManager *auth.JWTManager, pool *pgxpool.Pool) *Handler {
	return &Handler{
		orchestrationService: orchestrationService,
		jwtManager:           jwtManager,
		pool:                 pool,
	}
}

// LoginRequest represents a login request
type LoginRequest struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required"`
}

// LoginResponse represents a login response
type LoginResponse struct {
	Token  string `json:"token"`
	UserID string `json:"user_id"`
}

// Login godoc
// @Summary User login
// @Description Authenticate user and return JWT token
// @Tags auth
// @Accept json
// @Produce json
// @Param request body LoginRequest true "Login credentials"
// @Success 200 {object} LoginResponse
// @Failure 400 {object} map[string]string
// @Failure 401 {object} map[string]string
// @Router /auth/login [post]
func (h *Handler) Login(c *gin.Context) {
	var req LoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	// Lookup user in database
	var userID string
	var hashedPassword string
	err := h.pool.QueryRow(c.Request.Context(),
		`SELECT id, hashed_password FROM users WHERE email = $1`,
		req.Email,
	).Scan(&userID, &hashedPassword)

	if err != nil {
		log.Printf(`{"level":"warn","message":"User not found","email":"%s"}`, req.Email)
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}

	// Verify password using bcrypt
	if err := bcrypt.CompareHashAndPassword([]byte(hashedPassword), []byte(req.Password)); err != nil {
		log.Printf(`{"level":"warn","message":"Invalid password","email":"%s"}`, req.Email)
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid email or password"})
		return
	}

	// Generate JWT token
	token, err := h.jwtManager.GenerateToken(
		c.Request.Context(),
		userID,
		req.Email,
		[]string{"user"},
		24*time.Hour,
	)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to generate token"})
		return
	}

	c.JSON(http.StatusOK, LoginResponse{
		Token:  token,
		UserID: userID,
	})
}

// CreateWorkflowRequest represents a workflow creation request
type CreateWorkflowRequest struct {
	Name        string `json:"name" binding:"required"`
	Description string `json:"description"`
}

// WorkflowResponse represents a workflow response
type WorkflowResponse struct {
	ID          string `json:"id"`
	Name        string `json:"name"`
	Description string `json:"description"`
}

// CreateWorkflow godoc
// @Summary Create workflow
// @Description Create a new workflow
// @Tags workflows
// @Accept json
// @Produce json
// @Param request body CreateWorkflowRequest true "Workflow details"
// @Success 201 {object} WorkflowResponse
// @Failure 400 {object} map[string]string
// @Security BearerAuth
// @Router /workflows [post]
func (h *Handler) CreateWorkflow(c *gin.Context) {
	var req CreateWorkflowRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}
	userIDStr := userIDVal.(string)
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid user ID"})
		return
	}

	// Create workflow via orchestration service
	workflowID, err := h.orchestrationService.CreateWorkflow(c.Request.Context(), req.Name, req.Description, userID)
	if err != nil {
		log.Printf(`{"level":"error","message":"Failed to create workflow","error":"%v","user_id":"%s"}`, err, userID)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create workflow", "details": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, WorkflowResponse{
		ID:          workflowID.String(),
		Name:        req.Name,
		Description: req.Description,
	})
}

// CreateRefinementRequest represents a refinement request
type CreateRefinementRequest struct {
	UserPrompt       string  `json:"user_prompt" binding:"required"`
	ContextFilePath  *string `json:"context_file_path,omitempty"`
	ContextSelection *string `json:"context_selection,omitempty"`
}

// CreateRefinementResponse represents a refinement response
type CreateRefinementResponse struct {
	ProposalID    string `json:"proposal_id"`
	ThreadID      string `json:"thread_id"`
	Status        string `json:"status"`
	WebSocketURL  string `json:"websocket_url"`
	CreatedAt     string `json:"created_at"`
}

// CreateRefinement godoc
// @Summary Create refinement
// @Description Create a new refinement proposal using deepagents-runtime
// @Tags workflows
// @Accept json
// @Produce json
// @Param id path string true "Workflow ID"
// @Param request body CreateRefinementRequest true "Refinement request"
// @Success 200 {object} CreateRefinementResponse
// @Failure 400 {object} map[string]string
// @Failure 404 {object} map[string]string
// @Failure 503 {object} map[string]string
// @Security BearerAuth
// @Router /workflows/{id}/refinements [post]
func (h *Handler) CreateRefinement(c *gin.Context) {
	workflowIDStr := c.Param("id")
	workflowID, err := uuid.Parse(workflowIDStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid workflow ID"})
		return
	}

	var req CreateRefinementRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}
	userIDStr := userIDVal.(string)
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid user ID"})
		return
	}

	// Validate user access to workflow
	if !h.canAccessWorkflow(c.Request.Context(), workflowID, userID) {
		c.JSON(http.StatusForbidden, gin.H{"error": "Access denied to workflow"})
		return
	}

	// Get or create draft
	draftID, err := h.orchestrationService.GetOrCreateDraft(c.Request.Context(), workflowID, userID)
	if err != nil {
		log.Printf("Failed to create draft for workflow %s: %v", workflowID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create draft"})
		return
	}

	// Create proposal with user prompt and context
	proposalID, threadID, err := h.orchestrationService.CreateRefinementProposal(
		c.Request.Context(), 
		draftID, 
		userID, 
		req.UserPrompt,
		req.ContextFilePath,
		req.ContextSelection,
	)
	if err != nil {
		log.Printf("Failed to create refinement proposal: %v", err)
		if err.Error() == "deepagents-runtime unavailable" {
			c.JSON(http.StatusServiceUnavailable, gin.H{"error": "AI service temporarily unavailable"})
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create refinement proposal"})
		}
		return
	}

	// Build WebSocket URL for streaming
	websocketURL := fmt.Sprintf("/api/ws/refinements/%s", threadID)

	c.JSON(http.StatusOK, CreateRefinementResponse{
		ProposalID:   proposalID.String(),
		ThreadID:     threadID,
		Status:       "processing",
		WebSocketURL: websocketURL,
		CreatedAt:    time.Now().UTC().Format(time.RFC3339),
	})
}

// Placeholder handlers for other endpoints
func (h *Handler) GetWorkflow(c *gin.Context) {
	workflowIDStr := c.Param("id")
	workflowID, err := uuid.Parse(workflowIDStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid workflow ID"})
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}
	userIDStr := userIDVal.(string)
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid user ID"})
		return
	}

	// Check if user can access this workflow
	if !h.canAccessWorkflow(c.Request.Context(), workflowID, userID) {
		c.JSON(http.StatusForbidden, gin.H{"error": "Access denied to workflow"})
		return
	}

	// Get workflow from orchestration service
	workflow, err := h.orchestrationService.GetWorkflow(c.Request.Context(), workflowID)
	if err != nil {
		if err.Error() == "workflow not found" {
			c.JSON(http.StatusNotFound, gin.H{"error": "Workflow not found"})
		} else {
			log.Printf("Failed to get workflow %s: %v", workflowID, err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to retrieve workflow"})
		}
		return
	}

	c.JSON(http.StatusOK, WorkflowResponse{
		ID:          workflow.ID.String(),
		Name:        workflow.Name,
		Description: workflow.Description,
	})
}

func (h *Handler) GetVersions(c *gin.Context) {
	workflowIDStr := c.Param("id")
	workflowID, err := uuid.Parse(workflowIDStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid workflow ID"})
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}
	userIDStr := userIDVal.(string)
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid user ID"})
		return
	}

	// Check if user can access this workflow
	if !h.canAccessWorkflow(c.Request.Context(), workflowID, userID) {
		c.JSON(http.StatusForbidden, gin.H{"error": "Access denied to workflow"})
		return
	}

	// Get versions from orchestration service
	versions, err := h.orchestrationService.GetVersions(c.Request.Context(), workflowID)
	if err != nil {
		log.Printf("Failed to get versions for workflow %s: %v", workflowID, err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to retrieve versions"})
		return
	}

	// Convert to response format
	versionResponses := make([]map[string]interface{}, len(versions))
	for i, version := range versions {
		versionResponses[i] = map[string]interface{}{
			"id":             version.ID.String(),
			"version_number": version.VersionNumber,
			"status":         version.Status,
			"created_at":     version.CreatedAt.Format(time.RFC3339),
		}
	}

	c.JSON(http.StatusOK, gin.H{
		"versions": versionResponses,
	})
}

func (h *Handler) GetVersion(c *gin.Context) {
	c.JSON(http.StatusNotImplemented, gin.H{"error": "Not implemented"})
}

func (h *Handler) PublishDraft(c *gin.Context) {
	c.JSON(http.StatusNotImplemented, gin.H{"error": "Not implemented"})
}

func (h *Handler) DiscardDraft(c *gin.Context) {
	c.JSON(http.StatusNotImplemented, gin.H{"error": "Not implemented"})
}

func (h *Handler) DeployVersion(c *gin.Context) {
	c.JSON(http.StatusNotImplemented, gin.H{"error": "Not implemented"})
}

func (h *Handler) ApproveProposal(c *gin.Context) {
	proposalIDStr := c.Param("proposalId")
	proposalID, err := uuid.Parse(proposalIDStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid proposal ID"})
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}
	userIDStr := userIDVal.(string)
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid user ID"})
		return
	}

	// Verify user can access this proposal
	if !h.canAccessProposal(c.Request.Context(), proposalID, userID) {
		c.JSON(http.StatusForbidden, gin.H{"error": "Access denied to proposal"})
		return
	}

	// Approve proposal via orchestration service
	err = h.orchestrationService.ApproveProposal(c.Request.Context(), proposalID, userID)
	if err != nil {
		log.Printf("Failed to approve proposal %s: %v", proposalID, err)
		if err.Error() == "proposal not found" {
			c.JSON(http.StatusNotFound, gin.H{"error": "Proposal not found"})
		} else if err.Error() == "proposal not completed" {
			c.JSON(http.StatusBadRequest, gin.H{"error": "Proposal is not ready for approval"})
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to approve proposal"})
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"proposal_id": proposalID.String(),
		"approved_at": time.Now().UTC().Format(time.RFC3339),
		"message":     "Proposal approved and changes applied to draft",
	})
}

func (h *Handler) RejectProposal(c *gin.Context) {
	proposalIDStr := c.Param("proposalId")
	proposalID, err := uuid.Parse(proposalIDStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid proposal ID"})
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}
	userIDStr := userIDVal.(string)
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid user ID"})
		return
	}

	// Verify user can access this proposal
	if !h.canAccessProposal(c.Request.Context(), proposalID, userID) {
		c.JSON(http.StatusForbidden, gin.H{"error": "Access denied to proposal"})
		return
	}

	// Reject proposal via orchestration service
	err = h.orchestrationService.RejectProposal(c.Request.Context(), proposalID, userID)
	if err != nil {
		log.Printf("Failed to reject proposal %s: %v", proposalID, err)
		if err.Error() == "proposal not found" {
			c.JSON(http.StatusNotFound, gin.H{"error": "Proposal not found"})
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to reject proposal"})
		}
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"proposal_id": proposalID.String(),
		"message":     "Proposal rejected and discarded",
	})
}

// GetProposal godoc
// @Summary Get proposal details
// @Description Retrieve proposal details and generated files
// @Tags proposals
// @Produce json
// @Param id path string true "Proposal ID"
// @Success 200 {object} map[string]interface{}
// @Failure 400 {object} map[string]string
// @Failure 403 {object} map[string]string
// @Failure 404 {object} map[string]string
// @Security BearerAuth
// @Router /proposals/{id} [get]
func (h *Handler) GetProposal(c *gin.Context) {
	proposalIDStr := c.Param("id")
	proposalID, err := uuid.Parse(proposalIDStr)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid proposal ID"})
		return
	}

	userIDVal, exists := c.Get("user_id")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "User not authenticated"})
		return
	}
	userIDStr := userIDVal.(string)
	userID, err := uuid.Parse(userIDStr)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid user ID"})
		return
	}

	// Verify user can access this proposal
	if !h.canAccessProposal(c.Request.Context(), proposalID, userID) {
		c.JSON(http.StatusForbidden, gin.H{"error": "Access denied to proposal"})
		return
	}

	// Get proposal details via orchestration service
	proposal, err := h.orchestrationService.GetProposal(c.Request.Context(), proposalID)
	if err != nil {
		log.Printf("Failed to get proposal %s: %v", proposalID, err)
		if err.Error() == "proposal not found" {
			c.JSON(http.StatusNotFound, gin.H{"error": "Proposal not found"})
		} else {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to retrieve proposal"})
		}
		return
	}

	c.JSON(http.StatusOK, proposal)
}

// canAccessWorkflow checks if user can access the specified workflow
func (h *Handler) canAccessWorkflow(ctx context.Context, workflowID, userID uuid.UUID) bool {
	var count int
	err := h.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM workflows 
		WHERE id = $1 AND created_by_user_id = $2
	`, workflowID, userID).Scan(&count)
	
	return err == nil && count > 0
}

// canAccessProposal checks if user can access the specified proposal
func (h *Handler) canAccessProposal(ctx context.Context, proposalID, userID uuid.UUID) bool {
	var count int
	err := h.pool.QueryRow(ctx, `
		SELECT COUNT(*) FROM proposal_access 
		WHERE proposal_id = $1 AND user_id = $2
	`, proposalID, userID).Scan(&count)
	
	return err == nil && count > 0
}
