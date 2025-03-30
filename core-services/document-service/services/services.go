package services

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log"
	"mime/multipart"
	"net/http"
	"net/url"
	"os"
	"strings"
	"sync"
	"time"

	"document-service/models"
	"document-service/repositories"
)

// embeddingResult representa el resultado de procesar un embedding (NUEVO)
type embeddingResult struct {
	docID string
	err   error
}

// DocumentService proporciona funcionalidad para operaciones de documentos
type DocumentService struct {
	repo                *repositories.DocumentRepository
	httpClient          *http.Client
	embeddingServiceURL string
	embeddingQueue      chan embeddingTask
	resultChan          chan embeddingResult // NUEVO: Canal para resultados
	wg                  sync.WaitGroup
	errorLog            *log.Logger // NUEVO: Logger dedicado para errores
}

// embeddingTask representa una tarea de generación de embedding
type embeddingTask struct {
	doc    *models.Document
	userID string
	areaID string
}

// NewDocumentService crea un nuevo servicio de documentos
func NewDocumentService(repo *repositories.DocumentRepository, httpClient *http.Client, embeddingServiceURL string) *DocumentService {
	// NUEVO: Configurar logger para errores
	errorLog := log.New(os.Stderr, "ERROR: ", log.Ldate|log.Ltime|log.Lshortfile)

	service := &DocumentService{
		repo:                repo,
		httpClient:          httpClient,
		embeddingServiceURL: embeddingServiceURL,
		embeddingQueue:      make(chan embeddingTask, 100),   // Buffer para 100 tareas
		resultChan:          make(chan embeddingResult, 100), // NUEVO: Canal para resultados
		errorLog:            errorLog,                        // NUEVO: Logger para errores
	}

	// Iniciar 3 trabajadores para procesar embeddings en segundo plano
	for i := 0; i < 3; i++ {
		go service.embeddingWorker()
	}

	// NUEVO: Iniciar worker que procesa los resultados/errores
	go service.processResults()

	return service
}

// processResults procesa los resultados de embeddings y registra errores (NUEVO)
func (s *DocumentService) processResults() {
	for result := range s.resultChan {
		if result.err != nil {
			s.errorLog.Printf("Error procesando embedding para documento %s: %v", result.docID, result.err)
			// Aquí podrías implementar lógica de reintentos, alertas, etc.
		}
	}
}

// embeddingWorker procesa tareas de embedding en segundo plano
func (s *DocumentService) embeddingWorker() {
	for task := range s.embeddingQueue {
		s.processEmbedding(task.doc, task.userID, task.areaID)
	}
}

// UploadPersonalDocument sube un documento personal
func (s *DocumentService) UploadPersonalDocument(
	ctx context.Context,
	userID string,
	req *models.UploadDocumentRequest,
	file io.Reader,
	fileHeader *multipart.FileHeader,
) (*models.DocumentResponse, error) {

	doc := &models.Document{
		Title:       req.Title,
		Description: req.Description,
		FileName:    fileHeader.Filename,
		FileSize:    fileHeader.Size,
		FileType:    fileHeader.Header.Get("Content-Type"),
		Scope:       models.DocumentScopePersonal,
		OwnerID:     userID,
	}

	// Procesar etiquetas
	if req.Tags != "" {
		tagList := strings.Split(req.Tags, ",")
		for i, tag := range tagList {
			tagList[i] = strings.TrimSpace(tag)
		}
		doc.Tags = tagList
	}

	// Crear documento en la base de datos y almacenar archivo en MinIO
	createdDoc, err := s.repo.CreateDocument(ctx, doc, fileHeader)
	if err != nil {
		return nil, err
	}

	// Generar URL prefirmada de descarga (opcional, no crítico)
	downloadURL, err := s.generateDownloadURL(ctx, createdDoc)
	if err != nil {
		downloadURL = ""
	}

	// Agregar tarea de embedding en segundo plano
	s.wg.Add(1)
	s.embeddingQueue <- embeddingTask{
		doc:    createdDoc,
		userID: userID,
		areaID: "",
	}

	response := createdDoc.ToResponse(downloadURL)
	return &response, nil
}

// GetPersonalDocument obtiene un documento personal
func (s *DocumentService) GetPersonalDocument(
	ctx context.Context,
	docID string,
	userID string,
) (*models.DocumentResponse, error) {

	doc, err := s.repo.GetDocumentByID(ctx, docID)
	if err != nil {
		return nil, err
	}

	if doc.Scope != models.DocumentScopePersonal {
		return nil, errors.New("el documento no es personal")
	}
	if doc.OwnerID != userID {
		return nil, errors.New("no autorizado para acceder a este documento")
	}

	downloadURL, err := s.generateDownloadURL(ctx, doc)
	if err != nil {
		downloadURL = ""
	}

	response := doc.ToResponse(downloadURL)
	return &response, nil
}

