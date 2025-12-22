package integration

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/assert"
	"github.com/stretchr/testify/require"

	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/auth"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/gateway"
	"github.com/bizmatters/agent-builder/ide-orchestrator/internal/orchestration"
	"github.com/bizmatters/agent-builder/ide-orchestrator/tests/helpers"
)

// TestAuthDatabaseIntegration tests critical auth validations that require database access
func TestAuthDatabaseIntegration(t *testing.T) {
	// Set required environment variable for JWT manager
	t.Setenv("JWT_SECRET", "test-secret-key-for-auth-db-integration-tests")

	// Setup test environment with real infrastructure
	testDB := helpers.NewTestDatabase(t)
	defer testDB.Close()

	// Use transaction-based isolation
	txCtx, rollback := testDB.BeginTransaction(t)
	defer rollback()

	// Initialize services
	specEngineClient := orchestration.NewSpecEngineClient(testDB.Pool)
	orchestrationService := orchestration.NewService(testDB.Pool, specEngineClient)
	
	jwtManager, err := auth.NewJWTManager()
	require.NoError(t, err)

	gatewayHandler := gateway.NewHandler(orchestrationService, jwtManager, testDB.Pool)

	// Setup Gin router
	gin.SetMode(gin.TestMode)
	router := gin.New()
	
	api := router.Group("/api")
	api.POST("/auth/login", gatewayHandler.Login)

	protected := api.Group("")
	protected.Use(auth.RequireAuth(jwtManager))
	protected.POST("/workflows", gatewayHandler.CreateWorkflow)
	protected.GET("/protected", func(c *gin.Context) {
		userID, _ := c.Get("user_id")
		username, _ := c.Get("username")
		c.JSON(http.StatusOK, gin.H{
			"user_id": userID,
			"email":   username, // The middleware sets username, but we call it email in response for consistency
			"message": "Access granted",
		})
	})

	t.Run("Protected Endpoint Access with Database User", func(t *testing.T) {
		// Create real user in database
		userEmail := fmt.Sprintf("protected-auth-db-%d@example.com", time.Now().UnixNano())
		userID := testDB.CreateTestUserWithContext(t, txCtx, userEmail, "hashed-password")
		
		// Generate token for real user
		token, err := jwtManager.GenerateToken(context.Background(), userID, userEmail, []string{}, 24*time.Hour)
		require.NoError(t, err)

		// Test access with valid token
		req := httptest.NewRequest(http.MethodGet, "/api/protected", nil)
		req.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var response map[string]interface{}
		err = json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.Equal(t, userID, response["user_id"])
		assert.Equal(t, userEmail, response["email"])
		assert.Equal(t, "Access granted", response["message"])
	})

	t.Run("Token Claims Extraction with Workflow Creation", func(t *testing.T) {
		// Create real user in database
		userEmail := fmt.Sprintf("claims-auth-db-%d@example.com", time.Now().UnixNano())
		userID := testDB.CreateTestUserWithContext(t, txCtx, userEmail, "hashed-password")
		
		// Generate token for real user
		token, err := jwtManager.GenerateToken(context.Background(), userID, userEmail, []string{}, 24*time.Hour)
		require.NoError(t, err)

		// Create workflow to test claims extraction in middleware
		workflowReq := map[string]interface{}{
			"name":        "Claims Test Workflow",
			"description": "Testing claims extraction with database user",
		}
		workflowBody, _ := json.Marshal(workflowReq)

		req := httptest.NewRequest(http.MethodPost, "/api/workflows", bytes.NewBuffer(workflowBody))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusCreated, w.Code)

		var response map[string]interface{}
		err = json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		// Verify the workflow was created with correct user context
		assert.NotEmpty(t, response["id"])
		assert.Equal(t, "Claims Test Workflow", response["name"])
		
		// Verify the workflow is associated with the correct user in database
		workflowID := response["id"].(string)
		var dbUserID string
		err = testDB.Pool.QueryRow(txCtx, 
			"SELECT created_by_user_id FROM workflows WHERE id = $1", 
			workflowID).Scan(&dbUserID)
		require.NoError(t, err)
		assert.Equal(t, userID, dbUserID)
	})

	t.Run("Multiple Concurrent Requests with Database User", func(t *testing.T) {
		// Create real user in database
		userEmail := fmt.Sprintf("concurrent-auth-db-%d@example.com", time.Now().UnixNano())
		userID := testDB.CreateTestUserWithContext(t, txCtx, userEmail, "hashed-password")
		
		// Generate token for real user
		token, err := jwtManager.GenerateToken(context.Background(), userID, userEmail, []string{}, 24*time.Hour)
		require.NoError(t, err)

		const numRequests = 10
		results := make(chan int, numRequests)
		userIDs := make(chan string, numRequests)

		// Make multiple concurrent requests with the same token
		for i := 0; i < numRequests; i++ {
			go func() {
				req := httptest.NewRequest(http.MethodGet, "/api/protected", nil)
				req.Header.Set("Authorization", "Bearer "+token)
				w := httptest.NewRecorder()
				router.ServeHTTP(w, req)
				
				results <- w.Code
				
				if w.Code == http.StatusOK {
					var response map[string]interface{}
					json.Unmarshal(w.Body.Bytes(), &response)
					if uid, ok := response["user_id"].(string); ok {
						userIDs <- uid
					}
				}
			}()
		}

		// Collect results - all should succeed with same user ID
		for i := 0; i < numRequests; i++ {
			select {
			case statusCode := <-results:
				assert.Equal(t, http.StatusOK, statusCode)
			case <-time.After(5 * time.Second):
				t.Fatal("Timeout waiting for concurrent requests")
			}
		}

		// Verify all requests returned the same user ID
		for i := 0; i < numRequests; i++ {
			select {
			case returnedUserID := <-userIDs:
				assert.Equal(t, userID, returnedUserID)
			case <-time.After(1 * time.Second):
				// Some requests might not have returned user_id, that's ok
				break
			}
		}
	})

	t.Run("Token Reuse with Database User", func(t *testing.T) {
		// Create real user in database
		userEmail := fmt.Sprintf("reuse-auth-db-%d@example.com", time.Now().UnixNano())
		userID := testDB.CreateTestUserWithContext(t, txCtx, userEmail, "hashed-password")
		
		// Generate token for real user
		token, err := jwtManager.GenerateToken(context.Background(), userID, userEmail, []string{}, 24*time.Hour)
		require.NoError(t, err)

		// Use the same token multiple times - should work (JWT is stateless)
		for i := 0; i < 5; i++ {
			req := httptest.NewRequest(http.MethodGet, "/api/protected", nil)
			req.Header.Set("Authorization", "Bearer "+token)
			w := httptest.NewRecorder()
			router.ServeHTTP(w, req)

			assert.Equal(t, http.StatusOK, w.Code)

			var response map[string]interface{}
			err = json.Unmarshal(w.Body.Bytes(), &response)
			require.NoError(t, err)

			assert.Equal(t, userID, response["user_id"])
			assert.Equal(t, userEmail, response["email"])
		}
	})

	t.Run("Expired Token Handling", func(t *testing.T) {
		// Create real user in database
		userEmail := fmt.Sprintf("expired-auth-db-%d@example.com", time.Now().UnixNano())
		userID := testDB.CreateTestUserWithContext(t, txCtx, userEmail, "hashed-password")
		
		// Generate token with very short expiration (1 millisecond)
		token, err := jwtManager.GenerateToken(context.Background(), userID, userEmail, []string{}, 1*time.Millisecond)
		require.NoError(t, err)

		// Wait for token to expire
		time.Sleep(10 * time.Millisecond)

		// Try to use expired token
		req := httptest.NewRequest(http.MethodGet, "/api/protected", nil)
		req.Header.Set("Authorization", "Bearer "+token)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		// Should be rejected due to expiration
		assert.Equal(t, http.StatusUnauthorized, w.Code)

		var response map[string]interface{}
		err = json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		// Should contain expiration-related error
		errorMsg := response["error"].(string)
		assert.Contains(t, errorMsg, "token")
	})

	t.Run("User Access Control - Own Resources Only", func(t *testing.T) {
		// Create two different users
		userEmail1 := fmt.Sprintf("user1-auth-db-%d@example.com", time.Now().UnixNano())
		userID1 := testDB.CreateTestUserWithContext(t, txCtx, userEmail1, "hashed-password")
		
		userEmail2 := fmt.Sprintf("user2-auth-db-%d@example.com", time.Now().UnixNano())
		userID2 := testDB.CreateTestUserWithContext(t, txCtx, userEmail2, "hashed-password")

		// Generate tokens for both users
		token1, err := jwtManager.GenerateToken(context.Background(), userID1, userEmail1, []string{}, 24*time.Hour)
		require.NoError(t, err)
		
		token2, err := jwtManager.GenerateToken(context.Background(), userID2, userEmail2, []string{}, 24*time.Hour)
		require.NoError(t, err)

		// User 1 creates a workflow
		workflowReq := map[string]interface{}{
			"name":        "User 1 Workflow",
			"description": "Testing user access control",
		}
		workflowBody, _ := json.Marshal(workflowReq)

		req := httptest.NewRequest(http.MethodPost, "/api/workflows", bytes.NewBuffer(workflowBody))
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("Authorization", "Bearer "+token1)
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusCreated, w.Code)

		var response map[string]interface{}
		err = json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)
		workflowID := response["id"].(string)

		// User 1 can access their own workflow
		req = httptest.NewRequest(http.MethodGet, "/api/workflows/"+workflowID, nil)
		req.Header.Set("Authorization", "Bearer "+token1)
		w = httptest.NewRecorder()
		router.ServeHTTP(w, req)
		assert.Equal(t, http.StatusOK, w.Code)

		// User 2 cannot access User 1's workflow (should get 403 Forbidden)
		req = httptest.NewRequest(http.MethodGet, "/api/workflows/"+workflowID, nil)
		req.Header.Set("Authorization", "Bearer "+token2)
		w = httptest.NewRecorder()
		router.ServeHTTP(w, req)
		assert.Equal(t, http.StatusForbidden, w.Code)
	})

	t.Run("Login Integration with Database", func(t *testing.T) {
		// Create real user in database with known password
		userEmail := fmt.Sprintf("login-auth-db-%d@example.com", time.Now().UnixNano())
		testPassword := "test-password-123"
		
		// Hash the password properly for storage
		hashedPassword, err := testDB.HashPassword(testPassword)
		require.NoError(t, err)
		
		userID := testDB.CreateTestUserWithContext(t, txCtx, userEmail, hashedPassword)

		// Test successful login
		loginReq := map[string]interface{}{
			"email":    userEmail,
			"password": testPassword,
		}
		loginBody, _ := json.Marshal(loginReq)

		req := httptest.NewRequest(http.MethodPost, "/api/auth/login", bytes.NewBuffer(loginBody))
		req.Header.Set("Content-Type", "application/json")
		w := httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		var response map[string]interface{}
		err = json.Unmarshal(w.Body.Bytes(), &response)
		require.NoError(t, err)

		assert.NotEmpty(t, response["token"])
		assert.Equal(t, userID, response["user_id"])

		// Test the returned token works
		token := response["token"].(string)
		req = httptest.NewRequest(http.MethodGet, "/api/protected", nil)
		req.Header.Set("Authorization", "Bearer "+token)
		w = httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusOK, w.Code)

		// Test failed login with wrong password
		loginReq["password"] = "wrong-password"
		loginBody, _ = json.Marshal(loginReq)

		req = httptest.NewRequest(http.MethodPost, "/api/auth/login", bytes.NewBuffer(loginBody))
		req.Header.Set("Content-Type", "application/json")
		w = httptest.NewRecorder()
		router.ServeHTTP(w, req)

		assert.Equal(t, http.StatusUnauthorized, w.Code)
	})
}