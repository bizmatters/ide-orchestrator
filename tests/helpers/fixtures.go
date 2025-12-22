package helpers

import (
	"encoding/json"
)

// TestUser represents a test user fixture
type TestUser struct {
	Email    string `json:"email"`
	Password string `json:"password"`
}

// TestWorkflow represents a test workflow fixture
type TestWorkflow struct {
	Name         string                 `json:"name"`
	Description  string                 `json:"description"`
	Specification map[string]interface{} `json:"specification"`
}

// TestRefinement represents a test refinement request
type TestRefinement struct {
	Instructions string `json:"instructions"`
	Context      string `json:"context"`
}

// Default test fixtures
var (
	DefaultTestUser = TestUser{
		Email:    "test@example.com",
		Password: "test-password-123",
	}

	DefaultTestWorkflow = TestWorkflow{
		Name:        "Test Workflow",
		Description: "A test workflow for integration testing",
		Specification: map[string]interface{}{
			"nodes": []map[string]interface{}{
				{
					"id":   "start",
					"type": "start",
					"data": map[string]interface{}{
						"label": "Start Node",
					},
				},
				{
					"id":   "end",
					"type": "end", 
					"data": map[string]interface{}{
						"label": "End Node",
					},
				},
			},
			"edges": []map[string]interface{}{
				{
					"id":     "start-to-end",
					"source": "start",
					"target": "end",
				},
			},
		},
	}

	DefaultTestRefinement = TestRefinement{
		Instructions: "Add a processing node between start and end",
		Context:      "This is a simple workflow that needs a processing step",
	}
)

// CreateSingleAgentWorkflow creates a single-agent workflow specification
func CreateSingleAgentWorkflow(agentName, prompt string) map[string]interface{} {
	return map[string]interface{}{
		"type": "single-agent",
		"agent": map[string]interface{}{
			"name":   agentName,
			"prompt": prompt,
			"tools":  []string{},
		},
		"nodes": []map[string]interface{}{
			{
				"id":   "agent",
				"type": "agent",
				"data": map[string]interface{}{
					"agent_name": agentName,
					"prompt":     prompt,
				},
			},
		},
		"edges": []map[string]interface{}{},
	}
}

// CreateMultiAgentWorkflow creates a multi-agent workflow specification
func CreateMultiAgentWorkflow(agents []map[string]interface{}) map[string]interface{} {
	nodes := make([]map[string]interface{}, 0, len(agents))
	edges := make([]map[string]interface{}, 0, len(agents)-1)

	for i, agent := range agents {
		nodeID := agent["name"].(string)
		nodes = append(nodes, map[string]interface{}{
			"id":   nodeID,
			"type": "agent",
			"data": agent,
		})

		// Connect agents in sequence
		if i > 0 {
			prevNodeID := agents[i-1]["name"].(string)
			edges = append(edges, map[string]interface{}{
				"id":     prevNodeID + "-to-" + nodeID,
				"source": prevNodeID,
				"target": nodeID,
			})
		}
	}

	return map[string]interface{}{
		"type":   "multi-agent",
		"agents": agents,
		"nodes":  nodes,
		"edges":  edges,
	}
}

// ToJSON converts a fixture to JSON string
func ToJSON(fixture interface{}) string {
	data, _ := json.Marshal(fixture)
	return string(data)
}

// FromJSON parses JSON string to map
func FromJSON(jsonStr string) map[string]interface{} {
	var result map[string]interface{}
	json.Unmarshal([]byte(jsonStr), &result)
	return result
}

// CreateTestLoginRequest creates a login request payload
func CreateTestLoginRequest(email, password string) map[string]interface{} {
	return map[string]interface{}{
		"email":    email,
		"password": password,
	}
}

// CreateTestWorkflowRequest creates a workflow creation request payload
func CreateTestWorkflowRequest(name, description string, spec map[string]interface{}) map[string]interface{} {
	return map[string]interface{}{
		"name":          name,
		"description":   description,
		"specification": spec,
	}
}

// CreateTestRefinementRequest creates a refinement request payload
func CreateTestRefinementRequest(instructions, context string) map[string]interface{} {
	return map[string]interface{}{
		"instructions": instructions,
		"context":      context,
	}
}

// MockSpecEngineResponse creates a mock response from Spec Engine
func MockSpecEngineResponse(threadID string, status string) map[string]interface{} {
	response := map[string]interface{}{
		"thread_id": threadID,
		"status":    status,
	}

	if status == "completed" {
		response["result"] = map[string]interface{}{
			"specification": CreateSingleAgentWorkflow(
				"Enhanced Agent",
				"You are an enhanced AI agent with improved capabilities",
			),
			"changes": []string{
				"Added processing node",
				"Enhanced agent prompt",
				"Improved error handling",
			},
		}
	}

	return response
}

// CreateComplexWorkflowSpec creates a complex workflow for testing
func CreateComplexWorkflowSpec() map[string]interface{} {
	return map[string]interface{}{
		"type": "complex-workflow",
		"nodes": []map[string]interface{}{
			{
				"id":   "input",
				"type": "input",
				"data": map[string]interface{}{
					"label":  "User Input",
					"schema": map[string]interface{}{
						"type": "object",
						"properties": map[string]interface{}{
							"query": map[string]interface{}{
								"type": "string",
							},
						},
					},
				},
			},
			{
				"id":   "analyzer",
				"type": "agent",
				"data": map[string]interface{}{
					"agent_name": "Query Analyzer",
					"prompt":     "Analyze the user query and extract key information",
					"tools":      []string{"text_analysis", "entity_extraction"},
				},
			},
			{
				"id":   "processor",
				"type": "agent",
				"data": map[string]interface{}{
					"agent_name": "Data Processor",
					"prompt":     "Process the analyzed data and generate insights",
					"tools":      []string{"data_processing", "insight_generation"},
				},
			},
			{
				"id":   "output",
				"type": "output",
				"data": map[string]interface{}{
					"label":  "Final Output",
					"format": "json",
				},
			},
		},
		"edges": []map[string]interface{}{
			{
				"id":     "input-to-analyzer",
				"source": "input",
				"target": "analyzer",
			},
			{
				"id":     "analyzer-to-processor",
				"source": "analyzer",
				"target": "processor",
			},
			{
				"id":     "processor-to-output",
				"source": "processor",
				"target": "output",
			},
		},
	}
}