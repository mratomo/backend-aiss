package controllers

import (
	"context"
	"document-service/models"
	"document-service/services"
	"html"
	"io"
	"net/http"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

// DocumentController gestiona las solicitudes relacionadas con documentos
type DocumentController struct {
	docService *services.DocumentService
}

// NewDocumentController crea un nuevo controlador de documentos
func NewDocumentController(docService *services.DocumentService) *DocumentController {
	return &DocumentController{
		docService: docService,
	}
}

// extractUserID extrae el ID de usuario del token JWT
func extractUserID(c *gin.Context) string {
	userID, exists := c.Get("userID")
	if !exists {
		return ""
	}
	if id, ok := userID.(string); ok {
		return id
	}
	return ""
}

// ListPersonalDocuments lista los documentos personales del usuario
func (ctrl *DocumentController) ListPersonalDocuments(c *gin.Context) {
	userID := extractUserID(c)
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
		return
	}

	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	docs, total, err := ctrl.docService.ListPersonalDocuments(ctx, userID, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	response := gin.H{
		"documents":   docs,
		"total":       total,
		"limit":       limit,
		"offset":      offset,
		"page":        offset/limit + 1,
		"total_pages": (int(total) + limit - 1) / limit,
	}

	c.JSON(http.StatusOK, response)
}

// UploadPersonalDocument sube un nuevo documento personal
func (ctrl *DocumentController) UploadPersonalDocument(c *gin.Context) {
	// Extraer ID de usuario
	userID := extractUserID(c)
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
		return
	}

	// Obtener archivo
	file, fileHeader, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "archivo no proporcionado: " + err.Error()})
		return
	}
	defer file.Close()

	// NUEVO: Validar tamaño de archivo (máximo 50MB)
	const maxSize = 50 * 1024 * 1024 // 50MB
	if fileHeader.Size > maxSize {
		c.JSON(http.StatusBadRequest, gin.H{"error": "el archivo es demasiado grande, máximo 50MB"})
		return
	}

	// NUEVO: Validar tipo de archivo
	contentType := fileHeader.Header.Get("Content-Type")
	if !isValidFileType(contentType) {
		c.JSON(http.StatusBadRequest, gin.H{"error": "tipo de archivo no permitido: " + contentType})
		return
	}

	// Obtener metadatos del formulario
	title := c.PostForm("title")
	if title == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "título requerido"})
		return
	}

	// NUEVO: Validar longitud del título
	if len(title) > 200 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "el título no puede exceder 200 caracteres"})
		return
	}

	description := c.PostForm("description")

	// NUEVO: Validar longitud de descripción
	if len(description) > 1000 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "la descripción no puede exceder 1000 caracteres"})
		return
	}

	// Procesar etiquetas
	var tags []string
	if tagsStr := c.PostForm("tags"); tagsStr != "" {
		tags = strings.Split(tagsStr, ",")
		for i, tag := range tags {
			// NUEVO: Sanitizar etiquetas
			tag = strings.TrimSpace(tag)
			// NUEVO: Validar etiquetas
			if len(tag) > 50 {
				c.JSON(http.StatusBadRequest, gin.H{"error": "las etiquetas no pueden exceder 50 caracteres"})
				return
			}
			if tag == "" {
				continue // Omitir etiquetas vacías
			}
			tags[i] = tag
		}
	}

	// NUEVO: Validar cantidad de etiquetas
	if len(tags) > 20 {
		c.JSON(http.StatusBadRequest, gin.H{"error": "no se permite más de 20 etiquetas"})
		return
	}

	// Crear solicitud
	req := &models.UploadDocumentRequest{
		Title:       sanitizeString(title),       // NUEVO: Sanitizar título
		Description: sanitizeString(description), // NUEVO: Sanitizar descripción
		Tags:        strings.Join(tags, ","),
	}

	// Crear contexto con timeout extendido para archivos grandes
	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	// Subir documento
	doc, uploadErr := ctrl.docService.UploadPersonalDocument(ctx, userID, req, file, fileHeader)
	if uploadErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": uploadErr.Error()})
		return
	}

	c.JSON(http.StatusCreated, doc)
}

