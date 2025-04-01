package config

import (
	"fmt"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

// Config represents the server configuration
type Config struct {
	Server struct {
		Port             int           `json:"port"`
		Host             string        `json:"host"`
		Timeout          time.Duration `json:"timeout"`
		CORSAllowOrigin  string        `json:"cors_allow_origin"`
		CORSAllowMethods string        `json:"cors_allow_methods"`
		MaxSessions      int           `json:"max_sessions"`
	}
	Auth struct {
		JWTSecret      string        `json:"jwt_secret"`
		JWTExpiryHours int           `json:"jwt_expiry_hours"`
		JWTIssuer      string        `json:"jwt_issuer"`
		TokenTimeout   time.Duration `json:"token_timeout"`
	}
	SSH struct {
		KeyDir     string        `json:"key_dir"`
		Timeout    time.Duration `json:"timeout"`
		KeepAlive  time.Duration `json:"keep_alive"`
		DefaultKey string        `json:"default_key"`
	}
	Services struct {
		SessionServiceURL        string        `json:"session_service_url"`
		SessionServiceTimeout    time.Duration `json:"session_service_timeout"`
		ContextAggregatorURL     string        `json:"context_aggregator_url"`
		ContextAggregatorTimeout time.Duration `json:"context_aggregator_timeout"`
		SuggestionServiceURL     string        `json:"suggestion_service_url"`
		SuggestionServiceTimeout time.Duration `json:"suggestion_service_timeout"`
		RAGAgentURL              string        `json:"rag_agent_url"`
		RAGAgentTimeout          time.Duration `json:"rag_agent_timeout"`
	}
	Retry struct {
		MaxRetries  int           `json:"max_retries"`
		InitialWait time.Duration `json:"initial_wait"`
		MaxWait     time.Duration `json:"max_wait"`
	}
}

// LoadConfig loads the configuration from environment variables
func LoadConfig() (*Config, error) {
	// Load .env file if it exists
	_ = godotenv.Load()

	// Create default config
	var config Config

	// Server configuration
	config.Server.Port = getEnvAsInt("SERVER_PORT", 8080)
	config.Server.Host = getEnv("SERVER_HOST", "")
	config.Server.Timeout = getEnvAsDuration("SERVER_TIMEOUT", 30*time.Second)
	config.Server.CORSAllowOrigin = getEnv("CORS_ALLOW_ORIGIN", "*")
	config.Server.CORSAllowMethods = getEnv("CORS_ALLOW_METHODS", "GET,POST,PUT,DELETE,OPTIONS")
	config.Server.MaxSessions = getEnvAsInt("MAX_SESSIONS", 100)

	// Auth configuration
	// SECURITY RISK: Default JWT secret should never be used in production
	jwtSecret := getEnv("JWT_SECRET", "")
	if jwtSecret == "" {
		return nil, fmt.Errorf("JWT_SECRET environment variable is required")
	}
	config.Auth.JWTSecret = jwtSecret
	config.Auth.JWTExpiryHours = getEnvAsInt("JWT_EXPIRY_HOURS", 24)
	config.Auth.JWTIssuer = getEnv("JWT_ISSUER", "terminal-gateway-service")
	config.Auth.TokenTimeout = getEnvAsDuration("TOKEN_TIMEOUT", 5*time.Minute)

	// SSH configuration
	config.SSH.KeyDir = getEnv("SSH_KEY_DIR", "/app/keys")
	config.SSH.Timeout = getEnvAsDuration("SSH_TIMEOUT", 10*time.Second)
	config.SSH.KeepAlive = getEnvAsDuration("SSH_KEEP_ALIVE", 30*time.Second)
	config.SSH.DefaultKey = getEnv("SSH_DEFAULT_KEY", "")

	// Services configuration
	config.Services.SessionServiceURL = getEnv("SESSION_SERVICE_URL", "http://terminal-session-service:8080")
	config.Services.SessionServiceTimeout = getEnvAsDuration("SESSION_SERVICE_TIMEOUT", 5*time.Second)
	config.Services.ContextAggregatorURL = getEnv("CONTEXT_AGGREGATOR_URL", "http://terminal-context-aggregator:8000")
	config.Services.ContextAggregatorTimeout = getEnvAsDuration("CONTEXT_AGGREGATOR_TIMEOUT", 5*time.Second)
	config.Services.SuggestionServiceURL = getEnv("SUGGESTION_SERVICE_URL", "http://terminal-suggestion-service:8000")
	config.Services.SuggestionServiceTimeout = getEnvAsDuration("SUGGESTION_SERVICE_TIMEOUT", 5*time.Second)
	config.Services.RAGAgentURL = getEnv("RAG_AGENT_URL", "http://rag-agent:8000")
	config.Services.RAGAgentTimeout = getEnvAsDuration("RAG_AGENT_TIMEOUT", 30*time.Second)

	// Retry configuration
	config.Retry.MaxRetries = getEnvAsInt("RETRY_MAX_RETRIES", 3)
	config.Retry.InitialWait = getEnvAsDuration("RETRY_INITIAL_WAIT", 100*time.Millisecond)
	config.Retry.MaxWait = getEnvAsDuration("RETRY_MAX_WAIT", 2*time.Second)

	// Validate configuration
	if err := validateConfig(&config); err != nil {
		return nil, err
	}

	return &config, nil
}

// validateConfig validates the configuration
func validateConfig(config *Config) error {
	// Server validation
	if config.Server.Port < 1 || config.Server.Port > 65535 {
		return fmt.Errorf("invalid server port: %d, must be between 1 and 65535", config.Server.Port)
	}

	// Auth validation
	if config.Auth.JWTSecret == "" {
		return fmt.Errorf("JWT secret cannot be empty")
	}

	// Add more validation as needed

	return nil
}

// Helper functions for environment variables
func getEnv(key, defaultValue string) string {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}
	return value
}

func getEnvAsInt(key string, defaultValue int) int {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}

	intValue, err := strconv.Atoi(value)
	if err != nil {
		return defaultValue
	}

	return intValue
}

func getEnvAsDuration(key string, defaultValue time.Duration) time.Duration {
	value := os.Getenv(key)
	if value == "" {
		return defaultValue
	}

	// Try to parse as duration string (e.g. "5s", "10m")
	dur, err := time.ParseDuration(value)
	if err == nil {
		return dur
	}

	// Try to parse as seconds
	intValue, err := strconv.Atoi(value)
	if err != nil {
		return defaultValue
	}

	return time.Duration(intValue) * time.Second
}

// IsDevMode returns true if the app is running in development mode
func IsDevMode() bool {
	return strings.ToLower(getEnv("ENV", "development")) == "development"
}

// IsTestMode returns true if the app is running in test mode
func IsTestMode() bool {
	return strings.ToLower(getEnv("ENV", "")) == "test"
}
