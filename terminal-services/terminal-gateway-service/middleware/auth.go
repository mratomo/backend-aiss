package middleware

import (
	"errors"
	"fmt"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v4"
)

// JWTConfig stores configuration for JWT authentication
type JWTConfig struct {
	Secret      string
	ExpiryHours int
	Issuer      string
}

// JWTClaims represents JWT claims for authentication
type JWTClaims struct {
	UserID string `json:"user_id"`
	Role   string `json:"role"`
	jwt.RegisteredClaims
}

// AuthRequired is a middleware that checks for a valid JWT token
func AuthRequired(config JWTConfig) gin.HandlerFunc {
	return func(c *gin.Context) {
		// Validate config
		if config.Secret == "" {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "JWT configuration error"})
			c.Abort()
			return
		}

		// Get token from Authorization header
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Authorization header required"})
			c.Abort()
			return
		}

		// Check if the header has the Bearer prefix
		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Authorization header must be in the format 'Bearer {token}'"})
			c.Abort()
			return
		}

		tokenString := parts[1]

		// Parse and validate the token
		token, err := jwt.ParseWithClaims(tokenString, &JWTClaims{}, func(token *jwt.Token) (interface{}, error) {
			// Validate the signing method explicitly (only accept HS256)
			if token.Method.Alg() != jwt.SigningMethodHS256.Alg() {
				return nil, fmt.Errorf("unexpected signing method: %v", token.Header["alg"])
			}
			return []byte(config.Secret), nil
		})

		if err != nil {
			var validationError *jwt.ValidationError
			if errors.As(err, &validationError) {
				if validationError.Errors&jwt.ValidationErrorExpired != 0 {
					c.JSON(http.StatusUnauthorized, gin.H{"error": "Token has expired"})
				} else {
					c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid token: " + err.Error()})
				}
			} else {
				c.JSON(http.StatusUnauthorized, gin.H{"error": "Token validation error: " + err.Error()})
			}
			c.Abort()
			return
		}

		// Check if the token is valid
		if !token.Valid {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid token"})
			c.Abort()
			return
		}

		// Get claims
		claims, ok := token.Claims.(*JWTClaims)
		if !ok {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Invalid token claims format"})
			c.Abort()
			return
		}

		// Check token expiration
		if claims.ExpiresAt == nil || claims.ExpiresAt.Before(time.Now()) {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "Token has expired"})
			c.Abort()
			return
		}

		// Add user ID and role to context
		c.Set("userID", claims.UserID)
		c.Set("userRole", claims.Role)
		c.Set("isAdmin", claims.Role == "admin")

		c.Next()
	}
}

// AdminRequired is a middleware that checks if the user is an admin
func AdminRequired() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Check if the user is an admin
		isAdmin, exists := c.Get("isAdmin")
		if !exists {
			c.JSON(http.StatusForbidden, gin.H{"error": "Admin status not found in context"})
			c.Abort()
			return
		}

		isAdminValue, ok := isAdmin.(bool)
		if !ok || !isAdminValue {
			c.JSON(http.StatusForbidden, gin.H{"error": "Admin privileges required"})
			c.Abort()
			return
		}

		c.Next()
	}
}

// GenerateToken generates a new JWT token
func GenerateToken(userID, role string, config JWTConfig) (string, error) {
	if userID == "" {
		return "", errors.New("user ID is required")
	}

	if role == "" {
		return "", errors.New("role is required")
	}

	if config.Secret == "" {
		return "", errors.New("JWT secret is required")
	}

	// Set expiration time
	expirationTime := time.Now().Add(time.Duration(config.ExpiryHours) * time.Hour)

	// Create claims
	claims := &JWTClaims{
		UserID: userID,
		Role:   role,
		RegisteredClaims: jwt.RegisteredClaims{
			ExpiresAt: jwt.NewNumericDate(expirationTime),
			IssuedAt:  jwt.NewNumericDate(time.Now()),
			NotBefore: jwt.NewNumericDate(time.Now()),
			Issuer:    config.Issuer,
		},
	}

	// Create token with explicit algorithm
	token := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)

	// Sign token
	tokenString, err := token.SignedString([]byte(config.Secret))
	if err != nil {
		return "", err
	}

	return tokenString, nil
}
