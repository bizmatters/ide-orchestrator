package integration

import (
	"fmt"
	"os"
)

// ClusterConfig holds configuration for in-cluster testing
type ClusterConfig struct {
	DatabaseURL     string
	SpecEngineURL   string
	IsInCluster     bool
	Namespace       string
}

// SetupInClusterEnvironment configures the test environment for in-cluster execution
func SetupInClusterEnvironment() *ClusterConfig {
	config := &ClusterConfig{
		IsInCluster: isRunningInCluster(),
		Namespace:   getNamespace(),
	}

	if config.IsInCluster {
		// In-cluster configuration using Kubernetes DNS
		config.DatabaseURL = buildDatabaseURL()
		config.SpecEngineURL = "http://deepagents-runtime.intelligence-deepagents.svc:8080"
	} else {
		// Local development configuration (fallback)
		config.DatabaseURL = os.Getenv("DATABASE_URL")
		if config.DatabaseURL == "" {
			config.DatabaseURL = "postgres://postgres:postgres@localhost:5432/ide_orchestrator_test?sslmode=disable"
		}
		config.SpecEngineURL = os.Getenv("SPEC_ENGINE_URL")
		if config.SpecEngineURL == "" {
			config.SpecEngineURL = "http://localhost:8080"
		}
	}

	return config
}

// isRunningInCluster detects if we're running inside a Kubernetes cluster
func isRunningInCluster() bool {
	// Check for Kubernetes service account token
	if _, err := os.Stat("/var/run/secrets/kubernetes.io/serviceaccount/token"); err == nil {
		return true
	}
	
	// Check for Kubernetes environment variables
	if os.Getenv("KUBERNETES_SERVICE_HOST") != "" {
		return true
	}
	
	return false
}

// getNamespace returns the current Kubernetes namespace
func getNamespace() string {
	// Try to read from service account
	if data, err := os.ReadFile("/var/run/secrets/kubernetes.io/serviceaccount/namespace"); err == nil {
		return string(data)
	}
	
	// Fallback to environment variable
	if ns := os.Getenv("NAMESPACE"); ns != "" {
		return ns
	}
	
	// Default namespace
	return "intelligence-orchestrator"
}

// buildDatabaseURL constructs the database URL from environment variables
func buildDatabaseURL() string {
	host := os.Getenv("POSTGRES_HOST")
	if host == "" {
		host = "ide-orchestrator-db-rw.intelligence-orchestrator.svc"
	}
	
	port := os.Getenv("POSTGRES_PORT")
	if port == "" {
		port = "5432"
	}
	
	user := os.Getenv("POSTGRES_USER")
	if user == "" {
		user = "postgres"
	}
	
	password := os.Getenv("POSTGRES_PASSWORD")
	if password == "" {
		password = "postgres"
	}
	
	dbname := os.Getenv("POSTGRES_DB")
	if dbname == "" {
		dbname = "ide_orchestrator"
	}
	
	return fmt.Sprintf("postgres://%s:%s@%s:%s/%s?sslmode=prefer", 
		user, password, host, port, dbname)
}