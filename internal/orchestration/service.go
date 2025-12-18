package orchestration

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Service handles workflow orchestration logic
type Service struct {
	pool             *pgxpool.Pool
	SpecEngineClient *SpecEngineClient
}

// NewService creates a new orchestration service
func NewService(pool *pgxpool.Pool, specEngineClient *SpecEngineClient) *Service {
	return &Service{
		pool:             pool,
		SpecEngineClient: specEngineClient,
	}
}

// CreateWorkflow creates a new workflow in the database
func (s *Service) CreateWorkflow(ctx context.Context, name, description string, userID uuid.UUID) (uuid.UUID, error) {
	var workflowID uuid.UUID

	err := s.pool.QueryRow(ctx,
		`INSERT INTO workflows (name, description, created_by_user_id)
		 VALUES ($1, $2, $3)
		 RETURNING id`,
		name, description, userID,
	).Scan(&workflowID)

	if err != nil {
		return uuid.Nil, fmt.Errorf("failed to create workflow: %w", err)
	}

	return workflowID, nil
}

// GetOrCreateDraft gets existing draft or creates new one for workflow
func (s *Service) GetOrCreateDraft(ctx context.Context, workflowID uuid.UUID, userID uuid.UUID) (uuid.UUID, error) {
	var draftID uuid.UUID

	// Try to get existing draft
	err := s.pool.QueryRow(ctx,
		`SELECT id FROM drafts WHERE workflow_id = $1`,
		workflowID,
	).Scan(&draftID)

	if err == nil {
		return draftID, nil
	}

	// Get workflow name for draft
	var workflowName string
	err = s.pool.QueryRow(ctx,
		`SELECT name FROM workflows WHERE id = $1`,
		workflowID,
	).Scan(&workflowName)

	if err != nil {
		return uuid.Nil, fmt.Errorf("failed to get workflow name: %w", err)
	}

	// Create new draft with workflow name + " (Draft)"
	draftName := workflowName + " (Draft)"
	err = s.pool.QueryRow(ctx,
		`INSERT INTO drafts (workflow_id, name, created_by_user_id, status)
		 VALUES ($1, $2, $3, 'in_progress')
		 RETURNING id`,
		workflowID, draftName, userID,
	).Scan(&draftID)

	if err != nil {
		return uuid.Nil, fmt.Errorf("failed to create draft: %w", err)
	}

	return draftID, nil
}

// CreateProposal creates a new refinement proposal
func (s *Service) CreateProposal(ctx context.Context, draftID uuid.UUID, userID uuid.UUID, threadID string) (uuid.UUID, error) {
	var proposalID uuid.UUID

	// Create proposal with empty ai_generated_content (will be updated later)
	err := s.pool.QueryRow(ctx,
		`INSERT INTO proposals (draft_id, created_by_user_id, ai_generated_content, status, thread_id)
		 VALUES ($1, $2, '{}'::jsonb, 'pending', $3)
		 RETURNING id`,
		draftID, userID, threadID,
	).Scan(&proposalID)

	if err != nil {
		return uuid.Nil, fmt.Errorf("failed to create proposal: %w", err)
	}

	return proposalID, nil
}
