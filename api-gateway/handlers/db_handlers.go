package handlers

import (
	"errors"
	"net/http"
	"time"

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
	Name               string   `json:"name" binding:"required"`
	Description        string   `json:"description"`
	Type               string   `json:"type" binding:"required"` // rag+db, db-only
	ModelID            string   `json:"model_id" binding:"required"`
	AllowedOperations  []string `json:"allowed_operations"`
	MaxResultSize      int      `json:"max_result_size"`
	QueryTimeoutSecs   int      `json:"query_timeout_secs"`
	DefaultSystemPrompt string   `json:"default_system_prompt"`
}

type UpdateDBAgentRequest struct {
	Name               string   `json:"name"`
	Description        string   `json:"description"`
	ModelID            string   `json:"model_id"`
	AllowedOperations  []string `json:"allowed_operations"`
	MaxResultSize      *int     `json:"max_result_size"`
	QueryTimeoutSecs   *int     `json:"query_timeout_secs"`
	DefaultSystemPrompt string   `json:"default_system_prompt"`
}

type AgentPromptsRequest struct {
	SystemPrompt             string `json:"system_prompt"`
	QueryEvaluationPrompt    string `json:"query_evaluation_prompt"`
	QueryGenerationPrompt    string `json:"query_generation_prompt"`
	ResultFormattingPrompt   string `json:"result_formatting_prompt"`
	ExampleDBQueries         string `json:"example_db_queries"`
}

type AssignConnectionRequest struct {
	ConnectionID string   `json:"connection_id" binding:"required"`
	Permissions  []string `json:"permissions" binding:"required"`
}

type DBQueryRequest struct {
	AgentID     string   `json:"agent_id" binding:"required"`
	Query       string   `json:"query" binding:"required"`
	Connections []string `json:"connections"`
	Options     map[string]interface{} `json:"options"`
}

