# Implementation Plan - IDE Orchestrator deepagents-runtime Integration

## Task Overview

This implementation plan converts the deepagents-runtime integration design into actionable coding tasks. The tasks are sequenced to build incrementally with multiple checkpoints for validation and review. Each checkpoint represents a deliverable milestone with concrete verification criteria.

## Task List

### Phase 1: deepagents-runtime API Foundation

- [x] 1. Implement deepagents-runtime HTTP and WebSocket API endpoints
  - Add FastAPI endpoints for `/deepagents-runtime/invoke`, `/deepagents-runtime/state/{thread_id}`, and WebSocket `/deepagents-runtime/stream/{thread_id}`
  - Implement CloudEvent parsing and job execution workflow
  - Add WebSocket event streaming with proper event format
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [x] 1.1 Add FastAPI HTTP endpoints to deepagents-runtime
  - Create `POST /deepagents-runtime/invoke` endpoint that accepts JobExecutionEvent and returns thread_id
  - Create `GET /deepagents-runtime/state/{thread_id}` endpoint that returns final execution state
  - Add request/response models for JobRequest, ExecutionState, and error handling
  - _Requirements: 1.1, 1.2, 1.4_

- [x] 1.2 Implement WebSocket streaming endpoint
  - Create `GET /deepagents-runtime/stream/{thread_id}` WebSocket endpoint
  - Stream LangGraph events in real-time with format `{"event_type": "...", "data": {...}}`
  - Ensure "files" field is included in `on_state_update` events
  - Emit final `end` event when execution completes
  - _Requirements: 1.3, 1.5_

- [x] 1.3 Add health check endpoints for Kubernetes probes
  - Implement `/health` endpoint for liveness probe
  - Implement `/ready` endpoint for readiness probe with dependency checks
  - Add OpenTelemetry tracing and Prometheus metrics
  - _Requirements: 8.4_

- [x] **CHECKPOINT 1: deepagents-runtime API Validation**
  - **Deliverable**: Functional deepagents-runtime API with HTTP and WebSocket endpoints
  - **Verification Criteria**:
    - `POST /deepagents-runtime/invoke` returns valid thread_id for test job
    - `GET /deepagents-runtime/state/{thread_id}` returns execution status
    - WebSocket `/deepagents-runtime/stream/{thread_id}` streams events in correct format
    - Health endpoints `/health` and `/ready` return 200 OK
    - All endpoints handle errors gracefully with proper HTTP status codes
  - **Test Script**: Create integration test that invokes a simple job, streams events, and verifies final state
  - **Success Criteria**: All API endpoints functional and returning expected data structures

### Phase 2: Infrastructure Foundation

- [x] 2. Create WebService Crossplane XRD for HTTP services
  - Design XRD schema with image, port, size, database, secrets, and ingress configuration
  - Create Composition that provisions Deployment, Service, HTTPRoute, and PostgreSQL database
  - Implement resource sizing presets (micro/small/medium/large) matching EventDrivenService
  - Add secret management pattern with secret1Name through secret5Name slots
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [x] 2.1 Design WebService XRD schema
  - Create CompositeResourceDefinition with required fields (image, port) and optional fields (size, hostname, pathPrefix)
  - Add database configuration (databaseName) and secret management (secret1Name-secret5Name)
  - Include ingress configuration (hostname, pathPrefix) for external access
  - Add validation rules and examples for all fields
  - _Requirements: 5.2, 5.4_

- [x] 2.2 Implement WebService Composition
  - Create Composition that provisions Kubernetes Deployment with resource sizing
  - Add ClusterIP Service for internal communication
  - Create HTTPRoute for Gateway API ingress with TLS termination
  - Provision PostgreSQL database using existing database XRD
  - _Requirements: 5.1, 5.3, 5.5_

- [x] 2.3 Add WebService examples and tests
  - Create example WebService claims for different configurations
  - Add validation tests for XRD schema and Composition
  - Test resource provisioning and cleanup
  - _Requirements: 9.4_

- [x] **CHECKPOINT 2: Infrastructure Provisioning Validation**
  - **Deliverable**: Working WebService XRD that can provision HTTP services with databases
  - **Verification Criteria**:
    - WebService XRD validates against Kubernetes API server
    - Test WebService claim successfully provisions all resources (Deployment, Service, HTTPRoute, PostgreSQL)
    - Database connectivity works from provisioned pods
    - HTTPRoute provides external access with TLS termination
    - Resource sizing presets allocate correct CPU/memory limits
    - Secret injection works for all 5 secret slots
  - **Test Script**: Deploy test WebService claim and verify all resources are created and functional
  - **Success Criteria**: Complete infrastructure stack provisioned and accessible via HTTPS
  - **Completion Notes**: ✅ All verification criteria validated successfully. WebService XRD, Composition, and resource provisioning confirmed working. Schema validation, resource sizing, and secret injection patterns all functional.
  - **Status**: COMPLETED - Infrastructure foundation ready for IDE Orchestrator integration.

