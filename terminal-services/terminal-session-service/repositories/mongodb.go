package repositories

import (
	"context"
	"errors"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
	"go.mongodb.org/mongo-driver/mongo/readpref"

	"terminal-session-service/models"
)

// MongoRepository is a MongoDB implementation of the SessionRepository interface
type MongoRepository struct {
	client     *mongo.Client
	database   string
	timeout    time.Duration
	sessions   *mongo.Collection
	commands   *mongo.Collection
	bookmarks  *mongo.Collection
	contexts   *mongo.Collection
}

// NewMongoRepository creates a new MongoDB repository
func NewMongoRepository(uri, database string, timeout time.Duration) (*MongoRepository, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()

	// Create a MongoDB client
	client, err := mongo.Connect(ctx, options.Client().ApplyURI(uri))
	if err != nil {
		return nil, fmt.Errorf("failed to connect to MongoDB: %w", err)
	}

	// Verify the connection
	err = client.Ping(ctx, readpref.Primary())
	if err != nil {
		return nil, fmt.Errorf("failed to ping MongoDB: %w", err)
	}

	// Create the repository
	repo := &MongoRepository{
		client:    client,
		database:  database,
		timeout:   timeout,
		sessions:  client.Database(database).Collection("sessions"),
		commands:  client.Database(database).Collection("commands"),
		bookmarks: client.Database(database).Collection("bookmarks"),
		contexts:  client.Database(database).Collection("contexts"),
	}

	// Create indexes
	err = repo.createIndexes(ctx)
	if err != nil {
		return nil, fmt.Errorf("failed to create indexes: %w", err)
	}

	return repo, nil
}

