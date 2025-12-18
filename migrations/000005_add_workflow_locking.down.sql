-- Rollback workflow locking columns

-- Drop indexes
DROP INDEX IF EXISTS idx_workflows_locked_by;
DROP INDEX IF EXISTS idx_workflows_is_locked;

-- Drop foreign key constraint
ALTER TABLE workflows
DROP CONSTRAINT IF EXISTS fk_workflows_locked_by;

-- Drop columns
ALTER TABLE workflows
DROP COLUMN IF EXISTS locked_at,
DROP COLUMN IF EXISTS locked_by_user_id,
DROP COLUMN IF EXISTS is_locked;
