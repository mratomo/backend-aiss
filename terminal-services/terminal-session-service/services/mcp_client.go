package services

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"terminal-session-service/models"
	"terminal-session-service/utils"
)

// MCPClient provides methods to interact with the Model Context Protocol (MCP) service
type MCPClient struct {
	baseURL     string
	httpClient  *http.Client
	authToken   string
	retryConfig RetryConfig
	logger      *utils.Logger
}

// MCPStatus represents the status response from MCP
type MCPStatus struct {
	Name    string `json:"name"`
	Version string `json:"version"`
	Tools   []struct {
		Name        string `json:"name"`
		Description string `json:"description"`
	} `json:"tools"`
}

// RetryConfig defines the retry behavior for service calls
type RetryConfig struct {
	MaxRetries  int
	InitialWait time.Duration
	MaxWait     time.Duration
}

// ErrCircuitOpen is returned when the circuit breaker is open
var ErrCircuitOpen = errors.New("circuit breaker is open")

// NewMCPClient creates a new client for the MCP service
func NewMCPClient(baseURL string, timeout time.Duration) *MCPClient {
	// Try to get the service URL from the environment
	if baseURL == "" {
		baseURL = os.Getenv("MCP_SERVICE_URL")
		if baseURL == "" {
			// Default if not specified
			baseURL = "http://context-service:8083"
		}
	}

	client := &MCPClient{
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
		logger: utils.GetLogger("mcp_client"),
	}

	// Set auth token if available from environment
	authToken := os.Getenv("JWT_SECRET")
	if authToken != "" {
		client.authToken = authToken
	}

	return client
}

// SetAuthToken sets the authentication token for the client
func (c *MCPClient) SetAuthToken(token string) {
	c.authToken = token
}

// WithRetryConfig sets a custom retry configuration
func (c *MCPClient) WithRetryConfig(config RetryConfig) *MCPClient {
	c.retryConfig = config
	return c
}

// GetStatus retrieves the MCP service status
func (c *MCPClient) GetStatus() (*MCPStatus, error) {
	url := fmt.Sprintf("%s/api/v1/mcp/status", c.baseURL)

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	if c.authToken != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))
	}

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("MCP service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("MCP service returned error: %s", resp.Status)
	}

	var status MCPStatus
	if err := json.NewDecoder(resp.Body).Decode(&status); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return &status, nil
}

// GetActiveContexts retrieves the currently active contexts
func (c *MCPClient) GetActiveContexts() ([]map[string]interface{}, error) {
	url := fmt.Sprintf("%s/api/v1/mcp/active-contexts", c.baseURL)

	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	if c.authToken != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))
	}

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("MCP service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("MCP service returned error: %s", resp.Status)
	}

	var contexts []map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&contexts); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return contexts, nil
}

// StoreDocument stores a document in MCP
func (c *MCPClient) StoreDocument(information string, metadata map[string]interface{}) (map[string]interface{}, error) {
	url := fmt.Sprintf("%s/api/v1/mcp/tools/store-document", c.baseURL)

	data := map[string]interface{}{
		"information": information,
		"metadata":    metadata,
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal document data: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if c.authToken != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))
	}

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("MCP service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("MCP service returned error: %s", resp.Status)
	}

	var result map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		return nil, fmt.Errorf("failed to decode response: %w", err)
	}

	return result, nil
}

