package routes

import (
	"github.com/gin-gonic/gin"

	"terminal-gateway-service/config"
	"terminal-gateway-service/handlers"
	"terminal-gateway-service/middleware"
)

// SetupRoutes configures all routes for the application
func SetupRoutes(router *gin.Engine, cfg *config.Config, sshManager *handlers.SSHManager) {
	// Create handlers
	sessionHandler := handlers.NewSessionHandler(sshManager)

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
		// Terminal routes (auth required)
		terminal := v1.Group("/terminal")
		terminal.Use(middleware.AuthRequired(middleware.JWTConfig{
			Secret:      cfg.Auth.JWTSecret,
			ExpiryHours: cfg.Auth.JWTExpiryHours,
			Issuer:      cfg.Auth.JWTIssuer,
		}))
		{
			// Session management
			sessions := terminal.Group("/sessions")
			{
				sessions.POST("", sessionHandler.CreateSession)
				sessions.GET("", sessionHandler.GetSessions)
				sessions.GET("/:id", sessionHandler.GetSession)
				sessions.DELETE("/:id", sessionHandler.TerminateSession)
				sessions.PATCH("/:id", sessionHandler.UpdateSession)

				// WebSocket endpoint for terminal I/O
				sessions.GET("/:id/stream", sessionHandler.WebSocketHandler)
			}
		}

		// Admin routes
		admin := v1.Group("/admin")
		admin.Use(middleware.AuthRequired(middleware.JWTConfig{
			Secret:      cfg.Auth.JWTSecret,
			ExpiryHours: cfg.Auth.JWTExpiryHours,
			Issuer:      cfg.Auth.JWTIssuer,
		}))
		admin.Use(middleware.AdminRequired())
		{
			// Admin terminal routes
			adminTerminal := admin.Group("/terminal")
			{
				// Admin can access all sessions
				adminTerminal.GET("/sessions", sessionHandler.GetSessions)
				adminTerminal.GET("/sessions/:id", sessionHandler.GetSession)
				adminTerminal.DELETE("/sessions/:id", sessionHandler.TerminateSession)
			}
		}
	}
}