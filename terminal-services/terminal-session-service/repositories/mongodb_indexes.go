package repositories

import (
	"context"
	"fmt"
	"time"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// CreateOptimizedIndexes creates optimized indexes for MongoDB collections
func (r *MongoRepository) CreateOptimizedIndexes() error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Add additional indexes for improved query performance

	// Session indexes
	sessionIndexes := []mongo.IndexModel{
		{
			// Compound index for faster active area queries
			Keys:    bson.D{{Key: "user_id", Value: 1}, {Key: "active_area_id", Value: 1}},
			Options: options.Index().SetBackground(true).SetSparse(true),
		},
		{
			// Compound index for faster mode queries
			Keys:    bson.D{{Key: "user_id", Value: 1}, {Key: "mode", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			// Index for last activity with TTL for automatic cleanup
			Keys:    bson.D{{Key: "last_active", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			// Compound index for user's sessions with status
			Keys:    bson.D{{Key: "user_id", Value: 1}, {Key: "status", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
	}

	// Command indexes
	commandIndexes := []mongo.IndexModel{
		{
			// Optimized text search index with weights and limiting keys
			Keys: bson.D{
				{Key: "command", Value: "text"},
				{Key: "output", Value: "text"},
			},
			Options: options.Index().
				SetBackground(true).
				SetWeights(bson.D{
					{Key: "command", Value: 10},
					{Key: "output", Value: 5},
				}).
				SetDefaultLanguage("english").
				// Limiting this index helps with memory usage
				SetPartialFilterExpression(bson.M{
					"timestamp": bson.M{"$gt": time.Now().AddDate(0, -3, 0)}, // Only last 3 months
				}),
		},
		{
			// Compound index for faster time-based queries
			Keys:    bson.D{{Key: "user_id", Value: 1}, {Key: "timestamp", Value: -1}},
			Options: options.Index().SetBackground(true),
		},
		{
			// Compound index for error filtering
			Keys:    bson.D{{Key: "session_id", Value: 1}, {Key: "error_detected", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			// Index for suggested commands
			Keys:    bson.D{{Key: "is_suggested", Value: 1}, {Key: "suggestion_id", Value: 1}},
			Options: options.Index().SetBackground(true).SetSparse(true),
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
			Keys:    bson.D{{Key: "last_updated", Value: -1}},
			Options: options.Index().SetBackground(true),
		},
	}

	// Mode change indexes with TTL
	modeChangeIndexes := []mongo.IndexModel{
		{
			Keys:    bson.D{{Key: "session_id", Value: 1}},
			Options: options.Index().SetBackground(true),
		},
		{
			Keys:    bson.D{{Key: "timestamp", Value: 1}},
			Options: options.Index().SetBackground(true).SetExpireAfterSeconds(7 * 24 * 60 * 60), // 7 days TTL
		},
	}

	// Apply the new indexes
	_, err := r.sessions.Indexes().CreateMany(ctx, sessionIndexes)
	if err != nil {
		return fmt.Errorf("failed to create optimized session indexes: %w", err)
	}

	_, err = r.commands.Indexes().CreateMany(ctx, commandIndexes)
	if err != nil {
		return fmt.Errorf("failed to create optimized command indexes: %w", err)
	}

	_, err = r.sessionContexts.Indexes().CreateMany(ctx, contextIndexes)
	if err != nil {
		return fmt.Errorf("failed to create context indexes: %w", err)
	}

	_, err = r.modeChanges.Indexes().CreateMany(ctx, modeChangeIndexes)
	if err != nil {
		return fmt.Errorf("failed to create mode change indexes: %w", err)
	}

	return nil
}

// CreateSearchIndexes creates efficient text search indexes
func (r *MongoRepository) CreateSearchIndexes() error {
	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	// Check if search indexes exist
	cursor, err := r.commands.Indexes().List(ctx)
	if err != nil {
		return fmt.Errorf("failed to list indexes: %w", err)
	}
	defer cursor.Close(ctx)

	var results []bson.M
	if err = cursor.All(ctx, &results); err != nil {
		return fmt.Errorf("failed to read indexes: %w", err)
	}

	// Check if we need to create a new search index
	hasTextIndex := false
	for _, idx := range results {
		keys, ok := idx["key"].(bson.M)
		if !ok {
			continue
		}

		// Check if this is a text index
		for _, v := range keys {
			if v == "text" {
				hasTextIndex = true
				break
			}
		}

		if hasTextIndex {
			break
		}
	}

	// If no text index exists, create an optimized one
	if !hasTextIndex {
		cmdSearchIdx := mongo.IndexModel{
			Keys: bson.D{
				{Key: "command", Value: "text"},
				{Key: "output", Value: "text"},
			},
			Options: options.Index().
				SetBackground(true).
				SetWeights(bson.D{
					{Key: "command", Value: 10},
					{Key: "output", Value: 2},
				}).
				SetDefaultLanguage("english").
				// Limiting this index helps with memory usage
				SetPartialFilterExpression(bson.M{
					"timestamp": bson.M{"$gt": time.Now().AddDate(0, -3, 0)}, // Only index last 3 months
				}),
		}

		_, err = r.commands.Indexes().CreateOne(ctx, cmdSearchIdx)
		if err != nil {
			return fmt.Errorf("failed to create command search index: %w", err)
		}
	}

	return nil
}
