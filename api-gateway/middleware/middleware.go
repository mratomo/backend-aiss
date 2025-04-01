package middleware

import (
	"bytes"
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
		c.Next()

		// Si ya hay una respuesta, no hacer nada
		if c.Writer.Written() {
			return
		}

		// Si hay errores, responder con el primero
		if len(c.Errors) > 0 {
			err := c.Errors[0]
			c.JSON(http.StatusInternalServerError, gin.H{
				"error": err.Error(),
			})
			return
		}
	}
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

			// Verificar el emisor del token (issuer)
			expectedIssuer := "backend-aiss"
			if claims.Issuer != expectedIssuer {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token de emisor no válido"})
				return
			}

			// Verificar la audiencia del token
			validAudience := false
			expectedAudience := "aiss-client"
			if claims.Audience != nil {
				for _, aud := range claims.Audience {
					if aud == expectedAudience {
						validAudience = true
						break
					}
				}
			}

			if !validAudience {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token con audiencia no válida"})
				return
			}

			// Verificar ID único (jti) para prevenir reutilización
			if claims.ID == "" {
				c.AbortWithStatusJSON(http.StatusUnauthorized, gin.H{"error": "token sin identificador único"})
				return
			}

			// Añadir información de usuario al contexto
			c.Set("userID", claims.UserID)
			c.Set("userRole", claims.Role)
			c.Set("tokenExpiresAt", claims.ExpiresAt.Time)
			c.Set("tokenID", claims.ID)
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

		// Crear solicitud al servicio de usuarios
		reqBody, _ := json.Marshal(map[string]string{
			"user_id": userIDStr,
		})

		// Llamar al endpoint de verificación de admin
		resp, err := http.Post(
			am.UserServiceURL+"/users/verify-admin",
			"application/json",
			bytes.NewBuffer(reqBody),
		)

		if err != nil {
			c.AbortWithStatusJSON(http.StatusInternalServerError, gin.H{"error": "error al verificar permisos de administrador"})
			return
		}
		defer resp.Body.Close()

		// Leer respuesta
		body, _ := io.ReadAll(resp.Body)

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
