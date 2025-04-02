package services

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"net"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"terminal-gateway-service/models"
)

// RetryConfig defines the retry behavior for service calls
type RetryConfig struct {
	MaxRetries  int
	InitialWait time.Duration
	MaxWait     time.Duration
}

// SessionClient provides methods to interact with the terminal-session-service
type SessionClient struct {
	baseURL     string
	httpClient  *http.Client
	authToken   string
	retryConfig RetryConfig
}

// Suggestion represents a command suggestion from the suggestion service
type Suggestion struct {
	ID               string                 `json:"suggestion_id"`
	SuggestionType   string                 `json:"suggestion_type"`
	Title            string                 `json:"title"`
	Description      string                 `json:"description"`
	Command          string                 `json:"command"`
	RiskLevel        string                 `json:"risk_level"`
	RequiresApproval bool                   `json:"requires_approval"`
	Metadata         map[string]interface{} `json:"metadata"`
}

// NewSessionClient creates a new client for the terminal-session-service
func NewSessionClient(baseURL string, timeout time.Duration) *SessionClient {
	return &SessionClient{
		baseURL: baseURL,
		httpClient: &http.Client{
			Timeout: timeout,
			// Configure transport with connection pooling
			Transport: &http.Transport{
				MaxIdleConns:       10,
				IdleConnTimeout:    30 * time.Second,
				DisableCompression: false,
				MaxConnsPerHost:    10,
			},
		},
		retryConfig: RetryConfig{
			MaxRetries:  3,
			InitialWait: 100 * time.Millisecond,
			MaxWait:     2 * time.Second,
		},
	}
}

// WithRetryConfig sets a custom retry configuration
func (c *SessionClient) WithRetryConfig(config RetryConfig) *SessionClient {
	c.retryConfig = config
	return c
}

// doWithRetry performs an HTTP request with retry logic and circuit breaker pattern
func (c *SessionClient) doWithRetry(req *http.Request) (*http.Response, error) {
	if req == nil {
		return nil, fmt.Errorf("request cannot be nil")
	}

	// Get the circuit breaker for this service (create if doesn't exist)
	breaker := getCircuitBreaker(c.baseURL)
	
	// Execute with circuit breaker
	result, err := breaker.Execute(func() (interface{}, error) {
		var resp *http.Response
		var err error
		
		wait := c.retryConfig.InitialWait
		
		for attempt := 0; attempt <= c.retryConfig.MaxRetries; attempt++ {
			// Create request context with timeout
			ctx, cancel := context.WithTimeout(context.Background(), c.httpClient.Timeout)
			reqWithCtx := req.Clone(ctx)
			
			// Make the request
			resp, err = c.httpClient.Do(reqWithCtx)
			
			// Always cancel the context after the request is done
			cancel()
			
			// If successful or permanent error, return immediately
			if err == nil && resp != nil && resp.StatusCode < 500 {
				return resp, nil
			}
			
			// If it's the last attempt, return whatever we got
			if attempt == c.retryConfig.MaxRetries {
				if err != nil {
					// Convert temporary network errors to circuit breaker failures
					if isTemporaryError(err) {
						return nil, fmt.Errorf("service unavailable after %d attempts: %w", attempt+1, err)
					}
					return nil, fmt.Errorf("request failed after %d attempts: %w", attempt+1, err)
				}
				return resp, nil
			}
			
			// If response exists but has an error status, log it
			if err == nil && resp != nil && resp.StatusCode >= 500 {
				log.Printf("[%s] Request failed with status %d, retrying (%d/%d)...", 
					shortenURL(c.baseURL), resp.StatusCode, attempt+1, c.retryConfig.MaxRetries)
				resp.Body.Close() // Important: close the body to avoid leaks
			} else if err != nil {
				// Omit sensitive data like tokens from log messages
				errorString := err.Error()
				// Sanitize error message to prevent token leaks
				if strings.Contains(errorString, "Bearer") {
					errorString = "auth error (token details omitted for security)"
				}
				log.Printf("[%s] Request error: %s, retrying (%d/%d)...", 
					shortenURL(c.baseURL), errorString, attempt+1, c.retryConfig.MaxRetries)
			}
			
			// Wait before retrying (with exponential backoff, capped at MaxWait)
			time.Sleep(wait)
			wait *= 2
			if wait > c.retryConfig.MaxWait {
				wait = c.retryConfig.MaxWait
			}
		}
		
		// Should never reach here due to returns in the loop, but return empty values just in case
		if resp == nil && err == nil {
			err = fmt.Errorf("unexpected error: no response and no error after %d retries", c.retryConfig.MaxRetries)
		}
		return resp, err
	})
	
	if err != nil {
		if errors.Is(err, ErrCircuitOpen) {
			return nil, fmt.Errorf("service %s is temporarily unavailable (circuit open)", shortenURL(c.baseURL))
		}
		return nil, err
	}
	
	// Safe type assertion
	resp, ok := result.(*http.Response)
	if !ok || resp == nil {
		return nil, fmt.Errorf("invalid response type from circuit breaker")
	}
	
	return resp, nil
}

