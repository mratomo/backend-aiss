package handlers

import (
	"bytes"
	"io"
	"log"
	"net/http"
	"time"

	"github.com/gin-gonic/gin"
)

// HealthCheck Handler para verificar estado del servicio
func HealthCheck(c *gin.Context) {
	c.JSON(http.StatusOK, gin.H{
		"status": "ok",
		"time":   time.Now().Format(time.RFC3339),
	})
}

// UserHandler maneja solicitudes relacionadas con usuarios
type UserHandler struct {
	serviceURL string
}

// NewUserHandler crea un nuevo manejador de usuarios
func NewUserHandler(serviceURL string) *UserHandler {
	return &UserHandler{
		serviceURL: serviceURL,
	}
}

// Register maneja registro de nuevos usuarios
func (h *UserHandler) Register(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/auth/register", "POST")
}

// Login maneja inicio de sesión
func (h *UserHandler) Login(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/auth/login", "POST")
}

// RefreshToken maneja renovación de tokens
func (h *UserHandler) RefreshToken(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/auth/refresh", "POST")
}

// GetCurrentUser obtiene información del usuario actual
func (h *UserHandler) GetCurrentUser(c *gin.Context) {
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "no autorizado"})
		return
	}

	proxyRequest(c, h.serviceURL+"/users/"+userID.(string), "GET")
}

// UpdateUser actualiza un usuario
func (h *UserHandler) UpdateUser(c *gin.Context) {
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "no autorizado"})
		return
	}

	proxyRequest(c, h.serviceURL+"/users/"+userID.(string), "PUT")
}

// ChangePassword cambia la contraseña de un usuario
func (h *UserHandler) ChangePassword(c *gin.Context) {
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "no autorizado"})
		return
	}

	proxyRequest(c, h.serviceURL+"/users/"+userID.(string)+"/password", "PUT")
}

// GetAllUsers obtiene todos los usuarios (admin)
func (h *UserHandler) GetAllUsers(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/users", "GET")
}

// GetUserByID obtiene un usuario por ID (admin)
func (h *UserHandler) GetUserByID(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/users/"+c.Param("id"), "GET")
}

// UpdatePermissions actualiza permisos de un usuario (admin)
func (h *UserHandler) UpdatePermissions(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/users/"+c.Param("id")+"/permissions", "PUT")
}

// DocumentHandler maneja solicitudes relacionadas con documentos
type DocumentHandler struct {
	serviceURL string
}

// NewDocumentHandler crea un nuevo manejador de documentos
func NewDocumentHandler(serviceURL string) *DocumentHandler {
	return &DocumentHandler{
		serviceURL: serviceURL,
	}
}

// ListPersonalDocuments lista documentos personales
func (h *DocumentHandler) ListPersonalDocuments(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/personal", "GET")
}

// UploadPersonalDocument sube un documento personal
func (h *DocumentHandler) UploadPersonalDocument(c *gin.Context) {
	proxyMultipartRequest(c, h.serviceURL+"/personal")
}

// GetPersonalDocument obtiene información de un documento personal
func (h *DocumentHandler) GetPersonalDocument(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/personal/"+c.Param("id"), "GET")
}

// GetPersonalDocumentContent obtiene el contenido de un documento personal
func (h *DocumentHandler) GetPersonalDocumentContent(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/personal/"+c.Param("id")+"/content", "GET")
}

// DeletePersonalDocument elimina un documento personal
func (h *DocumentHandler) DeletePersonalDocument(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/personal/"+c.Param("id"), "DELETE")
}

// ListSharedDocuments lista documentos compartidos
func (h *DocumentHandler) ListSharedDocuments(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/shared", "GET")
}

// GetSharedDocument obtiene información de un documento compartido
func (h *DocumentHandler) GetSharedDocument(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/shared/"+c.Param("id"), "GET")
}

// GetSharedDocumentContent obtiene el contenido de un documento compartido
func (h *DocumentHandler) GetSharedDocumentContent(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/shared/"+c.Param("id")+"/content", "GET")
}

// UploadSharedDocument sube un documento compartido (admin)
func (h *DocumentHandler) UploadSharedDocument(c *gin.Context) {
	proxyMultipartRequest(c, h.serviceURL+"/shared")
}

// UpdateSharedDocument actualiza un documento compartido (admin)
func (h *DocumentHandler) UpdateSharedDocument(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/shared/"+c.Param("id"), "PUT")
}

// DeleteSharedDocument elimina un documento compartido (admin)
func (h *DocumentHandler) DeleteSharedDocument(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/shared/"+c.Param("id"), "DELETE")
}

// ContextHandler maneja solicitudes relacionadas con áreas y contextos
type ContextHandler struct {
	serviceURL string
}

// NewContextHandler crea un nuevo manejador de contextos
func NewContextHandler(serviceURL string) *ContextHandler {
	return &ContextHandler{
		serviceURL: serviceURL,
	}
}

// ListAreas lista todas las áreas de conocimiento
func (h *ContextHandler) ListAreas(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas", "GET")
}

// GetAreaByID obtiene un área por su ID
func (h *ContextHandler) GetAreaByID(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas/"+c.Param("id"), "GET")
}

// CreateArea crea una nueva área de conocimiento (admin)
func (h *ContextHandler) CreateArea(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas", "POST")
}

