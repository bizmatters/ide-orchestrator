-- Rollback: Remove based_on_version_id column from drafts table

-- Drop index
DROP INDEX IF EXISTS idx_drafts_based_on_version;

-- Drop foreign key constraint if it was added
-- ALTER TABLE drafts DROP CONSTRAINT IF EXISTS fk_drafts_based_on_version;

-- Drop column
ALTER TABLE drafts DROP COLUMN IF EXISTS based_on_version_id;
