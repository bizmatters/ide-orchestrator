"""
Prometheus metrics for IDE Orchestrator.

This module provides the same metrics as the Go implementation to ensure
Grafana dashboards continue working after the Python migration.

Based on archived/internal/metrics package patterns.
"""

from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time
from typing import Optional
from contextlib import contextmanager


# Metrics matching the Go implementation
agent_builder_jobs_created = Counter(
    'agent_builder_jobs_created_total',
    'Total number of agent builder jobs created',
    ['job_type', 'status']
)

agent_builder_job_duration = Histogram(
    'agent_builder_job_duration_seconds',
    'Duration of agent builder job processing',
    ['job_type', 'status'],
    buckets=[0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0]
)

agent_builder_jobs_active = Gauge(
    'agent_builder_jobs_active',
    'Number of currently active agent builder jobs',
    ['job_type']
)

# WebSocket proxy metrics (from design.md requirements)
ide_orchestrator_websocket_connections = Gauge(
    'ide_orchestrator_websocket_connections',
    'Active WebSocket proxy connections',
    ['thread_id']
)

ide_orchestrator_refinement_duration = Histogram(
    'ide_orchestrator_refinement_duration_seconds',
    'Duration of refinement workflows',
    ['status'],
    buckets=[1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0, 600.0]
)

ide_orchestrator_deepagents_requests = Counter(
    'ide_orchestrator_deepagents_runtime_requests_total',
    'Total requests to deepagents-runtime',
    ['endpoint', 'status']
)


class MetricsManager:
    """Manager for Prometheus metrics with context managers for timing."""
    
    def __init__(self):
        self._metrics_server_started = False
    
    def start_metrics_server(self, port: int = 8090) -> None:
        """Start Prometheus metrics HTTP server."""
        if not self._metrics_server_started:
            start_http_server(port)
            self._metrics_server_started = True
    
    def record_job_created(self, job_type: str, status: str = "created") -> None:
        """Record a new job creation."""
        agent_builder_jobs_created.labels(job_type=job_type, status=status).inc()
        agent_builder_jobs_active.labels(job_type=job_type).inc()
    
    def record_job_completed(self, job_type: str, status: str, duration: float) -> None:
        """Record job completion with duration."""
        agent_builder_job_duration.labels(job_type=job_type, status=status).observe(duration)
        agent_builder_jobs_active.labels(job_type=job_type).dec()
    
    @contextmanager
    def time_job(self, job_type: str):
        """Context manager for timing job execution."""
        start_time = time.time()
        self.record_job_created(job_type)
        
        try:
            yield
            # Job succeeded
            duration = time.time() - start_time
            self.record_job_completed(job_type, "completed", duration)
        except Exception as e:
            # Job failed
            duration = time.time() - start_time
            self.record_job_completed(job_type, "failed", duration)
            raise
    
    def record_websocket_connection(self, thread_id: str) -> None:
        """Record new WebSocket connection."""
        ide_orchestrator_websocket_connections.labels(thread_id=thread_id).inc()
    
    def record_websocket_disconnection(self, thread_id: str) -> None:
        """Record WebSocket disconnection."""
        ide_orchestrator_websocket_connections.labels(thread_id=thread_id).dec()
    
    @contextmanager
    def time_refinement(self):
        """Context manager for timing refinement workflows."""
        start_time = time.time()
        
        try:
            yield
            # Refinement succeeded
            duration = time.time() - start_time
            ide_orchestrator_refinement_duration.labels(status="completed").observe(duration)
        except Exception as e:
            # Refinement failed
            duration = time.time() - start_time
            ide_orchestrator_refinement_duration.labels(status="failed").observe(duration)
            raise
    
    def record_deepagents_request(self, endpoint: str, status: str) -> None:
        """Record request to deepagents-runtime."""
        ide_orchestrator_deepagents_requests.labels(endpoint=endpoint, status=status).inc()


# Global metrics manager instance
metrics = MetricsManager()