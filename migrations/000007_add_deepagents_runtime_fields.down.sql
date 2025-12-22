-- Rollback deepagents-runtime integration fields

-- Drop proposal_access table
DROP TABLE IF EXISTS proposal_access;

-- Drop indexes
DROP INDEX IF EXISTS idx_proposals_generated_files_gin;
DROP INDEX IF EXISTS idx_proposals_status_completed;
DROP INDEX IF EXISTS idx_proposals_thread_id;

-- Drop unique constraint
ALTER TABLE proposals DROP CONSTRAINT IF EXISTS unique_thread_id;

-- Remove new columns from proposals table
ALTER TABLE proposals 
DROP COLUMN IF EXISTS completed_at,
DROP COLUMN IF EXISTS generated_files,
DROP COLUMN IF EXISTS context_selection,
DROP COLUMN IF EXISTS context_file_path,
DROP COLUMN IF EXISTS user_prompt,
DROP COLUMN IF EXISTS thread_id;

-- Restore original status constraint
ALTER TABLE proposals DROP CONSTRAINT IF EXISTS status_valid;
ALTER TABLE proposals ADD CONSTRAINT status_valid 
    CHECK (status IN ('pending', 'approved', 'rejected', 'superseded'));