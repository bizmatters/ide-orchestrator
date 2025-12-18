package models

// SpecEngineState represents the initial state sent to Spec Engine
type SpecEngineState struct {
	UserPrompt           string                 `json:"user_prompt"`
	Files                map[string]string      `json:"files"`
	InitialFilesSnapshot map[string]string      `json:"initial_files_snapshot"`
	RevisionCount        int                    `json:"revision_count"`
	CompilerFeedback     interface{}            `json:"compiler_feedback"`
	ImpactAnalysis       interface{}            `json:"impact_analysis"`
	Definition           map[string]interface{} `json:"definition"`
}

// SpecEngineInvokeRequest represents the request to invoke Spec Engine
type SpecEngineInvokeRequest struct {
	Input    SpecEngineState `json:"input"`
	ThreadID string          `json:"thread_id"`
}

// SpecEngineInvokeResponse represents the response from Spec Engine invocation
type SpecEngineInvokeResponse struct {
	ThreadID string `json:"thread_id"`
	Status   string `json:"status"`
}

// SpecEngineFinalState represents the final state retrieved from Spec Engine
type SpecEngineFinalState struct {
	ProposedChanges map[string]interface{} `json:"proposed_changes"`
	ImpactAnalysis  string                 `json:"impact_analysis"`
	Definition      map[string]interface{} `json:"definition"`
	Messages        []interface{}          `json:"messages"`
}
