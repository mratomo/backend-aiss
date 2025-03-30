package config

import (
	"errors"
	"os"
	"strings"

	"github.com/spf13/viper"
)

// Config estructura para la configuración del servicio de usuarios
type Config struct {
	Port               string
	Environment        string
	CorsAllowedOrigins []string
	MongoDB            MongoDBConfig
	Auth               AuthConfig
}

// MongoDBConfig configuración para MongoDB
type MongoDBConfig struct {
	URI      string
	Database string
}

// AuthConfig configuración para autenticación
type AuthConfig struct {
	Secret          string
	ExpirationHours int
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
	viper.SetDefault("port", "8081")
	viper.SetDefault("environment", "development")
	viper.SetDefault("corsAllowedOrigins", []string{"*"})

	// MongoDB - CORREGIDO
	viper.SetDefault("mongodb.uri", "mongodb://localhost:27017")
	viper.SetDefault("mongodb.database", "mcp_knowledge_system")

	// Auth
	viper.SetDefault("auth.expirationHours", 24)

	// Intentar leer el archivo
	if err := viper.ReadInConfig(); err != nil {
		// Si el archivo no existe, intentamos usar variables de entorno
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			return nil, err
		}
	}

	// Verificar secret de autenticación
	authSecret := viper.GetString("auth.secret")
	if authSecret == "" {
		authSecret = os.Getenv("AUTH_SECRET")
		if authSecret == "" {
			return nil, errors.New("AUTH_SECRET no está configurado")
		}
		viper.Set("auth.secret", authSecret)
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
		Auth: AuthConfig{
			Secret:          viper.GetString("auth.secret"),
			ExpirationHours: viper.GetInt("auth.expirationHours"),
		},
	}, nil
}
