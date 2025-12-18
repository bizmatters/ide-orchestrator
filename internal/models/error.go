package models

// ErrorResponse represents an API error response
type ErrorResponse struct {
	Error   string            `json:"error"`
	Code    string            `json:"code"`
	Details map[string]string `json:"details,omitempty"`
}

// Error codes
const (
	ErrCodeInvalidRequest     = "INVALID_REQUEST"
	ErrCodeNotFound           = "NOT_FOUND"
	ErrCodeAlreadyExists      = "ALREADY_EXISTS"
	ErrCodeValidationFailed   = "VALIDATION_FAILED"
	ErrCodeUnauthorized       = "UNAUTHORIZED"
	ErrCodeForbidden          = "FORBIDDEN"
	ErrCodeInternalError      = "INTERNAL_ERROR"
	ErrCodeAgentDeployed      = "AGENT_DEPLOYED"
	ErrCodeWebhookNotFound    = "WEBHOOK_NOT_FOUND"
	ErrCodeToolNotFound       = "TOOL_NOT_FOUND"
	ErrCodeTemplateNotFound   = "TEMPLATE_NOT_FOUND"
)
