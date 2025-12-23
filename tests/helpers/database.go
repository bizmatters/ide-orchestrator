package helpers

import (
	"context"
	"fmt"
	"os"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
	"golang.org/x/crypto/bcrypt"
)

// GetTestDatabasePool creates a database connection pool for testing
func GetTestDatabasePool(ctx context.Context) (*pgxpool.Pool, error) {
	databaseURL := buildDatabaseURL()
	
	config, err := pgxpool.ParseConfig(databaseURL)
	if err != nil {
		return nil, fmt.Errorf("failed to parse database URL: %w", err)
	}
	
	pool, err := pgxpool.NewWithConfig(ctx, config)
	if err != nil {
		return nil, fmt.Errorf("failed to create connection pool: %w", err)
	}
	
	// Test the connection
	if err := pool.Ping(ctx); err != nil {
		pool.Close()
		return nil, fmt.Errorf("failed to ping database: %w", err)
	}
	
	return pool, nil
}

// buildDatabaseURL constructs the database URL from environment variables
func buildDatabaseURL() string {
	host := os.Getenv("POSTGRES_HOST")
	if host == "" {
		host = "ide-orchestrator-db-rw.intelligence-orchestrator.svc"
	}
	
	port := os.Getenv("POSTGRES_PORT")
	if port == "" {
		port = "5432"
	}
	
	user := os.Getenv("POSTGRES_USER")
	if user == "" {
		user = "postgres"
	}
	
	password := os.Getenv("POSTGRES_PASSWORD")
	if password == "" {
		password = "postgres"
	}
	
	dbname := os.Getenv("POSTGRES_DB")
	if dbname == "" {
		dbname = "ide_orchestrator"
	}
	
	return fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=prefer", 
		user, password, host, port, dbname)
}

// TestDatabase provides database utilities for testing
type TestDatabase struct {
	Pool *pgxpool.Pool
	ctx  context.Context
}

// NewTestDatabase creates a new test database instance
func NewTestDatabase(t *testing.T) *TestDatabase {
	ctx := context.Background()
	
	pool, err := GetTestDatabasePool(ctx)
	if err != nil {
		t.Fatalf("Failed to create test database: %v", err)
	}

	return &TestDatabase{
		Pool: pool,
		ctx:  ctx,
	}
}

// Close closes the database connection
func (db *TestDatabase) Close() {
	if db.Pool != nil {
		db.Pool.Close()
	}
}

// BeginTransaction starts a new transaction for test isolation
// Tests should use transaction rollback instead of deleting data
func (db *TestDatabase) BeginTransaction(t *testing.T) (context.Context, func()) {
	tx, err := db.Pool.Begin(db.ctx)
	if err != nil {
		t.Fatalf("Failed to begin transaction: %v", err)
	}

	// Create a context with the transaction
	txCtx := context.WithValue(db.ctx, "tx", tx)

	// Return rollback function
	rollback := func() {
		if err := tx.Rollback(db.ctx); err != nil {
			t.Logf("Warning: Failed to rollback transaction: %v", err)
		}
	}

	return txCtx, rollback
}

// CleanupTables removes test data from all tables (DEPRECATED - use transactions instead)
// This method violates CI testing patterns and should only be used for migration
func (db *TestDatabase) CleanupTables(t *testing.T) {
	t.Log("WARNING: CleanupTables is deprecated. Use transaction-based isolation instead.")
	tables := []string{
		"proposals",
		"drafts", 
		"workflow_versions",
		"workflows",
		"users",
	}

	for _, table := range tables {
		_, err := db.Pool.Exec(db.ctx, fmt.Sprintf("DELETE FROM %s", table))
		if err != nil {
			t.Logf("Warning: Failed to cleanup table %s: %v", table, err)
		}
	}
}

// CreateTestUser creates a test user and returns the user ID
// Uses the provided context which may contain a transaction
func (db *TestDatabase) CreateTestUser(t *testing.T, email, password string) string {
	return db.CreateTestUserWithContext(t, db.ctx, email, password)
}

// CreateTestUserWithContext creates a test user with a specific context (for transactions)
func (db *TestDatabase) CreateTestUserWithContext(t *testing.T, ctx context.Context, email, password string) string {
	var userID string
	
	// Use the pool directly - pgx handles transactions automatically when they're in the context
	err := db.Pool.QueryRow(ctx, `
		INSERT INTO users (name, email, hashed_password, created_at, updated_at) 
		VALUES ($1, $2, $3, NOW(), NOW()) 
		RETURNING id
	`, "Test User", email, password).Scan(&userID)
	
	if err != nil {
		t.Fatalf("Failed to create test user: %v", err)
	}
	
	return userID
}

// CreateTestWorkflow creates a test workflow and returns the workflow ID
func (db *TestDatabase) CreateTestWorkflow(t *testing.T, userID, name, description string) string {
	var workflowID string
	err := db.Pool.QueryRow(db.ctx, `
		INSERT INTO workflows (created_by_user_id, name, description, created_at, updated_at) 
		VALUES ($1, $2, $3, NOW(), NOW()) 
		RETURNING id
	`, userID, name, description).Scan(&workflowID)
	
	if err != nil {
		t.Fatalf("Failed to create test workflow: %v", err)
	}
	
	return workflowID
}

// CreateTestDraft creates a test draft and returns the draft ID
func (db *TestDatabase) CreateTestDraft(t *testing.T, workflowID, specification string) string {
	var draftID string
	err := db.Pool.QueryRow(db.ctx, `
		INSERT INTO drafts (workflow_id, specification, created_at, updated_at) 
		VALUES ($1, $2, NOW(), NOW()) 
		RETURNING id
	`, workflowID, specification).Scan(&draftID)
	
	if err != nil {
		t.Fatalf("Failed to create test draft: %v", err)
	}
	
	return draftID
}

// GetWorkflowCount returns the number of workflows in the database
func (db *TestDatabase) GetWorkflowCount(t *testing.T) int {
	var count int
	err := db.Pool.QueryRow(db.ctx, "SELECT COUNT(*) FROM workflows").Scan(&count)
	if err != nil {
		t.Fatalf("Failed to get workflow count: %v", err)
	}
	return count
}

// GetUserCount returns the number of users in the database
func (db *TestDatabase) GetUserCount(t *testing.T) int {
	var count int
	err := db.Pool.QueryRow(db.ctx, "SELECT COUNT(*) FROM users").Scan(&count)
	if err != nil {
		t.Fatalf("Failed to get user count: %v", err)
	}
	return count
}

// HashPassword hashes a password using bcrypt for testing
func (db *TestDatabase) HashPassword(password string) (string, error) {
	hashedBytes, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return "", fmt.Errorf("failed to hash password: %w", err)
	}
	return string(hashedBytes), nil
}

// WaitForDatabase waits for database to be ready
func WaitForDatabase(ctx context.Context, maxAttempts int) error {
	for i := 0; i < maxAttempts; i++ {
		pool, err := GetTestDatabasePool(ctx)
		if err == nil {
			pool.Close()
			return nil
		}
		
		if i < maxAttempts-1 {
			// Wait before retry (exponential backoff could be added here)
			select {
			case <-ctx.Done():
				return ctx.Err()
			default:
				// Simple delay - could be improved with exponential backoff
			}
		}
	}
	
	return fmt.Errorf("database not ready after %d attempts", maxAttempts)
}