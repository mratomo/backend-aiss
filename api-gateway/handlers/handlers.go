package handlers

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"strings"
	"sync"
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

// ConfigHandler maneja configuraciones dinámicas del sistema
type ConfigHandler struct {
	corsConfig     *[]string
	environment    string
	configFilePath string
}

// Instancia global del ConfigHandler para acceso desde las rutas
var (
	ConfigHandlerInstance *ConfigHandler
	configHandlerMutex    sync.RWMutex
	configHandlerOnce     sync.Once
)

// NewConfigHandler crea un nuevo manejador de configuración y lo asigna a la instancia global
func NewConfigHandler(corsConfig *[]string, environment, configPath string) *ConfigHandler {
	// Inicialización segura utilizando sync.Once sin anidamiento de locks
	configHandlerOnce.Do(func() {
		// Constructor sin locks anidados
		handler := &ConfigHandler{
			corsConfig:     corsConfig,
			environment:    environment,
			configFilePath: configPath,
		}

		// Asignar la instancia global de forma segura
		ConfigHandlerInstance = handler

		// No se necesita un lock explícito aquí porque sync.Once ya garantiza
		// que este bloque se ejecuta una sola vez de forma thread-safe
	})

	// No es necesario adquirir el lock para leer la referencia después de la inicialización
	// porque sync.Once garantiza visibilidad de memoria después de la inicialización
	return ConfigHandlerInstance
}

// GetCorsConfig devuelve la configuración CORS actual
func (h *ConfigHandler) GetCorsConfig(c *gin.Context) {
	configHandlerMutex.RLock()
	corsConfig := *h.corsConfig
	environment := h.environment
	configHandlerMutex.RUnlock()

	c.JSON(http.StatusOK, gin.H{
		"environment":          environment,
		"cors_allowed_origins": corsConfig,
	})
}

// UpdateCorsConfig actualiza la configuración CORS dinámicamente
func (h *ConfigHandler) UpdateCorsConfig(c *gin.Context) {
	var request struct {
		Origins []string `json:"origins" binding:"required"`
	}

	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Formato inválido. Se requiere un array 'origins' con los orígenes permitidos"})
		return
	}

	// Validar los orígenes
	for i, origin := range request.Origins {
		if !strings.HasPrefix(origin, "http://") && !strings.HasPrefix(origin, "https://") && origin != "*" {
			c.JSON(http.StatusBadRequest, gin.H{
				"error": fmt.Sprintf("Origen %d inválido: %s. Debe comenzar con 'http://' o 'https://' o ser '*'", i, origin),
			})
			return
		}
	}

	// Actualizar configuración en memoria (thread-safe)
	configHandlerMutex.Lock()
	*h.corsConfig = request.Origins
	configHandlerMutex.Unlock()

	// Registrar cambio
	log.Printf("CORS configuration updated to: %v", request.Origins)

	// Responder con la nueva configuración
	c.JSON(http.StatusOK, gin.H{
		"message":              "Configuración CORS actualizada correctamente",
		"cors_allowed_origins": request.Origins,
	})
}

// UserHandler maneja solicitudes relacionadas con usuarios
type UserHandler struct {
	serviceURL string
}

// Instancia global de UserHandler
var (
	userHandlerInstance *UserHandler
	userHandlerOnce     sync.Once
)

// NewUserHandler crea un nuevo manejador de usuarios
func NewUserHandler(serviceURL string) *UserHandler {
	userHandlerOnce.Do(func() {
		userHandlerInstance = &UserHandler{
			serviceURL: serviceURL,
		}
	})
	return userHandlerInstance
}

// GetUserHandler obtiene la instancia global del UserHandler
func GetUserHandler() *UserHandler {
	if userHandlerInstance == nil {
		panic("UserHandler no inicializado. Llame a NewUserHandler primero.")
	}
	return userHandlerInstance
}

// GetConfigHandlerInstance obtiene la instancia global del ConfigHandler
func GetConfigHandlerInstance() *ConfigHandler {
	if ConfigHandlerInstance == nil {
		panic("ConfigHandler no inicializado. Llame a NewConfigHandler primero.")
	}
	return ConfigHandlerInstance
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
	// Si es una ruta de admin, usar el ID del parámetro
	if c.Param("id") != "" {
		proxyRequest(c, h.serviceURL+"/users/"+c.Param("id"), "PUT")
		return
	}

	// Si no, usar el ID del usuario actual
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "no autorizado"})
		return
	}

	proxyRequest(c, h.serviceURL+"/users/"+userID.(string), "PUT")
}

