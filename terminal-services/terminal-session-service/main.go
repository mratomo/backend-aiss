package main

import (
	"context"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-gonic/gin"

	"terminal-session-service/config"
	"terminal-session-service/repositories"
	"terminal-session-service/routes"
)

func main() {
	// Load configuration
	cfg, err := config.Load()
	if err != nil {
		log.Fatalf("Failed to load configuration: %v", err)
	}

	// Set Gin mode
	if os.Getenv("ENVIRONMENT") == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	// Create MongoDB repository
	repo, err := repositories.NewMongoRepository(
		cfg.Database.URI,
		cfg.Database.Database,
		cfg.Database.Timeout,
	)
	if err != nil {
		log.Fatalf("Failed to connect to MongoDB: %v", err)
	}
	defer repo.Close()

	// Create router
	router := gin.Default()

	// Setup routes
	routes.SetupRoutes(router, cfg, repo)

	// Create HTTP server
	server := &http.Server{
		Addr:         fmt.Sprintf("%s:%d", cfg.Server.Host, cfg.Server.Port),
		Handler:      router,
		ReadTimeout:  cfg.Server.ReadTimeout,
		WriteTimeout: cfg.Server.WriteTimeout,
	}

	// Run server in a goroutine
	go func() {
		log.Printf("Starting server on %s:%d", cfg.Server.Host, cfg.Server.Port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Failed to start server: %v", err)
		}
	}()

	// Schedule regular maintenance
	maintenanceTicker := time.NewTicker(24 * time.Hour)
	go func() {
		for {
			select {
			case <-maintenanceTicker.C:
				// Purge old data
				log.Println("Running scheduled maintenance")
				sessionsDeleted, err := repo.PurgeOldSessions(cfg.Retention.SessionDays)
				if err != nil {
					log.Printf("Failed to purge old sessions: %v", err)
				} else {
					log.Printf("Purged %d old sessions", sessionsDeleted)
				}

				commandsDeleted, err := repo.PurgeOldCommands(cfg.Retention.CommandDays)
				if err != nil {
					log.Printf("Failed to purge old commands: %v", err)
				} else {
					log.Printf("Purged %d old commands", commandsDeleted)
				}
			}
		}
	}()

	// Wait for interrupt signal
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Shutting down server...")

	maintenanceTicker.Stop()

	// Create context with timeout for shutdown
	ctx, cancel := context.WithTimeout(context.Background(), cfg.Server.GracefulTimeout)
	defer cancel()

	// Shutdown server
	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("Server forced to shutdown: %v", err)
	}

	log.Println("Server exiting")
}