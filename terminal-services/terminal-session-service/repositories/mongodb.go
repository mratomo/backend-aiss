package repositories

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"sync"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readpref"

	"terminal-session-service/models"
)

// MongoRepository implements the SessionRepository interface using MongoDB
type MongoRepository struct {
	client          *mongo.Client
	db              *mongo.Database
	sessions        *mongo.Collection
	commands        *mongo.Collection
	bookmarks       *mongo.Collection
	contexts        *mongo.Collection
	sessionContexts *mongo.Collection
	modeChanges     *mongo.Collection
	timeout         time.Duration
	mu              sync.RWMutex // Mutex for thread-safe operations
}

// NewMongoRepository creates a new MongoRepository
func NewMongoRepository(uri, dbName string, timeout time.Duration) (*MongoRepository, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// Connect to MongoDB
	client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if err != nil {
		return nil, err
	}

	// Ping the database
	if err := client.Ping(ctx, readpref.Primary()); err != nil {
		return nil, err
	}

	// Get database and collections
	db := client.Database(dbName)
	sessions := db.Collection("sessions")
	commands := db.Collection("commands")
	bookmarks := db.Collection("bookmarks")
	contexts := db.Collection("contexts")
	sessionContexts := db.Collection("session_contexts")
	modeChanges := db.Collection("mode_changes")

	repo := &MongoRepository{
		client:          client,
		db:              db,
		sessions:        sessions,
		commands:        commands,
		bookmarks:       bookmarks,
		contexts:        contexts,
		sessionContexts: sessionContexts,
		modeChanges:     modeChanges,
		timeout:         timeout,
	}

	// Create indexes
	if err := repo.createIndexes(ctx); err != nil {
		return nil, err
	}

	return repo, nil
}

// CreateIndexes creates indexes for all collections
func (r *MongoRepository) createIndexes(ctx context.Context) error {
	// Session indexes
	sessionIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "session_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "user_id", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "created_at", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "status", Value: 1}},
		},
		{
			Keys: bson.D{
				{Key: "user_id", Value: 1},
				{Key: "status", Value: 1},
			},
		},
	}

	// Command indexes
	commandIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "command_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "session_id", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "user_id", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "executed_at", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "command", Value: "text"}},
		},
	}

	// Bookmark indexes
	bookmarkIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "bookmark_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "user_id", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "command_id", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "session_id", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "created_at", Value: 1}},
		},
	}

	// Context indexes
	contextIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "session_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys: bson.D{{Key: "user_id", Value: 1}},
		},
		{
			Keys: bson.D{{Key: "last_updated", Value: 1}},
		},
	}

	// Create session indexes
	_, err := r.sessions.Indexes().CreateMany(ctx, sessionIndexes)
	if err != nil {
		return fmt.Errorf("failed to create session indexes: %w", err)
	}

	// Create command indexes
	_, err = r.commands.Indexes().CreateMany(ctx, commandIndexes)
	if err != nil {
		return fmt.Errorf("failed to create command indexes: %w", err)
	}

	// Create bookmark indexes
	_, err = r.bookmarks.Indexes().CreateMany(ctx, bookmarkIndexes)
	if err != nil {
		return fmt.Errorf("failed to create bookmark indexes: %w", err)
	}

	// Create context indexes
	_, err = r.contexts.Indexes().CreateMany(ctx, contextIndexes)
	if err != nil {
		return fmt.Errorf("failed to create context indexes: %w", err)
	}

	return nil
}

// Close closes the MongoDB connection
func (r *MongoRepository) Close() error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()
	return r.client.Disconnect(ctx)
}

// SaveSession saves a session to the database
func (r *MongoRepository) SaveSession(session *models.Session) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Check if session already exists
	var existingSession models.Session
	err := r.sessions.FindOne(ctx, bson.M{"session_id": session.SessionID}).Decode(&existingSession)
	if err == nil {
		// Session exists, update it
		session.ID = existingSession.ID
		filter := bson.M{"_id": existingSession.ID}
		update := bson.M{"$set": session}
		_, err = r.sessions.UpdateOne(ctx, filter, update)
		return err
	} else if !errors.Is(err, mongo.ErrNoDocuments) {
		// Error other than document not found
		return err
	}

	// Session doesn't exist, create a new one
	_, err = r.sessions.InsertOne(ctx, session)
	return err
}

// GetSession gets a session by ID
func (r *MongoRepository) GetSession(sessionID string) (*models.Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	var session models.Session
	err := r.sessions.FindOne(ctx, bson.M{"session_id": sessionID}).Decode(&session)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("session not found: %s", sessionID)
		}
		return nil, err
	}

	return &session, nil
}