// createIndexes creates indexes for MongoDB collections
func (r *MongoRepository) createIndexes(ctx context.Context) error {
	// Sessions indexes
	sessionIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "session_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "user_id", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "status", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "created_at", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "last_active", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "target_info.hostname", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "target_info.os_detected", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
	}

	// Commands indexes
	commandIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "command_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "session_id", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "user_id", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "command", Value: "text"}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "timestamp", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "exit_code", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "is_suggested", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "tagged", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "error_detected", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
	}

	// Bookmarks indexes
	bookmarkIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "bookmark_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "command_id", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "session_id", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "user_id", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "created_at", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
	}

	// Context indexes
	contextIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "session_id", Value: 1}},
			Options: options.Index().SetUnique(true),
		},
		{
			Keys:    bson.D{{Key: "user_id", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "last_updated", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
	}

	// Create indexes
	_, err := r.sessions.Indexes().CreateMany(ctx, sessionIndexes)
	if err != nil {
		return fmt.Errorf("failed to create session indexes: %w", err)
	}

	_, err = r.commands.Indexes().CreateMany(ctx, commandIndexes)
	if err != nil {
		return fmt.Errorf("failed to create command indexes: %w", err)
	}

	_, err = r.bookmarks.Indexes().CreateMany(ctx, bookmarkIndexes)
	if err != nil {
		return fmt.Errorf("failed to create bookmark indexes: %w", err)
	}

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

	// Check if the session already exists
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
func (r *MongoRepository) GetUserSessions(userID string, status string, limit, offset int) ([]*models.Session, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{"user_id": userID}
	if status != "" {
		filter["status"] = status
	}

	// Create options
	findOptions := options.Find()
	findOptions.SetSort(bson.D{{Key: "created_at", Value: -1}})
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
	if req.Hostname != "" {
		filter["target_info.hostname"] = bson.M{"$regex": primitive.Regex{Pattern: req.Hostname, Options: "i"}}
	}
	if req.OSType != "" {
		filter["target_info.os_detected"] = bson.M{"$regex": primitive.Regex{Pattern: req.OSType, Options: "i"}}
	}
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
	if len(req.Tags) > 0 {
		filter["tags"] = bson.M{"$all": req.Tags}
	}

	// Create options
	findOptions := options.Find()
	if req.SortField != "" {
		sortOrder := 1
		if req.SortOrder == "desc" {
			sortOrder = -1
		}
		findOptions.SetSort(bson.D{{Key: req.SortField, Value: sortOrder}})
	} else {
		findOptions.SetSort(bson.D{{Key: "created_at", Value: -1}})
	}
	findOptions.SetLimit(int64(req.Limit))
	findOptions.SetSkip(int64(req.Offset))

	// Count total sessions
	totalCount, err := r.sessions.CountDocuments(ctx, filter)
	if err != nil {
		return nil, 0, err
	}

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

	return sessions, int(totalCount), nil
}

// UpdateSessionStatus updates the status of a session
func (r *MongoRepository) UpdateSessionStatus(sessionID string, status models.SessionStatus) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	update := bson.M{
		"$set": bson.M{
			"status":       status,
			"last_active":  time.Now(),
		},
	}

	// If status is disconnected, set ended_at
	if status == models.SessionStatusDisconnected || status == models.SessionStatusFailed {
		now := time.Now()
		update["$set"].(bson.M)["ended_at"] = now
	}

	_, err := r.sessions.UpdateOne(ctx, bson.M{"session_id": sessionID}, update)
	return err
}

// SaveCommand saves a command to the database
func (r *MongoRepository) SaveCommand(command *models.Command) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Check if the command already exists
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
	update := bson.M{
		"$inc": bson.M{
			"stats.command_count": 1,
			"stats.bytes_sent":    int64(len(command.CommandText)),
			"stats.bytes_received": int64(len(command.Output)),
		},
		"$set": bson.M{
			"last_active": time.Now(),
		},
	}
	_, err = r.sessions.UpdateOne(ctx, bson.M{"session_id": command.SessionID}, update)
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
	findOptions.SetSort(bson.D{{Key: "timestamp", Value: -1}})
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

// GetUserCommands gets all commands for a user
func (r *MongoRepository) GetUserCommands(userID string, limit, offset int) ([]*models.Command, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Create filter
	filter := bson.M{"user_id": userID}

	// Create options
	findOptions := options.Find()
	findOptions.SetSort(bson.D{{Key: "timestamp", Value: -1}})
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
			if len(countResult) > 0 {
				totalCount = int(countResult[0]["total"].(int32))
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
		findOptions.SetSort(bson.D{{Key: req.SortField, Value: sortOrder}})
	} else {
		findOptions.SetSort(bson.D{{Key: "timestamp", Value: -1}})
	}
	findOptions.SetLimit(int64(req.Limit))
	findOptions.SetSkip(int64(req.Offset))

	// Count total commands
	totalCount, err := r.commands.CountDocuments(ctx, filter)
	if err != nil {
		return nil, 0, err
	}

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

	return commands, int(totalCount), nil
}

// SaveBookmark saves a bookmark to the database
func (r *MongoRepository) SaveBookmark(bookmark *models.Bookmark) error {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Check if the bookmark already exists
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
	findOptions.SetSort(bson.D{{Key: "created_at", Value: -1}})
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

	// Check if the context already exists
	var existingContext models.SessionContext
	err := r.contexts.FindOne(ctx, bson.M{"session_id": sessionContext.SessionID}).Decode(&existingContext)
	if err == nil {
		// Context exists, update it
		sessionContext.ID = existingContext.ID
		filter := bson.M{"_id": existingContext.ID}
		update := bson.M{"$set": sessionContext}
		_, err = r.contexts.UpdateOne(ctx, filter, update)
		return err
	} else if !errors.Is(err, mongo.ErrNoDocuments) {
		// Error other than document not found
		return err
	}

	// Context doesn't exist, create a new one
	_, err = r.contexts.InsertOne(ctx, sessionContext)
	return err
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

// PurgeOldSessions removes sessions older than the specified number of days
func (r *MongoRepository) PurgeOldSessions(days int) (int, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Calculate cutoff date
	cutoff := time.Now().AddDate(0, 0, -days)

	// Delete old sessions
	deleteResult, err := r.sessions.DeleteMany(ctx, bson.M{"created_at": bson.M{"$lt": cutoff}})
	if err != nil {
		return 0, err
	}

	return int(deleteResult.DeletedCount), nil
}

// PurgeOldCommands removes commands older than the specified number of days
func (r *MongoRepository) PurgeOldCommands(days int) (int, error) {
	ctx, cancel := context.WithTimeout(context.Background(), r.timeout)
	defer cancel()

	// Calculate cutoff date
	cutoff := time.Now().AddDate(0, 0, -days)

	// Delete old commands
	deleteResult, err := r.commands.DeleteMany(ctx, bson.M{"timestamp": bson.M{"$lt": cutoff}})
	if err != nil {
		return 0, err
	}

	return int(deleteResult.DeletedCount), nil
}