// ListPersonalDocuments lista los documentos personales de un usuario
func (s *DocumentService) ListPersonalDocuments(
	ctx context.Context,
	userID string,
	limit, offset int,
) ([]models.DocumentResponse, int64, error) {

	docs, total, err := s.repo.ListPersonalDocuments(ctx, userID, limit, offset)
	if err != nil {
		return nil, 0, err
	}

	responses := make([]models.DocumentResponse, len(docs))
	for i, doc := range docs {
		downloadURL, _ := s.generateDownloadURL(ctx, doc)
		responses[i] = doc.ToResponse(downloadURL)
	}

	return responses, total, nil
}

// DeletePersonalDocument elimina un documento personal
func (s *DocumentService) DeletePersonalDocument(
	ctx context.Context,
	docID string,
	userID string,
) error {

	doc, err := s.repo.GetDocumentByID(ctx, docID)
	if err != nil {
		return err
	}

	if doc.Scope != models.DocumentScopePersonal {
		return errors.New("el documento no es personal")
	}
	if doc.OwnerID != userID {
		return errors.New("no autorizado para eliminar este documento")
	}

	return s.repo.DeleteDocument(ctx, docID)
}

// UploadSharedDocument sube un documento compartido (admin)
func (s *DocumentService) UploadSharedDocument(
	ctx context.Context,
	userID string,
	req *models.UploadDocumentRequest,
	file io.Reader,
	fileHeader *multipart.FileHeader,
) (*models.DocumentResponse, error) {

	doc := &models.Document{
		Title:       req.Title,
		Description: req.Description,
		FileName:    fileHeader.Filename,
		FileSize:    fileHeader.Size,
		FileType:    fileHeader.Header.Get("Content-Type"),
		Scope:       models.DocumentScopeShared,
		OwnerID:     userID,
		AreaID:      req.AreaID,
	}

	// Procesar etiquetas
	if req.Tags != "" {
		tagList := strings.Split(req.Tags, ",")
		for i, tag := range tagList {
			tagList[i] = strings.TrimSpace(tag)
		}
		doc.Tags = tagList
	}

	// Procesar metadatos
	if req.Metadata != nil {
		doc.Metadata = req.Metadata
	}

	// Crear documento y guardar en MinIO
	createdDoc, err := s.repo.CreateDocument(ctx, doc, fileHeader)
	if err != nil {
		return nil, err
	}

	downloadURL, err := s.generateDownloadURL(ctx, createdDoc)
	if err != nil {
		downloadURL = ""
	}

	// Agregar tarea de embedding en segundo plano
	s.wg.Add(1)
	s.embeddingQueue <- embeddingTask{
		doc:    createdDoc,
		userID: userID,
		areaID: req.AreaID,
	}

	response := createdDoc.ToResponse(downloadURL)
	return &response, nil
}

// GetSharedDocument obtiene un documento compartido
func (s *DocumentService) GetSharedDocument(
	ctx context.Context,
	docID string,
) (*models.DocumentResponse, error) {

	doc, err := s.repo.GetDocumentByID(ctx, docID)
	if err != nil {
		return nil, err
	}

	if doc.Scope != models.DocumentScopeShared {
		return nil, errors.New("el documento no es compartido")
	}

	downloadURL, err := s.generateDownloadURL(ctx, doc)
	if err != nil {
		downloadURL = ""
	}

	response := doc.ToResponse(downloadURL)
	return &response, nil
}

// ListSharedDocuments lista los documentos compartidos
func (s *DocumentService) ListSharedDocuments(
	ctx context.Context,
	areaID string,
	limit, offset int,
) ([]models.DocumentResponse, int64, error) {

	docs, total, err := s.repo.ListSharedDocuments(ctx, areaID, limit, offset)
	if err != nil {
		return nil, 0, err
	}

	responses := make([]models.DocumentResponse, len(docs))
	for i, doc := range docs {
		downloadURL, _ := s.generateDownloadURL(ctx, doc)
		responses[i] = doc.ToResponse(downloadURL)
	}

	return responses, total, nil
}

// UpdateSharedDocument actualiza un documento compartido
func (s *DocumentService) UpdateSharedDocument(
	ctx context.Context,
	docID string,
	req *models.UpdateDocumentRequest,
) (*models.DocumentResponse, error) {

	doc, err := s.repo.GetDocumentByID(ctx, docID)
	if err != nil {
		return nil, err
	}
	if doc.Scope != models.DocumentScopeShared {
		return nil, errors.New("el documento no es compartido")
	}

	updatedDoc, err := s.repo.UpdateDocument(ctx, docID, req)
	if err != nil {
		return nil, err
	}

	downloadURL, err := s.generateDownloadURL(ctx, updatedDoc)
	if err != nil {
		downloadURL = ""
	}

	response := updatedDoc.ToResponse(downloadURL)
	return &response, nil
}

