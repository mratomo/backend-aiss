package handlers

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"regexp"
	"runtime"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"
	"github.com/gorilla/websocket"
	"golang.org/x/crypto/ssh"
	"golang.org/x/crypto/ssh/knownhosts"

	"terminal-gateway-service/models"
	"terminal-gateway-service/services"
)

// readResult holds the result of a concurrent read operation
type readResult struct {
	n   int
	err error
}

// SSHManager manages SSH connections
type SSHManager struct {
	sessions        map[string]*models.SSHConnection
	sessionMutex    sync.RWMutex
	config          *ssh.ClientConfig
	upgrader        websocket.Upgrader
	timeout         time.Duration
	keepAlive       time.Duration
	keyDir          string
	maxSessions     int
	sessionClient   *services.SessionClient
	authToken       string
	// WebSocket clients tracking for broadcasting events
	wsClients       map[string][]*websocket.Conn  // Map sessionID -> array of websocket connections
	wsClientsMutex  sync.RWMutex                  // Mutex for wsClients map
}

// NewSSHManager creates a new SSH manager
func NewSSHManager(timeout, keepAlive time.Duration, keyDir string, maxSessions int, sessionServiceURL string) *SSHManager {
	// Create session client
	sessionClient := services.NewSessionClient(sessionServiceURL, timeout)
	
	// Set auth token if available from environment
	authToken := os.Getenv("AUTH_TOKEN")
	if authToken != "" {
		sessionClient.SetAuthToken(authToken)
	}
	
	return &SSHManager{
		sessions:      make(map[string]*models.SSHConnection),
		timeout:       timeout,
		keepAlive:     keepAlive,
		keyDir:        keyDir,
		maxSessions:   maxSessions,
		sessionClient: sessionClient,
		authToken:     authToken,
		wsClients:     make(map[string][]*websocket.Conn),
			upgrader: websocket.Upgrader{
				ReadBufferSize:  1024,
				WriteBufferSize: 1024,
				CheckOrigin: func(r *http.Request) bool {
					// Get allowed origins from config
					allowedOrigins := os.Getenv("CORS_ALLOWED_ORIGINS")
					if allowedOrigins == "" {
						// Default to localhost in development
						allowedOrigins = "http://localhost:3000,https://app.domain.com"
					}
					
					// Get request origin
					origin := r.Header.Get("Origin")
					if origin == "" {
						return false
					}
					
					// Check if origin is allowed
					for _, allowed := range strings.Split(allowedOrigins, ",") {
						if allowed == origin || allowed == "*" {
							return true
						}
					}
					
					// Log unauthorized access attempts
					log.Printf("Unauthorized WebSocket connection attempt from: %s", origin)
					return false
				},
			},
	}
}

// knownhostsCallback creates a HostKeyCallback from a known_hosts file
func knownhostsCallback(filepath string) (ssh.HostKeyCallback, error) {
	// Check if file exists, create if it doesn't
	if _, err := os.Stat(filepath); os.IsNotExist(err) {
		// Create the directory if it doesn't exist
		dir := filepath[:len(filepath)-len("/known_hosts")]
		if err := os.MkdirAll(dir, 0700); err != nil {
			return nil, fmt.Errorf("failed to create directory for known_hosts: %w", err)
		}
		
		// Create an empty known_hosts file with secure permissions
		file, err := os.Create(filepath)
		if err != nil {
			return nil, fmt.Errorf("failed to create known_hosts file: %w", err)
		}
		file.Close()
		
		// Set secure permissions for known_hosts file (only owner can read/write)
		if err := os.Chmod(filepath, 0600); err != nil {
			return nil, fmt.Errorf("failed to set permissions for known_hosts file: %w", err)
		}
	} else {
		// Check if the existing file has secure permissions and fix if needed
		fileInfo, err := os.Stat(filepath)
		if err != nil {
			return nil, fmt.Errorf("failed to check permissions for known_hosts file: %w", err)
		}
		
		// On Unix systems, make sure the permissions are set to 0600 (only owner can read/write)
		if fileInfo.Mode().Perm() != 0600 {
			if err := os.Chmod(filepath, 0600); err != nil {
				return nil, fmt.Errorf("failed to fix permissions for known_hosts file: %w", err)
			}
			log.Printf("Warning: Fixed permissions for known_hosts file: %s", filepath)
		}
	}
	
	return knownhosts.New(filepath)
}

