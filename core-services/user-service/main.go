package main

import (
	"context"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"
	"user-service/config"
	"user-service/controllers"
	"user-service/models"
	"user-service/repositories"
	"user-service/services"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
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

	// Conectar a MongoDB
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	client, err := mongo.Connect(ctx, options.Client().ApplyURI(cfg.MongoDB.URI))
	if err != nil {
		log.Fatalf("Error al conectar a MongoDB: %v", err)
	}

	// Verificar conexión
	err = client.Ping(ctx, nil)
	if err != nil {
		log.Fatalf("Error al verificar conexión a MongoDB: %v", err)
	}

	log.Println("Conexión a MongoDB establecida")

	// Configurar cierre de conexión al finalizar
	defer func() {
		if err := client.Disconnect(ctx); err != nil {
			log.Fatalf("Error al desconectar de MongoDB: %v", err)
		}
	}()

	// Inicializar repositorio, servicio y controlador
	userCollection := client.Database(cfg.MongoDB.Database).Collection("users")
	repo := repositories.NewUserRepository(userCollection)
	service := services.NewUserService(repo, cfg.Auth.Secret, cfg.Auth.ExpirationHours)
	controller := controllers.NewUserController(service)

	// Registrar al primer administrador si no existe ningún usuario
	registerFirstAdmin(ctx, repo, service, cfg.Environment)

	// Inicializar router
	router := gin.Default()

	// Configurar CORS
	router.Use(cors.New(cors.Config{
		AllowOrigins:     cfg.CorsAllowedOrigins,
		AllowMethods:     []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept", "Authorization"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))

	// Configurar rutas
	router.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok"})
	})

	// Rutas de autenticación
	router.POST("/auth/register", controller.Register)
	router.POST("/auth/login", controller.Login)
	router.POST("/auth/refresh", controller.RefreshToken)

	// Rutas de usuario
	router.GET("/users/:id", controller.GetUserByID)
	router.GET("/users", controller.GetAllUsers)
	router.PUT("/users/:id", controller.UpdateUser)
	router.DELETE("/users/:id", controller.DeleteUser)
	router.PUT("/users/:id/permissions", controller.UpdatePermissions)
	router.POST("/users/verify-admin", controller.VerifyAdmin)

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
	ctxShutdown, cancelShutdown := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancelShutdown()

	// Cerrar servidor gracefully
	if err := server.Shutdown(ctxShutdown); err != nil {
		log.Fatalf("Error al cerrar el servidor: %v", err)
	}

	log.Println("Servidor detenido correctamente")
}

// registerFirstAdmin registra al primer administrador si no existe ningún usuario
func registerFirstAdmin(ctx context.Context, repo *repositories.UserRepository, service *services.UserService, environment string) {
	// Verificar si ya existen usuarios
	count, err := repo.CountUsers(ctx)
	if err != nil {
		log.Printf("Error al verificar usuarios existentes: %v", err)
		return
	}

	// Si no hay usuarios, crear el primer administrador
	if count == 0 {
		adminPassword := os.Getenv("ADMIN_INITIAL_PASSWORD")

		// En entorno de producción, requerir contraseña explícitamente
		if environment == "production" && adminPassword == "" {
			log.Fatalf("Error: ADMIN_INITIAL_PASSWORD debe configurarse en entornos de producción")
		} else if adminPassword == "" {
			adminPassword = "admin123" // Contraseña por defecto solo para desarrollo
			log.Println("Advertencia: Usando contraseña de administrador por defecto. Defina ADMIN_INITIAL_PASSWORD para mayor seguridad.")
		}

		admin := models.User{
			Username: "admin",
			Email:    "admin@example.com",
			Role:     "admin",
			Active:   true,
		}

		// Registrar al admin
		_, err := service.RegisterUser(ctx, &admin, adminPassword)
		if err != nil {
			log.Printf("Error al crear usuario administrador inicial: %v", err)
			return
		}

		log.Println("Usuario administrador inicial creado correctamente")
	}
}
