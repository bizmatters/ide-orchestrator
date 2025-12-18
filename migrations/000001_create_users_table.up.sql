-- Create users table for foundational user management
-- Supports email/password authentication with proper security constraints

CREATE TABLE IF NOT EXISTS users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) NOT NULL UNIQUE,
    hashed_password VARCHAR(255) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),

    -- Constraints
    CONSTRAINT email_format CHECK (email ~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'),
    CONSTRAINT name_not_empty CHECK (LENGTH(TRIM(name)) > 0)
);

-- Create unique index on email for fast lookups and constraint enforcement
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(LOWER(email));

-- Create index on created_at for audit queries
CREATE INDEX IF NOT EXISTS idx_users_created_at ON users(created_at DESC);

-- Add trigger to automatically update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- Add comment for documentation
COMMENT ON TABLE users IS 'User accounts for agent-builder platform with email/password authentication';
COMMENT ON COLUMN users.id IS 'Primary key UUID for user identification';
COMMENT ON COLUMN users.email IS 'Unique email address for authentication';
COMMENT ON COLUMN users.hashed_password IS 'bcrypt hashed password (never store plaintext)';
