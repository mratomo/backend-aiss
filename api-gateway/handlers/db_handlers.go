package handlers

import (
	"net/http"

	"github.com/gin-gonic/gin"
)

// Estructuras para las solicitudes
type CreateDBConnectionRequest struct {
	Name        string            `json:"name" binding:"required"`
	Type        string            `json:"type" binding:"required"`
	Host        string            `json:"host" binding:"required"`
	Port        int               `json:"port" binding:"required"`
	Database    string            `json:"database" binding:"required"`
	Username    string            `json:"username" binding:"required"`
	Password    string            `json:"password"`
	SSL         bool              `json:"ssl"`
	Description string            `json:"description"`
	Tags        []string          `json:"tags"`
	Options     map[string]string `json:"options"`
}

type UpdateDBConnectionRequest struct {
	Name        string            `json:"name"`
	Host        string            `json:"host"`
	Port        int               `json:"port"`
	Database    string            `json:"database"`
	Username    string            `json:"username"`
	Password    string            `json:"password"`
	SSL         *bool             `json:"ssl"`
	Description string            `json:"description"`
	Tags        []string          `json:"tags"`
	Options     map[string]string `json:"options"`
}

type CreateDBAgentRequest struct {
	Name                string   `json:"name" binding:"required"`
	Description         string   `json:"description"`
	Type                string   `json:"type" binding:"required"` // rag+db, db-only
	ModelID             string   `json:"model_id" binding:"required"`
	AllowedOperations   []string `json:"allowed_operations"`
	MaxResultSize       int      `json:"max_result_size"`
	QueryTimeoutSecs    int      `json:"query_timeout_secs"`
	DefaultSystemPrompt string   `json:"default_system_prompt"`
}

type UpdateDBAgentRequest struct {
	Name                string   `json:"name"`
	Description         string   `json:"description"`
	ModelID             string   `json:"model_id"`
	AllowedOperations   []string `json:"allowed_operations"`
	MaxResultSize       *int     `json:"max_result_size"`
	QueryTimeoutSecs    *int     `json:"query_timeout_secs"`
	DefaultSystemPrompt string   `json:"default_system_prompt"`
}

type AgentPromptsRequest struct {
	SystemPrompt           string `json:"system_prompt"`
	QueryEvaluationPrompt  string `json:"query_evaluation_prompt"`
	QueryGenerationPrompt  string `json:"query_generation_prompt"`
	ResultFormattingPrompt string `json:"result_formatting_prompt"`
	ExampleDBQueries       string `json:"example_db_queries"`
}

type AssignConnectionRequest struct {
	ConnectionID string   `json:"connection_id" binding:"required"`
	Permissions  []string `json:"permissions" binding:"required"`
}

type DBQueryRequest struct {
	AgentID     string                 `json:"agent_id" binding:"required"`
	Query       string                 `json:"query" binding:"required"`
	Connections []string               `json:"connections"`
	Options     map[string]interface{} `json:"options"`
}

// DBHandlerInstance es la instancia global de DBHandler
var DBHandlerInstance *DBHandler

// DBHandler maneja solicitudes relacionadas con bases de datos
type DBHandler struct {
	dbConnectionServiceURL    string
	schemaDiscoveryServiceURL string
	ragAgentURL               string
}

// NewDBHandler crea un nuevo manejador de bases de datos
func NewDBHandler(dbConnectionService, schemaDiscoveryService, ragAgent string) *DBHandler {
	if DBHandlerInstance == nil {
		DBHandlerInstance = &DBHandler{
			dbConnectionServiceURL:    dbConnectionService,
			schemaDiscoveryServiceURL: schemaDiscoveryService,
			ragAgentURL:               ragAgent,
		}
	}
	return DBHandlerInstance
}

// GetDBHandler obtiene la instancia global del DBHandler
func GetDBHandler() *DBHandler {
	if DBHandlerInstance == nil {
		panic("DBHandler no inicializado. Llame a NewDBHandler primero.")
	}
	return DBHandlerInstance
}

// GetDBConnections obtiene todas las conexiones de BD
func GetDBConnections(c *gin.Context) {
	// Implementación del proxy al servicio db-connection
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/connections", "GET")
}

// GetDBConnection obtiene una conexión de BD específica
func GetDBConnection(c *gin.Context) {
	id := c.Param("id")
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/connections/"+id, "GET")
}

// CreateDBConnection crea una nueva conexión de BD
func CreateDBConnection(c *gin.Context) {
	var request CreateDBConnectionRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/connections", "POST")
}

// UpdateDBConnection actualiza una conexión de BD existente
func UpdateDBConnection(c *gin.Context) {
	id := c.Param("id")
	var request UpdateDBConnectionRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/connections/"+id, "PUT")
}

// DeleteDBConnection elimina una conexión de BD
func DeleteDBConnection(c *gin.Context) {
	id := c.Param("id")
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/connections/"+id, "DELETE")
}

// TestDBConnection prueba una conexión de BD
func TestDBConnection(c *gin.Context) {
	id := c.Param("id")
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/connections/"+id+"/test", "POST")
}

// GetDBConnectionSchema obtiene el esquema de una conexión de BD
func GetDBConnectionSchema(c *gin.Context) {
	id := c.Param("id")
	handler := GetDBHandler()
	proxyRequest(c, handler.schemaDiscoveryServiceURL+"/schema/"+id, "GET")
}

// GetDBAgents obtiene todos los agentes de BD
func GetDBAgents(c *gin.Context) {
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents", "GET")
}

// GetDBAgent obtiene un agente de BD específico
func GetDBAgent(c *gin.Context) {
	id := c.Param("id")
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents/"+id, "GET")
}

