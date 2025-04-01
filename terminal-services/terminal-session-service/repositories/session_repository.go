package repositories

import (
	"context"
	"terminal-session-service/models"
)

// SessionRepository defines the interface for session repositories
type SessionRepository interface {
	// Session operations
	CreateSession(session *models.Session) error
	GetSession(sessionID string) (*models.Session, error)
	GetUserSessions(userID string, limit, offset int) ([]*models.Session, error)
	GetSessionsByUserAndStatus(userID, status string) ([]*models.Session, error)
	SearchSessions(query models.SessionSearchRequest) ([]*models.Session, int, error)
	UpdateSessionStatus(sessionID string, status models.SessionStatus) error
	UpdateSessionStats(sessionID string, stats models.Stats) error
	DeleteSession(sessionID string) error
	
	// Command operations
	SaveCommand(command *models.Command) error
	GetCommand(commandID string) (*models.Command, error)
	GetSessionCommands(sessionID string, limit, offset int) ([]*models.Command, error)
	GetRecentCommands(sessionID string, limit int) ([]*models.Command, error)
	GetUserCommands(userID string, limit, offset int) ([]*models.Command, error)
	SearchCommands(query models.HistorySearchRequest) ([]*models.Command, int, error)
	UpdateCommandTags(commandID string, tags []string) error
	UpdateCommandNotes(commandID string, notes string) error
	
	// Bookmark operations
	CreateBookmark(bookmark *models.Bookmark) error
	GetBookmark(bookmarkID string) (*models.Bookmark, error)
	GetUserBookmarks(userID string, limit, offset int) ([]*models.Bookmark, error)
	DeleteBookmark(bookmarkID string) error
	
	// Context operations
	SaveContext(context *models.SessionContext) error
	GetContext(sessionID string) (*models.SessionContext, error)
	
	// Query mode operations
	UpdateSessionMode(sessionID string, mode models.SessionMode, areaID string) error
	SaveSessionModeChange(modeChange models.SessionModeChange) error
	GetSessionsWithActiveArea(userID string) ([]models.Session, error)
	
	// Maintenance operations
	PurgeOldSessions(olderThan int) (int, error)
	PurgeOldCommands(olderThan int) (int, error)
	
	// Health check
	Ping(ctx context.Context) error
	
	// Index operations
	CreateOptimizedIndexes() error
	CreateSearchIndexes() error
}