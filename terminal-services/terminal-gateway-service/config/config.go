package config

import (
	"fmt"
	"log"
	"time"

	"github.com/spf13/viper"
)

// Config stores all configuration for the service
type Config struct {
	Server   ServerConfig
	Auth     AuthConfig
	SSH      SSHConfig
	Services ServicesConfig
	Logging  LoggingConfig
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

// SSHConfig stores SSH client configuration
type SSHConfig struct {
	DefaultTimeout time.Duration
	KeepAlive      time.Duration
	KeyDir         string
	KnownHostsFile string
	MaxSessions    int
}

// ServicesConfig stores URLs for other services
type ServicesConfig struct {
	SessionServiceURL      string
	ContextAggregatorURL   string
	SuggestionServiceURL   string
}

// LoggingConfig stores logging configuration
type LoggingConfig struct {
	Level string
	File  string
}

// Load reads configuration from environment variables or config file
func Load() (*Config, error) {
	viper.SetDefault("SERVER.PORT", 8090)
	viper.SetDefault("SERVER.HOST", "0.0.0.0")
	viper.SetDefault("SERVER.READ_TIMEOUT", "15s")
	viper.SetDefault("SERVER.WRITE_TIMEOUT", "15s")
	viper.SetDefault("SERVER.GRACEFUL_TIMEOUT", "15s")
	viper.SetDefault("SERVER.CORS_ALLOW_ORIGIN", "*")

	viper.SetDefault("SSH.DEFAULT_TIMEOUT", "30s")
	viper.SetDefault("SSH.KEEP_ALIVE", "30s")
	viper.SetDefault("SSH.KEY_DIR", "/app/keys")
	viper.SetDefault("SSH.KNOWN_HOSTS_FILE", "/app/known_hosts")
	viper.SetDefault("SSH.MAX_SESSIONS", 50)

	viper.SetDefault("SERVICES.SESSION_SERVICE_URL", "http://terminal-session-service:8091")
	viper.SetDefault("SERVICES.CONTEXT_AGGREGATOR_URL", "http://terminal-context-aggregator:8092")
	viper.SetDefault("SERVICES.SUGGESTION_SERVICE_URL", "http://terminal-suggestion-service:8093")

	viper.SetDefault("LOGGING.LEVEL", "info")
	viper.SetDefault("LOGGING.FILE", "")

	viper.SetConfigName("config")
	viper.SetConfigType("yaml")
	viper.AddConfigPath(".")
	viper.AddConfigPath("/config")
	viper.AddConfigPath("$HOME/.terminal-gateway")
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

	sshTimeout, err := time.ParseDuration(viper.GetString("SSH.DEFAULT_TIMEOUT"))
	if err != nil {
		return nil, fmt.Errorf("invalid SSH.DEFAULT_TIMEOUT: %w", err)
	}

	sshKeepAlive, err := time.ParseDuration(viper.GetString("SSH.KEEP_ALIVE"))
	if err != nil {
		return nil, fmt.Errorf("invalid SSH.KEEP_ALIVE: %w", err)
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
		SSH: SSHConfig{
			DefaultTimeout: sshTimeout,
			KeepAlive:      sshKeepAlive,
			KeyDir:         viper.GetString("SSH.KEY_DIR"),
			KnownHostsFile: viper.GetString("SSH.KNOWN_HOSTS_FILE"),
			MaxSessions:    viper.GetInt("SSH.MAX_SESSIONS"),
		},
		Services: ServicesConfig{
			SessionServiceURL:      viper.GetString("SERVICES.SESSION_SERVICE_URL"),
			ContextAggregatorURL:   viper.GetString("SERVICES.CONTEXT_AGGREGATOR_URL"),
			SuggestionServiceURL:   viper.GetString("SERVICES.SUGGESTION_SERVICE_URL"),
		},
		Logging: LoggingConfig{
			Level: viper.GetString("LOGGING.LEVEL"),
			File:  viper.GetString("LOGGING.FILE"),
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