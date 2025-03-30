package models

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// DocumentType representa el tipo de documento
type DocumentType string

const (
	// DocumentTypeText representa un documento de texto
	DocumentTypeText DocumentType = "text"
	// DocumentTypePDF representa un documento PDF
	DocumentTypePDF DocumentType = "pdf"
	// DocumentTypeWord representa un documento de Word
	DocumentTypeWord DocumentType = "word"
	// DocumentTypeExcel representa un documento de Excel
	DocumentTypeExcel DocumentType = "excel"
	// DocumentTypeImage representa una imagen
	DocumentTypeImage DocumentType = "image"
	// DocumentTypeOther representa otro tipo de documento
	DocumentTypeOther DocumentType = "other"
)

// DocumentScope representa el ámbito del documento (personal o compartido)
type DocumentScope string

const (
	// DocumentScopePersonal representa un documento personal
	DocumentScopePersonal DocumentScope = "personal"
	// DocumentScopeShared representa un documento compartido
	DocumentScopeShared DocumentScope = "shared"
)

// Document representa un documento en el sistema
type Document struct {
	ID          primitive.ObjectID `bson:"_id,omitempty" json:"id,omitempty"`
	Title       string             `bson:"title" json:"title" binding:"required"`
	Description string             `bson:"description" json:"description"`
	FileName    string             `bson:"file_name" json:"file_name"`
	FileSize    int64              `bson:"file_size" json:"file_size"`
	FileType    string             `bson:"file_type" json:"file_type"`
	DocType     DocumentType       `bson:"doc_type" json:"doc_type"`
	Scope       DocumentScope      `bson:"scope" json:"scope"`
	OwnerID     string             `bson:"owner_id" json:"owner_id"`
	AreaID      string             `bson:"area_id,omitempty" json:"area_id,omitempty"`
	Tags        []string           `bson:"tags" json:"tags"`
	Metadata    map[string]string  `bson:"metadata" json:"metadata"`
	ContentPath string             `bson:"content_path" json:"content_path"`
	CreatedAt   time.Time          `bson:"created_at" json:"created_at"`
	UpdatedAt   time.Time          `bson:"updated_at" json:"updated_at"`
	// Campos para MCP
	EmbeddingID  string `bson:"embedding_id,omitempty" json:"embedding_id,omitempty"`
	MCPContextID string `bson:"mcp_context_id,omitempty" json:"mcp_context_id,omitempty"`
}

// UploadDocumentRequest representa la solicitud para subir un documento
type UploadDocumentRequest struct {
	Title       string            `form:"title" binding:"required"`
	Description string            `form:"description"`
	AreaID      string            `form:"area_id"`
	Tags        string            `form:"tags"`
	Metadata    map[string]string `form:"metadata"`
	// File se maneja como multipart/form-data
}

// UpdateDocumentRequest representa la solicitud para actualizar un documento
type UpdateDocumentRequest struct {
	Title       string            `json:"title,omitempty"`
	Description string            `json:"description,omitempty"`
	AreaID      string            `json:"area_id,omitempty"`
	Tags        []string          `json:"tags,omitempty"`
	Metadata    map[string]string `json:"metadata,omitempty"`
}

// DocumentResponse representa la respuesta con información de un documento
type DocumentResponse struct {
	ID          string            `json:"id"`
	Title       string            `json:"title"`
	Description string            `json:"description"`
	FileName    string            `json:"file_name"`
	FileSize    int64             `json:"file_size"`
	FileType    string            `json:"file_type"`
	DocType     string            `json:"doc_type"`
	Scope       string            `json:"scope"`
	OwnerID     string            `json:"owner_id"`
	AreaID      string            `json:"area_id,omitempty"`
	Tags        []string          `json:"tags"`
	Metadata    map[string]string `json:"metadata"`
	CreatedAt   time.Time         `json:"created_at"`
	UpdatedAt   time.Time         `json:"updated_at"`
	DownloadURL string            `json:"download_url,omitempty"`
}

// ToResponse convierte un Document a DocumentResponse
func (d *Document) ToResponse(downloadURL string) DocumentResponse {
	return DocumentResponse{
		ID:          d.ID.Hex(),
		Title:       d.Title,
		Description: d.Description,
		FileName:    d.FileName,
		FileSize:    d.FileSize,
		FileType:    d.FileType,
		DocType:     string(d.DocType),
		Scope:       string(d.Scope),
		OwnerID:     d.OwnerID,
		AreaID:      d.AreaID,
		Tags:        d.Tags,
		Metadata:    d.Metadata,
		CreatedAt:   d.CreatedAt,
		UpdatedAt:   d.UpdatedAt,
		DownloadURL: downloadURL,
	}
}

// SearchRequest representa la solicitud para buscar documentos
type SearchRequest struct {
	Query    string   `form:"query" binding:"required"`
	Scope    string   `form:"scope"`
	AreaID   string   `form:"area_id"`
	Tags     []string `form:"tags"`
	OwnerID  string   `form:"owner_id"`
	DocTypes []string `form:"doc_types"`
	Limit    int      `form:"limit,default=10"`
	Offset   int      `form:"offset,default=0"`
}

// SearchResult representa un resultado de búsqueda
type SearchResult struct {
	Document   DocumentResponse `json:"document"`
	Score      float64          `json:"score"`
	Highlights []string         `json:"highlights,omitempty"`
}

// SearchResponse representa la respuesta a una búsqueda
type SearchResponse struct {
	Results    []SearchResult `json:"results"`
	TotalCount int            `json:"total_count"`
	Query      string         `json:"query"`
	Offset     int            `json:"offset"`
	Limit      int            `json:"limit"`
}

// EmbeddingRequest representa la solicitud al servicio de embeddings
type EmbeddingRequest struct {
	Text          string                 `json:"text"`
	DocID         string                 `json:"doc_id"`
	OwnerID       string                 `json:"owner_id"`
	AreaID        string                 `json:"area_id,omitempty"`
	Scope         string                 `json:"scope"`
	EmbeddingType string                 `json:"embedding_type"`
	Metadata      map[string]interface{} `json:"metadata,omitempty"`
}

// EmbeddingResponse representa la respuesta del servicio de embeddings
type EmbeddingResponse struct {
	EmbeddingID string `json:"embedding_id"`
	ContextID   string `json:"context_id"`
	Status      string `json:"status"`
}
