package handlers

import (
	"net/http"
	"strconv"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"terminal-session-service/models"
	"terminal-session-service/repositories"
)

// SessionRepository interface defines the methods required for session operations
type SessionRepository interface {
	SaveSession(session *models.Session) error
	GetSession(sessionID string) (*models.Session, error)
	GetUserSessions(userID string, status string, limit, offset int) ([]*models.Session, error)
	SearchSessions(req *models.SessionSearchRequest) ([]*models.Session, int, error)
	UpdateSessionStatus(sessionID string, status models.SessionStatus) error
	
	SaveCommand(command *models.Command) error
	GetCommand(commandID string) (*models.Command, error)
	GetSessionCommands(sessionID string, limit, offset int) ([]*models.Command, error)
	GetUserCommands(userID string, limit, offset int) ([]*models.Command, error)
	SearchCommands(req *models.HistorySearchRequest) ([]*models.Command, int, error)
	
	SaveBookmark(bookmark *models.Bookmark) error
	GetBookmark(bookmarkID string) (*models.Bookmark, error)
	GetUserBookmarks(userID string, limit, offset int) ([]*models.Bookmark, error)
	DeleteBookmark(bookmarkID string) error
	
	SaveContext(context *models.SessionContext) error
	GetContext(sessionID string) (*models.SessionContext, error)
	
	PurgeOldSessions(days int) (int, error)
	PurgeOldCommands(days int) (int, error)
	
	Close() error
}

// HealthCheck returns the health status of the service
func HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status":  "ok",
		"time":    time.Now().Format(time.RFC3339),
		"service": "terminal-session-service",
	})
}

// SessionHandler handles session-related operations
type SessionHandler struct {
	repo SessionRepository
}

// NewSessionHandler creates a new SessionHandler
func NewSessionHandler(repo SessionRepository) *SessionHandler {
	return &SessionHandler{
		repo: repo,
	}
}

// CreateSession creates a new terminal session record
func (h *SessionHandler) CreateSession(c *gin.Context) {
	var session models.Session
	if err := c.ShouldBindJSON(&session); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Set user ID
	session.UserID = userID.(string)

	// Set session ID if not provided
	if session.SessionID == "" {
		session.SessionID = uuid.New().String()
	}

	// Set timestamps
	now := time.Now()
	session.CreatedAt = now
	session.LastActivity = now

	// Initialize stats
	session.Stats.CommandCount = 0
	session.Stats.BytesReceived = 0
	session.Stats.BytesSent = 0
	session.Stats.TotalDurationS = 0

	// Save session
	if err := h.repo.SaveSession(&session); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, session)
}

// GetSessions returns all sessions for the current user
func (h *SessionHandler) GetSessions(c *gin.Context) {
	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get query parameters
	status := c.Query("status")
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	// Get sessions
	sessions, err := h.repo.GetUserSessions(userID.(string), status, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"sessions": sessions,
		"count":    len(sessions),
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

	// Get session
	session, err := h.repo.GetSession(sessionID)
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

// UpdateSessionStatus updates a session's status
func (h *SessionHandler) UpdateSessionStatus(c *gin.Context) {
	sessionID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get session
	session, err := h.repo.GetSession(sessionID)
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

	// Parse status from body
	var statusUpdate struct {
		Status string `json:"status" binding:"required"`
	}
	if err := c.ShouldBindJSON(&statusUpdate); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Update status
	status := models.SessionStatus(statusUpdate.Status)
	if err := h.repo.UpdateSessionStatus(sessionID, status); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"status":     status,
		"message":    "Session status updated successfully",
	})
}

// SearchSessions searches for sessions based on criteria
func (h *SessionHandler) SearchSessions(c *gin.Context) {
	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Parse search request from query parameters
	var req models.SessionSearchRequest
	if err := c.ShouldBindQuery(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Set user ID if not admin
	isAdmin, _ := c.Get("isAdmin")
	if isAdmin == nil || !isAdmin.(bool) {
		req.UserID = userID.(string)
	}

	// Set default values if not provided
	if req.Limit <= 0 {
		req.Limit = 20
	}
	if req.SortField == "" {
		req.SortField = "created_at"
		req.SortOrder = "desc"
	}

	// Search sessions
	sessions, total, err := h.repo.SearchSessions(&req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"sessions": sessions,
		"total":    total,
		"limit":    req.Limit,
		"offset":   req.Offset,
	})
}