// GetPersonalDocument obtiene información de un documento personal
func (ctrl *DocumentController) GetPersonalDocument(c *gin.Context) {
	userID := extractUserID(c)
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
		return
	}

	docID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	doc, err := ctrl.docService.GetPersonalDocument(ctx, docID, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, doc)
}

// GetPersonalDocumentContent descarga el contenido de un documento personal
func (ctrl *DocumentController) GetPersonalDocumentContent(c *gin.Context) {
	userID := extractUserID(c)
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
		return
	}

	docID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	// Primero, obtener la info del documento
	doc, err := ctrl.docService.GetPersonalDocument(ctx, docID, userID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	// Llamamos a GetDocumentContent con doc.ID (string)
	content, contentType, fileName, getErr := ctrl.docService.GetDocumentContent(ctx, doc.ID)
	if getErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al obtener contenido: " + getErr.Error()})
		return
	}
	defer content.Close()

	c.Header("Content-Disposition", "attachment; filename="+fileName)
	c.Header("Content-Type", contentType)
	c.Status(http.StatusOK)

	if _, copyErr := io.Copy(c.Writer, content); copyErr != nil {
		// Generalmente, significa que el cliente cerró la conexión
		return
	}
}

// DeletePersonalDocument elimina un documento personal
func (ctrl *DocumentController) DeletePersonalDocument(c *gin.Context) {
	userID := extractUserID(c)
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
		return
	}

	docID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	err := ctrl.docService.DeletePersonalDocument(ctx, docID, userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.Status(http.StatusNoContent)
}

// ListSharedDocuments lista los documentos compartidos
func (ctrl *DocumentController) ListSharedDocuments(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "10"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	areaID := c.Query("area_id")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	docs, total, err := ctrl.docService.ListSharedDocuments(ctx, areaID, limit, offset)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	response := gin.H{
		"documents":   docs,
		"total":       total,
		"limit":       limit,
		"offset":      offset,
		"page":        offset/limit + 1,
		"total_pages": (int(total) + limit - 1) / limit,
	}

	c.JSON(http.StatusOK, response)
}

// GetSharedDocument obtiene información de un documento compartido
func (ctrl *DocumentController) GetSharedDocument(c *gin.Context) {
	docID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	doc, err := ctrl.docService.GetSharedDocument(ctx, docID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, doc)
}

// GetSharedDocumentContent descarga el contenido de un documento compartido
func (ctrl *DocumentController) GetSharedDocumentContent(c *gin.Context) {
	docID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Minute)
	defer cancel()

	doc, err := ctrl.docService.GetSharedDocument(ctx, docID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	content, contentType, fileName, getErr := ctrl.docService.GetDocumentContent(ctx, doc.ID)
	if getErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "error al obtener contenido: " + getErr.Error()})
		return
	}
	defer content.Close()

	c.Header("Content-Disposition", "attachment; filename="+fileName)
	c.Header("Content-Type", contentType)
	c.Status(http.StatusOK)

	if _, copyErr := io.Copy(c.Writer, content); copyErr != nil {
		return
	}
}

// UploadSharedDocument sube un nuevo documento compartido (admin)
func (ctrl *DocumentController) UploadSharedDocument(c *gin.Context) {
	userID := extractUserID(c)
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
		return
	}

	file, fileHeader, err := c.Request.FormFile("file")
	if err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "archivo no proporcionado: " + err.Error()})
		return
	}
	defer file.Close()

	title := c.PostForm("title")
	if title == "" {
		c.JSON(http.StatusBadRequest, gin.H{"error": "título requerido"})
		return
	}

	description := c.PostForm("description")
	areaID := c.PostForm("area_id")

	var tags []string
	if tagsStr := c.PostForm("tags"); tagsStr != "" {
		tags = strings.Split(tagsStr, ",")
		for i, tag := range tags {
			tags[i] = strings.TrimSpace(tag)
		}
	}

	req := &models.UploadDocumentRequest{
		Title:       title,
		Description: description,
		AreaID:      areaID,
		Tags:        strings.Join(tags, ","),
	}

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	doc, uploadErr := ctrl.docService.UploadSharedDocument(ctx, userID, req, file, fileHeader)
	if uploadErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": uploadErr.Error()})
		return
	}

	c.JSON(http.StatusCreated, doc)
}

