-- Create core workflow management tables
-- Supports version control, specification file management, and audit trail

-- workflows table: main workflow entities with production pointers
CREATE TABLE IF NOT EXISTS workflows (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    description TEXT,
    created_by_user_id UUID NOT NULL,
    production_version_id UUID, -- Points to the currently deployed version
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT name_not_empty CHECK (LENGTH(TRIM(name)) > 0),
    CONSTRAINT fk_workflows_created_by FOREIGN KEY (created_by_user_id)
        REFERENCES users(id) ON DELETE RESTRICT
);

-- versions table: immutable published snapshots of workflow specifications
CREATE TABLE IF NOT EXISTS versions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    workflow_id UUID NOT NULL,
    version_number INTEGER NOT NULL,
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    published_by_user_id UUID NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT version_number_positive CHECK (version_number > 0),
    CONSTRAINT status_valid CHECK (status IN ('draft', 'published', 'deprecated')),
    CONSTRAINT unique_workflow_version UNIQUE (workflow_id, version_number),
    CONSTRAINT fk_versions_workflow FOREIGN KEY (workflow_id)
        REFERENCES workflows(id) ON DELETE CASCADE,
    CONSTRAINT fk_versions_published_by FOREIGN KEY (published_by_user_id)
        REFERENCES users(id) ON DELETE RESTRICT
);

-- specification_files table: markdown source files per version
CREATE TABLE IF NOT EXISTS specification_files (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    version_id UUID NOT NULL,
    file_path VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    file_type VARCHAR(50) NOT NULL DEFAULT 'markdown',
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT file_path_not_empty CHECK (LENGTH(TRIM(file_path)) > 0),
    CONSTRAINT file_type_valid CHECK (file_type IN ('markdown', 'json', 'yaml')),
    CONSTRAINT unique_version_file_path UNIQUE (version_id, file_path),
    CONSTRAINT fk_specification_files_version FOREIGN KEY (version_id)
        REFERENCES versions(id) ON DELETE CASCADE
);

-- Add foreign key for production_version_id (must be added after versions table exists)
ALTER TABLE workflows
    ADD CONSTRAINT fk_workflows_production_version FOREIGN KEY (production_version_id)
        REFERENCES versions(id) ON DELETE SET NULL;

-- Create indexes for performance optimization

-- Workflows indexes
CREATE INDEX IF NOT EXISTS idx_workflows_created_by ON workflows(created_by_user_id);
CREATE INDEX IF NOT EXISTS idx_workflows_production_version ON workflows(production_version_id);
CREATE INDEX IF NOT EXISTS idx_workflows_created_at ON workflows(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_workflows_name ON workflows(name);

-- Versions indexes
CREATE INDEX IF NOT EXISTS idx_versions_workflow_id ON versions(workflow_id);
CREATE INDEX IF NOT EXISTS idx_versions_published_by ON versions(published_by_user_id);
CREATE INDEX IF NOT EXISTS idx_versions_created_at ON versions(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_versions_status ON versions(status);
CREATE INDEX IF NOT EXISTS idx_versions_workflow_version ON versions(workflow_id, version_number DESC);

-- Specification files indexes
CREATE INDEX IF NOT EXISTS idx_specification_files_version_id ON specification_files(version_id);
CREATE INDEX IF NOT EXISTS idx_specification_files_file_type ON specification_files(file_type);

-- Add trigger to automatically update updated_at timestamp for workflows
CREATE TRIGGER update_workflows_updated_at
    BEFORE UPDATE ON workflows
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comments for documentation
COMMENT ON TABLE workflows IS 'Main workflow entities with production version pointers';
COMMENT ON COLUMN workflows.id IS 'Primary key UUID for workflow identification';
COMMENT ON COLUMN workflows.name IS 'Workflow name for display and reference';
COMMENT ON COLUMN workflows.description IS 'Optional workflow description';
COMMENT ON COLUMN workflows.created_by_user_id IS 'User who created this workflow (audit trail)';
COMMENT ON COLUMN workflows.production_version_id IS 'Points to the currently deployed version';

COMMENT ON TABLE versions IS 'Immutable published snapshots of workflow specifications';
COMMENT ON COLUMN versions.id IS 'Primary key UUID for version identification';
COMMENT ON COLUMN versions.workflow_id IS 'Foreign key to parent workflow';
COMMENT ON COLUMN versions.version_number IS 'Sequential version number (1, 2, 3, ...)';
COMMENT ON COLUMN versions.status IS 'Version status: draft, published, deprecated';
COMMENT ON COLUMN versions.published_by_user_id IS 'User who published this version (audit trail)';

COMMENT ON TABLE specification_files IS 'Markdown source files associated with versions';
COMMENT ON COLUMN specification_files.id IS 'Primary key UUID for file identification';
COMMENT ON COLUMN specification_files.version_id IS 'Foreign key to parent version';
COMMENT ON COLUMN specification_files.file_path IS 'Relative path of the file within specification';
COMMENT ON COLUMN specification_files.content IS 'Full file content (markdown, JSON, or YAML)';
COMMENT ON COLUMN specification_files.file_type IS 'Type of specification file';