// CreateSession creates a new SSH session
func (m *SSHManager) CreateSession(userID string, params models.SessionCreateRequest, clientIP string) (*models.Session, error) {
	// Check if we are at max sessions
	m.sessionMutex.RLock()
	sessionCount := len(m.sessions)
	m.sessionMutex.RUnlock()

	if sessionCount >= m.maxSessions {
		return nil, errors.New("maximum number of sessions reached")
	}

	// Create a new session
	session := models.NewSession(userID)
	session.Metadata.ClientIP = clientIP

	// Configure terminal options
	if params.Options.TerminalType != "" {
		session.Metadata.TerminalType = params.Options.TerminalType
	} else {
		session.Metadata.TerminalType = "xterm-256color"
	}

	if params.Options.WindowSize.Cols > 0 && params.Options.WindowSize.Rows > 0 {
		session.Metadata.TermCols = params.Options.WindowSize.Cols
		session.Metadata.TermRows = params.Options.WindowSize.Rows
	} else {
		session.Metadata.TermCols = 80
		session.Metadata.TermRows = 24
	}

	// Create SSH auth method
	var authMethod ssh.AuthMethod
	var err error

	switch params.AuthMethod {
	case "password":
		authMethod = ssh.Password(params.Password)
	case "key":
		authMethod, err = m.getPublicKeyAuth(params.PrivateKey, params.Passphrase)
		if err != nil {
			return nil, fmt.Errorf("failed to create key auth: %w", err)
		}
	default:
		return nil, errors.New("unsupported authentication method")
	}
		// Create a host key callback
		var hostKeyCallback ssh.HostKeyCallback
		if m.keyDir \!= "" {
			// Try to use known_hosts file
			knownHostsFile := fmt.Sprintf("%s/known_hosts", m.keyDir)
			if hostKeyCallback, err = knownhostsCallback(knownHostsFile); err \!= nil {
				log.Printf("Warning: Could not load known_hosts file: %v", err),
				
				// Instead of InsecureIgnoreHostKey, use a custom handler that at least logs the key
				hostKeyCallback = func(hostname string, remote net.Addr, key ssh.PublicKey) error {
					fingerprint := ssh.FingerprintSHA256(key)
					keyType := key.Type()
					
					log.Printf("SECURITY WARNING: Host '%s' presents unknown key: %s %s", 
						hostname, keyType, fingerprint)
					
					// For enhanced security, we could store this key for future verification
					// Here we're logging the warning but still allowing the connection
					// In a production environment, you might want to require explicit confirmation
					
					// Create a record of this key for future reference
					if file, err := os.OpenFile(knownHostsFile, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0600); err == nil {
						defer file.Close()
						
						// Format is: hostname keytype key
						// We need to import encoding/base64 for this
						line := fmt.Sprintf("%s %s %s\n", hostname, keyType, base64.StdEncoding.EncodeToString(key.Marshal()))
						if _, err := file.WriteString(line); err \!= nil {
							log.Printf("Failed to write to known_hosts file: %v", err)
						} else {
							log.Printf("Added new host key to %s for future verification", knownHostsFile)
						}
					}
					
					return nil
				}
			}
		} else {
			// We require a keyDir for host key verification
			return nil, errors.New("secure SSH connections require a keyDir for host key verification")
		}
	}

	sshConfig := &ssh.ClientConfig{
		User: params.Username,
		Auth: []ssh.AuthMethod{
			authMethod,
		},
		HostKeyCallback: hostKeyCallback,
		Timeout:         m.timeout,
	}

	// Save session to the session service
	err = m.sessionClient.CreateSession(session)
	if err != nil {
		log.Printf("Failed to save session to session service: %v", err)
		// Continue with in-memory session but log the error
	}

	// Connect to the SSH server (in a goroutine to not block)
	go func() {
		conn, err := m.connectToSSH(session.ID, params.TargetHost, params.Port, sshConfig, userID, clientIP, session.Metadata.TerminalType, session.Metadata.TermCols, session.Metadata.TermRows)
		if err != nil {
			log.Printf("Failed to connect to SSH server: %v", err)
			m.updateSessionStatus(session.ID, models.SessionStatusFailed)
			return
		}

		// Add the connection to the manager
		m.sessionMutex.Lock()
		m.sessions[session.ID] = conn
		m.sessionMutex.Unlock()

		// Update session status
		m.updateSessionStatus(session.ID, models.SessionStatusConnected)

			// Update target info
			info, err := m.detectOSInfo(conn)
			if err \!= nil {
				log.Printf("Failed to detect OS info: %v", err),
			} else {
				m.updateSessionTargetInfo(session.ID, info)
				
				// Notify clients about the detected OS
				statusData, _ := json.Marshal(models.SessionStatusUpdate{
					Status:  "os_detected",
					Message: fmt.Sprintf("Detected %s %s", info.OSType, info.OSVersion),
				})
				m.SessionEventHandler(session.ID, "session_status", string(statusData))
			}
			m.updateSessionTargetInfo(session.ID, info)
		}
	}()

	return session, nil
}

// connectToSSH establishes an SSH connection
func (m *SSHManager) connectToSSH(sessionID, host string, port int, config *ssh.ClientConfig, userID, clientIP, termType string, cols, rows int) (*models.SSHConnection, error) {
	// Create the connection
	addr := fmt.Sprintf("%s:%d", host, port)
	client, err := ssh.Dial("tcp", addr, config)
	if err != nil {
		return nil, fmt.Errorf("failed to dial: %w", err)
	}

	// Create a session
	sshSession, err := client.NewSession()
	if err != nil {
		client.Close()
		return nil, fmt.Errorf("failed to create session: %w", err)
	}

	// Set up terminal modes
	modes := ssh.TerminalModes{
		ssh.ECHO:          1,
		ssh.TTY_OP_ISPEED: 14400,
		ssh.TTY_OP_OSPEED: 14400,
	}

	// Request pseudo terminal
	if err := sshSession.RequestPty(termType, rows, cols, modes); err != nil {
		sshSession.Close()
		client.Close()
		return nil, fmt.Errorf("failed to request pty: %w", err)
	}

	// Get stdin, stdout, stderr
	stdin, err := sshSession.StdinPipe()
	if err != nil {
		sshSession.Close()
		client.Close()
		return nil, fmt.Errorf("failed to get stdin pipe: %w", err)
	}

	stdout, err := sshSession.StdoutPipe()
	if err != nil {
		sshSession.Close()
		client.Close()
		return nil, fmt.Errorf("failed to get stdout pipe: %w", err)
	}

	stderr, err := sshSession.StderrPipe()
	if err != nil {
		sshSession.Close()
		client.Close()
		return nil, fmt.Errorf("failed to get stderr pipe: %w", err)
	}

	// Start shell
	if err := sshSession.Shell(); err != nil {
		sshSession.Close()
		client.Close()
		return nil, fmt.Errorf("failed to start shell: %w", err)
	}

	// Create connection object
	conn := &models.SSHConnection{
		SessionID:   sessionID,
		UserID:      userID,
		TargetHost:  host,
		Username:    config.User,
		Port:        port,
		ClientIP:    clientIP,
		Status:      models.SessionStatusConnected,
		ConnectedAt: time.Now(),
		LastActive:  time.Now(),
		Stdin:       stdin,
		Stdout:      stdout,
		Stderr:      stderr,
		Client:      client, // Store SSH client for command execution
		IsPaused:    false,
		Close: func() error {
			sshSession.Close()
			return client.Close()
		},
	}
	
	// Initialize pause channels
	conn.PauseChannels.Pause = make(chan bool, 1)
	conn.PauseChannels.IsPaused = make(chan bool, 1)

	conn.WindowSize.Cols = cols
	conn.WindowSize.Rows = rows
	conn.TerminalType = termType

	return conn, nil
}

// getPublicKeyAuth creates an SSH public key authentication method
func (m *SSHManager) getPublicKeyAuth(privateKey, passphrase string) (ssh.AuthMethod, error) {
	var signer ssh.Signer
	var err error

	if passphrase != "" {
		signer, err = ssh.ParsePrivateKeyWithPassphrase([]byte(privateKey), []byte(passphrase))
	} else {
		signer, err = ssh.ParsePrivateKey([]byte(privateKey))
	}

	if err != nil {
		return nil, err
	}

	return ssh.PublicKeys(signer), nil
}