// DeleteUser elimina un usuario (admin)
func (h *UserHandler) DeleteUser(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/users/"+c.Param("id"), "DELETE")
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

// SearchDocuments busca documentos
func (h *DocumentHandler) SearchDocuments(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/search", "GET")
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

// GetAreaSystemPrompt obtiene el prompt de sistema de un área
func (h *ContextHandler) GetAreaSystemPrompt(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas/"+c.Param("id")+"/system-prompt", "GET")
}

// UpdateAreaSystemPrompt actualiza el prompt de sistema de un área
func (h *ContextHandler) UpdateAreaSystemPrompt(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas/"+c.Param("id")+"/system-prompt", "PUT")
}

// GetAreaPrimaryLLM obtiene el proveedor LLM principal de un área
func (h *ContextHandler) GetAreaPrimaryLLM(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas/"+c.Param("id")+"/primary-llm", "GET")
}

// UpdateAreaPrimaryLLM actualiza el proveedor LLM principal de un área (admin)
func (h *ContextHandler) UpdateAreaPrimaryLLM(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/areas/"+c.Param("id")+"/primary-llm", "PUT")
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

// GenerateEmbedding genera un embedding para un texto
func (h *EmbeddingHandler) GenerateEmbedding(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/embedding", "POST")
}

// GetEmbeddingModels obtiene los modelos de embedding disponibles
func (h *EmbeddingHandler) GetEmbeddingModels(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/models", "GET")
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

// LLMSettingsHandler maneja solicitudes relacionadas con configuraciones LLM
type LLMSettingsHandler struct {
	serviceURL string
}

// NewLLMSettingsHandler crea un nuevo manejador de configuraciones LLM
func NewLLMSettingsHandler(serviceURL string) *LLMSettingsHandler {
	return &LLMSettingsHandler{
		serviceURL: serviceURL,
	}
}

// GetSystemPrompt obtiene el prompt de sistema global
func (h *LLMSettingsHandler) GetSystemPrompt(c *gin.Context) {
	proxyRequest(c, h.serviceURL+"/settings/system-prompt", "GET")
}

// UpdateSystemPrompt actualiza el prompt de sistema global
func (h *LLMSettingsHandler) UpdateSystemPrompt(c *gin.Context) {
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "no autorizado"})
		return
	}
	// Añadir user_id como query param
	url := h.serviceURL + "/settings/system-prompt?user_id=" + userID.(string)
	proxyRequest(c, url, "PUT")
}

// ResetSystemPrompt restablece el prompt de sistema global
func (h *LLMSettingsHandler) ResetSystemPrompt(c *gin.Context) {
	userID, exists := c.Get("userID")
	if !exists {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "no autorizado"})
		return
	}
	// Añadir user_id como query param
	url := h.serviceURL + "/settings/system-prompt/reset?user_id=" + userID.(string)
	proxyRequest(c, url, "POST")
}

// Estructura para la respuesta del proxy
type ProxyResponse struct {
	StatusCode int         `json:"status_code"`
	Body       interface{} `json:"body"`
	Headers    http.Header `json:"headers"`
}

// proxyRequestSimple es una función auxiliar para reenviar solicitudes a servicios internos
// versión original que se utiliza en los handlers existentes
func proxyRequestSimple(c *gin.Context, url string, method string) {
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

	// Implementar streaming para archivos grandes
	// Copiar headers de respuesta primero
	for key, values := range resp.Header {
		for _, value := range values {
			c.Header(key, value)
		}
	}

	// Establecer el código de estado
	c.Status(resp.StatusCode)

	// Streaming de respuesta directamente al cliente
	// Esto es más eficiente para archivos grandes ya que no carga todo en memoria
	_, err = io.Copy(c.Writer, resp.Body)
	if err != nil {
		// Ya hemos enviado cabeceras, no podemos enviar un JSON de error ahora
		log.Printf("Error streaming response: %v", err)
		return
	}
}

// proxyRequest es la función principal para enviar solicitudes a servicios internos
func proxyRequest(c *gin.Context, url string, method string) {
	proxyRequestSimple(c, url, method)
	// No se puede manejar errores aquí porque proxyRequestSimple ya escribe la respuesta directamente
	// y no devuelve errores. Si hay errores, ya se manejan dentro de proxyRequestSimple.
}

