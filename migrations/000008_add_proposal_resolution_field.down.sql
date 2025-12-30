-- Rollback resolution field from proposals table

-- Drop index
DROP INDEX IF EXISTS idx_proposals_resolution;

-- Drop constraints
ALTER TABLE proposals DROP CONSTRAINT IF EXISTS resolution_required_when_resolved;
ALTER TABLE proposals DROP CONSTRAINT IF EXISTS resolution_valid;

-- Remove resolution column
ALTER TABLE proposals DROP COLUMN IF EXISTS resolution;

-- Restore original status constraint
ALTER TABLE proposals DROP CONSTRAINT IF EXISTS status_valid;
ALTER TABLE proposals ADD CONSTRAINT status_valid 
    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'approved', 'rejected', 'superseded'));