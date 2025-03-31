package middleware

import (
	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"strings"
	"time"
)

// CORS returns a CORS middleware
func CORS(allowOrigin string) gin.HandlerFunc {
	// Parse allow origin string
	var allowOrigins []string
	if allowOrigin == "*" {
		allowOrigins = []string{"*"}
	} else {
		allowOrigins = strings.Split(allowOrigin, ",")
		for i, origin := range allowOrigins {
			allowOrigins[i] = strings.TrimSpace(origin)
		}
	}

	// Create CORS configuration
	config := cors.Config{
		AllowOrigins:     allowOrigins,
		AllowMethods:     []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept", "Authorization", "X-Requested-With"},
		ExposeHeaders:    []string{"Content-Length"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}

	return cors.New(config)
}