// GetUserSessions gets all sessions for a user
func (r *MongoRepository) GetUserSessions(userID, status string, limit, offset int) ([]*models.Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{"user_id": userID}
	if status != "" {
		filter["status"] = status
	}

	// Create options
	findOptions := options.Find()
	findOptions.SetSort(bson.M{"created_at": -1})
	findOptions.SetLimit(int64(limit))
	findOptions.SetSkip(int64(offset))

	// Find sessions
	cursor, err := r.sessions.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	// Decode sessions
	var sessions []*models.Session
	if err = cursor.All(ctx, &sessions); err != nil {
		return nil, err
	}

	return sessions, nil
}

// GetSessionsByUserAndStatus gets all sessions for a user with a specific status
func (r *MongoRepository) GetSessionsByUserAndStatus(userID, status string) ([]*models.Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{"user_id": userID, "status": status}

	// Create options
	findOptions := options.Find()
	findOptions.SetSort(bson.M{"last_active": -1})

	// Find sessions
	cursor, err := r.sessions.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	// Decode sessions
	var sessions []*models.Session
	if err = cursor.All(ctx, &sessions); err != nil {
		return nil, err
	}

	return sessions, nil
}

// SearchSessions searches for sessions based on criteria
func (r *MongoRepository) SearchSessions(req *models.SessionSearchRequest) ([]*models.Session, int, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{}
	if req.UserID != "" {
		filter["user_id"] = req.UserID
	}
	if req.Status != "" {
		filter["status"] = req.Status
	}
	// Eliminado búsqueda por SearchTerm que no existe en el modelo
	if !req.FromDate.IsZero() && !req.ToDate.IsZero() {
		filter["created_at"] = bson.M{
			"$gte": req.FromDate,
			"$lte": req.ToDate,
		}
	} else if !req.FromDate.IsZero() {
		filter["created_at"] = bson.M{"$gte": req.FromDate}
	} else if !req.ToDate.IsZero() {
		filter["created_at"] = bson.M{"$lte": req.ToDate}
	}

	// Count total
	total, err := r.sessions.CountDocuments(ctx, filter)
	if err != nil {
		return nil, 0, err
	}

	// Create options
	findOptions := options.Find()
	if req.SortField != "" {
		sortOrder := 1
		if req.SortOrder == "desc" {
			sortOrder = -1
		}
		findOptions.SetSort(bson.M{req.SortField: sortOrder})
	} else {
		findOptions.SetSort(bson.M{"created_at": -1})
	}
	findOptions.SetLimit(int64(req.Limit))
	findOptions.SetSkip(int64(req.Offset))

	// Find sessions
	cursor, err := r.sessions.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, 0, err
	}
	defer cursor.Close(ctx)

	// Decode sessions
	var sessions []*models.Session
	if err = cursor.All(ctx, &sessions); err != nil {
		return nil, 0, err
	}

	return sessions, int(total), nil
}

// UpdateSessionStatus updates a session's status
func (r *MongoRepository) UpdateSessionStatus(sessionID string, status models.SessionStatus) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	filter := bson.M{"session_id": sessionID}
	update := bson.M{
		"$set": bson.M{
			"status":        status,
			"last_activity": time.Now(),
		},
	}

	_, err := r.sessions.UpdateOne(ctx, filter, update)
	return err
}

// SaveCommand saves a command to the database
func (r *MongoRepository) SaveCommand(command *models.Command) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Check if command already exists
	var existingCommand models.Command
	err := r.commands.FindOne(ctx, bson.M{"command_id": command.CommandID}).Decode(&existingCommand)
	if err == nil {
		// Command exists, update it
		command.ID = existingCommand.ID
		filter := bson.M{"_id": existingCommand.ID}
		update := bson.M{"$set": command}
		_, err = r.commands.UpdateOne(ctx, filter, update)
		return err
	} else if !errors.Is(err, mongo.ErrNoDocuments) {
		// Error other than document not found
		return err
	}

	// Command doesn't exist, create a new one
	_, err = r.commands.InsertOne(ctx, command)
	if err != nil {
		return err
	}

	// Update session stats
	filter := bson.M{"session_id": command.SessionID}
	update := bson.M{
		"$inc": bson.M{
			"stats.command_count":    1,
			"stats.bytes_sent":       len(command.CommandText),
			"stats.bytes_received":   len(command.Output),
			"stats.total_duration_s": command.DurationMs / 1000,
		},
		"$set": bson.M{
			"last_activity": time.Now(),
		},
	}
	_, err = r.sessions.UpdateOne(ctx, filter, update)
	return err
}