// GetDBConnections obtiene todas las conexiones de BD
func GetDBConnections(c *gin.Context) {
	// Implementación del proxy al servicio db-connection
	response := proxyRequest(c, "http://db-connection-service:8086/connections", "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// GetDBConnection obtiene una conexión de BD específica
func GetDBConnection(c *gin.Context) {
	id := c.Param("id")
	response := proxyRequest(c, "http://db-connection-service:8086/connections/"+id, "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// CreateDBConnection crea una nueva conexión de BD
func CreateDBConnection(c *gin.Context) {
	var request CreateDBConnectionRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	response := proxyRequest(c, "http://db-connection-service:8086/connections", "POST", request)
	c.JSON(response.StatusCode, response.Body)
}

// UpdateDBConnection actualiza una conexión de BD existente
func UpdateDBConnection(c *gin.Context) {
	id := c.Param("id")
	var request UpdateDBConnectionRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	response := proxyRequest(c, "http://db-connection-service:8086/connections/"+id, "PUT", request)
	c.JSON(response.StatusCode, response.Body)
}

// DeleteDBConnection elimina una conexión de BD
func DeleteDBConnection(c *gin.Context) {
	id := c.Param("id")
	response := proxyRequest(c, "http://db-connection-service:8086/connections/"+id, "DELETE", nil)
	c.JSON(response.StatusCode, response.Body)
}

// TestDBConnection prueba una conexión de BD
func TestDBConnection(c *gin.Context) {
	id := c.Param("id")
	response := proxyRequest(c, "http://db-connection-service:8086/connections/"+id+"/test", "POST", nil)
	c.JSON(response.StatusCode, response.Body)
}

// GetDBConnectionSchema obtiene el esquema de una conexión de BD
func GetDBConnectionSchema(c *gin.Context) {
	id := c.Param("id")
	response := proxyRequest(c, "http://schema-discovery-service:8087/schema/"+id, "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// GetDBAgents obtiene todos los agentes de BD
func GetDBAgents(c *gin.Context) {
	response := proxyRequest(c, "http://db-connection-service:8086/agents", "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// GetDBAgent obtiene un agente de BD específico
func GetDBAgent(c *gin.Context) {
	id := c.Param("id")
	response := proxyRequest(c, "http://db-connection-service:8086/agents/"+id, "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// CreateDBAgent crea un nuevo agente de BD
func CreateDBAgent(c *gin.Context) {
	var request CreateDBAgentRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	response := proxyRequest(c, "http://db-connection-service:8086/agents", "POST", request)
	c.JSON(response.StatusCode, response.Body)
}

// UpdateDBAgent actualiza un agente de BD existente
func UpdateDBAgent(c *gin.Context) {
	id := c.Param("id")
	var request UpdateDBAgentRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	response := proxyRequest(c, "http://db-connection-service:8086/agents/"+id, "PUT", request)
	c.JSON(response.StatusCode, response.Body)
}

// DeleteDBAgent elimina un agente de BD
func DeleteDBAgent(c *gin.Context) {
	id := c.Param("id")
	response := proxyRequest(c, "http://db-connection-service:8086/agents/"+id, "DELETE", nil)
	c.JSON(response.StatusCode, response.Body)
}

// GetDBAgentPrompts obtiene los prompts configurados para un agente
func GetDBAgentPrompts(c *gin.Context) {
	id := c.Param("id")
	response := proxyRequest(c, "http://db-connection-service:8086/agents/"+id+"/prompts", "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// UpdateDBAgentPrompts actualiza los prompts para un agente
func UpdateDBAgentPrompts(c *gin.Context) {
	id := c.Param("id")
	var request AgentPromptsRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	response := proxyRequest(c, "http://db-connection-service:8086/agents/"+id+"/prompts", "PUT", request)
	c.JSON(response.StatusCode, response.Body)
}

// GetDBAgentConnections obtiene las conexiones asignadas a un agente
func GetDBAgentConnections(c *gin.Context) {
	id := c.Param("id")
	response := proxyRequest(c, "http://db-connection-service:8086/agents/"+id+"/connections", "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// AssignDBConnectionToAgent asigna una conexión de BD a un agente
func AssignDBConnectionToAgent(c *gin.Context) {
	id := c.Param("id")
	var request AssignConnectionRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	response := proxyRequest(c, "http://db-connection-service:8086/agents/"+id+"/connections", "POST", request)
	c.JSON(response.StatusCode, response.Body)
}

// RemoveDBConnectionFromAgent elimina una conexión de BD de un agente
func RemoveDBConnectionFromAgent(c *gin.Context) {
	id := c.Param("id")
	connectionId := c.Param("connectionId")
	response := proxyRequest(c, "http://db-connection-service:8086/agents/"+id+"/connections/"+connectionId, "DELETE", nil)
	c.JSON(response.StatusCode, response.Body)
}

// ProcessDBQuery procesa una consulta a través de un agente de BD
func ProcessDBQuery(c *gin.Context) {
	var request DBQueryRequest
	if err := c.ShouldBindJSON(&request); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// El agente se encarga de decidir si la consulta requiere acceso a BD o RAG convencional
	response := proxyRequest(c, "http://rag-agent:8085/db-query", "POST", request)
	c.JSON(response.StatusCode, response.Body)
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

	response := proxyRequest(c, "http://rag-agent:8085/db-query/history?user_id="+userId, "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// GetDBQueryDetail obtiene el detalle de una consulta específica
func GetDBQueryDetail(c *gin.Context) {
	id := c.Param("id")
	userId := getUserId(c)
	if userId == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "Usuario no identificado"})
		return
	}
	
	response := proxyRequest(c, "http://rag-agent:8085/db-query/history/"+id+"?user_id="+userId, "GET", nil)
	c.JSON(response.StatusCode, response.Body)
}

// GetOllamaModels obtiene los modelos disponibles en Ollama
func GetOllamaModels(c *gin.Context) {
	response := proxyRequest(c, "http://rag-agent:8085/ollama/models", "GET", nil)
	c.JSON(response.StatusCode, response.Body)
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
	response := proxyRequest(c, "http://rag-agent:8085/ollama/models/pull", "POST", request)
	c.JSON(response.StatusCode, response.Body)
}

// DeleteOllamaModel elimina un modelo de Ollama
func DeleteOllamaModel(c *gin.Context) {
	name := c.Param("name")
	response := proxyRequest(c, "http://rag-agent:8085/ollama/models/"+name, "DELETE", nil)
	c.JSON(response.StatusCode, response.Body)
}

// GetOllamaSettings obtiene la configuración de Ollama
func GetOllamaSettings(c *gin.Context) {
	response := proxyRequest(c, "http://rag-agent:8085/ollama/settings", "GET", nil)
	c.JSON(response.StatusCode, response.Body)
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

	response := proxyRequest(c, "http://rag-agent:8085/ollama/settings", "PUT", request)
	c.JSON(response.StatusCode, response.Body)
}