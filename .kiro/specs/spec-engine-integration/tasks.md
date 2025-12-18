# Implementation Plan - IDE Orchestrator Spec Engine Integration

## Task Overview

This implementation plan converts the Spec Engine integration design into actionable coding tasks. The tasks are sequenced to build incrementally, starting with Spec Engine API endpoints, then WebService XRD, and finally IDE Orchestrator integration.

## Task List

- [ ] 1. Implement Spec Engine HTTP and WebSocket API endpoints
  - Add FastAPI endpoints for `/spec-engine/invoke`, `/spec-engine/state/{thread_id}`, and WebSocket `/spec-engine/stream/{thread_id}`
  - Implement CloudEvent parsing and job execution workflow
  - Add WebSocket event streaming with proper event format
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_

- [ ] 1.1 Add FastAPI HTTP endpoints to deepagents-runtime
  - Create `POST /spec-engine/invoke` endpoint that accepts JobExecutionEvent and returns thread_id
  - Create `GET /spec-engine/state/{thread_id}` endpoint that returns final execution state
  - Add request/response models for JobRequest, ExecutionState, and error handling
  - _Requirements: 1.1, 1.2, 1.4_

- [ ] 1.2 Implement WebSocket streaming endpoint
  - Create `GET /spec-engine/stream/{thread_id}` WebSocket endpoint
  - Stream LangGraph events in real-time with format `{"event_type": "...", "data": {...}}`
  - Ensure "files" field is included in `on_state_update` events
  - Emit final `end` event when execution completes
  - _Requirements: 1.3, 1.5_

- [ ] 1.3 Add health check endpoints for Kubernetes probes
  - Implement `/health` endpoint for liveness probe
  - Implement `/ready` endpoint for readiness probe with dependency checks
  - Add OpenTelemetry tracing and Prometheus metrics
  - _Requirements: 8.4_

- [ ] 2. Create WebService Crossplane XRD for HTTP services
  - Design XRD schema with image, port, size, database, secrets, and ingress configuration
  - Create Composition that provisions Deployment, Service, HTTPRoute, and PostgreSQL database
  - Implement resource sizing presets (micro/small/medium/large) matching EventDrivenService
  - Add secret management pattern with secret1Name through secret5Name slots
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5_

- [ ] 2.1 Design WebService XRD schema
  - Create CompositeResourceDefinition with required fields (image, port) and optional fields (size, hostname, pathPrefix)
  - Add database configuration (databaseName) and secret management (secret1Name-secret5Name)
  - Include ingress configuration (hostname, pathPrefix) for external access
  - Add validation rules and examples for all fields
  - _Requirements: 5.2, 5.4_

- [ ] 2.2 Implement WebService Composition
  - Create Composition that provisions Kubernetes Deployment with resource sizing
  - Add ClusterIP Service for internal communication
  - Create HTTPRoute for Gateway API ingress with TLS termination
  - Provision PostgreSQL database using existing database XRD
  - _Requirements: 5.1, 5.3, 5.5_

- [ ] 2.3 Add WebService examples and tests
  - Create example WebService claims for different configurations
  - Add validation tests for XRD schema and Composition
  - Test resource provisioning and cleanup
  - _Requirements: 9.4_

- [ ] 3. Enhance IDE Orchestrator with Spec Engine integration
  - Add Spec Engine client with HTTP and WebSocket communication
  - Implement WebSocket proxy with JWT authentication and authorization
  - Add hybrid event processing to extract final files from streaming events
  - Extend database schema with proposals table and related models
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 3.4, 3.5_

- [ ] 3.1 Create Spec Engine client library
  - Implement SpecEngineClient with Invoke(), StreamWebSocket(), and GetState() methods
  - Add proper error handling, timeouts, and retry logic
  - Include OpenTelemetry tracing for all Spec Engine communication
  - Add circuit breaker pattern for resilience
  - _Requirements: 2.1, 8.1, 10.1, 10.3_

- [ ] 3.2 Implement WebSocket proxy handler
  - Create `/api/ws/refinements/{thread_id}` WebSocket endpoint
  - Add JWT authentication and thread_id authorization
  - Implement bidirectional WebSocket proxying between frontend and Spec Engine
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

- [ ] 4. Implement refinement workflow API endpoints
  - Add POST /api/workflows/{id}/refinements to initiate specification refinement
  - Add GET /api/proposals/{id} to retrieve proposal details and generated files
  - Add POST /api/proposals/{id}/approve and POST /api/proposals/{id}/reject for proposal management
  - Integrate with existing draft and version management system
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ] 4.1 Add refinement initiation endpoint
  - Create `POST /api/workflows/{id}/refinements` endpoint
  - Validate user access to workflow and create draft if needed
  - Call Spec Engine to initiate execution and return thread_id and proposal_id
  - Add proper error handling for Spec Engine unavailability
  - _Requirements: 7.1, 7.2, 10.2_

