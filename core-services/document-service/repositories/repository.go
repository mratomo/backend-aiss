package repositories

import (
	"context"
	"document-service/config"
	"document-service/models"
	"errors"
	"io"
	"mime/multipart"
	"strings"
	"time"

	"github.com/minio/minio-go/v7"
	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// DocumentRepository maneja las operaciones de base de datos para documentos
type DocumentRepository struct {
	collection  *mongo.Collection
	minioClient *minio.Client
	minioConfig config.MinIOConfig
}

// NewDocumentRepository crea un nuevo repositorio de documentos
func NewDocumentRepository(collection *mongo.Collection, minioClient *minio.Client, minioConfig config.MinIOConfig) *DocumentRepository {
	return &DocumentRepository{
		collection:  collection,
		minioClient: minioClient,
		minioConfig: minioConfig,
	}
}

// determineDocType determina el tipo de documento basado en el tipo MIME
func determineDocType(fileType string) models.DocumentType {
	lowerType := strings.ToLower(fileType)

	switch {
	case strings.Contains(lowerType, "text/") || strings.Contains(lowerType, "markdown"):
		return models.DocumentTypeText
	case strings.Contains(lowerType, "pdf"):
		return models.DocumentTypePDF
	case strings.Contains(lowerType, "word") || strings.Contains(lowerType, "docx") || strings.Contains(lowerType, "doc"):
		return models.DocumentTypeWord
	case strings.Contains(lowerType, "excel") || strings.Contains(lowerType, "xlsx") || strings.Contains(lowerType, "xls") || strings.Contains(lowerType, "csv"):
		return models.DocumentTypeExcel
	case strings.Contains(lowerType, "image/"):
		return models.DocumentTypeImage
	default:
		return models.DocumentTypeOther
	}
}

// CreateDocument crea un nuevo documento en la base de datos y almacena el archivo en MinIO
func (r *DocumentRepository) CreateDocument(ctx context.Context, doc *models.Document, file *multipart.FileHeader) (*models.Document, error) {
	// Establecer timestamps
	now := time.Now()
	doc.CreatedAt = now
	doc.UpdatedAt = now

	// Asignar ID
	doc.ID = primitive.NewObjectID()

	// Determinar el tipo de documento
	doc.DocType = determineDocType(file.Header.Get("Content-Type"))

	// Definir la ruta de contenido en MinIO
	var bucket string
	if doc.Scope == models.DocumentScopePersonal {
		bucket = r.minioConfig.PersonalBucket
	} else {
		bucket = r.minioConfig.SharedBucket
	}

	// El nombre del objeto en MinIO será <id>/<nombre_archivo>
	objectName := doc.ID.Hex() + "/" + file.Filename
	doc.ContentPath = objectName

	// Abrir el archivo
	src, err := file.Open()
	if err != nil {
		return nil, err
	}
	defer src.Close()

	// Subir archivo a MinIO
	contentType := file.Header.Get("Content-Type")
	_, err = r.minioClient.PutObject(ctx, bucket, objectName, src, file.Size, minio.PutObjectOptions{
		ContentType: contentType,
	})
	if err != nil {
		return nil, err
	}

	// Guardar documento en MongoDB
	_, err = r.collection.InsertOne(ctx, doc)
	if err != nil {
		// Si hay error, intentar eliminar el archivo de MinIO
		_ = r.minioClient.RemoveObject(ctx, bucket, objectName, minio.RemoveObjectOptions{})
		return nil, err
	}

	return doc, nil
}

// GetDocumentByID obtiene un documento por su ID
func (r *DocumentRepository) GetDocumentByID(ctx context.Context, id string) (*models.Document, error) {
	objectID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return nil, err
	}

	doc := &models.Document{}
	err = r.collection.FindOne(ctx, bson.M{"_id": objectID}).Decode(doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, errors.New("documento no encontrado")
		}
		return nil, err
	}

	return doc, nil
}

// ListPersonalDocuments lista los documentos personales de un usuario
func (r *DocumentRepository) ListPersonalDocuments(ctx context.Context, ownerID string, limit, offset int) ([]*models.Document, int64, error) {
	filter := bson.M{
		"owner_id": ownerID,
		"scope":    models.DocumentScopePersonal,
	}

	// Obtener el total de documentos
	total, err := r.collection.CountDocuments(ctx, filter)
	if err != nil {
		return nil, 0, err
	}

	// Configurar opciones de paginación
	opts := options.Find().
		SetSort(bson.D{{Key: "created_at", Value: -1}}).
		SetSkip(int64(offset)).
		SetLimit(int64(limit))

	// Ejecutar consulta
	cursor, err := r.collection.Find(ctx, filter, opts)
	if err != nil {
		return nil, 0, err
	}
	defer cursor.Close(ctx)

	// Decodificar resultados
	var docs []*models.Document
	if err := cursor.All(ctx, &docs); err != nil {
		return nil, 0, err
	}

	return docs, total, nil
}

