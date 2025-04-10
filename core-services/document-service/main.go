package main

import (
	"context"
	"document-service/config"
	"document-service/controllers"
	"document-service/repositories"
	"document-service/services"
	"errors"
	"fmt"
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

	// Conectar a MongoDB con reintentos
	var client *mongo.Client
	var mongoCtx context.Context
	var mongoCancel context.CancelFunc
	
	// Función para intentar conexión a MongoDB
	connectMongoDB := func() (*mongo.Client, error) {
		mongoCtx, mongoCancel = context.WithTimeout(context.Background(), 15*time.Second)
		return mongo.Connect(mongoCtx, options.Client().ApplyURI(cfg.MongoDB.URI))
	}
	
	// Intentar conexión a MongoDB con reintentos
	maxRetries := 6
	retryInterval := 5 * time.Second
	
	for i := 0; i < maxRetries; i++ {
		log.Printf("Intentando conectar a MongoDB, intento %d/%d", i+1, maxRetries)
		
		client, err = connectMongoDB()
		if err == nil {
			// Intentar ping
			pingCtx, pingCancel := context.WithTimeout(context.Background(), 5*time.Second)
			defer pingCancel()
			
			err = client.Ping(pingCtx, nil)
			if err == nil {
				// Conexión exitosa
				log.Println("Conexión a MongoDB establecida")
				break
			}
			
			// Si hay error en ping, cerrar el cliente y reintentar
			closeCtx, closeCancel := context.WithTimeout(context.Background(), 5*time.Second)
			_ = client.Disconnect(closeCtx)
			closeCancel()
		}
		
		if i+1 < maxRetries {
			log.Printf("Error al conectar a MongoDB: %v. Reintentando en %v...", err, retryInterval)
			time.Sleep(retryInterval)
		} else {
			// Último intento fallido
			mongoCancel()
			log.Fatalf("Error al conectar a MongoDB después de %d intentos: %v", maxRetries, err)
		}
	}

	// Configurar cierre de conexión al finalizar
	defer func() {
		mongoCancel()
		disconnectCtx, disconnectCancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer disconnectCancel()
		if client != nil {
			if err := client.Disconnect(disconnectCtx); err != nil {
				log.Printf("Error al desconectar de MongoDB: %v", err)
			}
		}
	}()

	// Conectar a MinIO con reintentos
	var minioClient *minio.Client
	maxMinioRetries := 6
	minioRetryInterval := 10 * time.Second
	
	log.Printf("Intentando conectar a MinIO en %s", cfg.MinIO.Endpoint)
	
	for i := 0; i < maxMinioRetries; i++ {
		log.Printf("Intentando conectar a MinIO, intento %d/%d", i+1, maxMinioRetries)
		
		// Crear cliente MinIO
		minioClient, err = minio.New(cfg.MinIO.Endpoint, &minio.Options{
			Creds:  credentials.NewStaticV4(cfg.MinIO.AccessKey, cfg.MinIO.SecretKey, ""),
			Secure: cfg.MinIO.UseSSL,
		})
		
		if err == nil {
			// Verificar conexión con una operación
			_, err = minioClient.ListBuckets(context.Background())
			if err == nil {
				log.Println("Conexión a MinIO establecida")
				break
			}
		}
		
		if i+1 < maxMinioRetries {
			log.Printf("Error al conectar a MinIO: %v. Reintentando en %v...", err, minioRetryInterval)
			time.Sleep(minioRetryInterval)
		} else {
			log.Fatalf("Error al conectar a MinIO después de %d intentos: %v", maxMinioRetries, err)
		}
	}
	
	// Verificar si los buckets existen, si no, esperar a que estén disponibles
	// Esto es porque el script init.sh podría estar creándolos al mismo tiempo
	buckets := []string{cfg.MinIO.SharedBucket, cfg.MinIO.PersonalBucket, "documents", "uploads", "temp"}
	bucketsCtx, bucketsCancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer bucketsCancel()
	
	log.Println("Verificando disponibilidad de buckets en MinIO...")
	
	for _, bucket := range buckets {
		verifySuccessful := false
		bucketCheckStart := time.Now()
		
		// Verificar con reintentos por si el bucket está siendo creado por el script init.sh
		for time.Since(bucketCheckStart) < 20*time.Second && !verifySuccessful {
			exists, err := minioClient.BucketExists(bucketsCtx, bucket)
			if err != nil {
				log.Printf("Error al verificar bucket %s: %v. Reintentando...", bucket, err)
				time.Sleep(2 * time.Second)
				continue
			}
			
			if exists {
				log.Printf("Bucket %s existe y está disponible", bucket)
				verifySuccessful = true
				break
			}
			
			// El bucket no existe, intentar crearlo
			log.Printf("Bucket %s no existe, intentando crear...", bucket)
			err = minioClient.MakeBucket(bucketsCtx, bucket, minio.MakeBucketOptions{})
			if err != nil {
				// Verifica si el error es porque el bucket ya fue creado (race condition)
				exists, checkErr := minioClient.BucketExists(bucketsCtx, bucket)
				if checkErr == nil && exists {
					log.Printf("Bucket %s ya existe (creado por otro proceso)", bucket)
					verifySuccessful = true
					break
				}
				
				log.Printf("Error al crear bucket %s: %v. Reintentando...", bucket, err)
				time.Sleep(2 * time.Second)
				continue
			}
			
			log.Printf("Bucket %s creado con éxito", bucket)
			verifySuccessful = true
		}
		
		if !verifySuccessful {
			log.Printf("Advertencia: No se pudo verificar/crear el bucket %s. El servicio intentará usar los buckets disponibles.", bucket)
		}
	}
	
	log.Println("Verificación de buckets MinIO completada")

	// Inicializar repositorio, servicio y controlador
	docCollection := client.Database(cfg.MongoDB.Database).Collection("documents")
	repo := repositories.NewDocumentRepository(docCollection, minioClient, cfg.MinIO)

	// Inicializar cliente HTTP para comunicación con servicio de embeddings
	httpClient := &http.Client{
		Timeout: time.Second * 30,
	}

	docService := services.NewDocumentService(repo, httpClient, cfg.EmbeddingService.URL)
	controller := controllers.NewDocumentController(docService)

	// Inicializar router con configuración para logs más detallados
	router := gin.New()
	router.Use(gin.Recovery())
	
	// Configurar logger personalizado
	router.Use(gin.LoggerWithFormatter(func(param gin.LogFormatterParams) string {
		// Formato personalizado para los logs
		return fmt.Sprintf("[%s] | %s | %s | %d | %s | %s | %s\n",
			param.TimeStamp.Format("2006/01/02 - 15:04:05"),
			param.ClientIP,
			param.Method,
			param.StatusCode,
			param.Latency,
			param.Path,
			param.ErrorMessage,
		)
	}))

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
		// Heath check mejorado
		status := http.StatusOK
		response := gin.H{
			"status":    "ok",
			"service":   "document-service",
			"version":   "1.1.0",
			"timestamp": time.Now().UTC().Format(time.RFC3339),
		}
		
		// Verificar conexión a MongoDB
		pingCtx, pingCancel := context.WithTimeout(context.Background(), 2*time.Second)
		defer pingCancel()
		err := client.Ping(pingCtx, nil)
		if err != nil {
			response["status"] = "degraded"
			response["mongodb"] = "error: " + err.Error()
			status = http.StatusServiceUnavailable
		} else {
			response["mongodb"] = "ok"
		}
		
		// Verificar conexión a MinIO
		_, minioErr := minioClient.ListBuckets(context.Background())
		if minioErr != nil {
			response["status"] = "degraded"
			response["minio"] = "error: " + minioErr.Error()
			status = http.StatusServiceUnavailable
		} else {
			response["minio"] = "ok"
		}
		
		c.JSON(status, response)
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