// CommandHandler handles command-related operations
type CommandHandler struct {
	repo SessionRepository
}

// NewCommandHandler creates a new CommandHandler
func NewCommandHandler(repo SessionRepository) *CommandHandler {
	return &CommandHandler{
		repo: repo,
	}
}

// SaveCommand saves a command
func (h *CommandHandler) SaveCommand(c *gin.Context) {
	var command models.Command
	if err := c.ShouldBindJSON(&command); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Set user ID
	command.UserID = userID.(string)

	// Generate command ID if not provided
	if command.CommandID == "" {
		command.CommandID = uuid.New().String()
	}

	// Set execution time if not provided
	if command.ExecutedAt.IsZero() {
		command.ExecutedAt = time.Now()
	}

	// Save command
	if err := h.repo.SaveCommand(&command); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, command)
}

// GetCommand returns a command by ID
func (h *CommandHandler) GetCommand(c *gin.Context) {
	commandID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get command
	command, err := h.repo.GetCommand(commandID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Command not found"})
		return
	}

	// Verify the command belongs to the user
	if command.UserID != userID.(string) {
		// Check if user is admin
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
			return
		}
	}

	c.JSON(http.StatusOK, command)
}

// GetSessionCommands returns all commands for a session
func (h *CommandHandler) GetSessionCommands(c *gin.Context) {
	sessionID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get session to verify ownership
	session, err := h.repo.GetSession(sessionID)
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

	// Get query parameters
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	// Get commands
	commands, err := h.repo.GetSessionCommands(sessionID, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"commands": commands,
		"count":    len(commands),
		"limit":    limit,
		"offset":   offset,
	})
}

// SearchCommands searches for commands based on criteria
func (h *CommandHandler) SearchCommands(c *gin.Context) {
	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Parse search request from query parameters
	var req models.HistorySearchRequest
	if err := c.ShouldBindQuery(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Set user ID if not admin
	isAdmin, _ := c.Get("isAdmin")
	if isAdmin == nil || !isAdmin.(bool) {
		req.UserID = userID.(string)
	}

	// Set default values if not provided
	if req.Limit <= 0 {
		req.Limit = 20
	}
	if req.SortField == "" {
		req.SortField = "timestamp"
		req.SortOrder = "desc"
	}

	// Search commands
	commands, total, err := h.repo.SearchCommands(&req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"commands": commands,
		"total":    total,
		"limit":    req.Limit,
		"offset":   req.Offset,
	})
}

// BookmarkHandler handles bookmark-related operations
type BookmarkHandler struct {
	repo SessionRepository
}

// NewBookmarkHandler creates a new BookmarkHandler
func NewBookmarkHandler(repo SessionRepository) *BookmarkHandler {
	return &BookmarkHandler{
		repo: repo,
	}
}

// CreateBookmark creates a new bookmark
func (h *BookmarkHandler) CreateBookmark(c *gin.Context) {
	var bookmark models.Bookmark
	if err := c.ShouldBindJSON(&bookmark); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Set user ID
	bookmark.UserID = userID.(string)

	// Set bookmark ID if not provided
	if bookmark.BookmarkID == "" {
		bookmark.BookmarkID = uuid.New().String()
	}

	// Set creation time
	bookmark.CreatedAt = time.Now()

	// Verify command exists and belongs to user
	command, err := h.repo.GetCommand(bookmark.CommandID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Command not found"})
		return
	}

	// Verify ownership or admin rights
	if command.UserID != userID.(string) {
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Cannot bookmark someone else's command"})
			return
		}
	}

	// Set session ID and command text from the command
	bookmark.SessionID = command.SessionID
	bookmark.CommandText = command.CommandText

	// Save bookmark
	if err := h.repo.SaveBookmark(&bookmark); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, bookmark)
}

