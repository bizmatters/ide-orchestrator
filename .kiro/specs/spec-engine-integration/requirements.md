# Requirements Document - IDE Orchestrator Spec Engine Integration

## Introduction

This document specifies the requirements for integrating the IDE Orchestrator service with the Spec Engine service (deepagents-runtime) to enable AI-powered workflow specification generation and refinement. This integration enables the Agentic IDE to provide real-time streaming updates during specification processing while maintaining secure communication patterns within the zerotouch-platform cluster.

The integration follows a hybrid architecture where IDE Orchestrator acts as a secure proxy between the frontend and the Spec Engine, providing JWT authentication, WebSocket proxying, and final state management.

## Glossary

- **IDE_Orchestrator**: The Go-based REST API service managing workflow specifications and user interactions
- **Spec_Engine**: The Python-based service (deepagents-runtime) that processes specification generation using LangGraph and deepagents framework
- **Constitutional_Refinement**: The AI-powered process for generating and refining workflow specifications
- **Thread_ID**: Unique identifier for a Spec Engine execution session
- **Proposal**: A generated specification change awaiting user approval
- **WebSocket_Proxy**: Secure proxying of WebSocket connections with JWT authentication
- **Zerotouch_Platform**: The Kubernetes platform providing infrastructure abstraction via Crossplane XRDs

## Requirements

### Requirement 1

**User Story:** As a System Integrator, I want the Spec Engine to expose HTTP and WebSocket endpoints, so that IDE Orchestrator can initiate executions and stream real-time updates.

#### Acceptance Criteria

1. THE Spec_Engine SHALL expose a REST endpoint `POST /spec-engine/invoke` to initiate agent execution with job parameters
2. THE Spec_Engine SHALL return a unique thread_id when execution is initiated successfully
3. THE Spec_Engine SHALL expose a WebSocket endpoint `GET /spec-engine/stream/{thread_id}` for real-time event streaming
4. THE Spec_Engine SHALL expose a REST endpoint `GET /spec-engine/state/{thread_id}` to retrieve final execution state
5. THE Spec_Engine SHALL emit events in the format `{"event_type": "...", "data": {...}}` via WebSocket

### Requirement 2

**User Story:** As a Frontend Developer, I want IDE Orchestrator to proxy WebSocket connections securely, so that the frontend can receive real-time updates without direct access to internal services.

#### Acceptance Criteria

1. THE IDE_Orchestrator SHALL provide a WebSocket endpoint `GET /api/ws/refinements/{thread_id}` that proxies to Spec Engine
2. THE IDE_Orchestrator SHALL validate JWT tokens before establishing WebSocket proxy connections
3. THE IDE_Orchestrator SHALL ensure only authorized users can access specific thread_id streams
4. THE IDE_Orchestrator SHALL maintain the WebSocket connection until the Spec Engine emits an "end" event
5. THE IDE_Orchestrator SHALL handle WebSocket connection failures gracefully with retry logic

### Requirement 3

**User Story:** As a Business Logic Manager, I want IDE Orchestrator to extract final proposals from streaming events, so that specification changes can be stored and managed in the database.

#### Acceptance Criteria

1. THE IDE_Orchestrator SHALL monitor WebSocket events for `event_type: "on_state_update"` containing a "files" field
2. THE IDE_Orchestrator SHALL extract the final files object from the last `on_state_update` event before the `end` event
3. THE IDE_Orchestrator SHALL store the extracted files as `generated_files` JSONB in the proposals table
4. THE IDE_Orchestrator SHALL update proposal status to "completed" when the `end` event is received
5. THE IDE_Orchestrator SHALL handle execution failures by updating proposal status to "failed" with error details

### Requirement 4

**User Story:** As a Database Administrator, I want IDE Orchestrator to use a separate PostgreSQL database, so that workflow data is isolated from Spec Engine execution data.

#### Acceptance Criteria

1. THE IDE_Orchestrator SHALL connect to a PostgreSQL database named `ide_orchestrator` 
2. THE Spec_Engine SHALL connect to a PostgreSQL database named `deepagents_runtime`
3. THE Zerotouch_Platform SHALL provision both databases using the same PostgreSQL instance via Crossplane XRD
4. THE IDE_Orchestrator SHALL store proposals with thread_id linking to Spec Engine executions
5. THE IDE_Orchestrator SHALL clean up Spec Engine checkpointer data after proposal resolution

