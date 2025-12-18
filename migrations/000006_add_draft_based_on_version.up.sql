-- Add based_on_version_id column to drafts table
-- Supports tracking which published version a draft is based on

ALTER TABLE drafts
ADD COLUMN based_on_version_id UUID;

-- Add foreign key constraint (assuming versions table exists or will exist)
-- If versions table doesn't exist yet, this can be added in a future migration
-- ALTER TABLE drafts
-- ADD CONSTRAINT fk_drafts_based_on_version FOREIGN KEY (based_on_version_id)
--     REFERENCES versions(id) ON DELETE SET NULL;

-- Add index for version-based queries
CREATE INDEX IF NOT EXISTS idx_drafts_based_on_version ON drafts(based_on_version_id) WHERE based_on_version_id IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN drafts.based_on_version_id IS 'Published version this draft is based on (NULL for initial draft)';
