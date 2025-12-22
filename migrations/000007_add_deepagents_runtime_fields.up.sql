-- Add deepagents-runtime integration fields to proposals table
-- Supports thread_id linking, user prompts, context, and generated files

-- Add new columns to proposals table
ALTER TABLE proposals 
ADD COLUMN IF NOT EXISTS thread_id VARCHAR(255),
ADD COLUMN IF NOT EXISTS user_prompt TEXT,
ADD COLUMN IF NOT EXISTS context_file_path TEXT,
ADD COLUMN IF NOT EXISTS context_selection TEXT,
ADD COLUMN IF NOT EXISTS generated_files JSONB,
ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP WITH TIME ZONE;

-- Update status constraint to include new statuses
ALTER TABLE proposals DROP CONSTRAINT IF EXISTS status_valid;
ALTER TABLE proposals ADD CONSTRAINT status_valid 
    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'approved', 'rejected', 'superseded'));

-- Add unique constraint on thread_id (one proposal per thread)
ALTER TABLE proposals ADD CONSTRAINT unique_thread_id UNIQUE (thread_id);

-- Add indexes for performance
CREATE INDEX IF NOT EXISTS idx_proposals_thread_id ON proposals(thread_id);
CREATE INDEX IF NOT EXISTS idx_proposals_status_completed ON proposals(status, completed_at DESC);

-- Add GIN index for generated_files JSONB search
CREATE INDEX IF NOT EXISTS idx_proposals_generated_files_gin ON proposals USING GIN (generated_files);

-- Add comments for new fields
COMMENT ON COLUMN proposals.thread_id IS 'deepagents-runtime execution thread ID (unique)';
COMMENT ON COLUMN proposals.user_prompt IS 'User prompt that initiated the refinement';
COMMENT ON COLUMN proposals.context_file_path IS 'Optional file path for context';
COMMENT ON COLUMN proposals.context_selection IS 'Optional text selection for context';
COMMENT ON COLUMN proposals.generated_files IS 'JSONB containing generated files from deepagents-runtime';
COMMENT ON COLUMN proposals.completed_at IS 'Timestamp when deepagents-runtime execution completed';

-- Create proposal_access table for user authorization
CREATE TABLE IF NOT EXISTS proposal_access (
    proposal_id UUID NOT NULL,
    user_id UUID NOT NULL,
    access_type VARCHAR(50) NOT NULL DEFAULT 'owner',
    granted_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    PRIMARY KEY (proposal_id, user_id),
    CONSTRAINT access_type_valid CHECK (access_type IN ('owner', 'viewer')),
    CONSTRAINT fk_proposal_access_proposal FOREIGN KEY (proposal_id)
        REFERENCES proposals(id) ON DELETE CASCADE,
    CONSTRAINT fk_proposal_access_user FOREIGN KEY (user_id)
        REFERENCES users(id) ON DELETE CASCADE
);

-- Add indexes for proposal_access
CREATE INDEX IF NOT EXISTS idx_proposal_access_user_id ON proposal_access(user_id);
CREATE INDEX IF NOT EXISTS idx_proposal_access_type ON proposal_access(access_type);

-- Add comments for proposal_access table
COMMENT ON TABLE proposal_access IS 'User authorization for proposal access';
COMMENT ON COLUMN proposal_access.proposal_id IS 'Foreign key to proposals table';
COMMENT ON COLUMN proposal_access.user_id IS 'Foreign key to users table';
COMMENT ON COLUMN proposal_access.access_type IS 'Type of access: owner, viewer';
COMMENT ON COLUMN proposal_access.granted_at IS 'Timestamp when access was granted';