package models

import (
	"time"
)

// AgentEvent represents an event in the event store
type AgentEvent struct {
	ID          string                 `json:"id" db:"id"`
	AggregateID string                 `json:"aggregate_id" db:"aggregate_id"`
	EventType   string                 `json:"event_type" db:"event_type"`
	EventData   map[string]interface{} `json:"event_data" db:"event_data"`
	Version     int                    `json:"version" db:"version"`
	Timestamp   time.Time              `json:"timestamp" db:"timestamp"`
}

// OutboxEventStatus represents the status of an outbox event
type OutboxEventStatus string

const (
	OutboxEventStatusPending   OutboxEventStatus = "PENDING"
	OutboxEventStatusPublished OutboxEventStatus = "PUBLISHED"
	OutboxEventStatusFailed    OutboxEventStatus = "FAILED"
)

// OutboxEvent represents an event in the transactional outbox
type OutboxEvent struct {
	ID          string                 `json:"id" db:"id"`
	EventType   string                 `json:"event_type" db:"event_type"`
	Payload     map[string]interface{} `json:"payload" db:"payload"`
	Status      OutboxEventStatus      `json:"status" db:"status"`
	CreatedAt   time.Time              `json:"created_at" db:"created_at"`
	PublishedAt *time.Time             `json:"published_at,omitempty" db:"published_at"`
	RetryCount  int                    `json:"retry_count" db:"retry_count"`
	LastError   *string                `json:"last_error,omitempty" db:"last_error"`
}

// Event types
const (
	EventTypeAgentCreated  = "agent.created"
	EventTypeAgentDeployed = "agent.deployed"
	EventTypeAgentUpdated  = "agent.updated"
	EventTypeAgentDeleted  = "agent.deleted"
)