- [ ] 4.2 Add proposal management endpoints
  - Create `GET /api/proposals/{id}` endpoint to retrieve proposal details
  - Create `POST /api/proposals/{id}/approve` to apply changes to draft
  - Create `POST /api/proposals/{id}/reject` to discard proposal
  - Add authorization checks for proposal access
  - _Requirements: 7.3, 7.4, 7.5, 6.3_

- [ ] 4.3 Integrate with draft management system
  - Update draft files when proposals are approved
  - Clean up Spec Engine checkpointer data after proposal resolution
  - Maintain audit trail of proposal decisions
  - Handle concurrent proposal management
  - _Requirements: 4.5, 10.4_

- [ ] 5. Add comprehensive observability and monitoring
  - Implement OpenTelemetry distributed tracing across both services
  - Add Prometheus metrics for WebSocket connections, proposal processing, and Spec Engine communication
  - Add structured logging for all integration events
  - Create health check endpoints and monitoring dashboards
  - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

- [ ] 5.1 Implement distributed tracing
  - Add OpenTelemetry instrumentation to IDE Orchestrator Spec Engine client
  - Ensure trace context propagation through WebSocket proxy
  - Add tracing to all refinement workflow operations
  - Create trace correlation between frontend requests and Spec Engine execution
  - _Requirements: 8.1, 8.5_

- [ ] 5.2 Add Prometheus metrics
  - Create metrics for refinement duration, WebSocket connections, and Spec Engine requests
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
  - Implement circuit breaker pattern for Spec Engine communication
  - Add graceful handling of Spec Engine service unavailability
  - Create user-friendly error messages for all failure scenarios
  - Add exponential backoff retry logic for transient failures
  - _Requirements: 10.1, 10.2, 10.3, 10.5_

- [ ] 7. Create comprehensive test suite
  - Add unit tests for WebSocket proxy and event processing
  - Create integration tests for complete refinement workflow
  - Add end-to-end tests covering frontend to Spec Engine communication
  - Implement performance tests for WebSocket streaming under load
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5_

- [ ] 7.1 Add unit tests for integration components
  - Test SpecEngineClient HTTP and WebSocket communication
  - Test WebSocket proxy functionality and error handling
  - Test hybrid event processing and file extraction
  - Test proposal management and database operations
  - _Requirements: 9.1_

- [ ] 7.2 Create integration tests
  - Test complete refinement workflow from initiation to completion
  - Test WebSocket streaming with mock Spec Engine
  - Test error scenarios and recovery mechanisms
  - Test concurrent proposal processing
  - _Requirements: 9.2, 9.3_

- [ ] 7.3 Add end-to-end tests
  - Test frontend WebSocket connection through IDE Orchestrator to Spec Engine
  - Test proposal approval and draft update workflow
  - Test authentication and authorization flows
  - Test error handling and user experience
  - _Requirements: 9.3_

- [ ] 8. Deploy and validate integration
  - Deploy Spec Engine using EventDrivenService XRD with new endpoints
  - Deploy IDE Orchestrator using WebService XRD with database and ingress
  - Validate end-to-end integration in zerotouch-platform cluster
  - Perform load testing and performance validation
  - _Requirements: 5.1, 5.2, 9.5_

- [ ] 8.1 Deploy Spec Engine with new endpoints
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

- [ ] 9. Final checkpoint - Ensure all tests pass and integration is complete
  - Ensure all tests pass, ask the user if questions arise.

## Implementation Notes

### Database Migration Strategy
- IDE Orchestrator will use `ide_orchestrator` database
- Spec Engine will use `deepagents_runtime` database  
- Both databases provisioned from same PostgreSQL instance via Crossplane
- Migration scripts will handle schema evolution

### Security Considerations
- All Spec Engine communication happens within cluster (no external exposure)
- JWT authentication required for all IDE Orchestrator endpoints
- WebSocket connections authenticated via JWT token
- CORS policies restrict frontend domain access

### Performance Requirements
- WebSocket streaming should handle real-time events without buffering delays
- Proposal processing should complete within 30 seconds of Spec Engine completion
- System should support up to 10 concurrent refinement sessions
- Database operations should complete within 100ms for typical queries

### Error Recovery
- Circuit breaker prevents cascade failures when Spec Engine is unavailable
- WebSocket reconnection logic handles temporary network issues
- Orphaned proposals are cleaned up after 24 hours
- Failed executions are retried up to 3 times with exponential backoff