// GetSessions returns all sessions for a user
func (m *SSHManager) GetSessions(userID, status string, limit, offset int) ([]*models.Session, error) {
	m.sessionMutex.RLock()
	defer m.sessionMutex.RUnlock()

	var result []*models.Session

	for _, conn := range m.sessions {
		if conn.UserID == userID && (status == "" || string(conn.Status) == status) {
			session := &models.Session{
				ID:           conn.SessionID,
				UserID:       conn.UserID,
				Status:       conn.Status,
				CreatedAt:    conn.ConnectedAt,
				LastActivity: conn.LastActive,
				TargetInfo: models.TargetInfo{
					Hostname:  conn.TargetHost,
					IPAddress: conn.TargetHost, // Might be resolved later
					OSType:    conn.OSInfo.Type,
					OSVersion: conn.OSInfo.Version,
				},
				Metadata: models.Metadata{
					ClientIP:     conn.ClientIP,
					TerminalType: conn.TerminalType,
					TermCols:     conn.WindowSize.Cols,
					TermRows:     conn.WindowSize.Rows,
				},
			}
			result = append(result, session)
		}
	}

	// Apply pagination
	if offset >= len(result) {
		return []*models.Session{}, nil
	}

	end := offset + limit
	if end > len(result) {
		end = len(result)
	}

	return result[offset:end], nil
}

// GetSession returns a session by ID
func (m *SSHManager) GetSession(sessionID string) (*models.Session, error) {
	m.sessionMutex.RLock()
	conn, exists := m.sessions[sessionID]
	m.sessionMutex.RUnlock()

	if !exists {
		return nil, errors.New("session not found")
	}

	session := &models.Session{
		ID:           conn.SessionID,
		UserID:       conn.UserID,
		Status:       conn.Status,
		CreatedAt:    conn.ConnectedAt,
		LastActivity: conn.LastActive,
		TargetInfo: models.TargetInfo{
			Hostname:  conn.TargetHost,
			IPAddress: conn.TargetHost, // Might be resolved later
			OSType:    conn.OSInfo.Type,
			OSVersion: conn.OSInfo.Version,
		},
		Metadata: models.Metadata{
			ClientIP:     conn.ClientIP,
			TerminalType: conn.TerminalType,
			TermCols:     conn.WindowSize.Cols,
			TermRows:     conn.WindowSize.Rows,
		},
	}

	return session, nil
}

// TerminateSession terminates an SSH session
func (m *SSHManager) TerminateSession(sessionID string) error {
	m.sessionMutex.Lock()
	conn, exists := m.sessions[sessionID]
	if !exists {
		m.sessionMutex.Unlock()
		// Try to update session status in session service even if not in memory
		_ = m.sessionClient.UpdateSessionStatus(sessionID, models.SessionStatusDisconnected)
		return errors.New("session not found")
	}

	err := conn.Close()
	delete(m.sessions, sessionID)
	m.sessionMutex.Unlock()

	// Update status in session service
	updateErr := m.sessionClient.UpdateSessionStatus(sessionID, models.SessionStatusDisconnected)
	if updateErr != nil {
		log.Printf("Failed to update session status in session service: %v", updateErr)
		// Don't return this error, prioritize the close error
	}

	return err
}

// UpdateSession updates session parameters
func (m *SSHManager) UpdateSession(sessionID string, params interface{}) error {
	m.sessionMutex.Lock()
	defer m.sessionMutex.Unlock()

	conn, exists := m.sessions[sessionID]
	if !exists {
		return errors.New("session not found")
	}

	// Update window size if provided
	if p, ok := params.(struct {
		WindowSize struct {
			Cols int `json:"cols"`
			Rows int `json:"rows"`
		} `json:"window_size"`
		KeepAliveInterval int `json:"keep_alive_interval"`
	}); ok {
		if p.WindowSize.Cols > 0 && p.WindowSize.Rows > 0 {
			conn.WindowSize.Cols = p.WindowSize.Cols
			conn.WindowSize.Rows = p.WindowSize.Rows
			
			// Update PTY window size using a new SSH session
			if conn.Client != nil {
				// Create a new session for window resize operation
				session, err := conn.Client.NewSession()
				if err != nil {
					log.Printf("Failed to create session for window resize: %v", err)
					return fmt.Errorf("failed to create session for window resize: %w", err)
				}
				defer session.Close()
				
				// Update PTY window size using standard SSH window-change request
				if sshSession, ok := session.(*ssh.Session); ok {
					err := sshSession.WindowChange(conn.WindowSize.Rows, conn.WindowSize.Cols)
					if err != nil {
						log.Printf("Failed to resize PTY window: %v", err)
						return fmt.Errorf("failed to resize PTY window: %w", err)
					}
					log.Printf("PTY window resized to %dx%d for session %s", conn.WindowSize.Cols, conn.WindowSize.Rows, conn.SessionID)
				}
			}
		}
	}

	return nil
}

// updateSessionStatus updates the status of a session
func (m *SSHManager) updateSessionStatus(sessionID string, status models.SessionStatus) {
	m.sessionMutex.Lock()
	if conn, exists := m.sessions[sessionID]; exists {
		conn.Status = status
		conn.LastActive = time.Now()
	}
	m.sessionMutex.Unlock()
	
	// Update status in session service as well
	err := m.sessionClient.UpdateSessionStatus(sessionID, status)
	if err != nil {
		log.Printf("Failed to update session status in session service: %v", err)
	}
	
	// Notify clients about the status change
	var message string
	switch status {
	case models.SessionStatusConnecting:
		message = "Connecting to the server..."
	case models.SessionStatusConnected:
		message = "Connected to the server."
	case models.SessionStatusDisconnected:
		message = "Disconnected from the server."
	case models.SessionStatusFailed:
		message = "Connection to the server failed."
	default:
		message = fmt.Sprintf("Session status changed to: %s", status)
	}
	
	statusData, _ := json.Marshal(models.SessionStatusUpdate{
		Status:  string(status),
		Message: message,
	})
	
	// Broadcast the event to all clients
	m.SessionEventHandler(sessionID, "session_status", string(statusData))
}

