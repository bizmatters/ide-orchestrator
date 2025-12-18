package auth

import (
	"context"
	"log"
	"net/http"
	"strings"

	"github.com/gin-gonic/gin"
	"go.opentelemetry.io/otel"
	"go.opentelemetry.io/otel/attribute"
)

var middlewareTracer = otel.Tracer("auth-middleware")

// ContextKey is a custom type for context keys to avoid collisions
type ContextKey string

const (
	// UserIDKey is the context key for user ID
	UserIDKey ContextKey = "user_id"
	// UsernameKey is the context key for username
	UsernameKey ContextKey = "username"
	// UserRolesKey is the context key for user roles
	UserRolesKey ContextKey = "user_roles"
	// ClaimsKey is the context key for full JWT claims
	ClaimsKey ContextKey = "claims"
)

// Middleware provides HTTP middleware for JWT authentication
type Middleware struct {
	jwtManager *JWTManager
}

// NewMiddleware creates a new authentication middleware
func NewMiddleware(jwtManager *JWTManager) *Middleware {
	return &Middleware{
		jwtManager: jwtManager,
	}
}

// RequireAuth is middleware that validates JWT tokens on protected endpoints
// It extracts the token from the Authorization header, validates it, and attaches user info to context
func (m *Middleware) RequireAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx, span := middlewareTracer.Start(r.Context(), "auth.require_auth")
		defer span.End()

		// Extract token from Authorization header
		token := extractBearerToken(r)
		if token == "" {
			span.SetAttributes(attribute.Bool("auth.token_present", false))
			respondUnauthorized(w, "Missing or invalid authorization header")
			return
		}

		span.SetAttributes(attribute.Bool("auth.token_present", true))

		// Validate token
		claims, err := m.jwtManager.ValidateToken(ctx, token)
		if err != nil {
			span.RecordError(err)
			span.SetAttributes(attribute.Bool("auth.token_valid", false))
			log.Printf(`{"level":"warn","message":"Invalid token","error":"%v"}`, err)
			respondUnauthorized(w, "Invalid or expired token")
			return
		}

		span.SetAttributes(
			attribute.Bool("auth.token_valid", true),
			attribute.String("user.id", claims.UserID),
			attribute.String("user.username", claims.Username),
		)

		// Note: Token revocation checking removed (was Vault-based)

		// Attach user context to request
		ctx = context.WithValue(ctx, UserIDKey, claims.UserID)
		ctx = context.WithValue(ctx, UsernameKey, claims.Username)
		ctx = context.WithValue(ctx, UserRolesKey, claims.Roles)
		ctx = context.WithValue(ctx, ClaimsKey, claims)

		// Log successful authentication with structured logging
		log.Printf(`{"level":"info","message":"User authenticated","user_id":"%s","username":"%s","path":"%s","method":"%s"}`,
			claims.UserID, claims.Username, r.URL.Path, r.Method)

		// Call next handler with enriched context
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// OptionalAuth is middleware that validates JWT tokens if present but doesn't require them
// Useful for endpoints that behave differently for authenticated vs anonymous users
func (m *Middleware) OptionalAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		ctx, span := middlewareTracer.Start(r.Context(), "auth.optional_auth")
		defer span.End()

		// Extract token from Authorization header
		token := extractBearerToken(r)
		if token == "" {
			span.SetAttributes(attribute.Bool("auth.authenticated", false))
			// No token present - continue without authentication
			next.ServeHTTP(w, r.WithContext(ctx))
			return
		}

		// Validate token
		claims, err := m.jwtManager.ValidateToken(ctx, token)
		if err != nil {
			span.RecordError(err)
			span.SetAttributes(attribute.Bool("auth.authenticated", false))
			log.Printf(`{"level":"warn","message":"Invalid optional token","error":"%v"}`, err)
			// Invalid token - continue without authentication
			next.ServeHTTP(w, r.WithContext(ctx))
			return
		}

		span.SetAttributes(
			attribute.Bool("auth.authenticated", true),
			attribute.String("user.id", claims.UserID),
		)

		// Note: Token revocation checking removed (was Vault-based)

		// Attach user context to request
		ctx = context.WithValue(ctx, UserIDKey, claims.UserID)
		ctx = context.WithValue(ctx, UsernameKey, claims.Username)
		ctx = context.WithValue(ctx, UserRolesKey, claims.Roles)
		ctx = context.WithValue(ctx, ClaimsKey, claims)

		// Call next handler with enriched context
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// RequireRole is middleware that checks if authenticated user has required role
// Must be used after RequireAuth middleware
func (m *Middleware) RequireRole(role string) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
			_, span := middlewareTracer.Start(r.Context(), "auth.require_role")
			defer span.End()

			span.SetAttributes(attribute.String("required.role", role))

			// Get user roles from context
			rolesValue := r.Context().Value(UserRolesKey)
			if rolesValue == nil {
				span.SetAttributes(attribute.Bool("auth.role_authorized", false))
				respondForbidden(w, "User roles not found in context")
				return
			}

			roles, ok := rolesValue.([]string)
			if !ok {
				span.SetAttributes(attribute.Bool("auth.role_authorized", false))
				respondForbidden(w, "Invalid user roles in context")
				return
			}

			// Check if user has required role
			hasRole := false
			for _, userRole := range roles {
				if userRole == role {
					hasRole = true
					break
				}
			}

			if !hasRole {
				userID := r.Context().Value(UserIDKey)
				span.SetAttributes(attribute.Bool("auth.role_authorized", false))
				log.Printf(`{"level":"warn","message":"Insufficient permissions","user_id":"%v","required_role":"%s"}`,
					userID, role)
				respondForbidden(w, "Insufficient permissions")
				return
			}

			span.SetAttributes(attribute.Bool("auth.role_authorized", true))

			// Call next handler
			next.ServeHTTP(w, r)
		})
	}
}