// isTemporaryError checks if an error is temporary and should trigger circuit breaker
func isTemporaryError(err error) bool {
	if err == nil {
		return false
	}
	
	// Check for network-related errors
	if errors.Is(err, context.DeadlineExceeded) || 
	   errors.Is(err, io.EOF) {
		return true
	}
	
	// Check string patterns safely
	errMsg := err.Error()
	if strings.Contains(errMsg, "connection refused") ||
	   strings.Contains(errMsg, "no such host") ||
	   strings.Contains(errMsg, "i/o timeout") {
		return true
	}
	
	// Check for temporary net errors
	var netErr net.Error
	if errors.As(err, &netErr) {
		return netErr.Temporary()
	}
	
	return false
}

// shortenURL returns a shorter version of the URL for logging
func shortenURL(url string) string {
	parts := strings.Split(url, "/")
	if len(parts) >= 3 {
		return parts[2] // Return only the host part
	}
	return url
}

// Global circuit breaker registry
var (
	circuitBreakers = make(map[string]*CircuitBreaker)
	breakerMutex    sync.Mutex
)

// getCircuitBreaker returns a circuit breaker for the given URL
func getCircuitBreaker(url string) *CircuitBreaker {
	breakerMutex.Lock()
	defer breakerMutex.Unlock()
	
	key := shortenURL(url)
	if cb, exists := circuitBreakers[key]; exists {
		return cb
	}
	
	// Create new circuit breaker with default settings
	cb := NewCircuitBreaker(
		key,
		WithTimeout(10 * time.Second),
		WithFailureThreshold(5),
		WithSuccessThreshold(2),
	)
	circuitBreakers[key] = cb
	
	return cb
}

// SetAuthToken sets the authentication token for the client
func (c *SessionClient) SetAuthToken(token string) {
	c.authToken = token
}

// CreateSession creates a new terminal session in the session service
func (c *SessionClient) CreateSession(session *models.Session) error {
	url := fmt.Sprintf("%s/api/v1/sessions", c.baseURL)
	
	// Convert gateway session to session service format
	sessionData := map[string]interface{}{
		"session_id":  session.ID,
		"user_id":     session.UserID,
		"status":      string(session.Status),
		"target_info": map[string]string{
			"hostname":    session.TargetInfo.Hostname,
			"ip":          session.TargetInfo.IPAddress,
			"os_detected": session.TargetInfo.OSType,
			"os_version":  session.TargetInfo.OSVersion,
		},
		"metadata": map[string]interface{}{
			"client_ip":     session.Metadata.ClientIP,
			"user_agent":    session.Metadata.UserAgent,
			"terminal_type": session.Metadata.TerminalType,
			"window_size": map[string]int{
				"cols": session.Metadata.TermCols,
				"rows": session.Metadata.TermRows,
			},
		},
	}

	jsonData, err := json.Marshal(sessionData)
	if err != nil {
		return fmt.Errorf("failed to marshal session: %w", err)
	}

	// Create session in the session service
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return fmt.Errorf("session service returned error: %s", resp.Status)
	}

	return nil
}

// UpdateSessionStatus updates the status of a terminal session
func (c *SessionClient) UpdateSessionStatus(sessionID string, status models.SessionStatus) error {
	url := fmt.Sprintf("%s/api/v1/sessions/%s/status", c.baseURL, sessionID)
	
	statusData := map[string]string{
		"status": string(status),
	}

	jsonData, err := json.Marshal(statusData)
	if err != nil {
		return fmt.Errorf("failed to marshal status data: %w", err)
	}

	req, err := http.NewRequest(http.MethodPatch, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return fmt.Errorf("session service returned error: %s", resp.Status)
	}

	return nil
}

