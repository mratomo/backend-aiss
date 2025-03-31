package config

import (
	"errors"
	"os"
	"strings"

	"github.com/spf13/viper"
)

// Config estructura para la configuración del API Gateway
type Config struct {
	Port               string
	Environment        string
	CorsAllowedOrigins []string
	Services           ServiceEndpoints
	AuthSecret         string
	JWTExpirationHours int
}

// ServiceEndpoints contiene las URLs de los servicios internos
type ServiceEndpoints struct {
	UserService      string
	DocumentService  string
	ContextService   string
	EmbeddingService string
	RagAgent         string
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
	viper.SetDefault("port", "8080")
	viper.SetDefault("environment", "development")
	// Configuración más segura para CORS - en producción debería ser más restrictiva
	viper.SetDefault("corsAllowedOrigins", []string{"http://localhost:3000", "https://app.domain.com"})
	viper.SetDefault("jwtExpirationHours", 24)

	// Servicios
	viper.SetDefault("services.userService", "http://user-service:8081")
	viper.SetDefault("services.documentService", "http://document-service:8082")
	viper.SetDefault("services.contextService", "http://context-service:8083")
	viper.SetDefault("services.embeddingService", "http://embedding-service:8084")
	viper.SetDefault("services.ragAgent", "http://rag-agent:8085")

	// Intentar leer el archivo
	if err := viper.ReadInConfig(); err != nil {
		// Si el archivo no existe, intentamos usar variables de entorno
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, err
		}
	}

	// Verificar secreto de autorización
	authSecret := viper.GetString("authSecret")
	if authSecret == "" {
		authSecret = os.Getenv("AUTH_SECRET")
		if authSecret == "" {
			return nil, errors.New("la clave de autenticación no está configurada (AUTH_SECRET)")
		}
		viper.Set("authSecret", authSecret)
	}

	// Crear y devolver la configuración
	return &Config{
		Port:               viper.GetString("port"),
		Environment:        viper.GetString("environment"),
		CorsAllowedOrigins: viper.GetStringSlice("corsAllowedOrigins"),
		AuthSecret:         viper.GetString("authSecret"),
		JWTExpirationHours: viper.GetInt("jwtExpirationHours"),
		Services: ServiceEndpoints{
			UserService:      viper.GetString("services.userService"),
			DocumentService:  viper.GetString("services.documentService"),
			ContextService:   viper.GetString("services.contextService"),
			EmbeddingService: viper.GetString("services.embeddingService"),
			RagAgent:         viper.GetString("services.ragAgent"),
		},
	}, nil
}
