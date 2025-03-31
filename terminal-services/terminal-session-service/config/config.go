package config

import (
	"fmt"
	"log"
	"time"

	"github.com/spf13/viper"
)

// Config stores all configuration for the service
type Config struct {
	Server    ServerConfig
	Auth      AuthConfig
	Database  DatabaseConfig
	Services  ServicesConfig
	Logging   LoggingConfig
	Retention RetentionConfig
}

// ServerConfig stores HTTP server configuration
type ServerConfig struct {
	Port            int
	Host            string
	ReadTimeout     time.Duration
	WriteTimeout    time.Duration
	GracefulTimeout time.Duration
	CORSAllowOrigin string
}

// AuthConfig stores authentication configuration
type AuthConfig struct {
	JWTSecret      string
	JWTExpiryHours int
	JWTIssuer      string
}

// DatabaseConfig stores database configuration
type DatabaseConfig struct {
	URI      string
	Database string
	Timeout  time.Duration
}

// ServicesConfig stores URLs for other services
type ServicesConfig struct {
	ContextAggregatorURL   string
	SuggestionServiceURL   string
}

// LoggingConfig stores logging configuration
type LoggingConfig struct {
	Level string
	File  string
}

// RetentionConfig stores data retention configuration
type RetentionConfig struct {
	SessionDays     int
	CommandDays     int
	HistoryMaxItems int
}

// Load reads configuration from environment variables or config file
func Load() (*Config, error) {
	viper.SetDefault("SERVER.PORT", 8091)
	viper.SetDefault("SERVER.HOST", "0.0.0.0")
	viper.SetDefault("SERVER.READ_TIMEOUT", "15s")
	viper.SetDefault("SERVER.WRITE_TIMEOUT", "15s")
	viper.SetDefault("SERVER.GRACEFUL_TIMEOUT", "15s")
	viper.SetDefault("SERVER.CORS_ALLOW_ORIGIN", "*")

	viper.SetDefault("DATABASE.URI", "mongodb://mongodb:27017")
	viper.SetDefault("DATABASE.DATABASE", "terminal_sessions")
	viper.SetDefault("DATABASE.TIMEOUT", "10s")

	viper.SetDefault("SERVICES.CONTEXT_AGGREGATOR_URL", "http://terminal-context-aggregator:8092")
	viper.SetDefault("SERVICES.SUGGESTION_SERVICE_URL", "http://terminal-suggestion-service:8093")

	viper.SetDefault("LOGGING.LEVEL", "info")
	viper.SetDefault("LOGGING.FILE", "")

	viper.SetDefault("RETENTION.SESSION_DAYS", 30)
	viper.SetDefault("RETENTION.COMMAND_DAYS", 90)
	viper.SetDefault("RETENTION.HISTORY_MAX_ITEMS", 1000)

	viper.SetConfigName("config")
	viper.SetConfigType("yaml")
	viper.AddConfigPath(".")
	viper.AddConfigPath("/config")
	viper.AddConfigPath("$HOME/.terminal-session")
	viper.AutomaticEnv()

	readTimeout, err := time.ParseDuration(viper.GetString("SERVER.READ_TIMEOUT"))
	if err != nil {
		return nil, fmt.Errorf("invalid SERVER.READ_TIMEOUT: %w", err)
	}

	writeTimeout, err := time.ParseDuration(viper.GetString("SERVER.WRITE_TIMEOUT"))
	if err != nil {
		return nil, fmt.Errorf("invalid SERVER.WRITE_TIMEOUT: %w", err)
	}

	gracefulTimeout, err := time.ParseDuration(viper.GetString("SERVER.GRACEFUL_TIMEOUT"))
	if err != nil {
		return nil, fmt.Errorf("invalid SERVER.GRACEFUL_TIMEOUT: %w", err)
	}

	dbTimeout, err := time.ParseDuration(viper.GetString("DATABASE.TIMEOUT"))
	if err != nil {
		return nil, fmt.Errorf("invalid DATABASE.TIMEOUT: %w", err)
	}

	jwtSecret := viper.GetString("AUTH.JWT_SECRET")
	if jwtSecret == "" {
		log.Println("WARNING: AUTH.JWT_SECRET not set, using default (insecure) value")
		jwtSecret = "default-insecure-jwt-secret-do-not-use-in-production"
	}

	config := &Config{
		Server: ServerConfig{
			Port:            viper.GetInt("SERVER.PORT"),
			Host:            viper.GetString("SERVER.HOST"),
			ReadTimeout:     readTimeout,
			WriteTimeout:    writeTimeout,
			GracefulTimeout: gracefulTimeout,
			CORSAllowOrigin: viper.GetString("SERVER.CORS_ALLOW_ORIGIN"),
		},
		Auth: AuthConfig{
			JWTSecret:      jwtSecret,
			JWTExpiryHours: viper.GetInt("AUTH.JWT_EXPIRY_HOURS"),
			JWTIssuer:      viper.GetString("AUTH.JWT_ISSUER"),
		},
		Database: DatabaseConfig{
			URI:      viper.GetString("DATABASE.URI"),
			Database: viper.GetString("DATABASE.DATABASE"),
			Timeout:  dbTimeout,
		},
		Services: ServicesConfig{
			ContextAggregatorURL:   viper.GetString("SERVICES.CONTEXT_AGGREGATOR_URL"),
			SuggestionServiceURL:   viper.GetString("SERVICES.SUGGESTION_SERVICE_URL"),
		},
		Logging: LoggingConfig{
			Level: viper.GetString("LOGGING.LEVEL"),
			File:  viper.GetString("LOGGING.FILE"),
		},
		Retention: RetentionConfig{
			SessionDays:     viper.GetInt("RETENTION.SESSION_DAYS"),
			CommandDays:     viper.GetInt("RETENTION.COMMAND_DAYS"),
			HistoryMaxItems: viper.GetInt("RETENTION.HISTORY_MAX_ITEMS"),
		},
	}

	// Try to read from config file (optional)
	if err := viper.ReadInConfig(); err != nil {
		if _, ok := err.(viper.ConfigFileNotFoundError); !ok {
			log.Printf("Warning: error reading config file: %v", err)
		}
	}

	return config, nil
}