// SaveCommand saves a command to the session service
func (c *SessionClient) SaveCommand(sessionID, userID, commandText, output string, exitCode int, workingDir string, durationMs int, hostname string, username string, isSuggested bool, suggestionID string) error {
	url := fmt.Sprintf("%s/api/v1/commands", c.baseURL)
	
	commandData := map[string]interface{}{
		"session_id":        sessionID,
		"user_id":           userID,
		"command":           commandText,
		"output":            output,
		"exit_code":         exitCode,
		"working_directory": workingDir,
		"timestamp":         time.Now(),
		"duration_ms":       durationMs,
		"is_suggested":      isSuggested,
	}
	
	// Add optional fields
	if suggestionID != "" {
		commandData["suggestion_id"] = suggestionID
	}
	
	// Add context information
	if hostname != "" || username != "" {
		contextInfo := map[string]string{}
		if hostname != "" {
			contextInfo["hostname"] = hostname
		}
		if username != "" {
			contextInfo["username"] = username
		}
		commandData["context_info"] = contextInfo
	}

	jsonData, err := json.Marshal(commandData)
	if err != nil {
		return fmt.Errorf("failed to marshal command data: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return fmt.Errorf("session service returned error: %s", resp.Status)
	}

	return nil
}

// UpdateSessionContext updates the context information for a terminal session
func (c *SessionClient) UpdateSessionContext(sessionID, userID, currentDir, currentUser string, envVars map[string]string, lastExitCode int) error {
	url := fmt.Sprintf("%s/api/v1/contexts", c.baseURL)
	
	contextData := map[string]interface{}{
		"session_id":           sessionID,
		"user_id":              userID,
		"working_directory":    currentDir,
		"current_user":         currentUser,
		"environment_variables": envVars,
		"last_exit_code":       lastExitCode,
	}

	jsonData, err := json.Marshal(contextData)
	if err != nil {
		return fmt.Errorf("failed to marshal context data: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return fmt.Errorf("session service returned error: %s", resp.Status)
	}

	return nil
}

// GetUserSessions gets all sessions for a user
func (c *SessionClient) GetUserSessions(userID, status string, limit, offset int) ([]models.Session, error) {
	url := fmt.Sprintf("%s/api/v1/sessions?user_id=%s", c.baseURL, userID)
	
	if status != "" {
		url += fmt.Sprintf("&status=%s", status)
	}
	
	if limit > 0 {
		url += fmt.Sprintf("&limit=%d", limit)
	}
	
	if offset > 0 {
		url += fmt.Sprintf("&offset=%d", offset)
	}

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("session service returned error: %s", resp.Status)
	}

	var response struct {
		Sessions []struct {
			SessionID  string            `json:"session_id"`
			UserID     string            `json:"user_id"`
			Status     string            `json:"status"`
			TargetInfo map[string]string `json:"target_info"`
			Metadata   struct {
				ClientIP     string `json:"client_ip"`
				UserAgent    string `json:"user_agent"`
				TerminalType string `json:"terminal_type"`
				WindowSize   struct {
					Cols int `json:"cols"`
					Rows int `json:"rows"`
				} `json:"window_size"`
			} `json:"metadata"`
			CreatedAt    time.Time  `json:"created_at"`
			LastActivity time.Time  `json:"last_active"`
			EndedAt      *time.Time `json:"ended_at"`
			Stats        struct {
				CommandCount   int   `json:"command_count"`
				BytesReceived  int64 `json:"bytes_received"`
				BytesSent      int64 `json:"bytes_sent"`
				TotalDurationS int   `json:"total_duration_s"`
			} `json:"stats"`
		} `json:"sessions"`
		Count  int `json:"count"`
		Limit  int `json:"limit"`
		Offset int `json:"offset"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	sessions := make([]models.Session, 0, len(response.Sessions))
	for _, sess := range response.Sessions {
		session := models.Session{
			ID:        sess.SessionID,
			UserID:    sess.UserID,
			Status:    models.SessionStatus(sess.Status),
			CreatedAt: sess.CreatedAt,
			LastActive: sess.LastActivity,
			EndedAt:   sess.EndedAt,
			Metadata: models.Metadata{
				ClientIP:     sess.Metadata.ClientIP,
				UserAgent:    sess.Metadata.UserAgent,
				TerminalType: sess.Metadata.TerminalType,
				TermCols:     sess.Metadata.WindowSize.Cols,
				TermRows:     sess.Metadata.WindowSize.Rows,
			},
			TargetInfo: models.TargetInfo{
				Hostname:   sess.TargetInfo["hostname"],
				IPAddress:  sess.TargetInfo["ip"],
				OSType:     sess.TargetInfo["os_detected"],
				OSVersion:  sess.TargetInfo["os_version"],
			},
			Stats: models.Stats{
				CommandCount:   sess.Stats.CommandCount,
				BytesReceived:  sess.Stats.BytesReceived,
				BytesSent:      sess.Stats.BytesSent,
				TotalDurationS: sess.Stats.TotalDurationS,
			},
		}
		sessions = append(sessions, session)
	}

	return sessions, nil
}

// GetSession gets a specific session by ID
func (c *SessionClient) GetSession(sessionID string) (*models.Session, error) {
	url := fmt.Sprintf("%s/api/v1/sessions/%s", c.baseURL, sessionID)

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		if resp.StatusCode == http.StatusNotFound {
			return nil, fmt.Errorf("session not found: %s", sessionID)
		}
		
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("session service returned error: %s", resp.Status)
	}

	var sess struct {
		SessionID  string            `json:"session_id"`
		UserID     string            `json:"user_id"`
		Status     string            `json:"status"`
		TargetInfo map[string]string `json:"target_info"`
		Metadata   struct {
			ClientIP     string `json:"client_ip"`
			UserAgent    string `json:"user_agent"`
			TerminalType string `json:"terminal_type"`
			WindowSize   struct {
				Cols int `json:"cols"`
				Rows int `json:"rows"`
			} `json:"window_size"`
		} `json:"metadata"`
		CreatedAt    time.Time  `json:"created_at"`
		LastActivity time.Time  `json:"last_active"`
		EndedAt      *time.Time `json:"ended_at"`
		Stats        struct {
			CommandCount   int   `json:"command_count"`
			BytesReceived  int64 `json:"bytes_received"`
			BytesSent      int64 `json:"bytes_sent"`
			TotalDurationS int   `json:"total_duration_s"`
		} `json:"stats"`
	}

	if err := json.NewDecoder(resp.Body).Decode(&sess); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	session := &models.Session{
		ID:        sess.SessionID,
		UserID:    sess.UserID,
		Status:    models.SessionStatus(sess.Status),
		CreatedAt: sess.CreatedAt,
		LastActive: sess.LastActivity,
		EndedAt:   sess.EndedAt,
		Metadata: models.Metadata{
			ClientIP:     sess.Metadata.ClientIP,
			UserAgent:    sess.Metadata.UserAgent,
			TerminalType: sess.Metadata.TerminalType,
			TermCols:     sess.Metadata.WindowSize.Cols,
			TermRows:     sess.Metadata.WindowSize.Rows,
		},
		TargetInfo: models.TargetInfo{
			Hostname:   sess.TargetInfo["hostname"],
			IPAddress:  sess.TargetInfo["ip"],
			OSType:     sess.TargetInfo["os_detected"],
			OSVersion:  sess.TargetInfo["os_version"],
		},
		Stats: models.Stats{
			CommandCount:   sess.Stats.CommandCount,
			BytesReceived:  sess.Stats.BytesReceived,
			BytesSent:      sess.Stats.BytesSent,
			TotalDurationS: sess.Stats.TotalDurationS,
		},
	}

	return session, nil
}

// GetRecentSuggestions gets the most recent suggestions for a session
func (c *SessionClient) GetRecentSuggestions(sessionID string, limit int) ([]Suggestion, error) {
	url := fmt.Sprintf("%s/api/v1/sessions/%s/suggestions?limit=%d", c.baseURL, sessionID, limit)

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("session service returned error: %s", resp.Status)
	}

	var response struct {
		Suggestions []Suggestion `json:"suggestions"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return response.Suggestions, nil
}

// GetSuggestion gets a suggestion by ID
func (c *SessionClient) GetSuggestion(suggestionID string) (*Suggestion, error) {
	url := fmt.Sprintf("%s/api/v1/suggestions/%s", c.baseURL, suggestionID)

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		if resp.StatusCode == http.StatusNotFound {
			return nil, fmt.Errorf("suggestion not found: %s", suggestionID)
		}
		
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("session service returned error: %s", resp.Status)
	}

	var suggestion Suggestion
	if err := json.NewDecoder(resp.Body).Decode(&suggestion); err != nil {
		return nil, fmt.Errorf("failed to decode suggestion: %w", err)
	}

	return &suggestion, nil
}

// UpdateSessionMode updates the mode of a terminal session
func (c *SessionClient) UpdateSessionMode(sessionID string, mode string, areaID string) error {
	url := fmt.Sprintf("%s/api/v1/sessions/%s/mode", c.baseURL, sessionID)
	
	modeData := map[string]string{
		"mode": mode,
	}
	
	if areaID != "" {
		modeData["area_id"] = areaID
	}

	jsonData, err := json.Marshal(modeData)
	if err != nil {
		return fmt.Errorf("failed to marshal mode data: %w", err)
	}

	req, err := http.NewRequest(http.MethodPatch, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return fmt.Errorf("session service returned error: %s", resp.Status)
	}

	return nil
}

// GetSessionContext gets the context for a terminal session
func (c *SessionClient) GetSessionContext(sessionID string) (map[string]interface{}, error) {
	url := fmt.Sprintf("%s/api/v1/contexts/%s", c.baseURL, sessionID)

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		if resp.StatusCode == http.StatusNotFound {
			// Return empty context if not found
			return map[string]interface{}{}, nil
		}
		
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("session service returned error: %s", resp.Status)
	}

	var context map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&context); err != nil {
		return nil, fmt.Errorf("failed to decode context: %w", err)
	}

	return context, nil
}

