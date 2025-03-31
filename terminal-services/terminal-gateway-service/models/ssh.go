package models

import (
	"io"
	"sync"
	"time"
	
	"golang.org/x/crypto/ssh"
)

// SSHConnection represents an SSH connection to a remote host
type SSHConnection struct {
	SessionID   string
	UserID      string
	TargetHost  string
	Username    string
	Port        int
	ClientIP    string
	Status      SessionStatus
	ConnectedAt time.Time
	LastActive  time.Time
	Stdin       io.WriteCloser
	Stdout      io.Reader
	Stderr      io.Reader
	Close       func() error
	Lock        sync.Mutex
	Client      *ssh.Client // SSH client for executing commands
	WindowSize  struct {
		Cols int
		Rows int
	}
	TerminalType string
	OSInfo       struct {
		Type    string
		Version string
	}
	IsPaused      bool           // Indicates if the session is paused
	PausedAt      time.Time      // When the session was paused
	PauseChannels struct {        // Channels to control data flow
		Pause    chan bool        // Send true to pause, false to resume
		IsPaused chan bool        // Receive true if paused, false if resumed
		Timeout  time.Duration    // Timeout for channel operations
	}
	// Memory management
	MemStats struct {
		OutputBufferSize int64     // Current size of output buffer
		MaxBufferSize    int64     // Maximum allowed buffer size
		LastBufferReset  time.Time // Last time buffer was reset
	}
}

// SSHCredentials represents credentials for SSH authentication
type SSHCredentials struct {
	AuthType   string // "password" or "key"
	Password   string
	PrivateKey []byte
	Passphrase string
}

// TerminalCommand represents a command executed in the terminal
type TerminalCommand struct {
	ID           string            `json:"id"`
	SessionID    string            `json:"session_id"`
	Command      string            `json:"command"`
	Output       string            `json:"output"`
	ExitCode     int               `json:"exit_code"`
	WorkingDir   string            `json:"working_directory"`
	ExecutedAt   time.Time         `json:"timestamp"`
	DurationMs   int               `json:"duration_ms"`
	IsSuggested  bool              `json:"is_suggested"`
	SuggestionID string            `json:"suggestion_id,omitempty"`
	ErrorType    string            `json:"error_type,omitempty"`
	HasError     bool              `json:"has_error"`
	Metadata     map[string]string `json:"metadata,omitempty"`
}

// CommandResult represents the result of a command execution
type CommandResult struct {
	Command      string            `json:"command"`
	Output       string            `json:"output"`
	ExitCode     int               `json:"exit_code"`
	WorkingDir   string            `json:"working_directory"`
	DurationMs   int               `json:"duration_ms"`
	Error        string            `json:"error,omitempty"`
	IsSuggested  bool              `json:"is_suggested"`
	SuggestionID string            `json:"suggestion_id,omitempty"`
	Timestamp    time.Time         `json:"timestamp"`
	HasError     bool              `json:"has_error"`
	Metadata     map[string]string `json:"metadata,omitempty"`
}

// SessionEvent represents an event in the SSH session
type SessionEvent struct {
	SessionID  string    `json:"session_id"`
	EventType  string    `json:"event_type"` // command, output, error, resize, etc.
	Data       string    `json:"data"`
	Timestamp  time.Time `json:"timestamp"`
	MetaData   map[string]interface{} `json:"metadata,omitempty"`
}

// SSHError represents an error that occurred during SSH operations
type SSHError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
	Details string `json:"details,omitempty"`
}

// SSHSessionMetrics represents metrics for an SSH session
type SSHSessionMetrics struct {
	SessionID      string    `json:"session_id"`
	CommandCount   int       `json:"command_count"`
	BytesReceived  int64     `json:"bytes_received"`
	BytesSent      int64     `json:"bytes_sent"`
	LastCommand    time.Time `json:"last_command"`
	TotalDurationS int       `json:"total_duration_s"`
}