// GetCommand gets a command by ID
func (r *MongoRepository) GetCommand(commandID string) (*models.Command, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	var command models.Command
	err := r.commands.FindOne(ctx, bson.M{"command_id": commandID}).Decode(&command)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("command not found: %s", commandID)
		}
		return nil, err
	}

	return &command, nil
}

// GetSessionCommands gets all commands for a session
func (r *MongoRepository) GetSessionCommands(sessionID string, limit, offset int) ([]*models.Command, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{"session_id": sessionID}

	// Create options
	findOptions := options.Find()
	findOptions.SetSort(bson.M{"executed_at": -1})
	findOptions.SetLimit(int64(limit))
	findOptions.SetSkip(int64(offset))

	// Find commands
	cursor, err := r.commands.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	// Decode commands
	var commands []*models.Command
	if err = cursor.All(ctx, &commands); err != nil {
		return nil, err
	}

	return commands, nil
}

// GetRecentCommands gets the most recent commands for a session
func (r *MongoRepository) GetRecentCommands(sessionID string, limit int) ([]*models.Command, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{"session_id": sessionID}

	// Create options
	findOptions := options.Find()
	findOptions.SetSort(bson.M{"executed_at": -1})
	findOptions.SetLimit(int64(limit))

	// Find commands
	cursor, err := r.commands.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	// Decode commands
	var commands []*models.Command
	if err = cursor.All(ctx, &commands); err != nil {
		return nil, err
	}

	return commands, nil
}

// GetUserCommands gets all commands for a user
func (r *MongoRepository) GetUserCommands(userID string, limit, offset int) ([]*models.Command, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{"user_id": userID}

	// Create options
	findOptions := options.Find()
	findOptions.SetSort(bson.M{"executed_at": -1})
	findOptions.SetLimit(int64(limit))
	findOptions.SetSkip(int64(offset))

	// Find commands
	cursor, err := r.commands.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	// Decode commands
	var commands []*models.Command
	if err = cursor.All(ctx, &commands); err != nil {
		return nil, err
	}

	return commands, nil
}

// SearchCommands searches for commands based on criteria
func (r *MongoRepository) SearchCommands(req *models.HistorySearchRequest) ([]*models.Command, int, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{}
	if req.UserID != "" {
		filter["user_id"] = req.UserID
	}
	if req.SessionID != "" {
		filter["session_id"] = req.SessionID
	}
	if req.CommandStr != "" {
		filter["command"] = bson.M{"$regex": primitive.Regex{Pattern: req.CommandStr, Options: "i"}}
	}
	if !req.FromDate.IsZero() && !req.ToDate.IsZero() {
		filter["timestamp"] = bson.M{
			"$gte": req.FromDate,
			"$lte": req.ToDate,
		}
	} else if !req.FromDate.IsZero() {
		filter["timestamp"] = bson.M{"$gte": req.FromDate}
	} else if !req.ToDate.IsZero() {
		filter["timestamp"] = bson.M{"$lte": req.ToDate}
	}
	if req.ExitCode != nil {
		filter["exit_code"] = *req.ExitCode
	}
	if req.HasError != nil {
		filter["error_detected"] = *req.HasError
	}
	if req.IsFavorite != nil {
		// If IsFavorite is true, find commands that have bookmarks
		if *req.IsFavorite {
			// Use aggregation to find commands with bookmarks
			pipeline := []bson.M{
				{"$match": filter},
				{"$lookup": bson.M{
					"from":         "bookmarks",
					"localField":   "command_id",
					"foreignField": "command_id",
					"as":           "bookmarks",
				}},
				{"$match": bson.M{"bookmarks": bson.M{"$ne": []interface{}{}}}},
			}

			// Add sort, limit, skip
			if req.SortField != "" {
				sortOrder := 1
				if req.SortOrder == "desc" {
					sortOrder = -1
				}
				pipeline = append(pipeline, bson.M{"$sort": bson.M{req.SortField: sortOrder}})
			} else {
				pipeline = append(pipeline, bson.M{"$sort": bson.M{"timestamp": -1}})
			}

			// Count total
			countPipeline := append(pipeline, bson.M{"$count": "total"})
			countCursor, err := r.commands.Aggregate(ctx, countPipeline)
			if err != nil {
				return nil, 0, err
			}
			defer countCursor.Close(ctx)

			var countResult []bson.M
			if err = countCursor.All(ctx, &countResult); err != nil {
				return nil, 0, err
			}

			totalCount := 0
			if len(countResult) > 0 && countResult[0]["total"] != nil {
				// Handle possible types returned by MongoDB for count (int32, int64, float64)
				count := countResult[0]["total"]
				switch v := count.(type) {
				case int32:
					totalCount = int(v)
				case int64:
					totalCount = int(v)
				case float64:
					totalCount = int(v)
				default:
					// If it's another type, convert to string and then parse as int
					totalCount, _ = strconv.Atoi(fmt.Sprintf("%v", count))
				}
			}

			// Apply pagination
			pipeline = append(pipeline, bson.M{"$skip": req.Offset})
			pipeline = append(pipeline, bson.M{"$limit": req.Limit})

			// Execute aggregation
			cursor, err := r.commands.Aggregate(ctx, pipeline)
			if err != nil {
				return nil, 0, err
			}
			defer cursor.Close(ctx)

			// Decode commands
			var commands []*models.Command
			if err = cursor.All(ctx, &commands); err != nil {
				return nil, 0, err
			}

			return commands, totalCount, nil
		}
	}

	// Normal query (not filtering by bookmarks)
	// Create options
	findOptions := options.Find()
	if req.SortField != "" {
		sortOrder := 1
		if req.SortOrder == "desc" {
			sortOrder = -1
		}
		findOptions.SetSort(bson.M{req.SortField: sortOrder})
	} else {
		findOptions.SetSort(bson.M{"executed_at": -1})
	}

	// Count total
	total, err := r.commands.CountDocuments(ctx, filter)
	if err != nil {
		return nil, 0, err
	}

	// Apply pagination
	findOptions.SetLimit(int64(req.Limit))
	findOptions.SetSkip(int64(req.Offset))

	// Find commands
	cursor, err := r.commands.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, 0, err
	}
	defer cursor.Close(ctx)

	// Decode commands
	var commands []*models.Command
	if err = cursor.All(ctx, &commands); err != nil {
		return nil, 0, err
	}

	return commands, int(total), nil
}