// RagResponse represents a response from the RAG agent
type RagResponse struct {
	Query       string `json:"query"`
	Answer      string `json:"answer"`
	HasError    bool   `json:"has_error"`
	ErrorMsg    string `json:"error_msg,omitempty"`
	LlmProvider string `json:"llm_provider"`
	Model       string `json:"model"`
	Sources     []struct {
		Title   string `json:"title"`
		Snippet string `json:"snippet"`
	} `json:"sources,omitempty"`
}

// ProcessRagQuery sends a query to the RAG agent
func (c *SessionClient) ProcessRagQuery(query string, userID string, areaID string, terminalContext map[string]interface{}) (*RagResponse, error) {
	// Construct the RAG API URL
	ragUrl := os.Getenv("RAG_AGENT_URL")
	if ragUrl == "" {
		ragUrl = "http://rag-agent:8000"
	}
	url := fmt.Sprintf("%s/api/v1/query", ragUrl)
	
	// Build query payload
	queryData := map[string]interface{}{
		"query":           query,
		"user_id":         userID,
		"area_id":         areaID,
		"include_context": true,
	}
	
	// Add terminal context if available
	if terminalContext != nil {
		queryData["terminal_context"] = terminalContext
	}

	jsonData, err := json.Marshal(queryData)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal query data: %w", err)
	}

	// Create request
	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Custom timeout for RAG queries
	httpClient := &http.Client{
		Timeout: 60 * time.Second, // Longer timeout for LLM generation
	}
	
	// Execute request with longer timeout
	resp, err := httpClient.Do(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("RAG agent error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("RAG agent returned error: %s", resp.Status)
	}

	var response RagResponse
	if err := json.NewDecoder(resp.Body).Decode(&response); err != nil {
		return nil, fmt.Errorf("failed to decode RAG response: %w", err)
	}

	return &response, nil
}

// GetAreaInfo obtiene información sobre un área de conocimiento
func (c *SessionClient) GetAreaInfo(areaID string) (struct { Name string }, error) {
	url := fmt.Sprintf("%s/api/v1/areas/%s", c.baseURL, areaID)

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return struct { Name string }{Name: areaID}, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return struct { Name string }{Name: areaID}, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		if resp.StatusCode == http.StatusNotFound {
			// Si no se encuentra el área, devolver el ID como nombre
			return struct { Name string }{Name: areaID}, nil
		}
		
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return struct { Name string }{Name: areaID}, fmt.Errorf("session service error: %s", errorResp.Error)
		}
		return struct { Name string }{Name: areaID}, fmt.Errorf("session service returned error: %s", resp.Status)
	}

	var area struct {
		Name string `json:"name"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&area); err != nil {
		return struct { Name string }{Name: areaID}, fmt.Errorf("failed to decode area info: %w", err)
	}

	return area, nil
}