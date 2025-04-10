package main

import (
	"context"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
	"user-service/config"
	"user-service/controllers"
	"user-service/repositories"
	"user-service/services"

	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

func main() {
	// Cargar configuración
	cfg, err := config.LoadConfig()
	if err != nil {
		log.Fatalf("Error al cargar configuración: %v", err)
	}

	// Configurar Gin
	if cfg.Environment == "production" {
		gin.SetMode(gin.ReleaseMode)
	}

	// Conectar a MongoDB
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	mongoURI := os.Getenv("MONGODB_URI")
	if mongoURI == "" {
		mongoURI = cfg.MongoDB.URI
	}

	mongoClient, err := mongo.Connect(ctx, options.Client().ApplyURI(mongoURI))
	if err != nil {
		log.Fatalf("Error al conectar a MongoDB: %v", err)
	}

	// Verificar conexión
	err = mongoClient.Ping(ctx, nil)
	if err != nil {
		log.Fatalf("Error al verificar conexión a MongoDB: %v", err)
	}

	log.Println("Conexión a MongoDB establecida correctamente")

	// Inicializar repositorio
	db := mongoClient.Database(cfg.MongoDB.Database)
	userCollection := db.Collection("users")
	userRepo := repositories.NewUserRepository(userCollection)

	// Inicializar servicio
	jwtSecret := os.Getenv("AUTH_SECRET")
	if jwtSecret == "" {
		jwtSecret = cfg.Auth.Secret
	}
	userService := services.NewUserService(userRepo, jwtSecret, cfg.Auth.ExpirationHours)

	// Inicializar controlador
	userController := controllers.NewUserController(userService)

	// Configurar rutas
	router := setupRoutes(userController)

	// Registrar el primer administrador si no hay usuarios
	initCtx, initCancel := context.WithTimeout(context.Background(), 30*time.Second)
	registerFirstAdmin(initCtx, userRepo, userService, cfg.Environment)
	initCancel()

	// Iniciar servidor
	server := &http.Server{
		Addr:         ":" + cfg.Port,
		Handler:      router,
		ReadTimeout:  15 * time.Second,
		WriteTimeout: 15 * time.Second,
	}

	// Iniciar servidor en goroutine
	go func() {
		log.Printf("Servidor iniciado en puerto %s", cfg.Port)
		if err := server.ListenAndServe(); err != nil && err != http.ErrServerClosed {
			log.Fatalf("Error al iniciar servidor: %v", err)
		}
	}()

	// Configurar apagado graceful
	quit := make(chan os.Signal, 1)
	signal.Notify(quit, syscall.SIGINT, syscall.SIGTERM)
	<-quit
	log.Println("Apagado de servidor iniciado...")

	// Dar tiempo para finalizar solicitudes en curso
	shutdownCtx, shutdownCancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer shutdownCancel()

	if err := server.Shutdown(shutdownCtx); err != nil {
		log.Fatalf("Error al apagar servidor: %v", err)
	}

	log.Println("Cerrando conexión a MongoDB...")
	if err := mongoClient.Disconnect(shutdownCtx); err != nil {
		log.Fatalf("Error al cerrar conexión a MongoDB: %v", err)
	}

	log.Println("Servidor detenido correctamente")
}

// registerFirstAdmin registra al primer administrador si no existe ningún usuario
// usando una operación atómica para evitar race conditions
func registerFirstAdmin(ctx context.Context, repo *repositories.UserRepository, service *services.UserService, environment string) {
	// Usar una operación atómica para verificar y crear admin si es necesario
	result, err := repo.CreateFirstAdminIfNeeded(ctx, "admin", "admin@example.com")
	if err != nil {
		log.Printf("Error durante verificación de primer administrador: %v", err)
		return
	}

	// Si el resultado es false, significa que ya existen usuarios
	// Si es true, significa que se creó el admin
	if result {
		adminPassword := os.Getenv("ADMIN_INITIAL_PASSWORD")

		// En entorno de producción, requerir contraseña explícitamente
		if environment == "production" && adminPassword == "" {
			log.Fatalf("Error: ADMIN_INITIAL_PASSWORD debe configurarse en entornos de producción")
		} else if adminPassword == "" {
			adminPassword = "admin123" // Contraseña por defecto solo para desarrollo
			log.Println("Advertencia: Usando contraseña de administrador por defecto. Defina ADMIN_INITIAL_PASSWORD para mayor seguridad.")
		}

		// Establecer la contraseña del admin
		err = service.SetAdminPassword(ctx, adminPassword)
		if err != nil {
			log.Printf("Error al establecer contraseña del administrador inicial: %v", err)
			return
		}

		log.Println("Usuario administrador inicial creado correctamente")
	}
}

// setupRoutes configura las rutas del API
func setupRoutes(userController *controllers.UserController) *gin.Engine {
	router := gin.Default()

	// Middlewares
	router.Use(gin.Recovery())

	// Rutas de autenticación
	authGroup := router.Group("/auth")
	{
		authGroup.POST("/register", userController.Register)
		authGroup.POST("/login", userController.Login)
		authGroup.POST("/refresh", userController.RefreshToken)
	}

	// Rutas de usuario
	userGroup := router.Group("/users")
	{
		userGroup.GET("", userController.GetAllUsers)
		userGroup.GET("/:id", userController.GetUserByID)
		userGroup.PUT("/:id", userController.UpdateUser)
		userGroup.DELETE("/:id", userController.DeleteUser)
		userGroup.POST("/verify-admin", userController.VerifyAdmin)
		userGroup.PUT("/:id/permissions", userController.UpdatePermissions)
		userGroup.PUT("/:id/password", userController.ChangePassword)
	}

	// Ruta de health check
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{
			"status": "ok",
			"time":   time.Now().Format(time.RFC3339),
		})
	})

	return router
}
