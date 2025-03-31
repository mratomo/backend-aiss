package handlers

import (
	"net/http"
	"time"

	"github.com/gin-gonic/gin"

	"terminal-gateway-service/models"
)

// HealthCheck returns the health status of the service
func HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status": "ok",
		"time":   time.Now().Format(time.RFC3339),
		"service": "terminal-gateway-service",
	})
}

// SessionHandler handles all SSH session related requests
type SessionHandler struct {
	sshManager *SSHManager
}

// NewSessionHandler creates a new SessionHandler
func NewSessionHandler(manager *SSHManager) *SessionHandler {
	return &SessionHandler{
		sshManager: manager,
	}
}

// CreateSession creates a new SSH session
func (h *SessionHandler) CreateSession(c *gin.Context) {
	var params models.SessionCreateRequest
	if err := c.ShouldBindJSON(&params); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	clientIP := c.ClientIP()

	// Create new session
	session, err := h.sshManager.CreateSession(userID.(string), params, clientIP)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{
			"error": err.Error(),
		})
		return
	}

	// Return session information
	c.JSON(http.StatusCreated, models.SessionCreateResponse{
		SessionID:    session.ID,
		Status:       session.Status,
		TargetInfo:   session.TargetInfo,
		WebSocketURL: "/api/v1/terminal/sessions/" + session.ID + "/stream",
		CreatedAt:    session.CreatedAt,
		Message:      "Session created successfully. Connect to WebSocket for terminal I/O.",
	})
}

// GetSessions returns all sessions for the current user
func (h *SessionHandler) GetSessions(c *gin.Context) {
	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get query parameters for filtering
	status := c.Query("status")
	limit := 20 // Default limit
	offset := 0 // Default offset

	// Get sessions from manager
	sessions, err := h.sshManager.GetSessions(userID.(string), status, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"sessions": sessions,
		"total":    len(sessions),
		"limit":    limit,
		"offset":   offset,
	})
}

// GetSession returns a specific session by ID
func (h *SessionHandler) GetSession(c *gin.Context) {
	sessionID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get session from manager
	session, err := h.sshManager.GetSession(sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	// Verify the session belongs to the user
	if session.UserID != userID.(string) {
		// Check if user is admin
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
			return
		}
	}

	c.JSON(http.StatusOK, session)
}

// TerminateSession terminates an SSH session
func (h *SessionHandler) TerminateSession(c *gin.Context) {
	sessionID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get session from manager
	session, err := h.sshManager.GetSession(sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	// Verify the session belongs to the user
	if session.UserID != userID.(string) {
		// Check if user is admin
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
			return
		}
	}

	// Terminate the session
	err = h.sshManager.TerminateSession(sessionID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"status":     "disconnected",
		"message":    "Session terminated successfully",
	})
}

// UpdateSession updates session parameters
func (h *SessionHandler) UpdateSession(c *gin.Context) {
	sessionID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get session from manager
	session, err := h.sshManager.GetSession(sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	// Verify the session belongs to the user
	if session.UserID != userID.(string) {
		// Check if user is admin
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
			return
		}
	}

	// Parse update parameters
	var params struct {
		WindowSize struct {
			Cols int `json:"cols"`
			Rows int `json:"rows"`
		} `json:"window_size"`
		KeepAliveInterval int `json:"keep_alive_interval"`
	}

	if err := c.ShouldBindJSON(&params); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Update session
	err = h.sshManager.UpdateSession(sessionID, params)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"status":     "updated",
		"message":    "Session settings updated",
	})
}

// WebSocketHandler handles WebSocket connections for terminal I/O
func (h *SessionHandler) WebSocketHandler(c *gin.Context) {
	sessionID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get session from manager
	session, err := h.sshManager.GetSession(sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	// Verify the session belongs to the user
	if session.UserID != userID.(string) {
		// Check if user is admin
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
			return
		}
	}

	// Handle WebSocket connection
	h.sshManager.HandleWebSocket(c, sessionID)
}