// SaveBookmark saves a bookmark to the database
func (r *MongoRepository) SaveBookmark(bookmark *models.Bookmark) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Check if bookmark already exists
	var existingBookmark models.Bookmark
	err := r.bookmarks.FindOne(ctx, bson.M{"bookmark_id": bookmark.BookmarkID}).Decode(&existingBookmark)
	if err == nil {
		// Bookmark exists, update it
		bookmark.ID = existingBookmark.ID
		filter := bson.M{"_id": existingBookmark.ID}
		update := bson.M{"$set": bookmark}
		_, err = r.bookmarks.UpdateOne(ctx, filter, update)
		return err
	} else if !errors.Is(err, mongo.ErrNoDocuments) {
		// Error other than document not found
		return err
	}

	// Bookmark doesn't exist, create a new one
	_, err = r.bookmarks.InsertOne(ctx, bookmark)
	return err
}

// GetBookmark gets a bookmark by ID
func (r *MongoRepository) GetBookmark(bookmarkID string) (*models.Bookmark, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	var bookmark models.Bookmark
	err := r.bookmarks.FindOne(ctx, bson.M{"bookmark_id": bookmarkID}).Decode(&bookmark)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("bookmark not found: %s", bookmarkID)
		}
		return nil, err
	}

	return &bookmark, nil
}

// GetUserBookmarks gets all bookmarks for a user
func (r *MongoRepository) GetUserBookmarks(userID string, limit, offset int) ([]*models.Bookmark, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{"user_id": userID}

	// Create options
	findOptions := options.Find()
	findOptions.SetSort(bson.M{"created_at": -1})
	findOptions.SetLimit(int64(limit))
	findOptions.SetSkip(int64(offset))

	// Find bookmarks
	cursor, err := r.bookmarks.Find(ctx, filter, findOptions)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	// Decode bookmarks
	var bookmarks []*models.Bookmark
	if err = cursor.All(ctx, &bookmarks); err != nil {
		return nil, err
	}

	return bookmarks, nil
}

// DeleteBookmark deletes a bookmark
func (r *MongoRepository) DeleteBookmark(bookmarkID string) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	_, err := r.bookmarks.DeleteOne(ctx, bson.M{"bookmark_id": bookmarkID})
	return err
}