// FindRelevant finds relevant information for a query
func (c *MCPClient) FindRelevant(query string, limit int) ([]map[string]interface{}, error) {
	url := fmt.Sprintf("%s/api/v1/mcp/tools/find-relevant", c.baseURL)

	data := map[string]interface{}{
		"query": query,
		"limit": limit,
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal query data: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return nil, fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if c.authToken != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))
	}

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return nil, fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return nil, fmt.Errorf("MCP service error: %s", errorResp.Error)
		}
		return nil, fmt.Errorf("MCP service returned error: %s", resp.Status)
	}

	var result struct {
		Results []map[string]interface{} `json:"results"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
		// Try as direct array
		var items []map[string]interface{}
		// Reset the response body reader
		resp.Body.Close()
		// Re-send the request
		resp, err = c.doWithRetry(req)
		if err != nil {
			return nil, fmt.Errorf("failed to re-send request: %w", err)
		}
		defer resp.Body.Close()
		
		if err := json.NewDecoder(resp.Body).Decode(&items); err != nil {
			return nil, fmt.Errorf("failed to decode response as array: %w", err)
		}
		return items, nil
	}

	return result.Results, nil
}

// StoreSessionContext stores a terminal session context in MCP
func (c *MCPClient) StoreSessionContext(sessionContext *models.SessionContext) (map[string]interface{}, error) {
	// Format the content in a structured way for better context retrieval
	text := fmt.Sprintf(`Terminal Session Context [%s]
User: %s
Working Directory: %s
Current User: %s
Last Exit Code: %d

Environment Variables:
%s
`, sessionContext.SessionID, sessionContext.UserID, sessionContext.CurrentDirectory, 
   sessionContext.CurrentUser, sessionContext.LastExitCode, formatEnvVars(sessionContext.EnvironmentVars))

	// Add detected applications if available
	if len(sessionContext.DetectedApplications) > 0 {
		text += fmt.Sprintf("\nDetected Applications:\n%s", strings.Join(sessionContext.DetectedApplications, ", "))
	}

	// Add detected errors if available
	if len(sessionContext.DetectedErrors) > 0 {
		text += "\n\nDetected Errors:\n"
		for _, err := range sessionContext.DetectedErrors {
			text += fmt.Sprintf("- %s (Count: %d, Last Seen: %s)\n", 
				err.Pattern, err.Count, err.LastSeen.Format(time.RFC3339))
		}
	}

	// Prepare metadata for efficient retrieval
	metadata := map[string]interface{}{
		"session_id":      sessionContext.SessionID,
		"user_id":         sessionContext.UserID,
		"content_type":    "terminal_session_context",
		"timestamp":       sessionContext.LastUpdated.Format(time.RFC3339),
		"session_context": map[string]interface{}{
			"current_directory":     sessionContext.CurrentDirectory,
			"current_user":          sessionContext.CurrentUser,
			"last_exit_code":        sessionContext.LastExitCode,
			"detected_applications": sessionContext.DetectedApplications,
		},
	}

	// Use the standard store_document tool to save session context
	return c.StoreDocument(text, metadata)
}

// formatEnvVars formats environment variables for display
func formatEnvVars(envVars map[string]string) string {
	if len(envVars) == 0 {
		return "None"
	}

	var result strings.Builder
	for key, value := range envVars {
		// Don't include secrets and tokens in the context
		if isSecret(key) {
			result.WriteString(fmt.Sprintf("%s=<REDACTED>\n", key))
		} else {
			result.WriteString(fmt.Sprintf("%s=%s\n", key, value))
		}
	}
	return result.String()
}

// isSecret checks if a key represents a secret
func isSecret(key string) bool {
	lowerKey := strings.ToLower(key)
	secretPatterns := []string{
		"token", "key", "password", "secret", "credential", "auth", 
		"passwd", "api_key", "apikey", "access_key",
	}

	for _, pattern := range secretPatterns {
		if strings.Contains(lowerKey, pattern) {
			return true
		}
	}
	return false
}

// doWithRetry performs an HTTP request with retry logic
func (c *MCPClient) doWithRetry(req *http.Request) (*http.Response, error) {
	if req == nil {
		return nil, fmt.Errorf("request cannot be nil")
	}
	
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
				return nil, fmt.Errorf("request failed after %d attempts: %w", attempt+1, err)
			}
			return resp, nil
		}
		
		// If response exists but has an error status, log it
		if err == nil && resp != nil && resp.StatusCode >= 500 {
			c.logger.Warn("Request failed with status %d, retrying (%d/%d)...", 
				resp.StatusCode, attempt+1, c.retryConfig.MaxRetries)
			resp.Body.Close() // Important: close the body to avoid leaks
		} else if err != nil {
			// Omit sensitive data like tokens from log messages
			errorString := err.Error()
			// Sanitize error message to prevent token leaks
			if strings.Contains(errorString, "Bearer") {
				errorString = "auth error (token details omitted for security)"
			}
			c.logger.Warn("Request error: %s, retrying (%d/%d)...", 
				errorString, attempt+1, c.retryConfig.MaxRetries)
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
}