### Phase 3: IDE Orchestrator Core Integration

- [ ] 3. Enhance IDE Orchestrator with deepagents-runtime integration
  - Add deepagents-runtime client with HTTP and WebSocket communication
  - Implement WebSocket proxy with JWT authentication and authorization
  - Add hybrid event processing to extract final files from streaming events
  - Extend database schema with proposals table and related models
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 3.1 Create deepagents-runtime client library
  - Implement DeepAgentsRuntimeClient with Invoke(), StreamWebSocket(), and GetState() methods
  - Add proper error handling, timeouts, and retry logic
  - Include OpenTelemetry tracing for all deepagents-runtime communication
  - Add circuit breaker pattern for resilience
  - _Requirements: 2.1, 8.1, 10.1, 10.3_

- [ ] 3.2 Implement WebSocket proxy handler
  - Create `/api/ws/refinements/{thread_id}` WebSocket endpoint
  - Add JWT authentication and thread_id authorization
  - Implement bidirectional WebSocket proxying between frontend and deepagents-runtime
  - Add connection management and graceful error handling
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 6.1, 6.2, 6.3_

- [ ] 3.3 Add hybrid event processing
  - Monitor WebSocket events for `on_state_update` with "files" field
  - Extract final files object from last `on_state_update` before `end` event
  - Update proposal status and generated_files in database
  - Handle execution failures and error states
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 3.4 Extend database schema for proposals
  - Add proposals table with thread_id, status, user_prompt, and generated_files fields
  - Create proposal_access table for user authorization
  - Add database migrations and indexes
  - Update existing models and repository methods
  - _Requirements: 4.1, 4.4_

- [ ] **CHECKPOINT 3: Core Integration Validation**
  - **Deliverable**: IDE Orchestrator with functional deepagents-runtime client and WebSocket proxy
  - **Verification Criteria**:
    - DeepAgentsRuntimeClient successfully invokes deepagents-runtime and receives thread_id
    - WebSocket proxy authenticates JWT tokens and authorizes thread access
    - Hybrid event processing extracts files from streaming events and updates database
    - Database schema migrations apply successfully with all indexes
    - Circuit breaker prevents cascade failures when deepagents-runtime is unavailable
  - **Test Script**: Integration test that creates proposal, streams events through proxy, and verifies database updates
  - **Success Criteria**: Complete WebSocket proxy workflow functional with database persistence

### Phase 4: Refinement Workflow API

- [ ] 4. Implement refinement workflow API endpoints
  - Add POST /api/workflows/{id}/refinements to initiate specification refinement
  - Add GET /api/proposals/{id} to retrieve proposal details and generated files
  - Add POST /api/proposals/{id}/approve and POST /api/proposals/{id}/reject for proposal management
  - Integrate with existing draft and version management system
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 4.1 Add refinement initiation endpoint
  - Create `POST /api/workflows/{id}/refinements` endpoint
  - Validate user access to workflow and create draft if needed
  - Call deepagents-runtime to initiate execution and return thread_id and proposal_id
  - Add proper error handling for deepagents-runtime unavailability
  - _Requirements: 7.1, 7.2, 10.2_

- [ ] 4.2 Add proposal management endpoints
  - Create `GET /api/proposals/{id}` endpoint to retrieve proposal details
  - Create `POST /api/proposals/{id}/approve` to apply changes to draft
  - Create `POST /api/proposals/{id}/reject` to discard proposal
  - Add authorization checks for proposal access
  - _Requirements: 7.3, 7.4, 7.5, 6.3_

- [ ] 4.3 Integrate with draft management system
  - Update draft files when proposals are approved
  - Clean up deepagents-runtime checkpointer data after proposal resolution
  - Maintain audit trail of proposal decisions
  - Handle concurrent proposal management
  - _Requirements: 4.5, 10.4_

- [ ] **CHECKPOINT 4: API Workflow Validation**
  - **Deliverable**: Complete refinement workflow API with proposal management
  - **Verification Criteria**:
    - `POST /api/workflows/{id}/refinements` creates proposal and returns thread_id
    - `GET /api/proposals/{id}` returns complete proposal with generated files
    - `POST /api/proposals/{id}/approve` successfully applies changes to draft
    - `POST /api/proposals/{id}/reject` discards proposal and cleans up resources
    - Authorization prevents unauthorized access to proposals
    - Concurrent proposal handling works without data corruption
  - **Test Script**: End-to-end API test covering complete refinement lifecycle
  - **Success Criteria**: Full proposal workflow functional via REST API

