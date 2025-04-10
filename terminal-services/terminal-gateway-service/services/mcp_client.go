package services

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"log"
	"net/http"
	"strings"
	"time"
)

// MCPClient provides methods to interact with the Model Context Protocol (MCP) service
type MCPClient struct {
	baseURL     string
	httpClient  *http.Client
	authToken   string
	retryConfig RetryConfig
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

// NewMCPClient creates a new client for the MCP service
func NewMCPClient(baseURL string, timeout time.Duration) *MCPClient {
	return &MCPClient{
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

// ActivateContext activates a context for the current session
func (c *MCPClient) ActivateContext(contextID string) error {
	url := fmt.Sprintf("%s/api/v1/mcp/activate-context", c.baseURL)

	data := map[string]string{
		"context_id": contextID,
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal context data: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if c.authToken != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))
	}

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return fmt.Errorf("MCP service error: %s", errorResp.Error)
		}
		return fmt.Errorf("MCP service returned error: %s", resp.Status)
	}

	return nil
}

// DeactivateContext deactivates a context
func (c *MCPClient) DeactivateContext(contextID string) error {
	url := fmt.Sprintf("%s/api/v1/mcp/deactivate-context", c.baseURL)

	data := map[string]string{
		"context_id": contextID,
	}

	jsonData, err := json.Marshal(data)
	if err != nil {
		return fmt.Errorf("failed to marshal context data: %w", err)
	}

	req, err := http.NewRequest(http.MethodPost, url, bytes.NewBuffer(jsonData))
	if err != nil {
		return fmt.Errorf("failed to create request: %w", err)
	}

	req.Header.Set("Content-Type", "application/json")
	if c.authToken != "" {
		req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", c.authToken))
	}

	// Use retry logic
	resp, err := c.doWithRetry(req)
	if err != nil {
		return fmt.Errorf("failed to send request: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		var errorResp struct {
			Error string `json:"error"`
		}
		if err := json.NewDecoder(resp.Body).Decode(&errorResp); err == nil && errorResp.Error != "" {
			return fmt.Errorf("MCP service error: %s", errorResp.Error)
		}
		return fmt.Errorf("MCP service returned error: %s", resp.Status)
	}

	return nil
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

// RetrieveTerminalContext gets context for a terminal command
func (c *MCPClient) RetrieveTerminalContext(sessionID, query string, terminalContext map[string]interface{}) (map[string]interface{}, error) {
	url := fmt.Sprintf("%s/api/v1/context/retrieve", c.baseURL)

	// Prepare the request payload
	payload := map[string]interface{}{
		"query": query,
		"context": map[string]interface{}{
			"session_id": sessionID,
		},
	}

	// Add terminal context if provided
	if terminalContext != nil {
		payload["context"].(map[string]interface{})["terminal_context"] = terminalContext
	}

	jsonData, err := json.Marshal(payload)
	if err != nil {
		return nil, fmt.Errorf("failed to marshal context data: %w", err)
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

// StoreTerminalContext stores terminal context in MCP
func (c *MCPClient) StoreTerminalContext(sessionID, userID, currentDir, currentUser string, lastCommands []string, hostname string) (map[string]interface{}, error) {
	// Prepare a formatted text representation of the terminal context
	commandHistory := strings.Join(lastCommands, "\n")
	text := fmt.Sprintf(`Terminal Session [%s]
User: %s
Host: %s
Directory: %s

Command History:
%s
`, sessionID, currentUser, hostname, currentDir, commandHistory)

	// Prepare metadata
	metadata := map[string]interface{}{
		"user_id":    userID,
		"session_id": sessionID,
		"terminal_context": map[string]interface{}{
			"current_directory": currentDir,
			"current_user":      currentUser,
			"hostname":          hostname,
		},
	}

	// Store using the standard store_document tool
	return c.StoreDocument(text, metadata)
}

// doWithRetry performs an HTTP request with retry logic
func (c *MCPClient) doWithRetry(req *http.Request) (*http.Response, error) {
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