// SaveContext saves a session context to the database
func (r *MongoRepository) SaveContext(sessionContext *models.SessionContext) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Use findOneAndUpdate operation to avoid race conditions
	// Set upsert to true to create if not exists (atomic operation)
	opts := options.FindOneAndUpdate().SetUpsert(true).SetReturnDocument(options.After)
	filter := bson.M{"session_id": sessionContext.SessionID}

	// Use $setOnInsert to keep the original ID if updating
	// and create a new one if inserting
	update := bson.M{
		"$set": bson.M{
			"user_id":               sessionContext.UserID,
			"working_directory":     sessionContext.CurrentDirectory,
			"current_user":          sessionContext.CurrentUser,
			"environment_variables": sessionContext.EnvironmentVars,
			"last_exit_code":        sessionContext.LastExitCode,
			"detected_applications": sessionContext.DetectedApplications,
			"detected_errors":       sessionContext.DetectedErrors,
			"last_updated":          time.Now().UTC(),
		},
		"$setOnInsert": bson.M{
			"created_at": time.Now().UTC(),
		},
	}

	var updatedContext models.SessionContext
	err := r.contexts.FindOneAndUpdate(ctx, filter, update, opts).Decode(&updatedContext)

	// If no documents matched and no documents were upserted
	if err != nil && !errors.Is(err, mongo.ErrNoDocuments) {
		return err
	}

	// Success - update the ID in the input object to match what's in the database
	sessionContext.ID = updatedContext.ID
	return nil
}

// GetContext gets a session context by session ID
func (r *MongoRepository) GetContext(sessionID string) (*models.SessionContext, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	var sessionContext models.SessionContext
	err := r.contexts.FindOne(ctx, bson.M{"session_id": sessionID}).Decode(&sessionContext)
	if err != nil {
		if errors.Is(err, mongo.ErrNoDocuments) {
			return nil, fmt.Errorf("context not found for session: %s", sessionID)
		}
		return nil, err
	}

	return &sessionContext, nil
}

// PurgeOldSessions purges old sessions and their related data
func (r *MongoRepository) PurgeOldSessions(days int) (int, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Calculate cutoff date
	cutoffDate := time.Now().AddDate(0, 0, -days)

	// Find old sessions
	filter := bson.M{"created_at": bson.M{"$lt": cutoffDate}}
	cursor, err := r.sessions.Find(ctx, filter)
	if err != nil {
		return 0, err
	}
	defer cursor.Close(ctx)

	// Get session IDs
	var sessions []struct {
		SessionID string `bson:"session_id"`
	}
	if err = cursor.All(ctx, &sessions); err != nil {
		return 0, err
	}

	if len(sessions) == 0 {
		return 0, nil
	}

	sessionIDs := make([]string, len(sessions))
	for i, session := range sessions {
		sessionIDs[i] = session.SessionID
	}

	// Delete commands for these sessions
	_, err = r.commands.DeleteMany(ctx, bson.M{"session_id": bson.M{"$in": sessionIDs}})
	if err != nil {
		return 0, err
	}

	// Delete bookmarks for these sessions
	_, err = r.bookmarks.DeleteMany(ctx, bson.M{"session_id": bson.M{"$in": sessionIDs}})
	if err != nil {
		return 0, err
	}

	// Delete contexts for these sessions
	_, err = r.contexts.DeleteMany(ctx, bson.M{"session_id": bson.M{"$in": sessionIDs}})
	if err != nil {
		return 0, err
	}

	// Delete the sessions
	result, err := r.sessions.DeleteMany(ctx, bson.M{"session_id": bson.M{"$in": sessionIDs}})
	if err != nil {
		return 0, err
	}

	return int(result.DeletedCount), nil
}

// PurgeOldCommands purges old commands
func (r *MongoRepository) PurgeOldCommands(days int) (int, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Calculate cutoff date
	cutoffDate := time.Now().AddDate(0, 0, -days)

	// Find old commands
	filter := bson.M{"executed_at": bson.M{"$lt": cutoffDate}}
	cursor, err := r.commands.Find(ctx, filter)
	if err != nil {
		return 0, err
	}
	defer cursor.Close(ctx)

	// Get command IDs
	var commands []struct {
		CommandID string `bson:"command_id"`
	}
	if err = cursor.All(ctx, &commands); err != nil {
		return 0, err
	}

	if len(commands) == 0 {
		return 0, nil
	}

	commandIDs := make([]string, len(commands))
	for i, command := range commands {
		commandIDs[i] = command.CommandID
	}

	// Delete bookmarks for these commands
	_, err = r.bookmarks.DeleteMany(ctx, bson.M{"command_id": bson.M{"$in": commandIDs}})
	if err != nil {
		return 0, err
	}

	// Delete the commands
	result, err := r.commands.DeleteMany(ctx, bson.M{"command_id": bson.M{"$in": commandIDs}})
	if err != nil {
		return 0, err
	}

	return int(result.DeletedCount), nil
}
