-- Drop core workflow tables and related objects

-- Drop triggers
DROP TRIGGER IF EXISTS update_workflows_updated_at ON workflows;

-- Drop indexes (specification_files)
DROP INDEX IF EXISTS idx_specification_files_file_type;
DROP INDEX IF EXISTS idx_specification_files_version_id;

-- Drop indexes (versions)
DROP INDEX IF EXISTS idx_versions_workflow_version;
DROP INDEX IF EXISTS idx_versions_status;
DROP INDEX IF EXISTS idx_versions_created_at;
DROP INDEX IF EXISTS idx_versions_published_by;
DROP INDEX IF EXISTS idx_versions_workflow_id;

-- Drop indexes (workflows)
DROP INDEX IF EXISTS idx_workflows_name;
DROP INDEX IF EXISTS idx_workflows_created_at;
DROP INDEX IF EXISTS idx_workflows_production_version;
DROP INDEX IF EXISTS idx_workflows_created_by;

-- Drop foreign key constraint from workflows to versions
ALTER TABLE workflows DROP CONSTRAINT IF EXISTS fk_workflows_production_version;

-- Drop tables in reverse dependency order
DROP TABLE IF EXISTS specification_files;
DROP TABLE IF EXISTS versions;
DROP TABLE IF EXISTS workflows;