// ListSharedDocuments lista los documentos compartidos, opcionalmente filtrado por área
func (r *DocumentRepository) ListSharedDocuments(ctx context.Context, areaID string, limit, offset int) ([]*models.Document, int64, error) {
	filter := bson.M{"scope": models.DocumentScopeShared}

	// Si se especifica área, filtrar por ella
	if areaID != "" {
		filter["area_id"] = areaID
	}

	// Obtener el total de documentos
	total, err := r.collection.CountDocuments(ctx, filter)
	if err != nil {
		return nil, 0, err
	}

	// Configurar opciones de paginación
	opts := options.Find().
		SetSort(bson.D{{Key: "created_at", Value: -1}}).
		SetSkip(int64(offset)).
		SetLimit(int64(limit))

	// Ejecutar consulta
	cursor, err := r.collection.Find(ctx, filter, opts)
	if err != nil {
		return nil, 0, err
	}
	defer cursor.Close(ctx)

	// Decodificar resultados
	var docs []*models.Document
	if err := cursor.All(ctx, &docs); err != nil {
		return nil, 0, err
	}

	return docs, total, nil
}

// UpdateDocument actualiza los metadatos de un documento
func (r *DocumentRepository) UpdateDocument(ctx context.Context, id string, updates *models.UpdateDocumentRequest) (*models.Document, error) {
	objectID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return nil, err
	}

	// Construir el documento de actualización
	updateDoc := bson.M{"updated_at": time.Now()}

	if updates.Title != "" {
		updateDoc["title"] = updates.Title
	}

	if updates.Description != "" {
		updateDoc["description"] = updates.Description
	}

	if updates.AreaID != "" {
		updateDoc["area_id"] = updates.AreaID
	}

	if updates.Tags != nil {
		updateDoc["tags"] = updates.Tags
	}

	if updates.Metadata != nil {
		updateDoc["metadata"] = updates.Metadata
	}

	// Actualizar documento
	filter := bson.M{"_id": objectID}
	update := bson.M{"$set": updateDoc}

	_, err = r.collection.UpdateOne(ctx, filter, update)
	if err != nil {
		return nil, err
	}

	// Obtener documento actualizado
	return r.GetDocumentByID(ctx, id)
}

// DeleteDocument elimina un documento
func (r *DocumentRepository) DeleteDocument(ctx context.Context, id string) error {
	objectID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return err
	}

	// Obtener documento para conocer la ruta en MinIO
	doc := &models.Document{}
	err = r.collection.FindOne(ctx, bson.M{"_id": objectID}).Decode(doc)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return errors.New("documento no encontrado")
		}
		return err
	}

	// Determinar el bucket
	var bucket string
	if doc.Scope == models.DocumentScopePersonal {
		bucket = r.minioConfig.PersonalBucket
	} else {
		bucket = r.minioConfig.SharedBucket
	}

	// Eliminar archivo de MinIO
	err = r.minioClient.RemoveObject(ctx, bucket, doc.ContentPath, minio.RemoveObjectOptions{})
	if err != nil {
		return err
	}

	// Eliminar documento de MongoDB
	_, err = r.collection.DeleteOne(ctx, bson.M{"_id": objectID})
	return err
}

// GetDocumentContent obtiene el contenido de un documento desde MinIO
func (r *DocumentRepository) GetDocumentContent(ctx context.Context, doc *models.Document) (io.ReadCloser, error) {
	var bucket string
	if doc.Scope == models.DocumentScopePersonal {
		bucket = r.minioConfig.PersonalBucket
	} else {
		bucket = r.minioConfig.SharedBucket
	}

	// Obtener objeto de MinIO
	obj, err := r.minioClient.GetObject(ctx, bucket, doc.ContentPath, minio.GetObjectOptions{})
	if err != nil {
		return nil, err
	}

	return obj, nil
}

// GeneratePresignedURL genera una URL prefirmada para descargar un documento
func (r *DocumentRepository) GeneratePresignedURL(ctx context.Context, doc *models.Document, expiry time.Duration) (string, error) {
	var bucket string
	if doc.Scope == models.DocumentScopePersonal {
		bucket = r.minioConfig.PersonalBucket
	} else {
		bucket = r.minioConfig.SharedBucket
	}

	// Generar URL prefirmada
	url, err := r.minioClient.PresignedGetObject(ctx, bucket, doc.ContentPath, expiry, nil)
	if err != nil {
		return "", err
	}

	return url.String(), nil
}

// UpdateEmbeddingInfo actualiza la información de embedding de un documento
func (r *DocumentRepository) UpdateEmbeddingInfo(ctx context.Context, docID string, embeddingID string, contextID string) error {
	objectID, err := primitive.ObjectIDFromHex(docID)
	if err != nil {
		return err
	}

	update := bson.M{
		"$set": bson.M{
			"embedding_id":   embeddingID,
			"mcp_context_id": contextID,
			"updated_at":     time.Now(),
		},
	}

	_, err = r.collection.UpdateOne(ctx, bson.M{"_id": objectID}, update)
	return err
}
