package main

import (
	"api-gateway/config"
	"api-gateway/handlers"
	"api-gateway/middleware"
	"api-gateway/routes"
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
)

func main() {
	// Cargar configuración
	cfg, err := config.LoadConfig()
	if err != nil {
		log.Fatalf("Error al cargar la configuración: %v", err)
	}

	// Configurar modo de Gin
	if cfg.Environment == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	// Inicializar router
	router := gin.Default()

	// Inicializar el manejador de configuración (para CORS dinámico)
	handlers.NewConfigHandler(&cfg.CorsAllowedOrigins, cfg.Environment, "config/config.yaml")
	log.Printf("Configuración CORS inicial: %v", cfg.CorsAllowedOrigins)

	// Inicializar los manejadores de servicios
	handlers.NewUserHandler(cfg.User.ServiceURL)
	log.Printf("User service URL: %s", cfg.User.ServiceURL)

	// Inicializar manejador de base de datos
	handlers.NewDBHandler(
		cfg.Services.DBConnectionService,
		cfg.Services.SchemaDiscoveryService,
		cfg.Services.RagAgent,
	)
	log.Printf("DB Connection service URL: %s", cfg.Services.DBConnectionService)
	log.Printf("Schema Discovery service URL: %s", cfg.Services.SchemaDiscoveryService)

	// Inicializar manejador de Ollama
	handlers.NewOllamaHandler(cfg.Services.RagAgent)
	log.Printf("RAG Agent URL: %s", cfg.Services.RagAgent)

	// Configurar CORS - versión restrictiva para configuración más segura
	corsConfig := cors.DefaultConfig()

	// Usar AllowOrigins en lugar de AllowAllOrigins para mayor seguridad
	corsConfig.AllowOrigins = cfg.CorsAllowedOrigins

	corsConfig.AllowMethods = []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
	corsConfig.AllowHeaders = []string{"Origin", "Content-Type", "Accept", "Authorization"}
	corsConfig.ExposeHeaders = []string{"Content-Length"}
	corsConfig.AllowCredentials = true
	corsConfig.MaxAge = 12 * time.Hour

	// Aplicar configuración CORS
	router.Use(cors.New(corsConfig))

	// Middleware global
	router.Use(middleware.RequestLogger())
	router.Use(middleware.ErrorHandler())

	// Configurar rutas
	routes.SetupRoutes(router, cfg)

	// Configurar servidor HTTP
	server := &http.Server{
		Addr:    ":" + cfg.Port,
		Handler: router,
	}

	// Canal para señales de cierre
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)

	// Ejecutar servidor en goroutine
	go func() {
		log.Printf("Servidor iniciado en el puerto %s", cfg.Port)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("Error al iniciar el servidor: %v", err)
		}
	}()

	// Esperar señal de cierre
	<-quit
	log.Println("Apagando servidor...")

	// Contexto con timeout para shutdown
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Cerrar servidor gracefully
	if err := server.Shutdown(ctx); err != nil {
		log.Fatalf("Error al cerrar el servidor: %v", err)
	}

	log.Println("Servidor detenido correctamente")
}
