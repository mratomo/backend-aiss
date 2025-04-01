package models

import (
	"time"

	"github.com/google/uuid"
)

// SessionStatus represents the status of an SSH session
type SessionStatus string

const (
	// SessionStatusConnecting means the SSH connection is being established
	SessionStatusConnecting SessionStatus = "connecting"
	// SessionStatusConnected means the SSH connection is established and active
	SessionStatusConnected SessionStatus = "connected"
	// SessionStatusDisconnected means the SSH connection was disconnected
	SessionStatusDisconnected SessionStatus = "disconnected"
	// SessionStatusFailed means the SSH connection failed to establish
	SessionStatusFailed SessionStatus = "failed"
)

// SessionMode represents the mode of the terminal session
type SessionMode string

const (
	// SessionModeNormal is the regular terminal mode
	SessionModeNormal SessionMode = "normal"
	// SessionModeQuery is the RAG query mode
	SessionModeQuery SessionMode = "query"
)

// SSHConnectionParams contains parameters for creating an SSH connection
type SSHConnectionParams struct {
	TargetHost string `json:"target_host" binding:"required"`
	Port       int    `json:"port" binding:"required,min=1,max=65535"`
	AuthMethod string `json:"auth_method" binding:"required,oneof=password key"`
	Username   string `json:"username" binding:"required"`
	Password   string `json:"password"`
	PrivateKey string `json:"private_key"`
	Passphrase string `json:"key_passphrase"`
	Options    struct {
		TerminalType     string `json:"terminal_type"`
		KeepAliveSeconds int    `json:"keep_alive_interval"`
		WindowSize       struct {
			Cols int `json:"cols"`
			Rows int `json:"rows"`
		} `json:"window_size"`
	} `json:"options"`
}

// TargetInfo contains information about the target system
type TargetInfo struct {
	Hostname  string `json:"hostname"`
	IPAddress string `json:"ip"`
	OSType    string `json:"os_detected"`
	OSVersion string `json:"os_version"`
}

// Stats tracks statistics for the session
type Stats struct {
	CommandCount   int   `json:"command_count"`
	BytesReceived  int64 `json:"bytes_received"`
	BytesSent      int64 `json:"bytes_sent"`
	TotalDurationS int   `json:"total_duration_s"`
}

// Metadata contains metadata about the session
type Metadata struct {
	ClientIP     string `json:"client_ip"`
	UserAgent    string `json:"user_agent"`
	TerminalType string `json:"terminal_type"`
	TermCols     int    `json:"cols"`
	TermRows     int    `json:"rows"`
}

// Session represents an SSH session
type Session struct {
	ID           string        `json:"session_id"`
	UserID       string        `json:"user_id"`
	Status       SessionStatus `json:"status"`
	TargetInfo   TargetInfo    `json:"target_info"`
	CreatedAt    time.Time     `json:"created_at"`
	LastActivity time.Time     `json:"last_active"`
	EndedAt      *time.Time    `json:"ended_at,omitempty"`
	WebSocketURL string        `json:"websocket_url,omitempty"`
	Metadata     Metadata      `json:"metadata"`
	Stats        Stats         `json:"stats"`
	Mode         SessionMode   `json:"mode,omitempty"`
	ActiveAreaID string        `json:"active_area_id,omitempty"`
}

// NewSession creates a new Session with default values
func NewSession(userID string) *Session {
	now := time.Now()
	return &Session{
		ID:           uuid.New().String(),
		UserID:       userID,
		Status:       SessionStatusConnecting,
		CreatedAt:    now,
		LastActivity: now,
		Stats: Stats{
			CommandCount:   0,
			BytesReceived:  0,
			BytesSent:      0,
			TotalDurationS: 0,
		},
		Metadata: Metadata{
			TerminalType: "xterm-256color",
			TermCols:     80,
			TermRows:     24,
		},
		Mode:         SessionModeNormal,
		ActiveAreaID: "",
	}
}

// SessionCreateRequest represents a request to create a new session
type SessionCreateRequest SSHConnectionParams

// SessionCreateResponse represents a response to a session creation request
type SessionCreateResponse struct {
	SessionID    string       `json:"session_id"`
	Status       SessionStatus `json:"status"`
	TargetInfo   TargetInfo    `json:"target_info,omitempty"`
	WebSocketURL string        `json:"websocket_url,omitempty"`
	CreatedAt    time.Time     `json:"created_at"`
	Message      string        `json:"message,omitempty"`
}

// Moved to websocket.go