// Helper functions

func extractBearerToken(r *http.Request) string {
	authHeader := r.Header.Get("Authorization")
	if authHeader == "" {
		return ""
	}

	// Expected format: "Bearer <token>"
	const prefix = "Bearer "
	if len(authHeader) < len(prefix) {
		return ""
	}

	if !strings.HasPrefix(authHeader, prefix) {
		return ""
	}

	return strings.TrimSpace(authHeader[len(prefix):])
}

func respondUnauthorized(w http.ResponseWriter, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusUnauthorized)
	w.Write([]byte(`{"error":"` + message + `","code":401}`))
}

func respondForbidden(w http.ResponseWriter, message string) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(http.StatusForbidden)
	w.Write([]byte(`{"error":"` + message + `","code":403}`))
}

// Gin-compatible middleware functions

// RequireAuth is a Gin middleware that validates JWT tokens
func RequireAuth(jwtManager *JWTManager) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx, span := middlewareTracer.Start(c.Request.Context(), "auth.require_auth_gin")
		defer span.End()

		// Extract token from Authorization header
		token := c.GetHeader("Authorization")
		if token == "" {
			span.SetAttributes(attribute.Bool("auth.token_present", false))
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Missing authorization header"})
			c.Abort()
			return
		}

		// Remove "Bearer " prefix
		const prefix = "Bearer "
		if len(token) < len(prefix) || !strings.HasPrefix(token, prefix) {
			span.SetAttributes(attribute.Bool("auth.token_present", false))
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid authorization header format"})
			c.Abort()
			return
		}

		token = strings.TrimSpace(token[len(prefix):])
		span.SetAttributes(attribute.Bool("auth.token_present", true))

		// Validate token
		claims, err := jwtManager.ValidateToken(ctx, token)
		if err != nil {
			span.RecordError(err)
			span.SetAttributes(attribute.Bool("auth.token_valid", false))
			log.Printf(`{"level":"warn","message":"Invalid token","error":"%v"}`, err)
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid or expired token"})
			c.Abort()
			return
		}

		span.SetAttributes(
			attribute.Bool("auth.token_valid", true),
			attribute.String("user.id", claims.UserID),
			attribute.String("user.username", claims.Username),
		)

		// Attach user context to Gin context
		c.Set("user_id", claims.UserID)
		c.Set("username", claims.Username)
		c.Set("user_roles", claims.Roles)
		c.Set("claims", claims)

		// Log successful authentication
		log.Printf(`{"level":"info","message":"User authenticated","user_id":"%s","username":"%s","path":"%s","method":"%s"}`,
			claims.UserID, claims.Username, c.Request.URL.Path, c.Request.Method)

		c.Next()
	}
}

// OptionalAuth is a Gin middleware that validates JWT tokens if present
func OptionalAuth(jwtManager *JWTManager) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx, span := middlewareTracer.Start(c.Request.Context(), "auth.optional_auth_gin")
		defer span.End()

		// Extract token from Authorization header
		token := c.GetHeader("Authorization")
		if token == "" {
			span.SetAttributes(attribute.Bool("auth.authenticated", false))
			c.Next()
			return
		}

		// Remove "Bearer " prefix
		const prefix = "Bearer "
		if len(token) < len(prefix) || !strings.HasPrefix(token, prefix) {
			span.SetAttributes(attribute.Bool("auth.authenticated", false))
			c.Next()
			return
		}

		token = strings.TrimSpace(token[len(prefix):])

		// Validate token
		claims, err := jwtManager.ValidateToken(ctx, token)
		if err != nil {
			span.RecordError(err)
			span.SetAttributes(attribute.Bool("auth.authenticated", false))
			log.Printf(`{"level":"warn","message":"Invalid optional token","error":"%v"}`, err)
			c.Next()
			return
		}

		span.SetAttributes(
			attribute.Bool("auth.authenticated", true),
			attribute.String("user.id", claims.UserID),
		)

		// Attach user context to Gin context
		c.Set("user_id", claims.UserID)
		c.Set("username", claims.Username)
		c.Set("user_roles", claims.Roles)
		c.Set("claims", claims)

		c.Next()
	}
}

// RequireRole is a Gin middleware that checks if authenticated user has required role
func RequireRole(role string) gin.HandlerFunc {
	return func(c *gin.Context) {
		_, span := middlewareTracer.Start(c.Request.Context(), "auth.require_role_gin")
		defer span.End()

		span.SetAttributes(attribute.String("required.role", role))

		// Get user roles from Gin context
		rolesValue, exists := c.Get("user_roles")
		if !exists {
			span.SetAttributes(attribute.Bool("auth.role_authorized", false))
			c.JSON(http.StatusForbidden, gin.H{"error": "User roles not found"})
			c.Abort()
			return
		}

		roles, ok := rolesValue.([]string)
		if !ok {
			span.SetAttributes(attribute.Bool("auth.role_authorized", false))
			c.JSON(http.StatusForbidden, gin.H{"error": "Invalid user roles"})
			c.Abort()
			return
		}

		// Check if user has required role
		hasRole := false
		for _, userRole := range roles {
			if userRole == role {
				hasRole = true
				break
			}
		}

		if !hasRole {
			userID, _ := c.Get("user_id")
			span.SetAttributes(attribute.Bool("auth.role_authorized", false))
			log.Printf(`{"level":"warn","message":"Insufficient permissions","user_id":"%v","required_role":"%s"}`,
				userID, role)
			c.JSON(http.StatusForbidden, gin.H{"error": "Insufficient permissions"})
			c.Abort()
			return
		}

		span.SetAttributes(attribute.Bool("auth.role_authorized", true))
		c.Next()
	}
}
