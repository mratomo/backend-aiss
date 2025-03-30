package routes

import (
	"api-gateway/config"
	"api-gateway/handlers"
	"api-gateway/middleware"

	"github.com/gin-gonic/gin"
)

// SetupRoutes configura todas las rutas del API Gateway
func SetupRoutes(router *gin.Engine, cfg *config.Config) {
	// Handler para health check
	router.GET("/health", handlers.HealthCheck)

	// Inicializar los handlers
	userHandler := handlers.NewUserHandler(cfg.Services.UserService)
	docHandler := handlers.NewDocumentHandler(cfg.Services.DocumentService)
	contextHandler := handlers.NewContextHandler(cfg.Services.ContextService)
	ragHandler := handlers.NewRAGHandler(cfg.Services.RagAgent)
	llmSettingsHandler := handlers.NewLLMSettingsHandler(cfg.Services.RagAgent)

	// Middleware de autenticación
	authMiddleware := middleware.NewAuthMiddleware(cfg.AuthSecret)
	adminMiddleware := middleware.NewAdminMiddleware(cfg.Services.UserService)

	// Rutas de autenticación
	auth := router.Group("/auth")
	{
		auth.POST("/register", userHandler.Register)
		auth.POST("/login", userHandler.Login)
		auth.POST("/refresh", userHandler.RefreshToken)
	}

	// Rutas de usuarios (requieren autenticación)
	users := router.Group("/users")
	users.Use(authMiddleware.Authenticate())
	{
		users.GET("/me", userHandler.GetCurrentUser)
		users.PUT("/me", userHandler.UpdateUser)
		users.PUT("/password", userHandler.ChangePassword)

		// Rutas de administración de usuarios (solo admin)
		admin := users.Group("/admin")
		admin.Use(adminMiddleware.AdminOnly())
		{
			admin.GET("", userHandler.GetAllUsers)
			admin.GET("/:id", userHandler.GetUserByID)
			admin.POST("", userHandler.Register)         // NUEVO: Crear usuario como admin
			admin.PUT("/:id", userHandler.UpdateUser)    // NUEVO: Actualizar cualquier usuario
			admin.DELETE("/:id", userHandler.DeleteUser) // NUEVO: Eliminar usuario
			admin.PUT("/:id/permissions", userHandler.UpdatePermissions)
		}
	}

	// Rutas de áreas de conocimiento
	knowledge := router.Group("/knowledge")
	knowledge.Use(authMiddleware.Authenticate())
	{
		// Listado y consulta de áreas (todos los usuarios)
		knowledge.GET("/areas", contextHandler.ListAreas)
		knowledge.GET("/areas/:id", contextHandler.GetAreaByID)
		knowledge.GET("/areas/:id/system-prompt", contextHandler.GetAreaSystemPrompt)

		// Administración de áreas (solo admin)
		admin := knowledge.Group("/admin")
		admin.Use(adminMiddleware.AdminOnly())
		{
			admin.POST("/areas", contextHandler.CreateArea)
			admin.PUT("/areas/:id", contextHandler.UpdateArea)
			admin.DELETE("/areas/:id", contextHandler.DeleteArea)
			admin.PUT("/areas/:id/system-prompt", contextHandler.UpdateAreaSystemPrompt)
		}
	}

	// Rutas de documentos
	docs := router.Group("/documents")
	docs.Use(authMiddleware.Authenticate())
	{
		// Documentos personales (todos los usuarios)
		docs.GET("/personal", docHandler.ListPersonalDocuments)
		docs.POST("/personal", docHandler.UploadPersonalDocument)
		docs.GET("/personal/:id", docHandler.GetPersonalDocument)
		docs.GET("/personal/:id/content", docHandler.GetPersonalDocumentContent)
		docs.DELETE("/personal/:id", docHandler.DeletePersonalDocument)

		// Documentos compartidos (lectura para todos)
		docs.GET("/shared", docHandler.ListSharedDocuments)
		docs.GET("/shared/:id", docHandler.GetSharedDocument)
		docs.GET("/shared/:id/content", docHandler.GetSharedDocumentContent)

		// Administración de documentos compartidos (solo admin)
		admin := docs.Group("/admin")
		admin.Use(adminMiddleware.AdminOnly())
		{
			admin.POST("/shared", docHandler.UploadSharedDocument)
			admin.PUT("/shared/:id", docHandler.UpdateSharedDocument)
			admin.DELETE("/shared/:id", docHandler.DeleteSharedDocument)
		}
	}

	// Rutas para búsqueda de documentos
	search := router.Group("/search")
	search.Use(authMiddleware.Authenticate())
	{
		search.GET("", docHandler.SearchDocuments) // NUEVO: Ruta de búsqueda de documentos
	}

	// Rutas para consultas RAG
	queries := router.Group("/queries")
	queries.Use(authMiddleware.Authenticate())
	{
		queries.POST("", ragHandler.QueryKnowledge)
		queries.POST("/area/:areaId", ragHandler.QuerySpecificArea)
		queries.POST("/personal", ragHandler.QueryPersonalKnowledge)
		queries.GET("/history", ragHandler.GetQueryHistory)
	}

	// Rutas para configuración LLM (solo admin)
	llm := router.Group("/llm")
	llm.Use(authMiddleware.Authenticate())
	llm.Use(adminMiddleware.AdminOnly())
	{
		llm.GET("/providers", ragHandler.ListProviders)
		llm.POST("/providers", ragHandler.AddProvider)
		llm.PUT("/providers/:id", ragHandler.UpdateProvider)
		llm.DELETE("/providers/:id", ragHandler.DeleteProvider)
		llm.POST("/providers/:id/test", ragHandler.TestProvider)

		// Rutas para configuración de system prompt global
		llm.GET("/settings/system-prompt", llmSettingsHandler.GetSystemPrompt)
		llm.PUT("/settings/system-prompt", llmSettingsHandler.UpdateSystemPrompt)
		llm.POST("/settings/system-prompt/reset", llmSettingsHandler.ResetSystemPrompt)
	}
}
