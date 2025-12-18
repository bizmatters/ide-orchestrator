### Component Architecture

#### API Gateway Service (Go)
- **Responsibility**: Authoritative transactional state manager for workflow specifications and secure WebSocket proxy to Deepagents Runtime Service
- **Technology Stack**: Go + Gin framework + pgx driver + golang-migrate/migrate + Gorilla WebSocket
- **Pattern**: REST API with WebSocket proxy capabilities, direct database operations and connection pooling
- **Key Features**: JWT authentication, workflow locking, proposal management, secure WebSocket proxy, REST API integration, OpenTelemetry tracing
- **Integration**: Connects to Deepagents Runtime Service via internal cluster communication and WebSocket proxying

#### Deepagents Runtime Service (Python)
- **Responsibility**: Intelligent specification processing using deepagents framework 
- **Technology Stack**: Python + deepagents + LangGraph + DragonFly + PostgresSaver checkpointer
- **Pattern**: Asynchronous multi-agent processing with real-time streaming via WebSocket
- **Key Features**: deterministic compilation tools, state persistence
- **Integration**: Accessed by Build API via secure proxy pattern with internal-only cluster access

## zerotouch-platform (Talos + Kube)
- Provides the runtime environment for the API Gateway Service and Deepagents Runtime Service
- Deepagents Runtime Service uses zerotouch-platform/platform/04-apis/event-driven-service as abstratcion claim to deploy the runtime service. This is already available.
- API Gateway Service should uses zerotouch-platform/platform/04-apis/webservice as abstratcion claim to deploy the runtime service. This is yet to be implemented.

