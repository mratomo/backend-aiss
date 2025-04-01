package repositories

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo/options"

	"terminal-session-service/models"
)

// UpdateSessionMode updates the mode of a session
func (r *MongoDBRepository) UpdateSessionMode(sessionID string, mode models.SessionMode, areaID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Prepare update
	update := bson.M{
		"$set": bson.M{
			"mode": mode,
			"last_active": time.Now(),
		},
	}

	// Add area ID if provided
	if areaID != "" {
		update["$set"].(bson.M)["active_area_id"] = areaID
	} else {
		// Clear area ID if mode is normal
		if mode == models.SessionModeNormal {
			update["$unset"] = bson.M{"active_area_id": ""}
		}
	}

	// Execute update
	_, err := r.sessions.UpdateOne(
		ctx,
		bson.M{"session_id": sessionID},
		update,
	)

	if err != nil {
		return fmt.Errorf("failed to update session mode: %w", err)
	}

	return nil
}

// SaveSessionModeChange saves a record of a session mode change
func (r *MongoDBRepository) SaveSessionModeChange(modeChange models.SessionModeChange) error {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Insert mode change record
	_, err := r.modeChanges.InsertOne(ctx, modeChange)
	if err != nil {
		return fmt.Errorf("failed to save session mode change: %w", err)
	}

	return nil
}

// GetSessionContext gets the context for a terminal session
func (r *MongoDBRepository) GetSessionContext(sessionID string) (map[string]interface{}, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
	defer cancel()

	// Get session to extract basic info
	var session models.Session
	err := r.sessions.FindOne(
		ctx,
		bson.M{"session_id": sessionID},
	).Decode(&session)

	if err != nil {
		return nil, fmt.Errorf("failed to get session: %w", err)
	}

	// Get session context from context collection
	var sessionContext models.SessionContext
	err = r.sessionContexts.FindOne(
		ctx,
		bson.M{"session_id": sessionID},
	).Decode(&sessionContext)

	// If not found, return basic context
	if err != nil {
		// Basic context with session info
		return map[string]interface{}{
			"session_id":    sessionID,
			"hostname":      session.TargetInfo.Hostname,
			"os_type":       session.TargetInfo.OSType,
			"os_version":    session.TargetInfo.OSVersion,
			"created_at":    session.CreatedAt,
			"last_activity": session.LastActivity,
		}, nil
	}

	// Convert to map for easier extension
	contextMap := map[string]interface{}{
		"session_id":             sessionID,
		"current_directory":      sessionContext.CurrentDirectory,
		"current_user":           sessionContext.CurrentUser,
		"environment_variables":  sessionContext.EnvironmentVars,
		"last_exit_code":         sessionContext.LastExitCode,
		"detected_applications":  sessionContext.DetectedApplications,
		"hostname":               session.TargetInfo.Hostname,
		"os_type":                session.TargetInfo.OSType,
		"os_version":             session.TargetInfo.OSVersion,
		"detected_errors":        sessionContext.DetectedErrors,
		"last_updated":           sessionContext.LastUpdated,
	}

	return contextMap, nil
}

// GetSessionsWithActiveArea gets all sessions for a user that have an active area
func (r *MongoDBRepository) GetSessionsWithActiveArea(userID string) ([]models.Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Define query to find sessions with active area
	filter := bson.M{
		"user_id": userID,
		"active_area_id": bson.M{"$exists": true, "$ne": ""},
	}

	// Define options
	findOptions := options.Find()
	findOptions.SetSort(bson.D{{Key: "last_active", Value: -1}})
	findOptions.SetLimit(10) // Limit to 10 most recent

	// Execute query
	cursor, err := r.sessions.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, fmt.Errorf("failed to get sessions with active area: %w", err)
	}
	defer cursor.Close(ctx)

	// Process results
	var sessions []models.Session
	if err = cursor.All(ctx, &sessions); err != nil {
		return nil, fmt.Errorf("failed to decode sessions: %w", err)
	}

	return sessions, nil
}