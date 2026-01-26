"""
In-cluster test configuration for IDE Orchestrator.

Provides environment detection and configuration for tests running
in Kubernetes clusters vs local development.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class ClusterConfig:
    """Configuration for in-cluster testing."""
    database_url: str
    spec_engine_url: str
    is_in_cluster: bool
    namespace: str


def is_running_in_cluster() -> bool:
    """
    Detect if we're running inside a Kubernetes cluster.
    
    Returns:
        True if running in cluster, False otherwise
    """
    # Check for Kubernetes service account token
    if os.path.exists("/var/run/secrets/kubernetes.io/serviceaccount/token"):
        return True
    
    # Check for Kubernetes environment variables
    if os.getenv("KUBERNETES_SERVICE_HOST"):
        return True
    
    return False


def get_namespace() -> str:
    """
    Get the current Kubernetes namespace.
    
    Returns:
        Namespace name
    """
    # Try to read from service account
    namespace_file = "/var/run/secrets/kubernetes.io/serviceaccount/namespace"
    if os.path.exists(namespace_file):
        with open(namespace_file, 'r') as f:
            return f.read().strip()
    
    # Fallback to environment variable
    if ns := os.getenv("NAMESPACE"):
        return ns
    
    # Default namespace
    return "intelligence-orchestrator"


def build_database_url() -> str:
    """Use DATABASE_URL from environment variables."""
    return os.getenv("DATABASE_URL")
    
    return f"postgresql://{user}:{password}@{host}:{port}/{dbname}?sslmode=prefer"


def setup_in_cluster_environment() -> ClusterConfig:
    """
    Configure test environment for in-cluster or local execution.
    
    Returns:
        ClusterConfig with appropriate settings
    """
    # Check for mock URL override first (for testing)
    mock_url = os.getenv("MOCK_SPEC_ENGINE_URL")
    
    in_cluster = is_running_in_cluster()
    namespace = get_namespace()
    database_url = build_database_url()
    
    if mock_url:
        # Use mock URL when provided
        spec_engine_url = mock_url
    elif in_cluster:
        # In-cluster configuration using Kubernetes DNS
        spec_engine_url = os.getenv("DEEPAGENTS_RUNTIME_URL", "http://deepagents-runtime.intelligence-deepagents.svc.cluster.local:8000")
    else:
        # Local development configuration
        spec_engine_url = os.getenv("SPEC_ENGINE_URL", "http://localhost:8080")
    
    config = ClusterConfig(
        database_url=database_url,
        spec_engine_url=spec_engine_url,
        is_in_cluster=in_cluster,
        namespace=namespace
    )
    
    return config