// proxyRequestWithData es una versión mejorada que acepta un parámetro de datos y devuelve una respuesta estructurada
// Esta versión es utilizada por los nuevos handlers de DB
func proxyRequestWithData(c *gin.Context, url string, method string, data interface{}) ProxyResponse {
	var reqBody []byte
	var err error

	// Si hay datos, convertirlos a JSON
	if data != nil {
		reqBody, err = json.Marshal(data)
		if err != nil {
			return ProxyResponse{
				StatusCode: http.StatusInternalServerError,
				Body:       gin.H{"error": "Error al serializar datos: " + err.Error()},
			}
		}
	} else if method != "GET" && method != "DELETE" {
		// Si no hay datos pero el método requiere body, leer del request
		reqBody, err = io.ReadAll(c.Request.Body)
		if err != nil {
			return ProxyResponse{
				StatusCode: http.StatusBadRequest,
				Body:       gin.H{"error": "Error al leer body: " + err.Error()},
			}
		}
	}

	// Crear solicitud al servicio interno
	req, err := http.NewRequest(method, url, bytes.NewBuffer(reqBody))
	if err != nil {
		return ProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Body:       gin.H{"error": "Error al crear solicitud: " + err.Error()},
		}
	}

	// Establecer Content-Type si hay datos
	if len(reqBody) > 0 {
		req.Header.Set("Content-Type", "application/json")
	}

	// Copiar el token de autenticación si existe
	if auth := c.GetHeader("Authorization"); auth != "" {
		req.Header.Set("Authorization", auth)
	}

	// Copiar query params
	req.URL.RawQuery = c.Request.URL.RawQuery

	// Realizar solicitud
	client := &http.Client{Timeout: 60 * time.Second}
	resp, err := client.Do(req)
	if err != nil {
		return ProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Body:       gin.H{"error": "Error al llamar al servicio: " + err.Error()},
		}
	}
	defer func(Body io.ReadCloser) {
		if err := Body.Close(); err != nil {
			log.Printf("Error closing response body: %v", err)
		}
	}(resp.Body)

	// Leer respuesta
	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		return ProxyResponse{
			StatusCode: http.StatusInternalServerError,
			Body:       gin.H{"error": "Error al leer respuesta: " + err.Error()},
		}
	}

	// Parsear respuesta JSON si existe
	var responseObj interface{}
	if len(respBody) > 0 && resp.Header.Get("Content-Type") == "application/json" {
		err = json.Unmarshal(respBody, &responseObj)
		if err != nil {
			// Si falla el parsing, devolver el body como string
			responseObj = string(respBody)
		}
	} else {
		responseObj = string(respBody)
	}

	return ProxyResponse{
		StatusCode: resp.StatusCode,
		Body:       responseObj,
		Headers:    resp.Header,
	}
}

// proxyMultipartRequest maneja específicamente solicitudes multipart/form-data
func proxyMultipartRequest(c *gin.Context, url string) {
	// Primero asegúrate de que es multipart/form-data
	err := c.Request.ParseMultipartForm(32 << 20) // 32MB max
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "error al analizar form: " + err.Error()})
		return
	}

	// Crear cliente HTTP con timeout adaptativo para subida de archivos
	// Calcular timeout basado en el tamaño del archivo (1 minuto base + 1 minuto por cada 10MB)
	fileSize := c.Request.ContentLength
	baseTimeout := 1 * time.Minute
	sizeTimeout := time.Duration(0)
	if fileSize > 0 {
		// 1 minuto adicional por cada 10MB
		sizeTimeout = time.Duration(fileSize/(10*1024*1024)) * time.Minute
	}
	// Máximo 30 minutos para archivos muy grandes
	timeout := baseTimeout + sizeTimeout
	if timeout > 30*time.Minute {
		timeout = 30 * time.Minute
	}

	client := &http.Client{Timeout: timeout}

	// Crear buffer para leer body y evitar memory leak
	bodyBytes, err := io.ReadAll(c.Request.Body)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al leer body: " + err.Error()})
		return
	}
	// Cerrar body original para evitar memory leak
	if err := c.Request.Body.Close(); err != nil {
		log.Printf("Error closing request body: %v", err)
	}

	// Crear una nueva solicitud multipart con buffer
	req, err := http.NewRequest("POST", url, bytes.NewBuffer(bodyBytes))
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

	// Implementar streaming para archivos grandes
	// Copiar headers de respuesta primero
	for key, values := range resp.Header {
		for _, value := range values {
			c.Header(key, value)
		}
	}

	// Establecer el código de estado
	c.Status(resp.StatusCode)

	// Streaming de respuesta directamente al cliente
	// Esto es más eficiente para archivos grandes ya que no carga todo en memoria
	_, err = io.Copy(c.Writer, resp.Body)
	if err != nil {
		// Ya hemos enviado cabeceras, no podemos enviar un JSON de error ahora
		log.Printf("Error streaming response: %v", err)
		return
	}
}
