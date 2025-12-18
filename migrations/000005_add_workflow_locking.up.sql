-- Add workflow locking mechanism columns
-- Supports collaborative editing and preventing concurrent modifications

ALTER TABLE workflows
ADD COLUMN is_locked BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN locked_by_user_id UUID,
ADD COLUMN locked_at TIMESTAMP WITH TIME ZONE;

-- Add foreign key constraint for locked_by_user_id
ALTER TABLE workflows
ADD CONSTRAINT fk_workflows_locked_by FOREIGN KEY (locked_by_user_id)
    REFERENCES users(id) ON DELETE SET NULL;

-- Add index for lock queries
CREATE INDEX IF NOT EXISTS idx_workflows_is_locked ON workflows(is_locked) WHERE is_locked = true;
CREATE INDEX IF NOT EXISTS idx_workflows_locked_by ON workflows(locked_by_user_id) WHERE locked_by_user_id IS NOT NULL;

-- Add comments for documentation
COMMENT ON COLUMN workflows.is_locked IS 'Whether this workflow is currently locked for editing';
COMMENT ON COLUMN workflows.locked_by_user_id IS 'User who currently holds the lock (NULL if not locked)';
COMMENT ON COLUMN workflows.locked_at IS 'Timestamp when the lock was acquired (NULL if not locked)';
