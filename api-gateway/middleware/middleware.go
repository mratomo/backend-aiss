package middleware

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v4"
)

// RequestLogger middleware para registrar detalles de las solicitudes
func RequestLogger() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Tiempo de inicio
		startTime := time.Now()

		// Procesar la solicitud
		c.Next()

		// Tiempo de finalización y duración
		endTime := time.Now()
		latency := endTime.Sub(startTime)

		// Detectar si la solicitud proviene del proxy inverso
		realIP := c.GetHeader("X-Real-IP")
		forwardedFor := c.GetHeader("X-Forwarded-For")

		// Determinar la IP del cliente (proxy o directa)
		clientIP := c.ClientIP()
		if realIP != "" {
			clientIP = realIP
		} else if forwardedFor != "" {
			// X-Forwarded-For puede contener múltiples IPs (proxies en cadena)
			ips := strings.Split(forwardedFor, ",")
			if len(ips) > 0 {
				// Usar la primera IP, que es la del cliente original
				clientIP = strings.TrimSpace(ips[0])
			}
		}

		// Registrar detalles de la solicitud
		log.Printf("[%s] %s %s %d %s",
			c.Request.Method,
			c.Request.URL.Path,
			clientIP,
			c.Writer.Status(),
			latency.String(),
		)
	}
}

// ErrorHandler middleware para manejar errores de forma centralizada
func ErrorHandler() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Crear un buffer para capturar el cuerpo de la respuesta
		blw := &bodyLogWriter{body: bytes.NewBufferString(""), ResponseWriter: c.Writer}
		c.Writer = blw

		// Procesar la solicitud
		c.Next()

		// Si ya hay una respuesta, solo registrar
		if c.Writer.Status() != 0 {
			// Capturar el error si es 4xx o 5xx
			if c.Writer.Status() >= 400 {
				log.Printf("[ERROR] Path: %s, Status: %d, Response: %s",
					c.Request.URL.Path, c.Writer.Status(), blw.body.String())
			}
			return
		}

		// Si hay errores en Gin, responder con el primero
		if len(c.Errors) > 0 {
			err := c.Errors[0]
			// Determinar código de estado basado en el tipo de error
			statusCode := http.StatusInternalServerError

			// Analizar error para determinar código apropiado
			errMsg := err.Error()
			if strings.Contains(errMsg, "no encontrado") || strings.Contains(errMsg, "not found") {
				statusCode = http.StatusNotFound
			} else if strings.Contains(errMsg, "no autorizado") || strings.Contains(errMsg, "unauthorized") {
				statusCode = http.StatusUnauthorized
			} else if strings.Contains(errMsg, "validación") || strings.Contains(errMsg, "validation") {
				statusCode = http.StatusBadRequest
			}

			c.JSON(statusCode, gin.H{
				"error": errMsg,
				"code":  statusCode,
				"path":  c.Request.URL.Path,
			})

			// Registrar error
			log.Printf("[ERROR] Path: %s, Status: %d, Error: %s",
				c.Request.URL.Path, statusCode, errMsg)
			return
		}
	}
}

// bodyLogWriter estructura para capturar el cuerpo de la respuesta
type bodyLogWriter struct {
	gin.ResponseWriter
	body *bytes.Buffer
}

// Write implementa la interfaz ResponseWriter
func (w *bodyLogWriter) Write(b []byte) (int, error) {
	w.body.Write(b)
	return w.ResponseWriter.Write(b)
}

// AuthMiddleware estructura para el middleware de autenticación
type AuthMiddleware struct {
	Secret string
}

// NewAuthMiddleware crea una nueva instancia del middleware de autenticación
func NewAuthMiddleware(secret string) *AuthMiddleware {
	return &AuthMiddleware{
		Secret: secret,
	}
}

// Claims estructura para los claims del JWT
type Claims struct {
	UserID string `json:"user_id"`
	Role   string `json:"role"`
	jwt.RegisteredClaims
}