// UpdateArea actualiza un área de conocimiento (admin)
func (h *ContextHandler) UpdateArea(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas/"+c.Param("id"), "PUT")
}

// DeleteArea elimina un área de conocimiento (admin)
func (h *ContextHandler) DeleteArea(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas/"+c.Param("id"), "DELETE")
}

// EmbeddingHandler maneja solicitudes relacionadas con embeddings
type EmbeddingHandler struct {
	serviceURL string
}

// NewEmbeddingHandler crea un nuevo manejador de embeddings
func NewEmbeddingHandler(serviceURL string) *EmbeddingHandler {
	return &EmbeddingHandler{
		serviceURL: serviceURL,
	}
}

// RAGHandler maneja solicitudes relacionadas con el agente RAG
type RAGHandler struct {
	serviceURL string
}

// NewRAGHandler crea un nuevo manejador para el agente RAG
func NewRAGHandler(serviceURL string) *RAGHandler {
	return &RAGHandler{
		serviceURL: serviceURL,
	}
}

// QueryKnowledge realiza una consulta general
func (h *RAGHandler) QueryKnowledge(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/query", "POST")
}

// QuerySpecificArea realiza una consulta en un área específica
func (h *RAGHandler) QuerySpecificArea(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/query/area/"+c.Param("areaId"), "POST")
}

// QueryPersonalKnowledge realiza una consulta en conocimiento personal
func (h *RAGHandler) QueryPersonalKnowledge(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/query/personal", "POST")
}

// GetQueryHistory obtiene el historial de consultas
func (h *RAGHandler) GetQueryHistory(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/query/history", "GET")
}

// ListProviders lista los proveedores LLM
func (h *RAGHandler) ListProviders(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/providers", "GET")
}

// AddProvider añade un nuevo proveedor LLM
func (h *RAGHandler) AddProvider(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/providers", "POST")
}

// UpdateProvider actualiza un proveedor LLM
func (h *RAGHandler) UpdateProvider(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/providers/"+c.Param("id"), "PUT")
}

// DeleteProvider elimina un proveedor LLM
func (h *RAGHandler) DeleteProvider(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/providers/"+c.Param("id"), "DELETE")
}

// TestProvider prueba un proveedor LLM
func (h *RAGHandler) TestProvider(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/providers/"+c.Param("id")+"/test", "POST")
}

// proxyRequest es una función auxiliar para reenviar solicitudes a servicios internos
func proxyRequest(c *gin.Context, url string, method string) {
	// Leer body de la solicitud
	body, err := io.ReadAll(c.Request.Body)
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "error al leer body: " + err.Error()})
		return
	}

	// Crear solicitud al servicio interno
	req, err := http.NewRequest(method, url, bytes.NewBuffer(body))
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al crear solicitud: " + err.Error()})
		return
	}

	// Copiar headers relevantes
	req.Header.Set("Content-Type", c.GetHeader("Content-Type"))
	if auth := c.GetHeader("Authorization"); auth != "" {
		req.Header.Set("Authorization", auth)
	}

	// Copiar query params
	req.URL.RawQuery = c.Request.URL.RawQuery

	// Realizar solicitud
	client := &http.Client{Timeout: 30 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al llamar al servicio: " + err.Error()})
		return
	}

	// Mejora: Implementar manejo de errores en el defer para cierre del cuerpo de respuesta
	defer func(Body io.ReadCloser) {
		if err := Body.Close(); err != nil {
			log.Printf("Error closing response body: %v", err)
		}
	}(resp.Body)

	// Leer respuesta
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al leer respuesta: " + err.Error()})
		return
	}

	// Copiar headers de respuesta
	for key, values := range resp.Header {
		for _, value := range values {
			c.Header(key, value)
		}
	}

	// Enviar respuesta al cliente
	c.Data(resp.StatusCode, resp.Header.Get("Content-Type"), respBody)
}

// proxyMultipartRequest maneja específicamente solicitudes multipart/form-data
func proxyMultipartRequest(c *gin.Context, url string) {
	// Primero asegúrate de que es multipart/form-data
	err := c.Request.ParseMultipartForm(32 << 20) // 32MB max
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "error al analizar form: " + err.Error()})
		return
	}

	// Crear cliente HTTP con timeout adecuado para subida de archivos
	client := &http.Client{Timeout: 5 * time.Minute}

	// Crear una nueva solicitud multipart
	req, err := http.NewRequest("POST", url, c.Request.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al crear solicitud: " + err.Error()})
		return
	}

	// Copiar encabezados originales
	req.Header = c.Request.Header

	// Copiar cookies
	for _, cookie := range c.Request.Cookies() {
		req.AddCookie(cookie)
	}

	// Realizar solicitud
	resp, err := client.Do(req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al llamar al servicio: " + err.Error()})
		return
	}

	// Mejora: Implementar manejo de errores en el defer para cierre del cuerpo de respuesta
	defer func(Body io.ReadCloser) {
		if err := Body.Close(); err != nil {
			log.Printf("Error closing response body: %v", err)
		}
	}(resp.Body)

	// Leer respuesta
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al leer respuesta: " + err.Error()})
		return
	}

	// Copiar headers de respuesta
	for key, values := range resp.Header {
		for _, value := range values {
			c.Header(key, value)
		}
	}

	// Enviar respuesta al cliente
	c.Data(resp.StatusCode, resp.Header.Get("Content-Type"), respBody)
}
