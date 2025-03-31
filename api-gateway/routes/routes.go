package routes

import (
	"github.com/gin-gonic/gin"

	"api-gateway/handlers"
	"api-gateway/middleware"
)

// SetupRoutes configura todas las rutas de la aplicación
func SetupRoutes(router *gin.Engine) {
	// Middleware global
	router.Use(middleware.Logger())
	router.Use(middleware.CORS())

	// Ruta de health check
	router.GET("/health", handlers.HealthCheck)

	// Rutas públicas
	public := router.Group("/api/v1")
	{
		public.POST("/auth/login", handlers.Login)
		public.POST("/auth/refresh", handlers.RefreshToken)
	}

	// Rutas protegidas
	api := router.Group("/api/v1")
	api.Use(middleware.AuthRequired())
	{
		// Usuarios
		users := api.Group("/users")
		{
			users.GET("", handlers.GetUsers)
			users.GET("/:id", handlers.GetUser)
			users.POST("", middleware.AdminRequired(), handlers.CreateUser)
			users.PUT("/:id", handlers.UpdateUser)
			users.DELETE("/:id", middleware.AdminRequired(), handlers.DeleteUser)
		}

		// Documentos
		documents := api.Group("/documents")
		{
			documents.GET("", handlers.GetDocuments)
			documents.GET("/:id", handlers.GetDocument)
			documents.POST("", handlers.UploadDocument)
			documents.PUT("/:id", handlers.UpdateDocument)
			documents.DELETE("/:id", handlers.DeleteDocument)
			documents.GET("/:id/content", handlers.GetDocumentContent)
			documents.GET("/search", handlers.SearchDocuments)
		}

		// Áreas de conocimiento
		areas := api.Group("/areas")
		{
			areas.GET("", handlers.GetAreas)
			areas.GET("/:id", handlers.GetArea)
			areas.POST("", middleware.AdminRequired(), handlers.CreateArea)
			areas.PUT("/:id", middleware.AdminRequired(), handlers.UpdateArea)
			areas.DELETE("/:id", middleware.AdminRequired(), handlers.DeleteArea)
		}

		// RAG
		rag := api.Group("/rag")
		{
			rag.POST("/query", handlers.ProcessQuery)
			rag.GET("/history", handlers.GetQueryHistory)
			rag.GET("/history/:id", handlers.GetQueryDetail)
		}

		// Configuración de LLM
		llm := api.Group("/llm")
		{
			llm.GET("/providers", handlers.GetLLMProviders)
			llm.GET("/providers/:id", handlers.GetLLMProvider)
			llm.POST("/providers", middleware.AdminRequired(), handlers.CreateLLMProvider)
			llm.PUT("/providers/:id", middleware.AdminRequired(), handlers.UpdateLLMProvider)
			llm.DELETE("/providers/:id", middleware.AdminRequired(), handlers.DeleteLLMProvider)
			llm.POST("/providers/:id/test", middleware.AdminRequired(), handlers.TestLLMProvider)

			llm.GET("/settings", handlers.GetLLMSettings)
			llm.PUT("/settings", middleware.AdminRequired(), handlers.UpdateLLMSettings)
		}

		// Nuevas rutas para conexiones de BD
		dbConnections := api.Group("/db-connections")
		dbConnections.Use(middleware.AdminRequired()) // Solo administradores pueden gestionar conexiones
		{
			dbConnections.GET("", handlers.GetDBConnections)
			dbConnections.GET("/:id", handlers.GetDBConnection)
			dbConnections.POST("", handlers.CreateDBConnection)
			dbConnections.PUT("/:id", handlers.UpdateDBConnection)
			dbConnections.DELETE("/:id", handlers.DeleteDBConnection)
			dbConnections.POST("/:id/test", handlers.TestDBConnection)
			dbConnections.GET("/:id/schema", handlers.GetDBConnectionSchema)
		}

		// Rutas para configuración de agentes DB
		dbAgents := api.Group("/db-agents")
		{
			dbAgents.GET("", handlers.GetDBAgents)
			dbAgents.GET("/:id", handlers.GetDBAgent)
			dbAgents.POST("", middleware.AdminRequired(), handlers.CreateDBAgent)
			dbAgents.PUT("/:id", middleware.AdminRequired(), handlers.UpdateDBAgent)
			dbAgents.DELETE("/:id", middleware.AdminRequired(), handlers.DeleteDBAgent)
			
			// Configuración de prompts para agentes
			dbAgents.GET("/:id/prompts", handlers.GetDBAgentPrompts)
			dbAgents.PUT("/:id/prompts", middleware.AdminRequired(), handlers.UpdateDBAgentPrompts)
			
			// Asignación de conexiones a agentes
			dbAgents.GET("/:id/connections", handlers.GetDBAgentConnections)
			dbAgents.POST("/:id/connections", middleware.AdminRequired(), handlers.AssignDBConnectionToAgent)
			dbAgents.DELETE("/:id/connections/:connectionId", middleware.AdminRequired(), handlers.RemoveDBConnectionFromAgent)
		}

		// Consultas a BD a través de agentes
		dbQueries := api.Group("/db-queries")
		{
			dbQueries.POST("", handlers.ProcessDBQuery)
			dbQueries.GET("/history", handlers.GetDBQueryHistory)
			dbQueries.GET("/history/:id", handlers.GetDBQueryDetail)
		}

		// Configuración de Ollama
		ollama := api.Group("/ollama")
		ollama.Use(middleware.AdminRequired())
		{
			ollama.GET("/models", handlers.GetOllamaModels)
			ollama.POST("/models/pull", handlers.PullOllamaModel)
			ollama.DELETE("/models/:name", handlers.DeleteOllamaModel)
			ollama.GET("/settings", handlers.GetOllamaSettings)
			ollama.PUT("/settings", handlers.UpdateOllamaSettings)
		}
	}

	// Admin panel
	admin := router.Group("/admin")
	admin.Use(middleware.AuthRequired(), middleware.AdminRequired())
	{
		admin.GET("/system/status", handlers.GetSystemStatus)
		admin.GET("/system/logs", handlers.GetSystemLogs)
	}
}