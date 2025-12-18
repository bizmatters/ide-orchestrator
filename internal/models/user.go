package models

import (
	"time"
)

// User represents a user account in the system
type User struct {
	ID             string    `json:"id" db:"id"`
	Name           string    `json:"name" db:"name"`
	Email          string    `json:"email" db:"email"`
	HashedPassword string    `json:"-" db:"hashed_password"` // Never expose in JSON
	CreatedAt      time.Time `json:"created_at" db:"created_at"`
	UpdatedAt      time.Time `json:"updated_at" db:"updated_at"`
}

// LoginRequest represents authentication request payload
type LoginRequest struct {
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required"`
}

// LoginResponse represents authentication response with JWT token
type LoginResponse struct {
	Token     string    `json:"token"`
	ExpiresAt time.Time `json:"expires_at"`
	User      UserInfo  `json:"user"`
}

// UserInfo represents safe user information (without sensitive data)
type UserInfo struct {
	ID        string    `json:"id"`
	Name      string    `json:"name"`
	Email     string    `json:"email"`
	CreatedAt time.Time `json:"created_at"`
}

// ToUserInfo converts User to UserInfo (safe for API responses)
func (u *User) ToUserInfo() UserInfo {
	return UserInfo{
		ID:        u.ID,
		Name:      u.Name,
		Email:     u.Email,
		CreatedAt: u.CreatedAt,
	}
}
