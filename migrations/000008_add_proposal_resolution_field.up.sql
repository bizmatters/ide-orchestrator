-- Add resolution field to proposals table
-- Supports tracking approved/rejected resolution outcomes

-- Add resolution column to proposals table
ALTER TABLE proposals 
ADD COLUMN IF NOT EXISTS resolution VARCHAR(50);

-- Update status constraint to include 'resolved' status
ALTER TABLE proposals DROP CONSTRAINT IF EXISTS status_valid;
ALTER TABLE proposals ADD CONSTRAINT status_valid 
    CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'approved', 'rejected', 'superseded', 'resolved'));

-- Add constraint for resolution field
ALTER TABLE proposals ADD CONSTRAINT resolution_valid 
    CHECK (resolution IS NULL OR resolution IN ('approved', 'rejected'));

-- Add constraint to ensure resolution is set when status is resolved
ALTER TABLE proposals ADD CONSTRAINT resolution_required_when_resolved
    CHECK (
        (status = 'resolved' AND resolution IS NOT NULL) OR
        (status != 'resolved')
    );

-- Add index for resolution field
CREATE INDEX IF NOT EXISTS idx_proposals_resolution ON proposals(resolution);

-- Add comment for new field
COMMENT ON COLUMN proposals.resolution IS 'Resolution outcome when status is resolved: approved, rejected';