// CreateDBAgent crea un nuevo agente de BD
func CreateDBAgent(c *gin.Context) {
	var request CreateDBAgentRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents", "POST")
}

// UpdateDBAgent actualiza un agente de BD existente
func UpdateDBAgent(c *gin.Context) {
	id := c.Param("id")
	var request UpdateDBAgentRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents/"+id, "PUT")
}

// DeleteDBAgent elimina un agente de BD
func DeleteDBAgent(c *gin.Context) {
	id := c.Param("id")
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents/"+id, "DELETE")
}

// GetDBAgentPrompts obtiene los prompts configurados para un agente
func GetDBAgentPrompts(c *gin.Context) {
	id := c.Param("id")
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents/"+id+"/prompts", "GET")
}

// UpdateDBAgentPrompts actualiza los prompts para un agente
func UpdateDBAgentPrompts(c *gin.Context) {
	id := c.Param("id")
	var request AgentPromptsRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents/"+id+"/prompts", "PUT")
}

// GetDBAgentConnections obtiene las conexiones asignadas a un agente
func GetDBAgentConnections(c *gin.Context) {
	id := c.Param("id")
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents/"+id+"/connections", "GET")
}

// AssignDBConnectionToAgent asigna una conexión de BD a un agente
func AssignDBConnectionToAgent(c *gin.Context) {
	id := c.Param("id")
	var request AssignConnectionRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents/"+id+"/connections", "POST")
}

// RemoveDBConnectionFromAgent elimina una conexión de BD de un agente
func RemoveDBConnectionFromAgent(c *gin.Context) {
	id := c.Param("id")
	connectionId := c.Param("connectionId")
	handler := GetDBHandler()
	proxyRequest(c, handler.dbConnectionServiceURL+"/agents/"+id+"/connections/"+connectionId, "DELETE")
}

// ProcessDBQuery procesa una consulta a través de un agente de BD
func ProcessDBQuery(c *gin.Context) {
	var request DBQueryRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// El agente se encarga de decidir si la consulta requiere acceso a BD o RAG convencional
	handler := GetDBHandler()
	proxyRequest(c, handler.ragAgentURL+"/db-query", "POST")
}

// Helper function to get user ID from context
func getUserId(c *gin.Context) string {
	userId, exists := c.Get("userID")
	if !exists {
		return ""
	}
	return userId.(string)
}

// GetDBQueryHistory obtiene el historial de consultas de BD
func GetDBQueryHistory(c *gin.Context) {
	userId := getUserId(c)
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Usuario no identificado"})
		return
	}

	handler := GetDBHandler()
	proxyRequest(c, handler.ragAgentURL+"/db-query/history?user_id="+userId, "GET")
}

// GetDBQueryDetail obtiene el detalle de una consulta específica
func GetDBQueryDetail(c *gin.Context) {
	id := c.Param("id")
	userId := getUserId(c)
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Usuario no identificado"})
		return
	}

	handler := GetDBHandler()
	proxyRequest(c, handler.ragAgentURL+"/db-query/history/"+id+"?user_id="+userId, "GET")
}

// OllamaHandler maneja solicitudes relacionadas con Ollama
type OllamaHandler struct {
	ragAgentURL string
}

// OllamaHandlerInstance es la instancia global de OllamaHandler
var OllamaHandlerInstance *OllamaHandler

// NewOllamaHandler crea un nuevo manejador de Ollama
func NewOllamaHandler(ragAgentURL string) *OllamaHandler {
	if OllamaHandlerInstance == nil {
		OllamaHandlerInstance = &OllamaHandler{
			ragAgentURL: ragAgentURL,
		}
	}
	return OllamaHandlerInstance
}

// GetOllamaHandler obtiene la instancia global del OllamaHandler
func GetOllamaHandler() *OllamaHandler {
	if OllamaHandlerInstance == nil {
		panic("OllamaHandler no inicializado. Llame a NewOllamaHandler primero.")
	}
	return OllamaHandlerInstance
}

// GetOllamaModels obtiene los modelos disponibles en Ollama
func GetOllamaModels(c *gin.Context) {
	handler := GetOllamaHandler()
	proxyRequest(c, handler.ragAgentURL+"/ollama/models", "GET")
}

// PullOllamaModel descarga un modelo en Ollama
func PullOllamaModel(c *gin.Context) {
	var request struct {
		Name string `json:"name" binding:"required"`
	}
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Iniciar descarga asíncrona
	handler := GetOllamaHandler()
	proxyRequest(c, handler.ragAgentURL+"/ollama/models/pull", "POST")
}

// DeleteOllamaModel elimina un modelo de Ollama
func DeleteOllamaModel(c *gin.Context) {
	name := c.Param("name")
	handler := GetOllamaHandler()
	proxyRequest(c, handler.ragAgentURL+"/ollama/models/"+name, "DELETE")
}

// GetOllamaSettings obtiene la configuración de Ollama
func GetOllamaSettings(c *gin.Context) {
	handler := GetOllamaHandler()
	proxyRequest(c, handler.ragAgentURL+"/ollama/settings", "GET")
}

// UpdateOllamaSettings actualiza la configuración de Ollama
func UpdateOllamaSettings(c *gin.Context) {
	var request struct {
		DefaultModel      string                 `json:"default_model"`
		UseGPU            bool                   `json:"use_gpu"`
		ConcurrentQueries int                    `json:"concurrent_queries"`
		DefaultParams     map[string]interface{} `json:"default_params"`
	}
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	handler := GetOllamaHandler()
	proxyRequest(c, handler.ragAgentURL+"/ollama/settings", "PUT")
}
