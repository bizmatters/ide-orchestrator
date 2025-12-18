-- Drop draft and proposal tables and related objects

-- Drop triggers
DROP TRIGGER IF EXISTS update_draft_specification_files_updated_at ON draft_specification_files;
DROP TRIGGER IF EXISTS update_drafts_updated_at ON drafts;

-- Drop indexes (proposals)
DROP INDEX IF EXISTS idx_proposals_ai_content_gin;
DROP INDEX IF EXISTS idx_proposals_resolved_at;
DROP INDEX IF EXISTS idx_proposals_created_at;
DROP INDEX IF EXISTS idx_proposals_status;
DROP INDEX IF EXISTS idx_proposals_resolved_by;
DROP INDEX IF EXISTS idx_proposals_created_by;
DROP INDEX IF EXISTS idx_proposals_draft_id;

-- Drop indexes (draft_specification_files)
DROP INDEX IF EXISTS idx_draft_specification_files_file_type;
DROP INDEX IF EXISTS idx_draft_specification_files_draft_id;

-- Drop indexes (drafts)
DROP INDEX IF EXISTS idx_drafts_created_at;
DROP INDEX IF EXISTS idx_drafts_status;
DROP INDEX IF EXISTS idx_drafts_created_by;
DROP INDEX IF EXISTS idx_drafts_workflow_id;

-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS proposals;
DROP TABLE IF EXISTS draft_specification_files;
DROP TABLE IF EXISTS drafts;
