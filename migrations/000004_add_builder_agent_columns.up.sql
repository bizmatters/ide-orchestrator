-- Add Builder Agent tracking columns to proposals table
-- Supports LangGraph checkpointer integration and execution tracing

ALTER TABLE proposals
ADD COLUMN thread_id TEXT,
ADD COLUMN execution_trace JSONB;

-- Add FAILED status to proposals
ALTER TABLE proposals
DROP CONSTRAINT IF EXISTS status_valid;

ALTER TABLE proposals
ADD CONSTRAINT status_valid CHECK (status IN ('pending', 'approved', 'rejected', 'superseded', 'failed'));

-- Add index for thread_id lookups
CREATE INDEX IF NOT EXISTS idx_proposals_thread_id ON proposals(thread_id);

-- Add comments for documentation
COMMENT ON COLUMN proposals.thread_id IS 'LangGraph thread ID for Builder Agent execution tracking';
COMMENT ON COLUMN proposals.execution_trace IS 'Full execution trace from Builder Agent (messages, state history)';
