-- Rollback Builder Agent columns

DROP INDEX IF EXISTS idx_proposals_thread_id;

ALTER TABLE proposals
DROP COLUMN IF EXISTS thread_id,
DROP COLUMN IF EXISTS execution_trace;