// UpdateSharedDocument actualiza un documento compartido (admin)
func (ctrl *DocumentController) UpdateSharedDocument(c *gin.Context) {
	userID := extractUserID(c)
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
		return
	}

	docID := c.Param("id")

	var req models.UpdateDocumentRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	doc, updateErr := ctrl.docService.UpdateSharedDocument(ctx, docID, &req)
	if updateErr != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": updateErr.Error()})
		return
	}

	c.JSON(http.StatusOK, doc)
}

// DeleteSharedDocument elimina un documento compartido (admin)
func (ctrl *DocumentController) DeleteSharedDocument(c *gin.Context) {
	userID := extractUserID(c)
	if userID == "" {
		c.JSON(http.StatusUnauthorized, gin.H{"error": "usuario no autenticado"})
		return
	}

	docID := c.Param("id")

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	if err := ctrl.docService.DeleteSharedDocument(ctx, docID); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.Status(http.StatusNoContent)
}

// SearchDocuments busca documentos
func (ctrl *DocumentController) SearchDocuments(c *gin.Context) {
	userID := extractUserID(c)

	var searchReq models.SearchRequest
	searchReq.Query = c.Query("query")
	searchReq.Scope = c.Query("scope")
	searchReq.AreaID = c.Query("area_id")
	searchReq.OwnerID = c.Query("owner_id")

	if searchReq.OwnerID == "" && searchReq.Scope == "personal" && userID != "" {
		searchReq.OwnerID = userID
	}

	if tagsStr := c.Query("tags"); tagsStr != "" {
		searchReq.Tags = strings.Split(tagsStr, ",")
		for i, tag := range searchReq.Tags {
			searchReq.Tags[i] = strings.TrimSpace(tag)
		}
	}

	if docTypesStr := c.Query("doc_types"); docTypesStr != "" {
		searchReq.DocTypes = strings.Split(docTypesStr, ",")
		for i, docType := range searchReq.DocTypes {
			searchReq.DocTypes[i] = strings.TrimSpace(docType)
		}
	}

	searchReq.Limit, _ = strconv.Atoi(c.DefaultQuery("limit", "10"))
	searchReq.Offset, _ = strconv.Atoi(c.DefaultQuery("offset", "0"))

	ctx, cancel := context.WithTimeout(context.Background(), 30*time.Second)
	defer cancel()

	results, err := ctrl.docService.SearchDocuments(ctx, &searchReq)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, results)
}

// NUEVO: Función para validar tipos de archivo permitidos
func isValidFileType(contentType string) bool {
	allowedTypes := map[string]bool{
		"application/pdf":    true,
		"application/msword": true,
		"application/vnd.openxmlformats-officedocument.wordprocessingml.document": true,
		"application/vnd.ms-excel": true,
		"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": true,
		"text/plain":       true,
		"text/csv":         true,
		"text/markdown":    true,
		"application/json": true,
		"image/jpeg":       true,
		"image/png":        true,
		"image/gif":        true,
	}

	return allowedTypes[contentType]
}

// NUEVO: Función para sanitizar strings y prevenir inyecciones
// sanitizeString limpia la entrada para prevenir inyecciones HTML.
func sanitizeString(input string) string {
	// Recorta espacios en blanco y escapa caracteres especiales para HTML
	return html.EscapeString(strings.TrimSpace(input))
}
