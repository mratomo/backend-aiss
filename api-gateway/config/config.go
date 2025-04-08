package config

import (
	"errors"
	"fmt"
	"log"
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
	UserService            string
	DocumentService        string
	ContextService         string
	EmbeddingService       string
	RagAgent               string
	TerminalGatewayService string
	TerminalSessionService string
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
	// CORS configuración específica por ambiente
	viper.SetDefault("environments", map[string]interface{}{
		"development": map[string]interface{}{
			"corsAllowedOrigins": []string{"http://localhost:3000", "http://localhost:8000"},
		},
		"staging": map[string]interface{}{
			"corsAllowedOrigins": []string{"https://staging.app.domain.com"},
		},
		"production": map[string]interface{}{
			"corsAllowedOrigins": []string{"https://app.domain.com"},
		},
	})
	viper.SetDefault("jwtExpirationHours", 24)

	// Servicios
	viper.SetDefault("services.userService", "http://user-service:8081")
	viper.SetDefault("services.documentService", "http://document-service:8082")
	viper.SetDefault("services.contextService", "http://context-service:8083")
	viper.SetDefault("services.embeddingService", "http://embedding-service:8084")
	viper.SetDefault("services.ragAgent", "http://rag-agent:8085")
	viper.SetDefault("services.terminalGatewayService", "http://terminal-gateway-service:8086")
	viper.SetDefault("services.terminalSessionService", "http://terminal-session-service:8087")

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

	// Obtener el ambiente actual
	environment := viper.GetString("environment")

	// Obtener orígenes CORS permitidos según el ambiente
	var corsAllowedOrigins []string

	// Intentar obtener configuración de ambiente específico
	envSpecificConfig := viper.GetStringMap(fmt.Sprintf("environments.%s", environment))
	if envSpecificConfig != nil && envSpecificConfig["corsAllowedOrigins"] != nil {
		// Si hay configuración específica para este ambiente, usarla
		if origins, ok := envSpecificConfig["corsAllowedOrigins"].([]string); ok {
			corsAllowedOrigins = origins
		} else if originsList, ok := envSpecificConfig["corsAllowedOrigins"].([]interface{}); ok {
			// Convertir de []interface{} a []string
			for _, origin := range originsList {
				if str, ok := origin.(string); ok {
					corsAllowedOrigins = append(corsAllowedOrigins, str)
				}
			}
		}
	}

	// Si no se encontró configuración específica, usar valor por defecto
	if len(corsAllowedOrigins) == 0 {
		corsAllowedOrigins = viper.GetStringSlice("corsAllowedOrigins")
		if len(corsAllowedOrigins) == 0 && environment == "production" {
			// En producción, si no hay configuración, ser más restrictivo
			corsAllowedOrigins = []string{"https://app.domain.com"}
		} else if len(corsAllowedOrigins) == 0 {
			// En otros ambientes, permitir localhost por defecto
			corsAllowedOrigins = []string{"http://localhost:3000"}
		}
	}

	// Log para seguridad - importante saber qué orígenes se están permitiendo
	log.Printf("CORS allowed origins for %s environment: %v", environment, corsAllowedOrigins)

	// Crear y devolver la configuración
	return &Config{
		Port:               viper.GetString("port"),
		Environment:        environment,
		CorsAllowedOrigins: corsAllowedOrigins,
		AuthSecret:         viper.GetString("authSecret"),
		JWTExpirationHours: viper.GetInt("jwtExpirationHours"),
		Services: ServiceEndpoints{
			UserService:            viper.GetString("services.userService"),
			DocumentService:        viper.GetString("services.documentService"),
			ContextService:         viper.GetString("services.contextService"),
			EmbeddingService:       viper.GetString("services.embeddingService"),
			RagAgent:               viper.GetString("services.ragAgent"),
			TerminalGatewayService: viper.GetString("services.terminalGatewayService"),
			TerminalSessionService: viper.GetString("services.terminalSessionService"),
		},
	}, nil
}