// updateSessionTargetInfo updates the target info of a session
func (m *SSHManager) updateSessionTargetInfo(sessionID string, info models.TargetInfo) {
	m.sessionMutex.Lock()
	if conn, exists := m.sessions[sessionID]; exists {
		conn.OSInfo.Type = info.OSType
		conn.OSInfo.Version = info.OSVersion
	}
	m.sessionMutex.Unlock()
}

// executeCommandWithOutput executes a command and returns its output
func (m *SSHManager) executeCommandWithOutput(client *ssh.Client, command string) (string, error) {
	// Create a new session for this command
	session, err := client.NewSession()
	if err != nil {
		return "", fmt.Errorf("failed to create session: %w", err)
	}
	defer session.Close()

	// Execute command and get combined output
	output, err := session.CombinedOutput(command)
	if err != nil {
		return string(output), fmt.Errorf("command execution failed: %w", err)
	}

	return string(output), nil
}

// detectOSInfo attempts to detect OS information for a connection
func (m *SSHManager) detectOSInfo(conn *models.SSHConnection) (models.TargetInfo, error) {
	// Get hostname from the connection
	var info models.TargetInfo
	info.Hostname = conn.TargetHost
	
	// Resolve IP address if it's a hostname
	if ip := net.ParseIP(conn.TargetHost); ip == nil {
		addresses, err := net.LookupHost(conn.TargetHost)
		if err == nil && len(addresses) > 0 {
			info.IPAddress = addresses[0]
		} else {
			info.IPAddress = conn.TargetHost
		}
	} else {
		info.IPAddress = conn.TargetHost
	}
	
	// Extract the SSH client from the connection
	// This requires modifying the connectToSSH function to store the client in the SSHConnection
	if conn.Client == nil {
		info.OSType = "Unknown"
		info.OSVersion = "Unknown"
		return info, errors.New("no SSH client available for OS detection")
	}
	
	// Try to detect if it's a Windows system first
	output, err := m.executeCommandWithOutput(conn.Client, "cmd.exe /c ver")
	if err == nil && (strings.Contains(output, "Microsoft Windows") || strings.Contains(output, "MS-DOS")) {
		// Windows system
		info.OSType = "Windows"
		
		// Extract version information
		if strings.Contains(output, "10.0") {
			info.OSVersion = "10/11/Server 2016+"
		} else if strings.Contains(output, "6.3") {
			info.OSVersion = "8.1/Server 2012 R2"
		} else if strings.Contains(output, "6.2") {
			info.OSVersion = "8/Server 2012"
		} else if strings.Contains(output, "6.1") {
			info.OSVersion = "7/Server 2008 R2"
		} else {
			// Extract whatever version we can find
			verPattern := regexp.MustCompile(`Version\s+([0-9\.]+)`)
			if matches := verPattern.FindStringSubmatch(output); len(matches) > 1 {
				info.OSVersion = matches[1]
			} else {
				info.OSVersion = "Unknown Windows"
			}
		}
		
		return info, nil
	}
	
	// Try Linux/Unix detection approaches in order of preference
	
	// 1. Try /etc/os-release first (most modern Linux distributions)
	output, err = m.executeCommandWithOutput(conn.Client, "cat /etc/os-release 2>/dev/null")
	if err == nil && len(output) > 0 {
		// Parse /etc/os-release
		namePattern := regexp.MustCompile(`NAME="([^"]+)"`)
		versionPattern := regexp.MustCompile(`VERSION="([^"]+)"`)
		idPattern := regexp.MustCompile(`ID=([^\s]+)`)
		
		var osName, osVersion, osID string
		
		if matches := namePattern.FindStringSubmatch(output); len(matches) > 1 {
			osName = matches[1]
		}
		
		if matches := versionPattern.FindStringSubmatch(output); len(matches) > 1 {
			osVersion = matches[1]
		}
		
		if matches := idPattern.FindStringSubmatch(output); len(matches) > 1 {
			osID = matches[1]
		}
		
		if osName != "" {
			info.OSType = osName
		} else if osID != "" {
			info.OSType = strings.Title(osID)
		} else {
			info.OSType = "Linux"
		}
		
		info.OSVersion = osVersion
		return info, nil
	}
	
	// 2. Try uname -a (works on most Unix-like systems)
	output, err = m.executeCommandWithOutput(conn.Client, "uname -a")
	if err == nil && len(output) > 0 {
		// Basic OS type detection from uname
		if strings.Contains(strings.ToLower(output), "darwin") {
			info.OSType = "macOS"
			
			// Try to get macOS version
			macVersion, vErr := m.executeCommandWithOutput(conn.Client, "sw_vers -productVersion")
			if vErr == nil && len(macVersion) > 0 {
				info.OSVersion = strings.TrimSpace(macVersion)
			} else {
				info.OSVersion = "Unknown"
			}
		} else if strings.Contains(strings.ToLower(output), "freebsd") {
			info.OSType = "FreeBSD"
			
			// Try to extract version from uname output
			versionPattern := regexp.MustCompile(`FreeBSD\s+([0-9\.]+)`)
			if matches := versionPattern.FindStringSubmatch(output); len(matches) > 1 {
				info.OSVersion = matches[1]
			} else {
				info.OSVersion = "Unknown"
			}
		} else {
			// Generic Linux
			info.OSType = "Linux"
			
			// Try to extract kernel version
			versionPattern := regexp.MustCompile(`([0-9]+\.[0-9]+\.[0-9]+)`)
			if matches := versionPattern.FindStringSubmatch(output); len(matches) > 1 {
				info.OSVersion = "Kernel " + matches[1]
			} else {
				info.OSVersion = "Unknown"
			}
			
			// Try specific distribution detection methods
			// Check for /etc/redhat-release
			redhatOutput, _ := m.executeCommandWithOutput(conn.Client, "cat /etc/redhat-release 2>/dev/null")
			if len(redhatOutput) > 0 {
				info.OSType = "Red Hat Linux"
				info.OSVersion = strings.TrimSpace(redhatOutput)
			}
			
			// Check for Debian version
			debianOutput, _ := m.executeCommandWithOutput(conn.Client, "cat /etc/debian_version 2>/dev/null")
			if len(debianOutput) > 0 {
				info.OSType = "Debian"
				info.OSVersion = strings.TrimSpace(debianOutput)
			}
		}
		
		return info, nil
	}
	
	// 3. Fall back to minimal info if we couldn't detect properly
	info.OSType = "Unknown"
	info.OSVersion = "Unknown"
	
	return info, nil
}

