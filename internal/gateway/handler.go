package gateway

import (
	"log"
	"net/http"
	"time"

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
	UserPrompt string `json:"user_prompt" binding:"required"`
}

// CreateRefinementResponse represents a refinement response
type CreateRefinementResponse struct {
	ThreadID   string `json:"thread_id"`
	ProposalID string `json:"proposal_id"`
}

// CreateRefinement godoc
// @Summary Create refinement
// @Description Create a new refinement proposal using Builder Agent
// @Tags workflows
// @Accept json
// @Produce json
// @Param id path string true "Workflow ID"
// @Param request body CreateRefinementRequest true "Refinement request"
// @Success 200 {object} CreateRefinementResponse
// @Failure 400 {object} map[string]string
// @Failure 404 {object} map[string]string
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

	// Get or create draft
	draftID, err := h.orchestrationService.GetOrCreateDraft(c.Request.Context(), workflowID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create draft"})
		return
	}

	// Invoke Spec Engine (async)
	threadID, err := h.orchestrationService.SpecEngineClient.InvokeAgent(c.Request.Context(), req.UserPrompt)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to invoke spec engine"})
		return
	}

	// Create proposal
	proposalID, err := h.orchestrationService.CreateProposal(c.Request.Context(), draftID, userID, threadID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to create proposal"})
		return
	}

	c.JSON(http.StatusOK, CreateRefinementResponse{
		ThreadID:   threadID,
		ProposalID: proposalID.String(),
	})
}

// Placeholder handlers for other endpoints
func (h *Handler) GetWorkflow(c *gin.Context) {
	c.JSON(http.StatusNotImplemented, gin.H{"error": "Not implemented"})
}

func (h *Handler) GetVersions(c *gin.Context) {
	c.JSON(http.StatusNotImplemented, gin.H{"error": "Not implemented"})
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
	c.JSON(http.StatusNotImplemented, gin.H{"error": "Not implemented"})
}

func (h *Handler) RejectProposal(c *gin.Context) {
	c.JSON(http.StatusNotImplemented, gin.H{"error": "Not implemented"})
}
