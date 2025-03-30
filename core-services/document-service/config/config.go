package config

import (
	"errors"
	"os"
	"strings"

	"github.com/spf13/viper"
)

// Config estructura para la configuración del servicio de documentos
type Config struct {
	Port               string
	Environment        string
	CorsAllowedOrigins []string
	MongoDB            MongoDBConfig
	MinIO              MinIOConfig
	EmbeddingService   EmbeddingServiceConfig
}

// MongoDBConfig configuración para MongoDB
type MongoDBConfig struct {
	URI      string
	Database string
}

// MinIOConfig configuración para MinIO
type MinIOConfig struct {
	Endpoint       string
	AccessKey      string
	SecretKey      string
	UseSSL         bool
	SharedBucket   string
	PersonalBucket string
}

// EmbeddingServiceConfig configuración para el servicio de embeddings
type EmbeddingServiceConfig struct {
	URL string
}

// LoadConfig carga la configuración desde archivo o variables de entorno
func LoadConfig() (*Config, error) {
	// Configurar Viper
	viper.SetConfigName("config")
	viper.SetConfigType("yaml")
	viper.AddConfigPath("./config")
	viper.AddConfigPath(".")

	// Variables de entorno
	viper.AutomaticEnv()
	viper.SetEnvKeyReplacer(strings.NewReplacer(".", "_"))

	// Valores por defecto
	viper.SetDefault("port", "8082")
	viper.SetDefault("environment", "development")
	viper.SetDefault("corsAllowedOrigins", []string{"*"})

	// MongoDB - corregido
	viper.SetDefault("mongodb.uri", "mongodb://localhost:27017")
	viper.SetDefault("mongodb.database", "mcp_knowledge_system")

	// MinIO - corregido
	viper.SetDefault("minio.endpoint", "localhost:9000")
	viper.SetDefault("minio.useSSL", false)
	viper.SetDefault("minio.sharedBucket", "shared-documents")
	viper.SetDefault("minio.personalBucket", "personal-documents")

	// Servicio de embeddings
	viper.SetDefault("embeddingService.url", "http://embedding-service:8084")

	// Intentar leer el archivo
	if err := viper.ReadInConfig(); err != nil {
		// Si el archivo no existe, intentamos usar variables de entorno
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, err
		}
	}

	// MinIO access key y secret key tienen que estar disponibles
	minioAccessKey := viper.GetString("minio.accessKey")
	if minioAccessKey == "" {
		minioAccessKey = os.Getenv("MINIO_ACCESS_KEY")
		if minioAccessKey == "" {
			return nil, errors.New("MINIO_ACCESS_KEY no está configurado")
		}
		viper.Set("minio.accessKey", minioAccessKey)
	}

	minioSecretKey := viper.GetString("minio.secretKey")
	if minioSecretKey == "" {
		minioSecretKey = os.Getenv("MINIO_SECRET_KEY")
		if minioSecretKey == "" {
			return nil, errors.New("MINIO_SECRET_KEY no está configurado")
		}
		viper.Set("minio.secretKey", minioSecretKey)
	}

	// Crear y devolver la configuración
	return &Config{
		Port:               viper.GetString("port"),
		Environment:        viper.GetString("environment"),
		CorsAllowedOrigins: viper.GetStringSlice("corsAllowedOrigins"),
		MongoDB: MongoDBConfig{
			URI:      viper.GetString("mongodb.uri"),
			Database: viper.GetString("mongodb.database"),
		},
		MinIO: MinIOConfig{
			Endpoint:       viper.GetString("minio.endpoint"),
			AccessKey:      viper.GetString("minio.accessKey"),
			SecretKey:      viper.GetString("minio.secretKey"),
			UseSSL:         viper.GetBool("minio.useSSL"),
			SharedBucket:   viper.GetString("minio.sharedBucket"),
			PersonalBucket: viper.GetString("minio.personalBucket"),
		},
		EmbeddingService: EmbeddingServiceConfig{
			URL: viper.GetString("embeddingService.url"),
		},
	}, nil
}