// HandleWebSocket handles a WebSocket connection for terminal I/O
func (m *SSHManager) HandleWebSocket(c *gin.Context, sessionID string) {
	// Upgrade HTTP connection to WebSocket
	ws, err := m.upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("Failed to upgrade to WebSocket: %v", err)
		return
	}
	defer ws.Close()

	// Get the SSH connection
	m.sessionMutex.RLock()
	conn, exists := m.sessions[sessionID]
	m.sessionMutex.RUnlock()

	if !exists {
		ws.WriteJSON(models.WebSocketMessage{
			Type: "session_status",
			Data: models.SessionStatusUpdate{
				Status:  "error",
				Message: "Session not found",
			},
		})
		return
	}
	
	// Register this WebSocket connection for the session
	m.registerWebSocketClient(sessionID, ws)

	// Create channels for communication
	done := make(chan struct{})
	defer close(done)

	// Read from WebSocket and write to SSH stdin
	go func() {
		defer func() { done <- struct{}{} }()
		
		for {
			var msg models.WebSocketMessage
			err := ws.ReadJSON(&msg)
			if err != nil {
				if !websocket.IsCloseError(err, websocket.CloseNormalClosure) {
					log.Printf("Failed to read WebSocket message: %v", err)
				}
				return
			}

			// Update last activity time
			conn.Lock.Lock()
			conn.LastActive = time.Now()
			conn.Lock.Unlock()

			switch msg.Type {
			case "terminal_input":
				// Parse terminal input message
				var input models.TerminalInput
				if data, ok := msg.Data.(map[string]interface{}); ok {
					if inputData, ok := data["data"].(string); ok {
						input.Data = inputData
					}
				}

				// Write to SSH stdin
				_, err := conn.Stdin.Write([]byte(input.Data))
				if err != nil {
					log.Printf("Failed to write to SSH: %v", err)
					return
				}

				// TODO: Record command for analysis

				case "resize":
					// Parse resize message
					var resize models.WindowResize
					if data, ok := msg.Data.(map[string]interface{}); ok {
						if cols, ok := data["cols"].(float64); ok {
							resize.Cols = int(cols)
						}
						if rows, ok := data["rows"].(float64); ok {
							resize.Rows = int(rows)
						}
					}

					// Update window size
					conn.Lock.Lock()
					conn.WindowSize.Cols = resize.Cols
					conn.WindowSize.Rows = resize.Rows
					conn.Lock.Unlock()

					// Update the real PTY window size
					if conn.Client \!= nil {
						// Create a new session for window resize operation
						session, err := conn.Client.NewSession()
						if err \!= nil {
							log.Printf("Failed to create session for window resize: %v", err)
						} else {
							defer session.Close()
							
							// Update PTY window size using standard SSH window-change request
							sshSession := session.(*ssh.Session)
							if sshSession \!= nil {
								err := sshSession.WindowChange(resize.Rows, resize.Cols)
								if err \!= nil {
									log.Printf("Failed to resize PTY window: %v", err)
								} else {
									log.Printf("PTY window resized to %dx%d for session %s", resize.Cols, resize.Rows, conn.SessionID)
								}
							}
						}
					}

				case "execute_suggestion":
					// Parse execute suggestion message
					var execute models.ExecuteSuggestion
					if data, ok := msg.Data.(map[string]interface{}); ok {
						if suggestionID, ok := data["suggestion_id"].(string); ok {
							execute.SuggestionID = suggestionID
						}
						if acknowledge, ok := data["acknowledge_risk"].(bool); ok {
							execute.AcknowledgeRisk = acknowledge
						}
					}

					// Execute the suggested command
					if execute.SuggestionID == "" {
						// Send error message to client
						ws.WriteJSON(models.WebSocketMessage{
							Type: "session_status",
							Data: models.SessionStatusUpdate{
								Status:  "error",
								Message: "Missing suggestion ID",
							},
						})
						continue
					}
					
					// Get the suggestion
					suggestion, err := m.sessionClient.GetSuggestion(execute.SuggestionID)
					if err \!= nil {
						log.Printf("Failed to get suggestion: %v", err),
						ws.WriteJSON(models.WebSocketMessage{
							Type: "session_status",
							Data: models.SessionStatusUpdate{
								Status:  "error",
								Message: fmt.Sprintf("Failed to get suggestion: %v", err),
							},
						})
						continue
					}
					
					// Check if we need approval for risky commands
					if suggestion.RequiresApproval && \!execute.AcknowledgeRisk {
						// Send a message requesting acknowledgment
						ws.WriteJSON(models.WebSocketMessage{
							Type: "suggestion_status",
							Data: map[string]interface{}{
								"suggestion_id":      suggestion.ID,
								"status":             "requires_approval",
								"message":            fmt.Sprintf("This suggestion has risk level '%s' and requires approval", suggestion.RiskLevel),
								"risk_level":         suggestion.RiskLevel,
								"requires_approval":  true,
								"command":            suggestion.Command,
							},
						})
						continue
					}
					
					// Log the execution of a suggested command
					log.Printf("Executing suggested command: %s (ID: %s) with risk level: %s", suggestion.Command, suggestion.ID, suggestion.RiskLevel)
					
						// Execute the command with the suggestion ID
						suggestionInfo := struct {
							ID string
							Command string
						}{
							ID: suggestion.ID,
							Command: suggestion.Command,
						}
						// Pass the suggestion ID as metadata for tracking
						result, err := m.executeSuggestionCommand(sessionID, suggestionInfo)
					if err \!= nil {
						log.Printf("Failed to execute suggested command: %v", err),
						ws.WriteJSON(models.WebSocketMessage{
							Type: "suggestion_status",
							Data: map[string]interface{}{
								"suggestion_id": suggestion.ID,
								"status":        "error",
								"message":       fmt.Sprintf("Failed to execute command: %v", err),
							},
						}),
					} else {
						// Notify client of successful execution
						ws.WriteJSON(models.WebSocketMessage{
							Type: "suggestion_status",
							Data: map[string]interface{}{
								"suggestion_id": suggestion.ID,
								"status":        "executed",
								"message":       "Command executed successfully",
								"command":       suggestion.Command,
								"duration_ms":   result.DurationMs,
							},
						})
					}
			case "session_control":
				// Parse session control message
				var control models.SessionControl
				if data, ok := msg.Data.(map[string]interface{}); ok {
					if action, ok := data["action"].(string); ok {
						control.Action = action
					}
				}

					// Handle control action
					switch control.Action {
					case "terminate":
						// Instead of closing the SSH connection, just disconnect this client
						// This allows other clients to continue using the session
						log.Printf("Client disconnected from session %s", conn.SessionID)
						
						// Notify this client about the disconnection
						ws.WriteJSON(models.WebSocketMessage{
							Type: "session_status",
							Data: models.SessionStatusUpdate{
								Status:  "disconnected",
								Message: "You have been disconnected from the session.",
							},
						})
						
						// Broadcast to other clients that this client left
						eventData := map[string]interface{}{
							"event": "client_disconnected",
							"client_id": ws.RemoteAddr().String(),
							"timestamp": time.Now().Format(time.RFC3339),
						}
						jsonData, _ := json.Marshal(eventData)
						go m.broadcastToSessionExcept(sessionID, ws, "session_event", string(jsonData))
						
						return
					case "pause":
						// Pause the session
						conn.Lock.Lock()
						if \!conn.IsPaused {
							conn.IsPaused = true
							conn.PausedAt = time.Now()
							// Signal pause to the readers
							conn.PauseChannels.Pause <- true
							
							// Prepare status update message
							statusMsg := models.WebSocketMessage{
								Type: "session_status",
								Data: models.SessionStatusUpdate{
									Status:  "paused",
									Message: "Session paused by " + ws.RemoteAddr().String() + ". Terminal input/output is suspended.",
								},
							}
							
							// Send pause notification to this client
							ws.WriteJSON(statusMsg)
							
							// Broadcast to all other clients
							go m.broadcastToSessionExcept(sessionID, ws, "session_status", statusMsg.Data)
							
							log.Printf("Session %s paused by client %s", conn.SessionID, ws.RemoteAddr())
						}
						conn.Lock.Unlock()
					case "resume":
						// Resume the session
						conn.Lock.Lock()
						if conn.IsPaused {
							conn.IsPaused = false
							// Signal resume to the readers
							conn.PauseChannels.Pause <- false
							
							pauseDuration := time.Since(conn.PausedAt).Seconds()
							
							// Prepare status update message
							statusMsg := models.WebSocketMessage{
								Type: "session_status",
								Data: models.SessionStatusUpdate{
									Status:  "resumed",
									Message: fmt.Sprintf("Session resumed by %s after %.1f seconds.", ws.RemoteAddr(), pauseDuration),
								},
							}
							
							// Send resume notification to this client
							ws.WriteJSON(statusMsg)
							
							// Broadcast to all other clients
							go m.broadcastToSessionExcept(sessionID, ws, "session_status", statusMsg.Data)
							
							log.Printf("Session %s resumed by client %s after %.2f seconds", 
								conn.SessionID, ws.RemoteAddr(), pauseDuration)
						}
						conn.Lock.Unlock()
			}
		}
	}

		// Read from SSH stdout/stderr and write to WebSocket
		go func() {
			defer func() { done <- struct{}{} }()
			
			buffer := make([]byte, 1024)
			isPaused := false
			
			for {
				// Check for pause/resume signals
				select {
				case pauseState := <-conn.PauseChannels.Pause:
					isPaused = pauseState
					conn.PauseChannels.IsPaused <- isPaused
					if isPaused {
						log.Printf("stdout reader paused for session %s", conn.SessionID)
					} else {
						log.Printf("stdout reader resumed for session %s", conn.SessionID)
					}
					continue
				default:
					// Continue with normal operation
				}
				
				// If paused, wait for resume signal
				if isPaused {
					time.Sleep(500 * time.Millisecond)
					continue
				}
				
				// Read from stdout
				n, err := conn.Stdout.Read(buffer)
				if err \!= nil {
					if err \!= io.EOF {
						log.Printf("Failed to read from SSH stdout: %v", err)
					}
					return
				}

				// Send to WebSocket
				err = ws.WriteJSON(models.WebSocketMessage{
					Type: "terminal_output",
					Data: models.TerminalOutput{
						Data: string(buffer[:n]),
					},
				})
				if err \!= nil {
					log.Printf("Failed to write to WebSocket: %v", err)
					return
				}
			}
		}()

		// Read from SSH stderr and write to WebSocket
		go func() {
			defer func() { done <- struct{}{} }()
			
			buffer := make([]byte, 1024)
			isPaused := false
			
			for {
				// Check for pause/resume signals
				select {
				case pauseState := <-conn.PauseChannels.Pause:
					isPaused = pauseState
					conn.PauseChannels.IsPaused <- isPaused
					if isPaused {
						log.Printf("stderr reader paused for session %s", conn.SessionID)
					} else {
						log.Printf("stderr reader resumed for session %s", conn.SessionID)
					}
					continue
				default:
					// Continue with normal operation
				}
				
				// If paused, wait for resume signal
				if isPaused {
					time.Sleep(500 * time.Millisecond)
					continue
				}

				// Read from stderr
				n, err := conn.Stderr.Read(buffer)
				if err \!= nil {
					if err \!= io.EOF {
						log.Printf("Failed to read from SSH stderr: %v", err)
					}
					return
				}

				// Send to WebSocket
				err = ws.WriteJSON(models.WebSocketMessage{
					Type: "terminal_output",
					Data: models.TerminalOutput{
						Data: string(buffer[:n]),
					},
				})
				if err \!= nil {
					log.Printf("Failed to write to WebSocket: %v", err)
					return
				}
			}
		}()

		// Keep-alive
	go func() {
		ticker := time.NewTicker(m.keepAlive)
		defer ticker.Stop()

		for {
			select {
			case <-ticker.C:
				// Send ping message
				if err := ws.WriteControl(websocket.PingMessage, []byte("ping"), time.Now().Add(time.Second)); err != nil {
					log.Printf("Failed to send ping: %v", err)
					return
				}
			case <-done:
				return
			}
		}
	}()

	// Wait for done signal
	<-done
	
	// Unregister this WebSocket connection
	m.unregisterWebSocketClient(sessionID, ws)
	
	// Clean up - the session might have been terminated on purpose
	m.sessionMutex.Lock()
	if _, exists := m.sessions[sessionID]; exists {
		// Only close if it still exists (might have been closed by terminate action)
		conn.Close()
		delete(m.sessions, sessionID)
	}
	m.sessionMutex.Unlock()
}