### Phase 5: Observability and Monitoring

- [ ] 5. Add comprehensive observability and monitoring
  - Implement OpenTelemetry distributed tracing across both services
  - Add Prometheus metrics for WebSocket connections, proposal processing, and deepagents-runtime communication
  - Add structured logging for all integration events
  - Create health check endpoints and monitoring dashboards
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 5.1 Implement distributed tracing
  - Add OpenTelemetry instrumentation to IDE Orchestrator deepagents-runtime client
  - Ensure trace context propagation through WebSocket proxy
  - Add tracing to all refinement workflow operations
  - Create trace correlation between frontend requests and deepagents-runtime execution
  - _Requirements: 8.1, 8.5_

- [ ] 5.2 Add Prometheus metrics
  - Create metrics for refinement duration, WebSocket connections, and deepagents-runtime requests
  - Add business metrics for proposal approval rates and user activity
  - Implement metrics collection for error rates and performance
  - Expose metrics endpoint for Prometheus scraping
  - _Requirements: 8.2_

- [ ] 5.3 Implement structured logging
  - Add structured logging for all refinement workflow events
  - Log WebSocket proxy connections and disconnections
  - Include correlation IDs for request tracking
  - Add error context and stack traces for debugging
  - _Requirements: 8.3_

- [ ] **CHECKPOINT 5: Observability Validation**
  - **Deliverable**: Complete observability stack with tracing, metrics, and logging
  - **Verification Criteria**:
    - OpenTelemetry traces span across IDE Orchestrator and deepagents-runtime
    - Prometheus metrics endpoint exposes all defined metrics with correct labels
    - Structured logs contain correlation IDs and proper context
    - Distributed tracing shows complete request flow from frontend to deepagents-runtime
    - Metrics accurately reflect system behavior (connection counts, durations, error rates)
  - **Test Script**: Generate load and verify all observability data is collected correctly
  - **Success Criteria**: Full observability stack operational with meaningful data

### Phase 6: Security and Error Handling

- [ ] 6. Implement security and error handling
  - Add JWT authentication for all API endpoints
  - Implement CORS policies for frontend domain restrictions
  - Add comprehensive error handling with user-friendly messages
  - Implement rate limiting and request validation
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 10.1, 10.2, 10.3, 10.4, 10.5_

- [ ] 6.1 Add JWT authentication and authorization
  - Validate JWT tokens for all API endpoints
  - Implement user authorization for workflow and proposal access
  - Add WebSocket JWT authentication via query parameter or header
  - Create middleware for consistent authentication across endpoints
  - _Requirements: 6.2, 6.3_

- [ ] 6.2 Implement CORS and security policies
  - Configure CORS to allow only authorized frontend domains
  - Add security headers and request validation
  - Implement rate limiting for API endpoints
  - Add input sanitization and validation
  - _Requirements: 6.5_

- [ ] 6.3 Add comprehensive error handling
  - Implement circuit breaker pattern for deepagents-runtime communication
  - Add graceful handling of deepagents-runtime service unavailability
  - Create user-friendly error messages for all failure scenarios
  - Add exponential backoff retry logic for transient failures
  - _Requirements: 10.1, 10.2, 10.3, 10.5_

- [ ] **CHECKPOINT 6: Security and Resilience Validation**
  - **Deliverable**: Secure and resilient integration with comprehensive error handling
  - **Verification Criteria**:
    - JWT authentication blocks unauthorized requests with 401/403 responses
    - CORS policies prevent cross-origin requests from unauthorized domains
    - Rate limiting prevents abuse with 429 responses
    - Circuit breaker opens after consecutive failures and recovers automatically
    - Error messages are user-friendly and don't expose internal details
    - Exponential backoff retry logic handles transient failures gracefully
  - **Test Script**: Security and resilience test suite covering authentication, authorization, rate limiting, and failure scenarios
  - **Success Criteria**: System secure and resilient under various failure conditions

### Phase 7: Comprehensive Testing

- [ ] 7. Create comprehensive test suite
  - Add unit tests for WebSocket proxy and event processing
  - Create integration tests for complete refinement workflow
  - Add end-to-end tests covering frontend to deepagents-runtime communication
  - Implement performance tests for WebSocket streaming under load
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 7.1 Add unit tests for integration components
  - Test DeepAgentsRuntimeClient HTTP and WebSocket communication
  - Test WebSocket proxy functionality and error handling
  - Test hybrid event processing and file extraction
  - Test proposal management and database operations
  - _Requirements: 9.1_

- [ ] 7.2 Create integration tests
  - Test complete refinement workflow from initiation to completion
  - Test WebSocket streaming with mock deepagents-runtime
  - Test error scenarios and recovery mechanisms
  - Test concurrent proposal processing
  - _Requirements: 9.2, 9.3_

