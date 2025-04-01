package models

// WebSocketMessage represents a message sent over WebSocket
type WebSocketMessage struct {
	Type string      `json:"type"`
	Data interface{} `json:"data"`
}

// TerminalInput represents a user input to the terminal
type TerminalInput struct {
	Data string `json:"data"`
}

// TerminalOutput represents output from the terminal
type TerminalOutput struct {
	Data string `json:"data"`
}

// SessionStatusUpdate represents an update to the session status
type SessionStatusUpdate struct {
	Status  string `json:"status"`
	Message string `json:"message"`
}

// WindowResize represents a terminal window resize event
type WindowResize struct {
	Cols int `json:"cols"`
	Rows int `json:"rows"`
}

// ExecuteSuggestion represents a request to execute a suggested command
type ExecuteSuggestion struct {
	SuggestionID    string `json:"suggestion_id"`
	AcknowledgeRisk bool   `json:"acknowledge_risk"`
}

// SessionControl represents a control action for the session
type SessionControl struct {
	Action string `json:"action"`
}

// ContextUpdate represents a terminal context update
type ContextUpdate struct {
	CurrentDirectory string            `json:"current_directory"`
	EnvironmentVars  map[string]string `json:"environment_variables,omitempty"`
	DetectedApps     []string          `json:"detected_applications,omitempty"`
}

// SuggestionAvailable represents a notification that a suggestion is available
type SuggestionAvailable struct {
	SuggestionID string `json:"suggestion_id"`
	Title        string `json:"title"`
	Preview      string `json:"preview"`
}

// KeyboardShortcut represents a keyboard shortcut event from the terminal
type KeyboardShortcut struct {
	Name      string `json:"name"`      // Name of the shortcut (e.g., "query_mode")
	Key       string `json:"key"`       // Key combination (e.g., "ctrl+alt+q")
	Timestamp int64  `json:"timestamp"` // When the shortcut was triggered
}

// ModeChange represents a mode change request or notification
type ModeChange struct {
	PreviousMode string `json:"previous_mode"` // Previous session mode
	NewMode      string `json:"new_mode"`      // New session mode
	AreaID       string `json:"area_id,omitempty"` // Knowledge area ID when entering query mode
}

// RagQuery represents a RAG query in query mode
type RagQuery struct {
	Query      string `json:"query"`      // User's query text
	SessionID  string `json:"session_id"` // Terminal session ID
	AreaID     string `json:"area_id"`    // Knowledge area ID
	IncludeTerminalContext bool `json:"include_terminal_context"` // Whether to include terminal context
}

// RagResponse represents a response from the RAG system
type RagResponse struct {
	Query       string `json:"query"`        // Original query
	Answer      string `json:"answer"`       // Generated answer
	HasError    bool   `json:"has_error"`    // Whether there was an error
	ErrorMsg    string `json:"error_msg,omitempty"` // Error message if any
	LlmProvider string `json:"llm_provider"` // LLM provider used
	Model       string `json:"model"`        // Model used
	Sources     []struct {  // Sources used in the response
		Title   string `json:"title"`
		Snippet string `json:"snippet"`
	} `json:"sources,omitempty"`
}