// registerWebSocketClient adds a WebSocket connection to a session
func (m *SSHManager) registerWebSocketClient(sessionID string, ws *websocket.Conn) {
	m.wsClientsMutex.Lock()
	defer m.wsClientsMutex.Unlock()
	
	// Add this connection to the list for this session
	m.wsClients[sessionID] = append(m.wsClients[sessionID], ws)
	
	log.Printf("WebSocket client registered for session %s, total clients: %d", 
		sessionID, len(m.wsClients[sessionID]))
}

// unregisterWebSocketClient removes a WebSocket connection from a session
func (m *SSHManager) unregisterWebSocketClient(sessionID string, ws *websocket.Conn) {
	m.wsClientsMutex.Lock()
	defer m.wsClientsMutex.Unlock()
	
	clients := m.wsClients[sessionID]
	for i, client := range clients {
		if client == ws {
			// Remove this client by swapping with the last element and truncating the slice
			clients[i] = clients[len(clients)-1]
			m.wsClients[sessionID] = clients[:len(clients)-1]
			log.Printf("WebSocket client unregistered from session %s, remaining clients: %d", 
				sessionID, len(m.wsClients[sessionID]))
			break
		}
	}
	
	// If no more clients for this session, clean up the map entry
	if len(m.wsClients[sessionID]) == 0 {
		delete(m.wsClients, sessionID)
	}
}

