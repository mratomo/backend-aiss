package handlers

import (
	"encoding/json"
	"fmt"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/bson/primitive"

	"terminal-session-service/models"
	"terminal-session-service/repositories"
)

// QueryModeHandler handles queries related to terminal session query mode
type QueryModeHandler struct {
	repository *repositories.MongoDBRepository
}

// NewQueryModeHandler creates a new QueryModeHandler
func NewQueryModeHandler(repository *repositories.MongoDBRepository) *QueryModeHandler {
	return &QueryModeHandler{
		repository: repository,
	}
}

// UpdateSessionMode handles a request to update a session's mode
func (h *QueryModeHandler) UpdateSessionMode(c *gin.Context) {
	sessionID := c.Param("id")

	// Parse request
	var updateRequest struct {
		Mode    string `json:"mode" binding:"required,oneof=normal query"`
		AreaID  string `json:"area_id"`
	}

	if err := c.ShouldBindJSON(&updateRequest); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Get user ID from context
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Update the session mode in the database
	err := h.repository.UpdateSessionMode(sessionID, models.SessionMode(updateRequest.Mode), updateRequest.AreaID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Create a mode change log entry
	modeChangeLog := models.SessionModeChange{
		ID:          primitive.NewObjectID(),
		SessionID:   sessionID,
		UserID:      userID.(string),
		PreviousMode: "", // We don't track this on the server side
		NewMode:     updateRequest.Mode,
		AreaID:      updateRequest.AreaID,
		Timestamp:   time.Now(),
	}

	// Save mode change log
	err = h.repository.SaveSessionModeChange(modeChangeLog)
	if err != nil {
		// Log the error but continue
		fmt.Printf("Failed to save mode change log: %v\n", err)
	}

	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"mode":       updateRequest.Mode,
		"area_id":    updateRequest.AreaID,
		"message":    "Session mode updated successfully",
	})
}

// GetSessionContext retrieves context information for a session
func (h *QueryModeHandler) GetSessionContext(c *gin.Context) {
	sessionID := c.Param("id")

	// Get user ID from context
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get session context from repository
	context, err := h.repository.GetSessionContext(sessionID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Get command history for additional context
	commandHistory, err := h.repository.GetRecentCommands(sessionID, 10)
	if err != nil {
		// Log error but continue
		fmt.Printf("Failed to get command history: %v\n", err)
	}

	// Add command history to context
	if len(commandHistory) > 0 {
		commandTexts := make([]string, 0, len(commandHistory))
		outputs := make([]string, 0, len(commandHistory))
		
		for _, cmd := range commandHistory {
			commandTexts = append(commandTexts, cmd.CommandText)
			if cmd.Output != "" {
				outputs = append(outputs, cmd.Output)
			}
		}
		
		context["recent_commands"] = commandTexts
		context["recent_outputs"] = outputs
	}

	// Add user ID to context
	context["user_id"] = userID.(string)
	
	c.JSON(http.StatusOK, context)
}

// GetActiveSessionsByUser gets all active sessions for a user
func (h *QueryModeHandler) GetActiveSessionsByUser(c *gin.Context) {
	// Get user ID from context
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get active sessions from repository
	sessions, err := h.repository.GetSessionsByUserAndStatus(userID.(string), string(models.SessionStatusConnected))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Return the active sessions
	c.JSON(http.StatusOK, gin.H{
		"sessions": sessions,
		"count":    len(sessions),
	})
}

// GetUserSessionsWithArea gets all sessions that have an active area for a user
func (h *QueryModeHandler) GetUserSessionsWithArea(c *gin.Context) {
	// Get user ID from context
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get sessions with active area from repository
	sessions, err := h.repository.GetSessionsWithActiveArea(userID.(string))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Return the sessions
	c.JSON(http.StatusOK, gin.H{
		"sessions": sessions,
		"count":    len(sessions),
	})
}