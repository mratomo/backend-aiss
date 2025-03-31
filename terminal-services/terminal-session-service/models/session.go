package models

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// SessionStatus represents the status of a terminal session
type SessionStatus string

const (
	// SessionStatusConnecting means the terminal session is being established
	SessionStatusConnecting SessionStatus = "connecting"
	// SessionStatusConnected means the terminal session is established and active
	SessionStatusConnected SessionStatus = "connected"
	// SessionStatusDisconnected means the terminal session was disconnected
	SessionStatusDisconnected SessionStatus = "disconnected"
	// SessionStatusFailed means the terminal session failed to establish
	SessionStatusFailed SessionStatus = "failed"
)

// TargetInfo contains information about the target system
type TargetInfo struct {
	Hostname  string `json:"hostname" bson:"hostname"`
	IPAddress string `json:"ip" bson:"ip"`
	OSType    string `json:"os_detected" bson:"os_detected"`
	OSVersion string `json:"os_version" bson:"os_version"`
}

// TerminalMetadata contains metadata about the terminal session
type TerminalMetadata struct {
	ClientIP     string `json:"client_ip" bson:"client_ip"`
	UserAgent    string `json:"user_agent" bson:"user_agent"`
	TerminalType string `json:"terminal_type" bson:"terminal_type"`
	WindowSize   struct {
		Cols int `json:"cols" bson:"cols"`
		Rows int `json:"rows" bson:"rows"`
	} `json:"window_size" bson:"window_size"`
}

// Session represents a terminal session
type Session struct {
	ID           primitive.ObjectID `json:"id" bson:"_id,omitempty"`
	SessionID    string             `json:"session_id" bson:"session_id"`
	UserID       string             `json:"user_id" bson:"user_id"`
	Status       SessionStatus      `json:"status" bson:"status"`
	TargetInfo   TargetInfo         `json:"target_info" bson:"target_info"`
	Metadata     TerminalMetadata   `json:"metadata" bson:"metadata"`
	CreatedAt    time.Time          `json:"created_at" bson:"created_at"`
	LastActivity time.Time          `json:"last_active" bson:"last_active"`
	EndedAt      *time.Time         `json:"ended_at,omitempty" bson:"ended_at,omitempty"`
	Stats        struct {
		CommandCount   int   `json:"command_count" bson:"command_count"`
		BytesReceived  int64 `json:"bytes_received" bson:"bytes_received"`
		BytesSent      int64 `json:"bytes_sent" bson:"bytes_sent"`
		TotalDurationS int   `json:"total_duration_s" bson:"total_duration_s"`
	} `json:"stats" bson:"stats"`
	Tags []string `json:"tags,omitempty" bson:"tags,omitempty"`
}

// Command represents a command executed in a terminal session
type Command struct {
	ID            primitive.ObjectID `json:"id" bson:"_id,omitempty"`
	CommandID     string             `json:"command_id" bson:"command_id"`
	SessionID     string             `json:"session_id" bson:"session_id"`
	UserID        string             `json:"user_id" bson:"user_id"`
	CommandText   string             `json:"command" bson:"command"`
	Output        string             `json:"output" bson:"output"`
	ExitCode      int                `json:"exit_code" bson:"exit_code"`
	WorkingDir    string             `json:"working_directory" bson:"working_directory"`
	ExecutedAt    time.Time          `json:"timestamp" bson:"timestamp"`
	DurationMs    int                `json:"duration_ms" bson:"duration_ms"`
	IsSuggested   bool               `json:"is_suggested" bson:"is_suggested"`
	SuggestionID  string             `json:"suggestion_id,omitempty" bson:"suggestion_id,omitempty"`
	Tagged        bool               `json:"tagged" bson:"tagged"`
	Tags          []string           `json:"tags,omitempty" bson:"tags,omitempty"`
	Notes         string             `json:"notes,omitempty" bson:"notes,omitempty"`
	ErrorDetected bool               `json:"error_detected" bson:"error_detected"`
	ErrorType     string             `json:"error_type,omitempty" bson:"error_type,omitempty"`
}

// Bookmark represents a bookmarked command
type Bookmark struct {
	ID          primitive.ObjectID `json:"id" bson:"_id,omitempty"`
	BookmarkID  string             `json:"bookmark_id" bson:"bookmark_id"`
	UserID      string             `json:"user_id" bson:"user_id"`
	CommandID   string             `json:"command_id" bson:"command_id"`
	SessionID   string             `json:"session_id" bson:"session_id"`
	Label       string             `json:"label" bson:"label"`
	Notes       string             `json:"notes,omitempty" bson:"notes,omitempty"`
	CreatedAt   time.Time          `json:"created_at" bson:"created_at"`
	CommandText string             `json:"command" bson:"command"`
}

// SessionContext represents the current context of a terminal session
type SessionContext struct {
	ID                  primitive.ObjectID `json:"id" bson:"_id,omitempty"`
	SessionID           string             `json:"session_id" bson:"session_id"`
	UserID              string             `json:"user_id" bson:"user_id"`
	CurrentDirectory    string             `json:"working_directory" bson:"working_directory"`
	CurrentUser         string             `json:"current_user" bson:"current_user"`
	EnvironmentVars     map[string]string  `json:"environment_variables" bson:"environment_variables"`
	LastExitCode        int                `json:"last_exit_code" bson:"last_exit_code"`
	DetectedApplications []string          `json:"detected_applications" bson:"detected_applications"`
	DetectedErrors      []struct {
		Pattern  string    `json:"pattern" bson:"pattern"`
		Count    int       `json:"count" bson:"count"`
		LastSeen time.Time `json:"last_seen" bson:"last_seen"`
	} `json:"detected_errors" bson:"detected_errors"`
	LastUpdated time.Time `json:"last_updated" bson:"last_updated"`
}

// SessionSearchRequest represents a request to search for sessions
type SessionSearchRequest struct {
	UserID    string    `json:"user_id" form:"user_id"`
	Status    string    `json:"status" form:"status"`
	FromDate  time.Time `json:"from_date" form:"from_date"`
	ToDate    time.Time `json:"to_date" form:"to_date"`
	Hostname  string    `json:"hostname" form:"hostname"`
	OSType    string    `json:"os_type" form:"os_type"`
	Tags      []string  `json:"tags" form:"tags"`
	Limit     int       `json:"limit" form:"limit"`
	Offset    int       `json:"offset" form:"offset"`
	SortField string    `json:"sort_field" form:"sort_field"`
	SortOrder string    `json:"sort_order" form:"sort_order"`
}

// HistorySearchRequest represents a request to search command history
type HistorySearchRequest struct {
	UserID     string    `json:"user_id" form:"user_id"`
	SessionID  string    `json:"session_id" form:"session_id"`
	CommandStr string    `json:"command" form:"command"`
	FromDate   time.Time `json:"from_date" form:"from_date"`
	ToDate     time.Time `json:"to_date" form:"to_date"`
	ExitCode   *int      `json:"exit_code" form:"exit_code"`
	HasError   *bool     `json:"has_error" form:"has_error"`
	IsFavorite *bool     `json:"is_favorite" form:"is_favorite"`
	Limit      int       `json:"limit" form:"limit"`
	Offset     int       `json:"offset" form:"offset"`
	SortField  string    `json:"sort_field" form:"sort_field"`
	SortOrder  string    `json:"sort_order" form:"sort_order"`
}