// broadcastToSession sends a message to all WebSocket clients for a session
// broadcastToSessionExcept sends a message to all WebSocket clients for a session except the specified client
func (m *SSHManager) broadcastToSessionExcept(sessionID string, except *websocket.Conn, msgType string, msgData interface{}) {
	m.wsClientsMutex.RLock()
	clients := m.wsClients[sessionID]
	m.wsClientsMutex.RUnlock()
	
	if len(clients) == 0 {
		return // No clients connected for this session
	}
	
	message := models.WebSocketMessage{
		Type: msgType,
		Data: msgData,
	}
	
	// Send to all clients except the excluded one
	for _, client := range clients {
		if client \!= except {
			err := client.WriteJSON(message)
			if err \!= nil {
				log.Printf("Failed to send message to WebSocket client: %v", err)
				// Note: We don't unregister here as the client might still be active
				// The unregister will happen when the read loop detects the error
			}
		}
	}
}
func (m *SSHManager) broadcastToSession(sessionID string, msgType string, msgData interface{}) {
	m.wsClientsMutex.RLock()
	clients := m.wsClients[sessionID]
	m.wsClientsMutex.RUnlock()
	
	if len(clients) == 0 {
		return // No clients connected for this session
	}
	
	message := models.WebSocketMessage{
		Type: msgType,
		Data: msgData,
	}
	
	// Send to all clients
	for _, client := range clients {
		err := client.WriteJSON(message)
		if err != nil {
			log.Printf("Failed to send message to WebSocket client: %v", err)
			// Note: We don't unregister here as the client might still be active
			// The unregister will happen when the read loop detects the error
		}
	}
}

// SessionEventHandler notifies clients about session events
func (m *SSHManager) SessionEventHandler(sessionID string, eventType string, data string) error {
	m.sessionMutex.RLock()
	_, exists := m.sessions[sessionID]
	m.sessionMutex.RUnlock()

	if !exists {
		return errors.New("session not found")
	}

	// Create an event based on the event type
	var msgData interface{}
	
	switch eventType {
	case "context_update":
		// Parse the data as a context update
		var update models.ContextUpdate
		if err := json.Unmarshal([]byte(data), &update); err != nil {
			log.Printf("Failed to parse context update data: %v", err)
			return err
		}
		msgData = update
		
	case "suggestion_available":
		// Parse the data as a suggestion notification
		var suggestion models.SuggestionAvailable
		if err := json.Unmarshal([]byte(data), &suggestion); err != nil {
			log.Printf("Failed to parse suggestion data: %v", err)
			return err
		}
		msgData = suggestion
		
	case "session_status":
		// Parse the data as a status update
		var status models.SessionStatusUpdate
		if err := json.Unmarshal([]byte(data), &status); err != nil {
			log.Printf("Failed to parse status update data: %v", err)
			return err
		}
		msgData = status
		
	default:
		// For other event types, use a generic map
		var genericData map[string]interface{}
		if err := json.Unmarshal([]byte(data), &genericData); err != nil {
			// If it's not valid JSON, just use the string as is
			msgData = data
		} else {
			msgData = genericData
		}
	}
	
	// Broadcast the event to all WebSocket clients for this session
	m.broadcastToSession(sessionID, eventType, msgData)
	
	return nil
}