// Authenticate middleware para verificar autenticación
func (am *AuthMiddleware) Authenticate() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Obtener token del header Authorization
		authHeader := c.GetHeader("Authorization")
		if authHeader == "" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token de autorización no proporcionado"})
			return
		}

		// El formato debe ser "Bearer <token>"
		parts := strings.Split(authHeader, " ")
		if len(parts) != 2 || parts[0] != "Bearer" {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "formato de token inválido"})
			return
		}

		tokenStr := parts[1]

		// Parsear y validar el token
		token, err := jwt.ParseWithClaims(tokenStr, &Claims{}, func(token *jwt.Token) (interface{}, error) {
			// Asegurar que el método de firma sea HMAC
			if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
				return nil, fmt.Errorf("método de firma inesperado: %v", token.Header["alg"])
			}
			return []byte(am.Secret), nil
		})

		if err != nil {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token inválido: " + err.Error()})
			return
		}

		// Extraer claims
		if claims, ok := token.Claims.(*Claims); ok && token.Valid {
			// Verificar explícitamente la expiración del token
			if claims.ExpiresAt != nil && time.Now().After(claims.ExpiresAt.Time) {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token expirado"})
				return
			}

			// Verificar que el token no sea usado antes de su tiempo de inicio
			if claims.IssuedAt != nil && time.Now().Before(claims.IssuedAt.Time) {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token no válido todavía"})
				return
			}

			// Verificación del emisor temporalmente desactivada para desarrollo
			if claims.Issuer != "" {
				log.Printf("Token issuer: %s", claims.Issuer)
			}

			// Verificación de audiencia temporalmente desactivada para desarrollo
			if claims.Audience != nil && len(claims.Audience) > 0 {
				log.Printf("Token audience: %v", claims.Audience)
			}

			// Verificación de JTI temporalmente desactivada para desarrollo
			if claims.ID != "" {
				log.Printf("Token ID (jti): %s", claims.ID)
			}

			// Añadir información de usuario al contexto
			c.Set("userID", claims.UserID)
			c.Set("userRole", claims.Role)
			c.Set("tokenExpiresAt", claims.ExpiresAt.Time)
			if claims.ID != "" {
				c.Set("tokenID", claims.ID)
			}
			c.Next()
		} else {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token inválido"})
			return
		}
	}
}

// AdminMiddleware estructura para el middleware de administración
type AdminMiddleware struct {
	UserServiceURL string
}

// NewAdminMiddleware crea una nueva instancia del middleware de administración
func NewAdminMiddleware(userServiceURL string) *AdminMiddleware {
	return &AdminMiddleware{
		UserServiceURL: userServiceURL,
	}
}

// AdminOnly middleware para verificar si el usuario es administrador
func (am *AdminMiddleware) AdminOnly() gin.HandlerFunc {
	return func(c *gin.Context) {
		// Obtener rol del contexto
		role, exists := c.Get("userRole")
		if !exists {
			c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
			return
		}

		// Verificar si es admin
		if role == "admin" {
			c.Next()
			return
		}

		// Verificar con el servicio de usuarios
		userID, _ := c.Get("userID")
		userIDStr := userID.(string)

		// Crear solicitud al servicio de usuarios con contexto y timeout
		reqBody, _ := json.Marshal(map[string]string{
			"user_id": userIDStr,
		})

		// Crear contexto con timeout
		ctx, cancel := context.WithTimeout(c.Request.Context(), 5*time.Second)
		defer cancel()

		// Crear solicitud HTTP con contexto
		req, err := http.NewRequestWithContext(
			ctx,
			"POST",
			am.UserServiceURL+"/users/verify-admin",
			bytes.NewBuffer(reqBody),
		)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "error al crear solicitud de verificación de admin"})
			return
		}
		req.Header.Set("Content-Type", "application/json")

		// Enviar solicitud
		client := &http.Client{}
		resp, err := client.Do(req)

		if err != nil {
			if ctx.Err() == context.DeadlineExceeded {
				c.AbortWithStatusJSON(http.StatusGatewayTimeout, gin.H{"error": "timeout al verificar permisos de administrador"})
			} else {
				c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "error al verificar permisos de administrador: " + err.Error()})
			}
			return
		}
		defer resp.Body.Close()

		// Leer respuesta
		body, err := io.ReadAll(resp.Body)
		if err != nil {
			c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "error al leer respuesta de verificación"})
			return
		}

		// Verificar respuesta
		var result map[string]interface{}
		if err := json.Unmarshal(body, &result); err != nil {
			c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "error al procesar respuesta de verificación"})
			return
		}

		// Si es admin, continuar
		if isAdmin, ok := result["is_admin"].(bool); ok && isAdmin {
			c.Next()
			return
		}

		// Si no es admin, denegar acceso
		c.AbortWithStatusJSON(http.StatusForbidden, gin.H{"error": "acceso denegado: se requieren permisos de administrador"})
	}
}