### Requirement 5

**User Story:** As a Platform Engineer, I want both services deployed using Crossplane XRDs, so that infrastructure is managed consistently through GitOps.

#### Acceptance Criteria

1. THE Spec_Engine SHALL be deployed using the existing EventDrivenService XRD with NATS JetStream integration
2. THE IDE_Orchestrator SHALL be deployed using a new WebService XRD with HTTP ingress and PostgreSQL database
3. THE WebService XRD SHALL provision Deployment, Service, HTTPRoute, and PostgreSQL database resources
4. THE WebService XRD SHALL support the same secret management pattern as EventDrivenService (secret1Name through secret5Name)
5. THE WebService XRD SHALL support resource sizing presets (micro/small/medium/large) for consistent resource allocation

### Requirement 6

**User Story:** As a Security Engineer, I want all communication to be secured within the cluster, so that sensitive specification data is protected.

#### Acceptance Criteria

1. THE Spec_Engine SHALL be accessible only within the Kubernetes cluster with no external exposure
2. THE IDE_Orchestrator SHALL authenticate all API requests using JWT tokens before proxying to Spec Engine
3. THE IDE_Orchestrator SHALL validate user authorization for specific workflow and thread_id access
4. THE IDE_Orchestrator SHALL be exposed externally via HTTPRoute with TLS termination
5. THE IDE_Orchestrator SHALL implement CORS policies to restrict frontend domain access

### Requirement 7

**User Story:** As a Frontend Developer, I want a complete refinement workflow API, so that the UI can initiate, monitor, and manage specification changes.

#### Acceptance Criteria

1. THE IDE_Orchestrator SHALL provide `POST /api/workflows/{id}/refinements` to initiate specification refinement
2. THE IDE_Orchestrator SHALL return thread_id and proposal_id immediately upon refinement initiation
3. THE IDE_Orchestrator SHALL provide `POST /api/proposals/{id}/approve` to apply approved changes to drafts
4. THE IDE_Orchestrator SHALL provide `POST /api/proposals/{id}/reject` to discard rejected proposals
5. THE IDE_Orchestrator SHALL provide `GET /api/proposals/{id}` to retrieve proposal details and generated files

### Requirement 8

**User Story:** As a DevOps Engineer, I want comprehensive observability, so that I can monitor the integration health and performance.

#### Acceptance Criteria

1. THE IDE_Orchestrator SHALL implement OpenTelemetry tracing for all Spec Engine integration calls
2. THE IDE_Orchestrator SHALL expose Prometheus metrics for WebSocket proxy connections and proposal processing
3. THE IDE_Orchestrator SHALL log all refinement workflow events with structured logging
4. THE Spec_Engine SHALL implement health check endpoints for Kubernetes readiness and liveness probes
5. THE integration SHALL provide distributed tracing across both services for end-to-end request tracking

### Requirement 9

**User Story:** As a Quality Assurance Engineer, I want comprehensive testing coverage, so that the integration is reliable and maintainable.

#### Acceptance Criteria

1. THE IDE_Orchestrator SHALL have unit tests for WebSocket proxy functionality and event processing
2. THE Spec_Engine SHALL have integration tests validating HTTP and WebSocket endpoint functionality
3. THE integration SHALL have end-to-end tests covering the complete refinement workflow
4. THE WebService XRD SHALL have validation tests ensuring proper resource provisioning
5. THE integration SHALL have performance tests validating WebSocket streaming under load

### Requirement 10

**User Story:** As a System Administrator, I want proper error handling and recovery, so that the system remains stable under failure conditions.

#### Acceptance Criteria

1. THE IDE_Orchestrator SHALL implement circuit breaker patterns for Spec Engine communication
2. THE IDE_Orchestrator SHALL handle Spec Engine service unavailability gracefully with appropriate error messages
3. THE IDE_Orchestrator SHALL implement exponential backoff retry logic for transient failures
4. THE IDE_Orchestrator SHALL clean up orphaned proposals when Spec Engine executions fail
5. THE IDE_Orchestrator SHALL provide clear error messages to the frontend for all failure scenarios