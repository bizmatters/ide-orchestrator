package main

import (
	"context"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/auth"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/gateway"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/orchestration"
	swaggerFiles "github.com/swaggo/files"
	ginSwagger "github.com/swaggo/gin-swagger"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/stdout/stdouttrace"
	"go.opentelemetry.io/otel/sdk/trace"

	_ "github.com/bizmatters/agent-builder/ide-orchestrator/docs" // swagger docs
)

// @title IDE Orchestrator API
// @version 1.0
// @description AI-powered workflow builder API for multi-agent orchestration
// @description
// @description This API enables creation, refinement, and deployment of LangGraph-based AI workflows.
// @description Features include: workflow versioning, draft refinements, AI-powered proposals, and production deployment.

// @contact.name API Support
// @contact.email support@bizmatters.dev

// @license.name MIT
// @license.url https://opensource.org/licenses/MIT

// @host localhost:8080
// @BasePath /api

// @securityDefinitions.apikey BearerAuth
// @in header
// @name Authorization
// @description Type "Bearer" followed by a space and the JWT token.

func main() {
	// Initialize OpenTelemetry
	if err := initTracer(); err != nil {
		log.Fatalf("Failed to initialize tracer: %v", err)
	}

	// Get database connection string from environment
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable"
	}

	// Connect to PostgreSQL with retry logic
	log.Println("Connecting to PostgreSQL database...")
	var pool *pgxpool.Pool
	var err error

	// Add a retry loop for the initial connection
	for i := 0; i < 10; i++ {
		pool, err = pgxpool.New(context.Background(), dbURL)
		if err == nil {
			err = pool.Ping(context.Background())
			if err == nil {
				break
			}
		}
		log.Printf("Waiting for database... (attempt %d/10): %v", i+1, err)
		time.Sleep(3 * time.Second)
	}

	if err != nil {
		log.Fatalf("Failed to connect to database after retries: %v", err)
	}

	defer pool.Close()
	log.Println("Connected to PostgreSQL database")

	// Initialize orchestration layer
	specEngineClient := orchestration.NewSpecEngineClient(pool)
	deepAgentsClient := orchestration.NewDeepAgentsRuntimeClient()
	orchestrationService := orchestration.NewService(pool, specEngineClient)

	// Initialize JWT manager
	jwtManager, err := auth.NewJWTManager()
	if err != nil {
		log.Fatalf("Failed to initialize JWT manager: %v", err)
	}

	// Get Spec Engine URL for WebSocket proxy
	specEngineURL := os.Getenv("SPEC_ENGINE_URL")
	if specEngineURL == "" {
		specEngineURL = "http://spec-engine-service:8001"
	}

	// Initialize gateway layer
	gatewayHandler := gateway.NewHandler(orchestrationService, jwtManager, pool)
	// wsProxy := gateway.NewWebSocketProxy(pool, specEngineURL)  // TODO: Use this when needed
	deepAgentsWSProxy := gateway.NewDeepAgentsWebSocketProxy(pool, deepAgentsClient, jwtManager)

	// Setup Gin router
	router := gin.Default()

	// Add structured JSON logging middleware
	router.Use(structuredLoggingMiddleware())

	// Health checks MUST be at the root for the WebService standard
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})

	router.GET("/ready", func(c *gin.Context) {
		// Check database connectivity for readiness
		if err := pool.Ping(context.Background()); err != nil {
			c.JSON(http.StatusServiceUnavailable, gin.H{
				"status": "not ready", 
				"error": "database connection failed",
			})
			return
		}
		c.JSON(http.StatusOK, gin.H{"status": "ready"})
	})

	// API routes
	api := router.Group("/api")

	// Public routes (no authentication required)
	api.POST("/auth/login", gatewayHandler.Login)

	// Health check (public) - keep for backward compatibility
	api.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "healthy"})
	})

	// Swagger documentation (public)
	router.GET("/swagger/*any", ginSwagger.WrapHandler(swaggerFiles.Handler))

	// Protected routes (require JWT authentication)
	protected := api.Group("")
	protected.Use(auth.RequireAuth(jwtManager))

	// Workflow routes
	protected.POST("/workflows", gatewayHandler.CreateWorkflow)
	protected.GET("/workflows/:id", gatewayHandler.GetWorkflow)
	protected.GET("/workflows/:id/versions", gatewayHandler.GetVersions)
	protected.GET("/workflows/:id/versions/:versionNumber", gatewayHandler.GetVersion)
	protected.POST("/workflows/:id/versions", gatewayHandler.PublishDraft)
	protected.DELETE("/workflows/:id/draft", gatewayHandler.DiscardDraft)
	protected.POST("/workflows/:id/deploy", gatewayHandler.DeployVersion)

	// Refinement routes
	protected.POST("/workflows/:id/refinements", gatewayHandler.CreateRefinement)
	protected.POST("/refinements/:proposalId/approve", gatewayHandler.ApproveProposal)
	protected.POST("/refinements/:proposalId/reject", gatewayHandler.RejectProposal)

	// Proposal routes
	protected.GET("/proposals/:id", gatewayHandler.GetProposal)
	protected.POST("/proposals/:id/approve", gatewayHandler.ApproveProposal)
	protected.POST("/proposals/:id/reject", gatewayHandler.RejectProposal)

	// WebSocket routes (authenticated)
	protected.GET("/ws/refinements/:thread_id", deepAgentsWSProxy.StreamRefinement)

	// HTTP server configuration
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}

	server := &http.Server{
		Addr:         fmt.Sprintf(":%s", port),
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 60 * time.Second, // Increased for synchronous Builder Agent calls
		IdleTimeout:  60 * time.Second,
	}

	// Start server in goroutine
	go func() {
		log.Printf("Starting IDE Orchestrator API server on port %s\n", port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// Wait for interrupt signal to gracefully shutdown
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Shutting down server...")

	// Graceful shutdown with timeout
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Shutdown HTTP server
	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exited")
}

// initTracer initializes OpenTelemetry tracing
func initTracer() error {
	exporter, err := stdouttrace.New(stdouttrace.WithPrettyPrint())
	if err != nil {
		return fmt.Errorf("failed to create stdout exporter: %w", err)
	}

	tp := trace.NewTracerProvider(
		trace.WithBatcher(exporter),
	)

	otel.SetTracerProvider(tp)

	return nil
}

// structuredLoggingMiddleware provides structured JSON logging for all requests
func structuredLoggingMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		start := time.Now()

		// Process request
		c.Next()

		// Calculate latency
		latency := time.Since(start)

		// Get user ID from context if available
		userID, _ := c.Get("user_id")

		// Build log entry
		logEntry := map[string]interface{}{
			"timestamp":   time.Now().UTC().Format(time.RFC3339),
			"method":      c.Request.Method,
			"path":        c.Request.URL.Path,
			"status":      c.Writer.Status(),
			"latency_ms":  latency.Milliseconds(),
			"client_ip":   c.ClientIP(),
			"user_agent":  c.Request.UserAgent(),
		}

		// Add user ID if authenticated
		if userID != nil {
			logEntry["user_id"] = userID
		}

		// Add error if present
		if len(c.Errors) > 0 {
			logEntry["errors"] = c.Errors.String()
		}

		// Output as JSON
		logJSON, _ := json.Marshal(logEntry)
		log.Println(string(logJSON))
	}
}