// ExecuteCommand executes a command in a session
func (m *SSHManager) ExecuteCommand(sessionID string, command string, isSuggested bool) (*models.CommandResult, error) {
	m.sessionMutex.RLock()
	conn, exists := m.sessions[sessionID]
	m.sessionMutex.RUnlock()

	if !exists {
		return nil, errors.New("session not found")
	}

	// Start timing
	startTime := time.Now()

	// Notify clients about starting the command
	if isSuggested {
		jsonData, _ := json.Marshal(map[string]interface{}{
			"command":     command,
			"is_suggested": true,
			"status":      "starting",
		})
		m.SessionEventHandler(sessionID, "command_starting", string(jsonData))
	}
	
	// Execute command by writing to stdin
	_, err := conn.Stdin.Write([]byte(command + "\n"))
	if err != nil {
		return nil, fmt.Errorf("failed to write command: %w", err)
	}

	// Calculate duration
	duration := time.Since(startTime)
	
	// Create a command result
	result := &models.CommandResult{
		Command:    command,
		Output:     "", // We can't capture output properly this way
		ExitCode:   0,  // We don't know the exit code
		WorkingDir: "", // We don't know the working directory
		DurationMs: int(duration.Milliseconds()),
	}

	// Log command to session service
	go func() {
		// If this is a suggested command, get its ID
		suggestionID := ""
		if isSuggested {
			// Try to find the suggestion ID from the previous request
			// For simplicity, we assume the most recent suggestion is the one being executed
			suggestion, err := m.sessionClient.GetRecentSuggestions(sessionID, 1)
			if err == nil && len(suggestion) > 0 {
				suggestionID = suggestion[0].ID
			}
		}
		
		err := m.sessionClient.SaveCommand(
			sessionID,
			conn.UserID,
			command,
			"", // We don't have output yet
			0,  // We don't know exit code
			"", // We don't know working directory
			int(duration.Milliseconds()),
			conn.TargetHost,       // Hostname
			conn.Username,         // Username
			isSuggested,           // From parameter
			suggestionID,          // Suggestion ID
		)
		if err != nil {
			log.Printf("Failed to save command to session service: %v", err)
		}
		
		// Notify clients about the command execution
		eventData := map[string]interface{}{
			"command": command,
			"duration_ms": int(duration.Milliseconds()),
			"is_suggested": isSuggested,
			"timestamp": time.Now().Format(time.RFC3339),
		}
		
		jsonData, _ := json.Marshal(eventData)
		m.SessionEventHandler(sessionID, "command_executed", string(jsonData))
	}()

	return result, nil
}

// CommandAnalysis contains information about a command for analysis
type CommandAnalysis struct {
	Command    string
	ID         string
	SessionID  string
	IsSuggested bool
}

// executeSuggestionCommand executes a suggested command with proper tracking and analysis
func (m *SSHManager) executeSuggestionCommand(sessionID string, suggestion struct {
	ID string
	Command string
}) (*models.CommandResult, error) {
	m.sessionMutex.RLock()
	conn, exists := m.sessions[sessionID]
	m.sessionMutex.RUnlock()

	if !exists {
		return nil, errors.New("session not found")
	}

	// Start timing
	startTime := time.Now()

	// Create metadata for tracking
	metadata := map[string]string{
		"source":        "suggestion",
		"suggestion_id": suggestion.ID,
		"host":          conn.TargetHost,
		"username":      conn.Username,
		"client_ip":     conn.ClientIP,
	}

	// Notify clients about starting the suggested command
	jsonData, _ := json.Marshal(map[string]interface{}{
		"command":       suggestion.Command,
		"is_suggested":  true,
		"suggestion_id": suggestion.ID,
		"status":        "starting",
		"metadata":      metadata,
		"timestamp":     startTime.Format(time.RFC3339),
	})
	m.SessionEventHandler(sessionID, "command_starting", string(jsonData))
	
	// Execute command by writing to stdin
	_, err := conn.Stdin.Write([]byte(suggestion.Command + "\n"))
	if err != nil {
		// Log the error
		log.Printf("Failed to execute suggested command: %v", err)
		
		// Create failure event
		failureData, _ := json.Marshal(map[string]interface{}{
			"command":       suggestion.Command,
			"is_suggested":  true,
			"suggestion_id": suggestion.ID,
			"status":        "failed",
			"error":         err.Error(),
			"timestamp":     time.Now().Format(time.RFC3339),
		})
		m.SessionEventHandler(sessionID, "command_failed", string(failureData))
		
		return nil, fmt.Errorf("failed to write command: %w", err)
	}

	// Calculate duration
	duration := time.Since(startTime)
	
	// Schedule command analysis
	go m.analyzeCommand(CommandAnalysis{
		Command:     suggestion.Command,
		ID:          suggestion.ID,
		SessionID:   sessionID,
		IsSuggested: true,
	})
	
	// Create a command result
	result := &models.CommandResult{
		Command:      suggestion.Command,
		Output:       "", // We can't capture output properly this way
		ExitCode:     0,  // We don't know the exit code
		WorkingDir:   "", // We don't know the working directory
		DurationMs:   int(duration.Milliseconds()),
		IsSuggested:  true,
		SuggestionID: suggestion.ID,
		Timestamp:    startTime,
		HasError:     false, // We don't know yet
		Metadata:     metadata,
	}

	// Log command to session service
	go func() {
		err := m.sessionClient.SaveCommand(
			sessionID,
			conn.UserID,
			suggestion.Command,
			"", // We don't have output yet
			0,  // We don't know exit code
			"", // We don't know working directory
			int(duration.Milliseconds()),
			conn.TargetHost,       // Hostname
			conn.Username,         // Username
			true,                  // Is suggested
			suggestion.ID,         // Suggestion ID from parameter
		)
		if err != nil {
			log.Printf("Failed to save command to session service: %v", err)
		}
		
		// Notify clients about the command execution
		eventData := map[string]interface{}{
			"command":       suggestion.Command,
			"duration_ms":   int(duration.Milliseconds()),
			"is_suggested":  true,
			"suggestion_id": suggestion.ID,
			"timestamp":     time.Now().Format(time.RFC3339),
			"metadata":      metadata,
		}
		
		jsonData, _ := json.Marshal(eventData)
		m.SessionEventHandler(sessionID, "command_executed", string(jsonData))
	}()

	return result, nil
}

// analyzeCommand analyzes a command for patterns and sends the analysis to the context aggregator
func (m *SSHManager) analyzeCommand(cmdInfo CommandAnalysis) {
	// Exit early if we don't have a session client
	if m.sessionClient == nil {
		return
	}
	
	// Wait a short delay to allow output to be processed
	time.Sleep(500 * time.Millisecond)
	
	// Here we would typically call the context aggregator to analyze the command
	// For now, we'll just log that we would do this
	log.Printf("Analyzing command: %s (ID: %s, Suggested: %v)", 
		cmdInfo.Command, cmdInfo.ID, cmdInfo.IsSuggested)
		
	// In a complete implementation, we would call an endpoint like:
	// POST /api/v1/context-aggregator/analyze-command
	// with details about the command, its output, and context
	
	// You could implement a more sophisticated version that:
	// 1. Retrieves recent output from the session service
	// 2. Sends it to the context aggregator for analysis
	// 3. Updates the command record with analysis results
}