- [ ] 7.3 Add end-to-end tests
  - Test frontend WebSocket connection through IDE Orchestrator to deepagents-runtime
  - Test proposal approval and draft update workflow
  - Test authentication and authorization flows
  - Test error handling and user experience
  - _Requirements: 9.3_

- [ ] **CHECKPOINT 7: Testing Validation**
  - **Deliverable**: Comprehensive test suite with high coverage and reliability
  - **Verification Criteria**:
    - Unit tests achieve >90% code coverage for integration components
    - Integration tests validate complete workflows with mock dependencies
    - End-to-end tests pass against real services in test environment
    - Performance tests validate WebSocket streaming under 10 concurrent connections
    - All tests pass consistently in CI/CD pipeline
    - Test suite runs in <5 minutes for fast feedback
  - **Test Script**: Full test suite execution with coverage reporting
  - **Success Criteria**: Comprehensive test coverage with reliable, fast-running tests

### Phase 8: Production Deployment

- [ ] 8. Deploy and validate integration
  - Deploy deepagents-runtime using EventDrivenService XRD with new endpoints
  - Deploy IDE Orchestrator using WebService XRD with database and ingress
  - Validate end-to-end integration in zerotouch-platform cluster
  - Perform load testing and performance validation
  - _Requirements: 5.1, 5.2, 9.5_

- [ ] 8.1 Deploy deepagents-runtime with new endpoints
  - Update deepagents-runtime deployment to include new FastAPI endpoints
  - Configure EventDrivenService claim with proper resource sizing
  - Validate health checks and service discovery
  - Test WebSocket endpoint accessibility within cluster
  - _Requirements: 5.1_

- [ ] 8.2 Deploy IDE Orchestrator using WebService XRD
  - Create WebService claim for IDE Orchestrator with database and secrets
  - Configure HTTPRoute for external access with TLS
  - Validate database connectivity and secret injection
  - Test external API access and CORS configuration
  - _Requirements: 5.2_

- [ ] 8.3 Validate end-to-end integration
  - Test complete refinement workflow from frontend through both services
  - Validate WebSocket streaming performance and reliability
  - Test proposal management and database consistency
  - Perform security validation and penetration testing
  - _Requirements: 9.3, 9.5_

- [ ] **CHECKPOINT 8: Production Deployment Validation**
  - **Deliverable**: Fully deployed and operational integration in production environment
  - **Verification Criteria**:
    - deepagents-runtime deployed with all endpoints accessible within cluster
    - IDE Orchestrator deployed with external HTTPS access and database connectivity
    - End-to-end refinement workflow functional from external frontend
    - WebSocket streaming performs reliably under production load
    - Security validation passes with no critical vulnerabilities
    - Performance meets requirements (30s proposal processing, 10 concurrent sessions)
  - **Test Script**: Production validation suite covering functionality, performance, and security
  - **Success Criteria**: Production system fully operational and meeting all performance requirements

### Final Validation

- [ ] 9. **FINAL CHECKPOINT: Complete Integration Validation**
  - **Deliverable**: Production-ready IDE Orchestrator deepagents-runtime integration
  - **Verification Criteria**:
    - All previous checkpoints completed successfully
    - Full refinement workflow operational from frontend to deepagents-runtime
    - All tests passing in CI/CD pipeline
    - Production deployment stable and performant
    - Documentation complete and up-to-date
    - Monitoring and alerting functional
  - **Test Script**: Complete system validation including user acceptance testing
  - **Success Criteria**: System ready for production use with all requirements satisfied
  - Ensure all tests pass, ask the user if questions arise.

## Implementation Notes

### Database Migration Strategy
- IDE Orchestrator will use `ide_orchestrator` database
- deepagents-runtime will use `deepagents_runtime` database  
- Both databases provisioned from same PostgreSQL instance via Crossplane
- Migration scripts will handle schema evolution

### Security Considerations
- All deepagents-runtime communication happens within cluster (no external exposure)
- JWT authentication required for all IDE Orchestrator endpoints
- WebSocket connections authenticated via JWT token
- CORS policies restrict frontend domain access

### Performance Requirements
- WebSocket streaming should handle real-time events without buffering delays
- Proposal processing should complete within 30 seconds of deepagents-runtime completion
- System should support up to 10 concurrent refinement sessions
- Database operations should complete within 100ms for typical queries

### Error Recovery
- Circuit breaker prevents cascade failures when deepagents-runtime is unavailable
- WebSocket reconnection logic handles temporary network issues
- Orphaned proposals are cleaned up after 24 hours
- Failed executions are retried up to 3 times with exponential backoff