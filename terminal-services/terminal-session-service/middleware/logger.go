package middleware

import (
	"fmt"
	"time"

	"github.com/gin-gonic/gin"
)

// Logger is a middleware that logs request details
func Logger() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Start timer
		start := time.Now()
		path := c.Request.URL.Path
		raw := c.Request.URL.RawQuery

		// Process request
		c.Next()

		// Log details after request is processed
		if raw != "" {
			path = path + "?" + raw
		}

		// Calculate latency
		latency := time.Since(start)

		// Get client IP
		clientIP := c.ClientIP()

		// Get status
		status := c.Writer.Status()

		// Log format
		logMsg := fmt.Sprintf("[%s] | %3d | %13v | %15s | %-7s | %s",
			time.Now().Format("2006/01/02 - 15:04:05"),
			status,
			latency,
			clientIP,
			c.Request.Method,
			path,
		)

		// Log using different methods based on status code
		switch {
		case status >= 500:
			fmt.Println(logMsg, "| SERVER ERROR")
		case status >= 400:
			fmt.Println(logMsg, "| CLIENT ERROR")
		case status >= 300:
			fmt.Println(logMsg, "| REDIRECT")
		default:
			fmt.Println(logMsg)
		}
	}
}

// AuditLogger logs security-relevant operations
func AuditLogger() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Get user ID from context if it exists
		userID, exists := c.Get("userID")
		if !exists {
			userID = "anonymous"
		}

		// Process request
		c.Next()

		// Log only for certain critical operations
		path := c.Request.URL.Path
		method := c.Request.Method

		// Check if this is a security-critical operation
		isSecurityCritical := false
		
		// Session status updates
		if (method == "PATCH" || method == "PUT") && len(path) > 23 && path[:23] == "/api/v1/sessions/status" {
			isSecurityCritical = true
		}
		
		// Command creation
		if method == "POST" && path == "/api/v1/commands" {
			isSecurityCritical = true
		}
		
		// Bookmark operations
		if (method == "POST" || method == "DELETE") && (path == "/api/v1/bookmarks" || len(path) > 18 && path[:18] == "/api/v1/bookmarks/") {
			isSecurityCritical = true
		}
		
		// Context updates
		if (method == "POST" || method == "PUT") && path == "/api/v1/contexts" {
			isSecurityCritical = true
		}
		
		// Maintenance operations
		if method == "POST" && path == "/api/v1/admin/maintenance/purge" {
			isSecurityCritical = true
		}

		// If security critical, log with more details
		if isSecurityCritical {
			clientIP := c.ClientIP()
			status := c.Writer.Status()
			userAgent := c.Request.UserAgent()

			auditLog := fmt.Sprintf("[AUDIT] %s | %s | %s | %s | %s | %d",
				time.Now().Format("2006/01/02 - 15:04:05"),
				userID,
				clientIP,
				method,
				path,
				status,
			)

			// Add user agent for additional context
			if userAgent != "" {
				auditLog += fmt.Sprintf(" | %s", userAgent)
			}

			fmt.Println(auditLog)
		}
	}
}

// ErrorLogger logs errors that occur during request processing
func ErrorLogger() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Next()

		// Count errors
		errorCount := len(c.Errors)
		if errorCount > 0 {
			for _, e := range c.Errors {
				fmt.Printf("[ERROR] %s | %s | %s | %s\n",
					time.Now().Format("2006/01/02 - 15:04:05"),
					c.Request.Method,
					c.Request.URL.Path,
					e.Error(),
				)
			}
		}
	}
}