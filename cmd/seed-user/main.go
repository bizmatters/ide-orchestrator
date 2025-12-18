package main

import (
	"context"
	"flag"
	"fmt"
	"log"
	"os"
	"regexp"
	"strings"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/exporters/stdout/stdouttrace"
	"go.opentelemetry.io/otel/sdk/trace"
	"golang.org/x/crypto/bcrypt"
)

const (
	// MinPasswordLength is the minimum password length requirement
	MinPasswordLength = 8
	// BcryptCost is the cost factor for bcrypt hashing (10 = ~100ms)
	BcryptCost = 10
)

var (
	emailRegex = regexp.MustCompile(`^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$`)
)

func main() {
	// Parse command-line flags
	name := flag.String("name", "", "Full name of the user (required)")
	email := flag.String("email", "", "Email address (required)")
	password := flag.String("password", "", "Password (required, min 8 chars)")
	flag.Parse()

	// Initialize OpenTelemetry for observability
	if err := initTracer(); err != nil {
		log.Fatalf("Failed to initialize tracer: %v", err)
	}

	// Validate inputs
	if err := validateInputs(*name, *email, *password); err != nil {
		log.Fatalf("Validation error: %v", err)
	}

	// Get database connection string from environment
	dbURL := os.Getenv("DATABASE_URL")
	if dbURL == "" {
		dbURL = "postgres://postgres:bizmatters-secure-password@localhost:5432/agent_builder?sslmode=disable"
		log.Printf("Using default database URL (set DATABASE_URL to override)")
	}

	// Connect to PostgreSQL
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dbURL)
	if err != nil {
		log.Fatalf("Failed to connect to database: %v", err)
	}
	defer pool.Close()

	// Test database connection
	if err := pool.Ping(ctx); err != nil {
		log.Fatalf("Failed to ping database: %v", err)
	}
	log.Println("Connected to PostgreSQL database")

	// Create user
	userID, err := createUser(ctx, pool, *name, *email, *password)
	if err != nil {
		log.Fatalf("Failed to create user: %v", err)
	}

	log.Printf("✓ Successfully created user")
	log.Printf("  ID: %s", userID)
	log.Printf("  Name: %s", *name)
	log.Printf("  Email: %s", *email)
}

// validateInputs validates user input according to security requirements
func validateInputs(name, email, password string) error {
	// Validate name
	if strings.TrimSpace(name) == "" {
		return fmt.Errorf("name is required and cannot be empty")
	}

	// Validate email format
	if !emailRegex.MatchString(email) {
		return fmt.Errorf("invalid email format: %s", email)
	}

	// Validate password strength
	if len(password) < MinPasswordLength {
		return fmt.Errorf("password must be at least %d characters long", MinPasswordLength)
	}

	// Check for password complexity (at least one letter and one number)
	hasLetter := regexp.MustCompile(`[a-zA-Z]`).MatchString(password)
	hasNumber := regexp.MustCompile(`[0-9]`).MatchString(password)

	if !hasLetter || !hasNumber {
		return fmt.Errorf("password must contain at least one letter and one number")
	}

	return nil
}

// createUser creates a new user with hashed password using pgx transaction
func createUser(ctx context.Context, pool *pgxpool.Pool, name, email, password string) (string, error) {
	tracer := otel.Tracer("seed-user")
	ctx, span := tracer.Start(ctx, "create_user")
	defer span.End()

	// Hash password using bcrypt
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(password), BcryptCost)
	if err != nil {
		return "", fmt.Errorf("failed to hash password: %w", err)
	}

	// Generate UUID for user
	userID := uuid.New().String()

	// Begin transaction for atomicity
	tx, err := pool.Begin(ctx)
	if err != nil {
		return "", fmt.Errorf("failed to begin transaction: %w", err)
	}
	defer tx.Rollback(ctx) // Rollback if not committed

	// Insert user with parameterized query (SQL injection protection)
	query := `
		INSERT INTO users (id, name, email, hashed_password)
		VALUES ($1, $2, $3, $4)
		RETURNING id
	`

	var returnedID string
	err = tx.QueryRow(ctx, query, userID, name, strings.ToLower(strings.TrimSpace(email)), string(hashedPassword)).Scan(&returnedID)
	if err != nil {
		// Check for unique constraint violation
		if strings.Contains(err.Error(), "duplicate key") || strings.Contains(err.Error(), "unique constraint") {
			return "", fmt.Errorf("user with email %s already exists", email)
		}
		return "", fmt.Errorf("failed to insert user: %w", err)
	}

	// Commit transaction
	if err := tx.Commit(ctx); err != nil {
		return "", fmt.Errorf("failed to commit transaction: %w", err)
	}

	log.Printf("User inserted successfully with ID: %s", returnedID)

	return returnedID, nil
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
