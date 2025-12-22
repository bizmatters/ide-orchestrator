package orchestration

import (
	"context"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/jackc/pgx/v5"
)

// Service handles workflow orchestration logic
type Service struct {
	pool                *pgxpool.Pool
	SpecEngineClient    *SpecEngineClient
	DeepAgentsClient    DeepAgentsRuntimeClientInterface
}

// NewService creates a new orchestration service
func NewService(pool *pgxpool.Pool, specEngineClient *SpecEngineClient) *Service {
	return &Service{
		pool:             pool,
		SpecEngineClient: specEngineClient,
		DeepAgentsClient: NewDeepAgentsRuntimeClient(),
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

// Workflow represents a workflow entity
type Workflow struct {
	ID                   uuid.UUID  `json:"id"`
	Name                 string     `json:"name"`
	Description          string     `json:"description"`
	CreatedByUserID      uuid.UUID  `json:"created_by_user_id"`
	ProductionVersionID  *uuid.UUID `json:"production_version_id,omitempty"`
	CreatedAt            time.Time  `json:"created_at"`
	UpdatedAt            time.Time  `json:"updated_at"`
}

// Version represents a workflow version
type Version struct {
	ID                uuid.UUID `json:"id"`
	WorkflowID        uuid.UUID `json:"workflow_id"`
	VersionNumber     int       `json:"version_number"`
	Status            string    `json:"status"`
	PublishedByUserID uuid.UUID `json:"published_by_user_id"`
	CreatedAt         time.Time `json:"created_at"`
}

// GetWorkflow retrieves a workflow by ID
func (s *Service) GetWorkflow(ctx context.Context, workflowID uuid.UUID) (*Workflow, error) {
	var workflow Workflow
	
	err := s.pool.QueryRow(ctx, `
		SELECT id, name, description, created_by_user_id, production_version_id, created_at, updated_at
		FROM workflows 
		WHERE id = $1
	`, workflowID).Scan(
		&workflow.ID,
		&workflow.Name,
		&workflow.Description,
		&workflow.CreatedByUserID,
		&workflow.ProductionVersionID,
		&workflow.CreatedAt,
		&workflow.UpdatedAt,
	)
	
	if err != nil {
		if err == pgx.ErrNoRows {
			return nil, fmt.Errorf("workflow not found")
		}
		return nil, fmt.Errorf("failed to get workflow: %w", err)
	}
	
	return &workflow, nil
}

// GetVersions retrieves all versions for a workflow
func (s *Service) GetVersions(ctx context.Context, workflowID uuid.UUID) ([]*Version, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT id, workflow_id, version_number, status, published_by_user_id, created_at
		FROM versions 
		WHERE workflow_id = $1
		ORDER BY version_number DESC
	`, workflowID)
	
	if err != nil {
		return nil, fmt.Errorf("failed to query versions: %w", err)
	}
	defer rows.Close()
	
	var versions []*Version
	for rows.Next() {
		var version Version
		err := rows.Scan(
			&version.ID,
			&version.WorkflowID,
			&version.VersionNumber,
			&version.Status,
			&version.PublishedByUserID,
			&version.CreatedAt,
		)
		if err != nil {
			return nil, fmt.Errorf("failed to scan version: %w", err)
		}
		versions = append(versions, &version)
	}
	
	if err = rows.Err(); err != nil {
		return nil, fmt.Errorf("error iterating versions: %w", err)
	}
	
	return versions, nil
}

// CreateRefinementProposal creates a new refinement proposal and initiates deepagents-runtime execution
func (s *Service) CreateRefinementProposal(ctx context.Context, draftID uuid.UUID, userID uuid.UUID, userPrompt string, contextFilePath, contextSelection *string) (uuid.UUID, string, error) {
	// Check if deepagents-runtime is healthy
	if !s.DeepAgentsClient.IsHealthy(ctx) {
		return uuid.Nil, "", fmt.Errorf("deepagents-runtime unavailable")
	}

	// Create job request for deepagents-runtime
	jobReq := JobRequest{
		TraceID: uuid.New().String(),
		JobID:   uuid.New().String(),
		AgentDefinition: map[string]interface{}{
			"type": "workflow_refinement",
			"version": "1.0",
		},
		InputPayload: InputPayload{
			Messages: []Message{
				{
					Role:    "user",
					Content: userPrompt,
				},
			},
		},
	}

	// Add context if provided
	if contextFilePath != nil || contextSelection != nil {
		contextData := make(map[string]interface{})
		if contextFilePath != nil {
			contextData["file_path"] = *contextFilePath
		}
		if contextSelection != nil {
			contextData["selection"] = *contextSelection
		}
		jobReq.AgentDefinition["context"] = contextData
	}

	// Invoke deepagents-runtime
	threadID, err := s.DeepAgentsClient.Invoke(ctx, jobReq)
	if err != nil {
		return uuid.Nil, "", fmt.Errorf("failed to invoke deepagents-runtime: %w", err)
	}

	// Create proposal in database
	var proposalID uuid.UUID
	err = s.pool.QueryRow(ctx,
		`INSERT INTO proposals (draft_id, created_by_user_id, thread_id, user_prompt, context_file_path, context_selection, ai_generated_content, status)
		 VALUES ($1, $2, $3, $4, $5, $6, '{}'::jsonb, 'processing')
		 RETURNING id`,
		draftID, userID, threadID, userPrompt, contextFilePath, contextSelection,
	).Scan(&proposalID)

	if err != nil {
		return uuid.Nil, "", fmt.Errorf("failed to create proposal: %w", err)
	}

	// Create proposal access record
	_, err = s.pool.Exec(ctx,
		`INSERT INTO proposal_access (proposal_id, user_id, access_type)
		 VALUES ($1, $2, 'owner')`,
		proposalID, userID,
	)

	if err != nil {
		return uuid.Nil, "", fmt.Errorf("failed to create proposal access: %w", err)
	}

	return proposalID, threadID, nil
}

// GetProposal retrieves a proposal by ID
func (s *Service) GetProposal(ctx context.Context, proposalID uuid.UUID) (map[string]interface{}, error) {
	var proposal struct {
		ID                 string                 `db:"id"`
		DraftID            string                 `db:"draft_id"`
		ThreadID           *string                `db:"thread_id"`
		UserPrompt         *string                `db:"user_prompt"`
		ContextFilePath    *string                `db:"context_file_path"`
		ContextSelection   *string                `db:"context_selection"`
		GeneratedFiles     map[string]interface{} `db:"generated_files"`
		Status             string                 `db:"status"`
		CreatedAt          time.Time              `db:"created_at"`
		CompletedAt        *time.Time             `db:"completed_at"`
		ResolvedAt         *time.Time             `db:"resolved_at"`
	}

	err := s.pool.QueryRow(ctx, `
		SELECT id, draft_id, thread_id, user_prompt, context_file_path, context_selection, 
		       generated_files, status, created_at, completed_at, resolved_at
		FROM proposals 
		WHERE id = $1
	`, proposalID).Scan(
		&proposal.ID, &proposal.DraftID, &proposal.ThreadID, &proposal.UserPrompt,
		&proposal.ContextFilePath, &proposal.ContextSelection, &proposal.GeneratedFiles,
		&proposal.Status, &proposal.CreatedAt, &proposal.CompletedAt, &proposal.ResolvedAt,
	)

	if err != nil {
		return nil, fmt.Errorf("proposal not found")
	}

	result := map[string]interface{}{
		"id":                 proposal.ID,
		"draft_id":           proposal.DraftID,
		"thread_id":          proposal.ThreadID,
		"user_prompt":        proposal.UserPrompt,
		"context_file_path":  proposal.ContextFilePath,
		"context_selection":  proposal.ContextSelection,
		"generated_files":    proposal.GeneratedFiles,
		"status":             proposal.Status,
		"created_at":         proposal.CreatedAt.Format(time.RFC3339),
	}

	if proposal.CompletedAt != nil {
		result["completed_at"] = proposal.CompletedAt.Format(time.RFC3339)
	}
	if proposal.ResolvedAt != nil {
		result["resolved_at"] = proposal.ResolvedAt.Format(time.RFC3339)
	}

	return result, nil
}

// ApproveProposal approves a proposal and applies changes to the draft
func (s *Service) ApproveProposal(ctx context.Context, proposalID uuid.UUID, userID uuid.UUID) error {
	// Start transaction
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to start transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	// Lock proposal for update to prevent concurrent modifications
	currentStatus, err := s.lockProposalForUpdate(ctx, tx, proposalID)
	if err != nil {
		return err
	}

	// Validate status transition
	err = s.validateProposalTransition(currentStatus, "approved")
	if err != nil {
		return err
	}

	// Get additional proposal data
	var draftID uuid.UUID
	var threadID *string
	var generatedFiles map[string]interface{}
	err = tx.QueryRow(ctx, `
		SELECT draft_id, thread_id, generated_files 
		FROM proposals 
		WHERE id = $1
	`, proposalID).Scan(&draftID, &threadID, &generatedFiles)

	if err != nil {
		return fmt.Errorf("failed to get proposal data: %w", err)
	}

	// Apply generated files to draft
	if generatedFiles != nil {
		err = s.applyFilesToDraft(ctx, tx, draftID, generatedFiles)
		if err != nil {
			return fmt.Errorf("failed to apply files to draft: %w", err)
		}
	}

	// Update proposal status to approved
	_, err = tx.Exec(ctx, `
		UPDATE proposals 
		SET status = 'approved', resolved_by_user_id = $1, resolved_at = NOW()
		WHERE id = $2
	`, userID, proposalID)

	if err != nil {
		return fmt.Errorf("failed to update proposal status: %w", err)
	}

	// Create audit trail
	auditDetails := map[string]interface{}{
		"files_applied": len(generatedFiles),
		"draft_id":      draftID.String(),
	}
	err = s.createAuditTrail(ctx, proposalID, userID, "approved", auditDetails)
	if err != nil {
		// Log error but don't fail the transaction
		fmt.Printf("Failed to create audit trail: %v\n", err)
	}

	// Commit transaction
	if err = tx.Commit(ctx); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	// Clean up deepagents-runtime data in background
	if threadID != nil {
		go func() {
			cleanupCtx := context.Background()
			if err := s.cleanupDeepAgentsRuntimeData(cleanupCtx, *threadID); err != nil {
				fmt.Printf("Failed to cleanup deepagents-runtime data for thread %s: %v\n", *threadID, err)
			}
		}()
	}

	return nil
}

// RejectProposal rejects a proposal and cleans up resources
func (s *Service) RejectProposal(ctx context.Context, proposalID uuid.UUID, userID uuid.UUID) error {
	// Start transaction for locking
	tx, err := s.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("failed to start transaction: %w", err)
	}
	defer tx.Rollback(ctx)

	// Lock proposal for update to prevent concurrent modifications
	currentStatus, err := s.lockProposalForUpdate(ctx, tx, proposalID)
	if err != nil {
		return err
	}

	// Validate status transition
	err = s.validateProposalTransition(currentStatus, "rejected")
	if err != nil {
		return err
	}

	// Get thread_id for cleanup
	var threadID *string
	err = tx.QueryRow(ctx, `
		SELECT thread_id FROM proposals WHERE id = $1
	`, proposalID).Scan(&threadID)

	if err != nil {
		return fmt.Errorf("failed to get proposal data: %w", err)
	}

	// Update proposal status to rejected
	_, err = tx.Exec(ctx, `
		UPDATE proposals 
		SET status = 'rejected', resolved_by_user_id = $1, resolved_at = NOW()
		WHERE id = $2
	`, userID, proposalID)

	if err != nil {
		return fmt.Errorf("failed to update proposal status: %w", err)
	}

	// Create audit trail
	auditDetails := map[string]interface{}{
		"reason": "user_rejected",
	}
	err = s.createAuditTrail(ctx, proposalID, userID, "rejected", auditDetails)
	if err != nil {
		// Log error but don't fail the operation
		fmt.Printf("Failed to create audit trail: %v\n", err)
	}

	// Commit transaction
	if err = tx.Commit(ctx); err != nil {
		return fmt.Errorf("failed to commit transaction: %w", err)
	}

	// Clean up deepagents-runtime data in background
	if threadID != nil {
		go func() {
			cleanupCtx := context.Background()
			if err := s.cleanupDeepAgentsRuntimeData(cleanupCtx, *threadID); err != nil {
				fmt.Printf("Failed to cleanup deepagents-runtime data for thread %s: %v\n", *threadID, err)
			}
		}()
	}

	return nil
}

// applyFilesToDraft applies generated files to the draft
func (s *Service) applyFilesToDraft(ctx context.Context, tx pgx.Tx, draftID uuid.UUID, generatedFiles map[string]interface{}) error {
	// Parse and apply each generated file
	for filePath, fileData := range generatedFiles {
		if fileDataMap, ok := fileData.(map[string]interface{}); ok {
			// Extract file content
			var content string
			if contentArray, ok := fileDataMap["content"].([]interface{}); ok {
				// Convert array of lines to string
				lines := make([]string, len(contentArray))
				for i, line := range contentArray {
					if lineStr, ok := line.(string); ok {
						lines[i] = lineStr
					}
				}
				content = fmt.Sprintf("%s\n", fmt.Sprintf("%v", lines))
			} else if contentStr, ok := fileDataMap["content"].(string); ok {
				content = contentStr
			}

			// Update or create draft specification file
			_, err := tx.Exec(ctx, `
				INSERT INTO draft_specification_files (draft_id, file_path, content, created_at, updated_at)
				VALUES ($1, $2, $3, NOW(), NOW())
				ON CONFLICT (draft_id, file_path) 
				DO UPDATE SET content = EXCLUDED.content, updated_at = NOW()
			`, draftID, filePath, content)

			if err != nil {
				return fmt.Errorf("failed to apply file %s: %w", filePath, err)
			}
		}
	}

	// Update draft's updated_at timestamp
	_, err := tx.Exec(ctx, `
		UPDATE drafts 
		SET updated_at = NOW()
		WHERE id = $1
	`, draftID)

	if err != nil {
		return fmt.Errorf("failed to update draft timestamp: %w", err)
	}

	return nil
}

// cleanupDeepAgentsRuntimeData cleans up deepagents-runtime checkpointer data
func (s *Service) cleanupDeepAgentsRuntimeData(ctx context.Context, threadID string) error {
	// This is a background cleanup operation
	// In a real implementation, you would:
	// 1. Call deepagents-runtime cleanup API
	// 2. Remove checkpointer data from Redis/database
	// 3. Clean up any temporary files
	
	// For now, we'll just log the cleanup request
	fmt.Printf("Cleaning up deepagents-runtime data for thread: %s\n", threadID)
	
	// TODO: Implement actual cleanup when deepagents-runtime provides cleanup API
	// This might involve calling something like:
	// return s.DeepAgentsClient.CleanupThread(ctx, threadID)
	
	return nil
}

// createAuditTrail creates an audit trail entry for proposal decisions
func (s *Service) createAuditTrail(ctx context.Context, proposalID uuid.UUID, userID uuid.UUID, action string, details map[string]interface{}) error {
	// Create audit trail entry
	auditJSON := fmt.Sprintf(`{"action": "%s", "proposal_id": "%s", "user_id": "%s", "timestamp": "%s"}`, 
		action, proposalID.String(), userID.String(), time.Now().UTC().Format(time.RFC3339))

	// Store audit trail in proposals table ai_generated_content field
	_, err := s.pool.Exec(ctx, `
		UPDATE proposals 
		SET ai_generated_content = jsonb_set(
			COALESCE(ai_generated_content, '{}'),
			'{audit_trail}',
			COALESCE(ai_generated_content->'audit_trail', '[]'::jsonb) || $1::jsonb
		)
		WHERE id = $2
	`, auditJSON, proposalID)

	if err != nil {
		return fmt.Errorf("failed to create audit trail: %w", err)
	}

	return nil
}

// lockProposalForUpdate locks a proposal for update to prevent concurrent modifications
func (s *Service) lockProposalForUpdate(ctx context.Context, tx pgx.Tx, proposalID uuid.UUID) (string, error) {
	var status string
	
	// Use SELECT FOR UPDATE to lock the row
	err := tx.QueryRow(ctx, `
		SELECT status FROM proposals 
		WHERE id = $1 
		FOR UPDATE
	`, proposalID).Scan(&status)

	if err != nil {
		return "", fmt.Errorf("proposal not found or locked")
	}

	return status, nil
}

// validateProposalTransition validates if a status transition is allowed
func (s *Service) validateProposalTransition(currentStatus, newStatus string) error {
	validTransitions := map[string][]string{
		"pending":    {"processing", "failed", "rejected"},
		"processing": {"completed", "failed", "rejected"},
		"completed":  {"approved", "rejected"},
		"failed":     {"rejected"},
		"approved":   {}, // Terminal state
		"rejected":   {}, // Terminal state
	}

	allowedNext, exists := validTransitions[currentStatus]
	if !exists {
		return fmt.Errorf("invalid current status: %s", currentStatus)
	}

	for _, allowed := range allowedNext {
		if allowed == newStatus {
			return nil
		}
	}

	return fmt.Errorf("invalid status transition from %s to %s", currentStatus, newStatus)
}
