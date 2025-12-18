package auth

import (
	"context"
	"fmt"
	"os"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
	"go.opentelemetry.io/otel/trace"
)

var tracer = otel.Tracer("jwt-manager")

// JWTManager manages JWT token creation and validation
type JWTManager struct {
	signingKey string
	algorithm  string
	keyID      string
	tracer     trace.Tracer
}

// Claims represents JWT claims for agent-builder API
type Claims struct {
	UserID   string   `json:"user_id"`
	Username string   `json:"username"`
	Roles    []string `json:"roles"`
	jwt.RegisteredClaims
}

// NewJWTManager creates a new JWT manager using environment variables
func NewJWTManager() (*JWTManager, error) {
	// Load JWT signing key from environment variable
	signingKey := os.Getenv("JWT_SECRET")
	if signingKey == "" {
		return nil, fmt.Errorf("JWT_SECRET environment variable is required")
	}

	return &JWTManager{
		signingKey: signingKey,
		algorithm:  "HS256", // Default to HMAC-SHA256
		keyID:      "default",
		tracer:     tracer,
	}, nil
}

// GenerateToken generates a new JWT token
func (jm *JWTManager) GenerateToken(ctx context.Context, userID, username string, roles []string, duration time.Duration) (string, error) {
	ctx, span := jm.tracer.Start(ctx, "jwt.generate_token")
	defer span.End()

	span.SetAttributes(
		attribute.String("user.id", userID),
		attribute.String("user.username", username),
	)

	now := time.Now()
	claims := &Claims{
		UserID:   userID,
		Username: username,
		Roles:    roles,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(now.Add(duration)),
			IssuedAt:  jwt.NewNumericDate(now),
			NotBefore: jwt.NewNumericDate(now),
			Issuer:    "agent-ide-orchestrator",
			Subject:   userID,
			ID:        fmt.Sprintf("jwt-%d", now.Unix()), // JTI for revocation
		},
	}

	token := jwt.NewWithClaims(jwt.GetSigningMethod(jm.algorithm), claims)

	// Set key ID header for key rotation support
	token.Header["kid"] = jm.keyID

	// Sign token with signing key
	tokenString, err := token.SignedString([]byte(jm.signingKey))
	if err != nil {
		return "", fmt.Errorf("failed to sign token: %w", err)
	}

	span.SetAttributes(
		attribute.String("jwt.id", claims.ID),
		attribute.String("jwt.expires_at", claims.ExpiresAt.String()),
	)

	return tokenString, nil
}

// ValidateToken validates a JWT token
func (jm *JWTManager) ValidateToken(ctx context.Context, tokenString string) (*Claims, error) {
	ctx, span := jm.tracer.Start(ctx, "jwt.validate_token")
	defer span.End()

	token, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (interface{}, error) {
		// Validate signing method
		if token.Method.Alg() != jm.algorithm {
			return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
		}

		// Validate key ID if present
		if kid, ok := token.Header["kid"].(string); ok {
			if kid != jm.keyID {
				// Key ID mismatch - might indicate key rotation
				// Key ID mismatch - might indicate key rotation
				span.SetAttributes(attribute.String("jwt.kid_mismatch", kid))
			}
		}

		return []byte(jm.signingKey), nil
	})

	if err != nil {
		span.RecordError(err)
		return nil, fmt.Errorf("failed to parse token: %w", err)
	}

	claims, ok := token.Claims.(*Claims)
	if !ok || !token.Valid {
		return nil, fmt.Errorf("invalid token claims")
	}

	span.SetAttributes(
		attribute.String("user.id", claims.UserID),
		attribute.String("jwt.id", claims.ID),
	)

	return claims, nil
}

// RefreshToken generates a new token from an existing valid token
func (jm *JWTManager) RefreshToken(ctx context.Context, tokenString string, duration time.Duration) (string, error) {
	ctx, span := jm.tracer.Start(ctx, "jwt.refresh_token")
	defer span.End()

	// Validate existing token
	claims, err := jm.ValidateToken(ctx, tokenString)
	if err != nil {
		return "", fmt.Errorf("cannot refresh invalid token: %w", err)
	}

	// Generate new token with same user info
	return jm.GenerateToken(ctx, claims.UserID, claims.Username, claims.Roles, duration)
}

// RotateSigningKey updates the signing key from environment variable
func (jm *JWTManager) RotateSigningKey(ctx context.Context) error {
	ctx, span := jm.tracer.Start(ctx, "jwt.rotate_signing_key")
	defer span.End()

	signingKey := os.Getenv("JWT_SECRET")
	if signingKey == "" {
		return fmt.Errorf("JWT_SECRET environment variable is required")
	}

	jm.signingKey = signingKey

	span.SetAttributes(
		attribute.String("jwt.algorithm", jm.algorithm),
		attribute.String("jwt.key_id", jm.keyID),
	)

	return nil
}
