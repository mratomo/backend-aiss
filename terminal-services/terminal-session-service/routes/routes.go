package routes

import (
	"github.com/gin-gonic/gin"

	"terminal-session-service/config"
	"terminal-session-service/handlers"
	"terminal-session-service/middleware"
)

// SetupRoutes configures all routes for the application
func SetupRoutes(router *gin.Engine, cfg *config.Config, repo handlers.SessionRepository) {
	// Create handlers
	sessionHandler := handlers.NewSessionHandler(repo)
	commandHandler := handlers.NewCommandHandler(repo)
	bookmarkHandler := handlers.NewBookmarkHandler(repo)
	contextHandler := handlers.NewContextHandler(repo)
	maintenanceHandler := handlers.NewMaintenanceHandler(
		repo,
		cfg.Retention.SessionDays,
		cfg.Retention.CommandDays,
	)

	// Global middleware
	router.Use(middleware.Logger())
	router.Use(middleware.ErrorLogger())
	router.Use(middleware.AuditLogger())
	router.Use(middleware.CORS(cfg.Server.CORSAllowOrigin))

	// Health check route (no auth required)
	router.GET("/health", handlers.HealthCheck)

	// API v1 routes
	v1 := router.Group("/api/v1")
	{
		// Auth middleware for all API routes
		v1.Use(middleware.AuthRequired(middleware.JWTConfig{
			Secret:      cfg.Auth.JWTSecret,
			ExpiryHours: cfg.Auth.JWTExpiryHours,
			Issuer:      cfg.Auth.JWTIssuer,
		}))

		// Session routes
		sessions := v1.Group("/sessions")
		{
			sessions.POST("", sessionHandler.CreateSession)
			sessions.GET("", sessionHandler.GetSessions)
			sessions.GET("/:id", sessionHandler.GetSession)
			sessions.PATCH("/:id/status", sessionHandler.UpdateSessionStatus)
			sessions.GET("/search", sessionHandler.SearchSessions)
		}

		// Command routes
		commands := v1.Group("/commands")
		{
			commands.POST("", commandHandler.SaveCommand)
			commands.GET("/:id", commandHandler.GetCommand)
			commands.GET("/session/:id", commandHandler.GetSessionCommands)
			commands.GET("/search", commandHandler.SearchCommands)
		}

		// Bookmark routes
		bookmarks := v1.Group("/bookmarks")
		{
			bookmarks.POST("", bookmarkHandler.CreateBookmark)
			bookmarks.GET("/:id", bookmarkHandler.GetBookmark)
			bookmarks.GET("", bookmarkHandler.GetUserBookmarks)
			bookmarks.DELETE("/:id", bookmarkHandler.DeleteBookmark)
		}

		// Context routes
		contexts := v1.Group("/contexts")
		{
			contexts.POST("", contextHandler.SaveContext)
			contexts.GET("/:id", contextHandler.GetContext)
		}

		// Admin routes
		admin := v1.Group("/admin")
		admin.Use(middleware.AdminRequired())
		{
			// Maintenance operations
			maintenance := admin.Group("/maintenance")
			{
				maintenance.POST("/purge", maintenanceHandler.PurgeOldData)
			}
		}
	}
}