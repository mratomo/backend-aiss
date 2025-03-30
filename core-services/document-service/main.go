package main

import (
	"context"
	"document-service/config"
	"document-service/controllers"
	"document-service/repositories"
	"document-service/services"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"syscall"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/minio/minio-go/v7"
	"github.com/minio/minio-go/v7/pkg/credentials"
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

	// Conectar a MinIO
	minioClient, err := minio.New(cfg.MinIO.Endpoint, &minio.Options{
		Creds:  credentials.NewStaticV4(cfg.MinIO.AccessKey, cfg.MinIO.SecretKey, ""),
		Secure: cfg.MinIO.UseSSL,
	})
	if err != nil {
		log.Fatalf("Error al conectar a MinIO: %v", err)
	}

	// Verificar si los buckets existen, si no, crearlos
	buckets := []string{cfg.MinIO.SharedBucket, cfg.MinIO.PersonalBucket}
	for _, bucket := range buckets {
		exists, err := minioClient.BucketExists(ctx, bucket)
		if err != nil {
			log.Fatalf("Error al verificar bucket %s: %v", bucket, err)
		}

		if !exists {
			err = minioClient.MakeBucket(ctx, bucket, minio.MakeBucketOptions{})
			if err != nil {
				log.Fatalf("Error al crear bucket %s: %v", bucket, err)
			}
			log.Printf("Bucket %s creado con éxito", bucket)
		}
	}

	log.Println("Conexión a MinIO establecida")

	// Inicializar repositorio, servicio y controlador
	docCollection := client.Database(cfg.MongoDB.Database).Collection("documents")
	repo := repositories.NewDocumentRepository(docCollection, minioClient, cfg.MinIO)

	// Inicializar cliente HTTP para comunicación con servicio de embeddings
	httpClient := &http.Client{
		Timeout: time.Second * 30,
	}

	docService := services.NewDocumentService(repo, httpClient, cfg.EmbeddingService.URL)
	controller := controllers.NewDocumentController(docService)

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

	// Rutas de documentos personales
	router.GET("/personal", controller.ListPersonalDocuments)
	router.POST("/personal", controller.UploadPersonalDocument)
	router.GET("/personal/:id", controller.GetPersonalDocument)
	router.GET("/personal/:id/content", controller.GetPersonalDocumentContent)
	router.DELETE("/personal/:id", controller.DeletePersonalDocument)

	// Rutas de documentos compartidos
	router.GET("/shared", controller.ListSharedDocuments)
	router.POST("/shared", controller.UploadSharedDocument)
	router.GET("/shared/:id", controller.GetSharedDocument)
	router.GET("/shared/:id/content", controller.GetSharedDocumentContent)
	router.PUT("/shared/:id", controller.UpdateSharedDocument)
	router.DELETE("/shared/:id", controller.DeleteSharedDocument)

	// Rutas para búsqueda
	router.GET("/search", controller.SearchDocuments)

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
