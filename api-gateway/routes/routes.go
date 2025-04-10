package routes

import (
	"github.com/gin-gonic/gin"

	"api-gateway/config"
	"api-gateway/handlers"
	"api-gateway/middleware"
)

// SetupRoutes configura todas las rutas de la aplicación
func SetupRoutes(router *gin.Engine, cfg *config.Config) {
	// Inicializar middlewares
	authMiddleware := middleware.NewAuthMiddleware(cfg.Auth.Secret)
	adminMiddleware := middleware.NewAdminMiddleware(cfg.User.ServiceURL)

	// Middleware global
	router.Use(middleware.RequestLogger())

	// Ruta de health check
	router.GET("/health", handlers.HealthCheck)
	router.GET("/api/health", handlers.HealthCheck)

	// Rutas públicas
	public := router.Group("/api/v1")
	{
		public.POST("/auth/login", handlers.GetUserHandler().Login)
		public.POST("/auth/refresh", handlers.GetUserHandler().RefreshToken)
	}

	// Rutas protegidas
	api := router.Group("/api/v1")
	api.Use(authMiddleware.Authenticate())
	{
		// Usuarios
		users := api.Group("/users")
		{
			users.GET("", adminMiddleware.AdminOnly(), handlers.GetUserHandler().GetAllUsers)
			users.GET("/:id", handlers.GetUserHandler().GetUserByID)
			users.POST("", adminMiddleware.AdminOnly(), handlers.GetUserHandler().Register)
			users.PUT("/:id", handlers.GetUserHandler().UpdateUser)
			users.DELETE("/:id", adminMiddleware.AdminOnly(), handlers.GetUserHandler().DeleteUser)
			users.PUT("/:id/password", handlers.GetUserHandler().ChangePassword)
		}

		// Configuración del sistema
		systemConfig := api.Group("/system/config")
		{
			// CORS - Especialmente útil para entornos locales
			systemConfig.GET("/cors", handlers.GetConfigHandlerInstance().GetCorsConfig)
			systemConfig.PUT("/cors", handlers.GetConfigHandlerInstance().UpdateCorsConfig)
		}

		// DB Connections
		dbConnections := api.Group("/db-connections")
		dbConnections.Use(adminMiddleware.AdminOnly()) // Solo administradores pueden gestionar conexiones
		{
			dbConnections.GET("", handlers.GetDBConnections)
			dbConnections.GET("/:id", handlers.GetDBConnection)
			dbConnections.POST("", handlers.CreateDBConnection)
			dbConnections.PUT("/:id", handlers.UpdateDBConnection)
			dbConnections.DELETE("/:id", handlers.DeleteDBConnection)
			dbConnections.POST("/:id/test", handlers.TestDBConnection)
			dbConnections.GET("/:id/schema", handlers.GetDBConnectionSchema)
		}

		// DB Agents
		dbAgents := api.Group("/db-agents")
		dbAgents.Use(adminMiddleware.AdminOnly()) // Solo administradores pueden gestionar agentes
		{
			dbAgents.GET("", handlers.GetDBAgents)
			dbAgents.GET("/:id", handlers.GetDBAgent)
			dbAgents.POST("", handlers.CreateDBAgent)
			dbAgents.PUT("/:id", handlers.UpdateDBAgent)
			dbAgents.DELETE("/:id", handlers.DeleteDBAgent)
			dbAgents.GET("/:id/prompts", handlers.GetDBAgentPrompts)
			dbAgents.PUT("/:id/prompts", handlers.UpdateDBAgentPrompts)
			dbAgents.GET("/:id/connections", handlers.GetDBAgentConnections)
			dbAgents.POST("/:id/connections", handlers.AssignDBConnectionToAgent)
			dbAgents.DELETE("/:id/connections/:connectionId", handlers.RemoveDBConnectionFromAgent)
		}

		// DB Queries
		dbQueries := api.Group("/db-queries")
		{
			dbQueries.POST("", handlers.ProcessDBQuery)
			dbQueries.GET("/history", handlers.GetDBQueryHistory)
			dbQueries.GET("/history/:id", handlers.GetDBQueryDetail)
		}

		// Ollama Models
		ollama := api.Group("/ollama")
		ollama.Use(adminMiddleware.AdminOnly()) // Solo administradores pueden gestionar modelos
		{
			ollama.GET("/models", handlers.GetOllamaModels)
			ollama.POST("/models/pull", handlers.PullOllamaModel)
			ollama.DELETE("/models/:name", handlers.DeleteOllamaModel)
			ollama.GET("/settings", handlers.GetOllamaSettings)
			ollama.PUT("/settings", handlers.UpdateOllamaSettings)
		}
	}
}