// DeleteSharedDocument elimina un documento compartido
func (s *DocumentService) DeleteSharedDocument(
	ctx context.Context,
	docID string,
) error {

	doc, err := s.repo.GetDocumentByID(ctx, docID)
	if err != nil {
		return err
	}
	if doc.Scope != models.DocumentScopeShared {
		return errors.New("el documento no es compartido")
	}

	return s.repo.DeleteDocument(ctx, docID)
}

// GetDocumentContent obtiene el contenido de un documento desde MinIO
func (s *DocumentService) GetDocumentContent(
	ctx context.Context,
	docID string,
) (io.ReadCloser, string, string, error) {

	// 1) Obtener el documento real
	doc, err := s.repo.GetDocumentByID(ctx, docID)
	if err != nil {
		return nil, "", "", err
	}

	// 2) Obtener contenido de MinIO
	content, err := s.repo.GetDocumentContent(ctx, doc)
	if err != nil {
		return nil, "", "", err
	}

	return content, doc.FileType, doc.FileName, nil
}

// SearchDocuments realiza búsqueda semántica en documentos
func (s *DocumentService) SearchDocuments(
	ctx context.Context,
	req *models.SearchRequest,
) (*models.SearchResponse, error) {

	if req.Query == "" {
		return nil, errors.New("consulta vacía")
	}

	embeddingType := "general"
	if req.Scope == "personal" {
		embeddingType = "personal"
	}

	// Construir la URL con parámetros
	searchURL := fmt.Sprintf("%s/search?query=%s&embedding_type=%s&limit=%d",
		s.embeddingServiceURL,
		url.QueryEscape(req.Query),
		embeddingType,
		req.Limit,
	)

	// Añadir filtros
	if req.OwnerID != "" {
		searchURL += "&owner_id=" + url.QueryEscape(req.OwnerID)
	}
	if req.AreaID != "" {
		searchURL += "&area_id=" + url.QueryEscape(req.AreaID)
	}

	resp, err := s.httpClient.Get(searchURL)
	if err != nil {
		return nil, fmt.Errorf("error al conectar con servicio de embeddings: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		bodyBytes, _ := io.ReadAll(resp.Body)
		return nil, fmt.Errorf("error del servicio de embeddings: %s", string(bodyBytes))
	}

	var embeddingResults struct {
		Results []struct {
			EmbeddingID string                 `json:"embedding_id"`
			DocID       string                 `json:"doc_id"`
			Score       float64                `json:"score"`
			Text        string                 `json:"text"`
			Metadata    map[string]interface{} `json:"metadata"`
		} `json:"results"`
	}
	if err := json.NewDecoder(resp.Body).Decode(&embeddingResults); err != nil {
		return nil, fmt.Errorf("error al decodificar respuesta: %w", err)
	}

	var searchResults []models.SearchResult
	for _, result := range embeddingResults.Results {
		// Buscar el documento real
		doc, err := s.repo.GetDocumentByID(ctx, result.DocID)
		if err != nil {
			// Omitir si hay error
			continue
		}

		// Filtrar si es personal y no pertenece al usuario
		if req.Scope == "personal" && req.OwnerID != "" && doc.OwnerID != req.OwnerID {
			continue
		}
		// Filtrar por área
		if req.AreaID != "" && doc.AreaID != req.AreaID {
			continue
		}
		// Filtrar etiquetas
		if len(req.Tags) > 0 {
			hasTag := false
			for _, tag := range req.Tags {
				for _, docTag := range doc.Tags {
					if strings.EqualFold(tag, docTag) {
						hasTag = true
						break
					}
				}
				if hasTag {
					break
				}
			}
			if !hasTag {
				continue
			}
		}
		// Filtrar tipo de documento
		if len(req.DocTypes) > 0 {
			docTypeStr := string(doc.DocType)
			docTypeMatches := false
			for _, reqType := range req.DocTypes {
				if strings.EqualFold(reqType, docTypeStr) {
					docTypeMatches = true
					break
				}
			}
			if !docTypeMatches {
				continue
			}
		}

		// Generar URL de descarga (opcional)
		downloadURL, _ := s.generateDownloadURL(ctx, doc)
		docResponse := doc.ToResponse(downloadURL)

		searchResult := models.SearchResult{
			Document:   docResponse,
			Score:      result.Score,
			Highlights: []string{result.Text},
		}
		searchResults = append(searchResults, searchResult)
	}

	response := &models.SearchResponse{
		Results:    searchResults,
		TotalCount: len(searchResults),
		Query:      req.Query,
		Offset:     req.Offset,
		Limit:      req.Limit,
	}

	return response, nil
}

// generateDownloadURL genera una URL presignada para descargar el contenido de un documento
func (s *DocumentService) generateDownloadURL(ctx context.Context, doc *models.Document) (string, error) {
	return s.repo.GeneratePresignedURL(ctx, doc, 1*time.Hour)
}

// processEmbedding procesa la generación de embeddings para un documento (NUEVO: maneja errores con resultChan)
func (s *DocumentService) processEmbedding(doc *models.Document, userID, areaID string) {
	defer s.wg.Done()

	ctx, cancel := context.WithTimeout(context.Background(), 5*time.Minute)
	defer cancel()

	embeddingType := "general"
	if doc.Scope == models.DocumentScopePersonal {
		embeddingType = "personal"
	}

	content, err := s.repo.GetDocumentContent(ctx, doc)
	if err != nil {
		select {
		case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: fmt.Errorf("error al obtener contenido: %w", err)}:
		default:
			s.errorLog.Printf("Error al obtener contenido para documento %s: %v", doc.ID.Hex(), err)
		}
		return
	}
	defer content.Close()

	fileContent, err := io.ReadAll(content)
	if err != nil {
		select {
		case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: fmt.Errorf("error al leer contenido: %w", err)}:
		default:
			s.errorLog.Printf("Error al leer contenido para documento %s: %v", doc.ID.Hex(), err)
		}
		return
	}

	reqBody := models.EmbeddingRequest{
		Text:          string(fileContent),
		DocID:         doc.ID.Hex(),
		OwnerID:       userID,
		AreaID:        areaID,
		Scope:         string(doc.Scope),
		EmbeddingType: embeddingType,
		Metadata: map[string]interface{}{
			"title":       doc.Title,
			"description": doc.Description,
			"file_name":   doc.FileName,
			"file_type":   doc.FileType,
			"doc_type":    string(doc.DocType),
			"tags":        doc.Tags,
		},
	}

	jsonData, err := json.Marshal(reqBody)
	if err != nil {
		select {
		case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: fmt.Errorf("error al serializar solicitud: %w", err)}:
		default:
			s.errorLog.Printf("Error al serializar solicitud para documento %s: %v", doc.ID.Hex(), err)
		}
		return
	}

	resp, err := s.httpClient.Post(
		s.embeddingServiceURL+"/embeddings/document",
		"application/json",
		bytes.NewBuffer(jsonData),
	)
	if err != nil {
		select {
		case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: fmt.Errorf("error al llamar servicio de embeddings: %w", err)}:
		default:
			s.errorLog.Printf("Error al llamar servicio de embeddings para documento %s: %v", doc.ID.Hex(), err)
		}
		return
	}
	defer resp.Body.Close()

	if resp.StatusCode >= 400 {
		bodyBytes, _ := io.ReadAll(resp.Body)
		errMsg := fmt.Sprintf("error HTTP %d: %s", resp.StatusCode, string(bodyBytes))
		select {
		case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: errors.New(errMsg)}:
		default:
			s.errorLog.Printf("Error HTTP para documento %s: %s", doc.ID.Hex(), errMsg)
		}
		return
	}

	respBody, err := io.ReadAll(resp.Body)
	if err != nil {
		select {
		case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: fmt.Errorf("error al leer respuesta: %w", err)}:
		default:
			s.errorLog.Printf("Error al leer respuesta para documento %s: %v", doc.ID.Hex(), err)
		}
		return
	}

	var embeddingResp models.EmbeddingResponse
	if err := json.Unmarshal(respBody, &embeddingResp); err != nil {
		select {
		case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: fmt.Errorf("error al decodificar respuesta: %w", err)}:
		default:
			s.errorLog.Printf("Error al decodificar respuesta para documento %s: %v", doc.ID.Hex(), err)
		}
		return
	}

	err = s.repo.UpdateEmbeddingInfo(ctx, doc.ID.Hex(), embeddingResp.EmbeddingID, embeddingResp.ContextID)
	if err != nil {
		select {
		case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: fmt.Errorf("error al actualizar info de embedding: %w", err)}:
		default:
			s.errorLog.Printf("Error al actualizar info de embedding para documento %s: %v", doc.ID.Hex(), err)
		}
		return
	}

	// Reportar éxito (opcional)
	select {
	case s.resultChan <- embeddingResult{docID: doc.ID.Hex(), err: nil}:
	default:
		// Si el canal está lleno, no hacemos nada
	}
}

// Shutdown cierra el servicio de documentos de forma ordenada
func (s *DocumentService) Shutdown() {
	close(s.embeddingQueue)
	s.wg.Wait()
	close(s.resultChan) // NUEVO: Cerrar canal de resultados
}
