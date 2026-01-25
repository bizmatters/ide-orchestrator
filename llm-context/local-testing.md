# AWS Credentials (dummy values for local preview mode)
AWS_ACCESS_KEY_ID=<REDACTED>
AWS_SECRET_ACCESS_KEY=<REDACTED>
BOT_GITHUB_USERNAME=arun4infra
BOT_GITHUB_TOKEN=<REDACTED>
TENANTS_REPO_NAME=zerotouch-tenants

# OpenAI API Key for Kagent
OPENAI_API_KEY=<REDACTED>
ANTHROPIC_API_KEY=<REDACTED>
AWS_ROLE_ARN=arn:aws:iam::337832075585:role/eso_gitHub_actions_access

## pass below env variables 
NODE_ENV=local

### PG DG
DATABASE_URL=postgresql://neondb_owner:npg_xhb7deHlum2n@ep-square-base-ah3e7r3r-pooler.c-3.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require

# Cache Configuration (will be overridden by platform)
NATS_URL=nats://localhost:14222
USE_MOCK_LLM=true
MODEL=gpt-4.1-mini
RUNTIME_MODE=development
LANGSMITH_TRACING=false

### run below command to run integration test
npm run test:integration -- tests/integration --reporter=verbose
