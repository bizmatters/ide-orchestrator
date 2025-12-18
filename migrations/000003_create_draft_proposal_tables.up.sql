-- Create draft and proposal management tables
-- Supports work-in-progress state, Constitutional Refinement workflow, and AI-generated proposals

-- drafts table: work-in-progress state management for workflows
CREATE TABLE IF NOT EXISTS drafts (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL UNIQUE, -- One draft per workflow at a time
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_by_user_id UUID NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'in_progress',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT name_not_empty CHECK (LENGTH(TRIM(name)) > 0),
    CONSTRAINT status_valid CHECK (status IN ('in_progress', 'ready_to_publish', 'abandoned')),
    CONSTRAINT fk_drafts_workflow FOREIGN KEY (workflow_id)
        REFERENCES workflows(id) ON DELETE CASCADE,
    CONSTRAINT fk_drafts_created_by FOREIGN KEY (created_by_user_id)
        REFERENCES users(id) ON DELETE RESTRICT
);

-- draft_specification_files table: draft content storage
CREATE TABLE IF NOT EXISTS draft_specification_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL DEFAULT 'markdown',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT file_path_not_empty CHECK (LENGTH(TRIM(file_path)) > 0),
    CONSTRAINT file_type_valid CHECK (file_type IN ('markdown', 'json', 'yaml')),
    CONSTRAINT unique_draft_file_path UNIQUE (draft_id, file_path),
    CONSTRAINT fk_draft_specification_files_draft FOREIGN KEY (draft_id)
        REFERENCES drafts(id) ON DELETE CASCADE
);

-- proposals table: refinement workflow tracking and AI-generated content
CREATE TABLE IF NOT EXISTS proposals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    draft_id UUID NOT NULL,
    ai_generated_content JSONB NOT NULL, -- Stores proposed changes, diffs, and impact analysis
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_by_user_id UUID NOT NULL,
    resolved_by_user_id UUID,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    resolved_at TIMESTAMP WITH TIME ZONE,

    -- Constraints
    CONSTRAINT status_valid CHECK (status IN ('pending', 'approved', 'rejected', 'superseded')),
    CONSTRAINT ai_generated_content_not_empty CHECK (jsonb_typeof(ai_generated_content) = 'object'),
    CONSTRAINT resolved_at_requires_resolved_by CHECK (
        (resolved_at IS NULL AND resolved_by_user_id IS NULL) OR
        (resolved_at IS NOT NULL AND resolved_by_user_id IS NOT NULL)
    ),
    CONSTRAINT fk_proposals_draft FOREIGN KEY (draft_id)
        REFERENCES drafts(id) ON DELETE CASCADE,
    CONSTRAINT fk_proposals_created_by FOREIGN KEY (created_by_user_id)
        REFERENCES users(id) ON DELETE RESTRICT,
    CONSTRAINT fk_proposals_resolved_by FOREIGN KEY (resolved_by_user_id)
        REFERENCES users(id) ON DELETE RESTRICT
);

-- Create indexes for performance optimization

-- Drafts indexes
CREATE INDEX IF NOT EXISTS idx_drafts_workflow_id ON drafts(workflow_id);
CREATE INDEX IF NOT EXISTS idx_drafts_created_by ON drafts(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_drafts_status ON drafts(status);
CREATE INDEX IF NOT EXISTS idx_drafts_created_at ON drafts(created_at DESC);

-- Draft specification files indexes
CREATE INDEX IF NOT EXISTS idx_draft_specification_files_draft_id ON draft_specification_files(draft_id);
CREATE INDEX IF NOT EXISTS idx_draft_specification_files_file_type ON draft_specification_files(file_type);

-- Proposals indexes
CREATE INDEX IF NOT EXISTS idx_proposals_draft_id ON proposals(draft_id);
CREATE INDEX IF NOT EXISTS idx_proposals_created_by ON proposals(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_proposals_resolved_by ON proposals(resolved_by_user_id);
CREATE INDEX IF NOT EXISTS idx_proposals_status ON proposals(status);
CREATE INDEX IF NOT EXISTS idx_proposals_created_at ON proposals(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_proposals_resolved_at ON proposals(resolved_at DESC);

-- Add GIN index for JSONB content search in proposals
CREATE INDEX IF NOT EXISTS idx_proposals_ai_content_gin ON proposals USING GIN (ai_generated_content);

-- Add triggers to automatically update updated_at timestamps
CREATE TRIGGER update_drafts_updated_at
    BEFORE UPDATE ON drafts
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_draft_specification_files_updated_at
    BEFORE UPDATE ON draft_specification_files
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE drafts IS 'Work-in-progress state management for workflows (one draft per workflow)';
COMMENT ON COLUMN drafts.id IS 'Primary key UUID for draft identification';
COMMENT ON COLUMN drafts.workflow_id IS 'Foreign key to parent workflow (unique - one draft per workflow)';
COMMENT ON COLUMN drafts.name IS 'Draft name for display and reference';
COMMENT ON COLUMN drafts.description IS 'Optional draft description';
COMMENT ON COLUMN drafts.created_by_user_id IS 'User who created this draft (audit trail)';
COMMENT ON COLUMN drafts.status IS 'Draft status: in_progress, ready_to_publish, abandoned';

COMMENT ON TABLE draft_specification_files IS 'Draft content storage for work-in-progress specifications';
COMMENT ON COLUMN draft_specification_files.id IS 'Primary key UUID for draft file identification';
COMMENT ON COLUMN draft_specification_files.draft_id IS 'Foreign key to parent draft';
COMMENT ON COLUMN draft_specification_files.file_path IS 'Relative path of the file within specification';
COMMENT ON COLUMN draft_specification_files.content IS 'Full file content (markdown, JSON, or YAML)';
COMMENT ON COLUMN draft_specification_files.file_type IS 'Type of specification file';

COMMENT ON TABLE proposals IS 'Refinement workflow tracking and AI-generated proposals';
COMMENT ON COLUMN proposals.id IS 'Primary key UUID for proposal identification';
COMMENT ON COLUMN proposals.draft_id IS 'Foreign key to parent draft';
COMMENT ON COLUMN proposals.ai_generated_content IS 'JSONB containing proposed changes, diffs, and impact analysis';
COMMENT ON COLUMN proposals.status IS 'Proposal status: pending, approved, rejected, superseded';
COMMENT ON COLUMN proposals.created_by_user_id IS 'User who requested this proposal (audit trail)';
COMMENT ON COLUMN proposals.resolved_by_user_id IS 'User who approved/rejected this proposal (audit trail)';
COMMENT ON COLUMN proposals.resolved_at IS 'Timestamp when proposal was approved/rejected';