// GetBookmark returns a bookmark by ID
func (h *BookmarkHandler) GetBookmark(c *gin.Context) {
	bookmarkID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get bookmark
	bookmark, err := h.repo.GetBookmark(bookmarkID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Bookmark not found"})
		return
	}

	// Verify the bookmark belongs to the user
	if bookmark.UserID != userID.(string) {
		// Check if user is admin
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
			return
		}
	}

	c.JSON(http.StatusOK, bookmark)
}

// GetUserBookmarks returns all bookmarks for the user
func (h *BookmarkHandler) GetUserBookmarks(c *gin.Context) {
	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get query parameters
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	// Get bookmarks
	bookmarks, err := h.repo.GetUserBookmarks(userID.(string), limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"bookmarks": bookmarks,
		"count":     len(bookmarks),
		"limit":     limit,
		"offset":    offset,
	})
}

// DeleteBookmark deletes a bookmark
func (h *BookmarkHandler) DeleteBookmark(c *gin.Context) {
	bookmarkID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Get bookmark to verify ownership
	bookmark, err := h.repo.GetBookmark(bookmarkID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Bookmark not found"})
		return
	}

	// Verify the bookmark belongs to the user
	if bookmark.UserID != userID.(string) {
		// Check if user is admin
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Access denied"})
			return
		}
	}

	// Delete bookmark
	if err := h.repo.DeleteBookmark(bookmarkID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"bookmark_id": bookmarkID,
		"message":     "Bookmark deleted successfully",
	})
}

// ContextHandler handles session context operations
type ContextHandler struct {
	repo SessionRepository
}

// NewContextHandler creates a new ContextHandler
func NewContextHandler(repo SessionRepository) *ContextHandler {
	return &ContextHandler{
		repo: repo,
	}
}

// SaveContext saves or updates a session context
func (h *ContextHandler) SaveContext(c *gin.Context) {
	var context models.SessionContext
	if err := c.ShouldBindJSON(&context); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Set user ID
	context.UserID = userID.(string)

	// Verify session exists and belongs to user
	session, err := h.repo.GetSession(context.SessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	// Verify ownership or admin rights
	if session.UserID != userID.(string) {
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Cannot update context for someone else's session"})
			return
		}
	}

	// Set last updated time
	context.LastUpdated = time.Now()

	// Save context
	if err := h.repo.SaveContext(&context); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, context)
}

// GetContext returns the context for a session
func (h *ContextHandler) GetContext(c *gin.Context) {
	sessionID := c.Param("id")

	// Get user ID from context (added by auth middleware)
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Unauthorized"})
		return
	}

	// Verify session exists and belongs to user
	session, err := h.repo.GetSession(sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Session not found"})
		return
	}

	// Verify ownership or admin rights
	if session.UserID != userID.(string) {
		isAdmin, _ := c.Get("isAdmin")
		if isAdmin == nil || !isAdmin.(bool) {
			c.JSON(http.StatusForbidden, gin.H{"error": "Cannot access context for someone else's session"})
			return
		}
	}

	// Get context
	context, err := h.repo.GetContext(sessionID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": "Context not found for session"})
		return
	}

	c.JSON(http.StatusOK, context)
}

// MaintenanceHandler handles system maintenance operations
type MaintenanceHandler struct {
	repo                SessionRepository
	sessionRetentionDays int
	commandRetentionDays int
}

// NewMaintenanceHandler creates a new MaintenanceHandler
func NewMaintenanceHandler(repo SessionRepository, sessionDays, commandDays int) *MaintenanceHandler {
	return &MaintenanceHandler{
		repo:                repo,
		sessionRetentionDays: sessionDays,
		commandRetentionDays: commandDays,
	}
}

// PurgeOldData purges old sessions and commands
func (h *MaintenanceHandler) PurgeOldData(c *gin.Context) {
	// Only allow admins
	isAdmin, _ := c.Get("isAdmin")
	if isAdmin == nil || !isAdmin.(bool) {
		c.JSON(http.StatusForbidden, gin.H{"error": "Admin privileges required"})
		return
	}

	// Purge old sessions
	sessionCount, err := h.repo.PurgeOldSessions(h.sessionRetentionDays)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Purge old commands
	commandCount, err := h.repo.PurgeOldCommands(h.commandRetentionDays)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"message":        "Purge completed successfully",
		"purged_sessions": sessionCount,
		"purged_commands": commandCount,
	})
}