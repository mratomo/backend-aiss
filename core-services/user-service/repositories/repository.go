package repositories

import (
	"context"
	"errors"
	"time"
	"user-service/models"

	"go.mongodb.org/mongo-driver/bson"
	"go.mongodb.org/mongo-driver/bson/primitive"
	"go.mongodb.org/mongo-driver/mongo"
	"go.mongodb.org/mongo-driver/mongo/options"
)

// UserRepository maneja las operaciones de base de datos para usuarios
type UserRepository struct {
	collection *mongo.Collection
}

// NewUserRepository crea un nuevo repositorio de usuarios
func NewUserRepository(collection *mongo.Collection) *UserRepository {
	return &UserRepository{
		collection: collection,
	}
}

// CreateUser crea un nuevo usuario en la base de datos
func (r *UserRepository) CreateUser(ctx context.Context, user *models.User) (*models.User, error) {
	// Establecer timestamps
	now := time.Now()
	user.CreatedAt = now
	user.UpdatedAt = now

	// Validar si ya existe un usuario con el mismo username o email
	existing := &models.User{}
	filter := bson.M{
		"$or": []bson.M{
			{"username": user.Username},
			{"email": user.Email},
		},
	}

	err := r.collection.FindOne(ctx, filter).Decode(existing)
	if err == nil {
		// Ya existe un usuario con ese username o email
		return nil, errors.New("ya existe un usuario con ese nombre de usuario o email")
	} else if err != mongo.ErrNoDocuments {
		// Error diferente a "no documento encontrado"
		return nil, err
	}

	// Insertar el usuario
	result, err := r.collection.InsertOne(ctx, user)
	if err != nil {
		return nil, err
	}

	// Obtener el ID generado
	user.ID = result.InsertedID.(primitive.ObjectID)

	return user, nil
}

// GetUserByID obtiene un usuario por su ID
func (r *UserRepository) GetUserByID(ctx context.Context, id string) (*models.User, error) {
	objectID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return nil, err
	}

	user := &models.User{}
	err = r.collection.FindOne(ctx, bson.M{"_id": objectID}).Decode(user)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, errors.New("usuario no encontrado")
		}
		return nil, err
	}

	return user, nil
}

// GetUserByUsername obtiene un usuario por su nombre de usuario
func (r *UserRepository) GetUserByUsername(ctx context.Context, username string) (*models.User, error) {
	user := &models.User{}
	err := r.collection.FindOne(ctx, bson.M{"username": username}).Decode(user)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, errors.New("usuario no encontrado")
		}
		return nil, err
	}

	return user, nil
}

// GetUserByEmail obtiene un usuario por su email
func (r *UserRepository) GetUserByEmail(ctx context.Context, email string) (*models.User, error) {
	user := &models.User{}
	err := r.collection.FindOne(ctx, bson.M{"email": email}).Decode(user)
	if err != nil {
		if err == mongo.ErrNoDocuments {
			return nil, errors.New("usuario no encontrado")
		}
		return nil, err
	}

	return user, nil
}

// GetAllUsers obtiene todos los usuarios
func (r *UserRepository) GetAllUsers(ctx context.Context) ([]*models.User, error) {
	opts := options.Find().SetSort(bson.D{{Key: "username", Value: 1}})
	cursor, err := r.collection.Find(ctx, bson.M{}, opts)
	if err != nil {
		return nil, err
	}
	defer cursor.Close(ctx)

	var users []*models.User
	if err := cursor.All(ctx, &users); err != nil {
		return nil, err
	}

	return users, nil
}

// UpdateUser actualiza un usuario
func (r *UserRepository) UpdateUser(ctx context.Context, user *models.User) error {
	user.UpdatedAt = time.Now()

	filter := bson.M{"_id": user.ID}
	_, err := r.collection.ReplaceOne(ctx, filter, user)
	return err
}

// UpdateUserPartial actualiza campos específicos de un usuario
func (r *UserRepository) UpdateUserPartial(ctx context.Context, id string, updates bson.M) error {
	objectID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return err
	}

	// Añadir timestamp de actualización
	updates["updated_at"] = time.Now()

	filter := bson.M{"_id": objectID}
	update := bson.M{"$set": updates}

	_, err = r.collection.UpdateOne(ctx, filter, update)
	return err
}

// DeleteUser elimina un usuario
func (r *UserRepository) DeleteUser(ctx context.Context, id string) error {
	objectID, err := primitive.ObjectIDFromHex(id)
	if err != nil {
		return err
	}

	filter := bson.M{"_id": objectID}
	result, err := r.collection.DeleteOne(ctx, filter)
	if err != nil {
		return err
	}

	if result.DeletedCount == 0 {
		return errors.New("usuario no encontrado")
	}

	return nil
}

// UpdateLastLogin actualiza la fecha de último login
func (r *UserRepository) UpdateLastLogin(ctx context.Context, id primitive.ObjectID) error {
	now := time.Now()
	filter := bson.M{"_id": id}
	update := bson.M{"$set": bson.M{"last_login": now, "updated_at": now}}

	_, err := r.collection.UpdateOne(ctx, filter, update)
	return err
}

// CountUsers cuenta el número total de usuarios
func (r *UserRepository) CountUsers(ctx context.Context) (int64, error) {
	return r.collection.CountDocuments(ctx, bson.M{})
}

// CreateFirstAdminIfNeeded verifica si hay usuarios y crea el primer admin si no hay
// Usa operaciones atómicas para evitar race conditions en entornos multi-instancia
func (r *UserRepository) CreateFirstAdminIfNeeded(ctx context.Context, username, email string) (bool, error) {
	// Preparar un administrador por defecto
	now := time.Now()
	admin := models.User{
		Username:        username,
		Email:           email,
		Role:            "admin",
		Active:          true,
		AreaPermissions: make(map[string]models.Permission),
		CreatedAt:       now,
		UpdatedAt:       now,
		// La contraseña se establecerá después
	}

	// Usar FindOneAndUpdate con upsert para crear el admin solo si no hay usuarios
	// Esta operación es atómica y evita race conditions
	filter := bson.M{"role": "admin"} // Buscar cualquier admin
	update := bson.M{"$setOnInsert": admin}

	opts := options.FindOneAndUpdate().
		SetUpsert(true).
		SetReturnDocument(options.After)

	result := r.collection.FindOneAndUpdate(ctx, filter, update, opts)

	// Si hay error, no es NoDocuments, es un error real
	if result.Err() != nil && result.Err() != mongo.ErrNoDocuments {
		return false, result.Err()
	}

	// Si no hay error, se creó un nuevo admin o ya existía uno
	var existingAdmin models.User
	err := result.Decode(&existingAdmin)

	// Si hay error al decodificar, algo salió mal
	if err != nil {
		return false, err
	}

	// Si el ID es válido, se encontró o creó un admin
	return !existingAdmin.ID.IsZero(), nil
}

// UpdateUserPermissions actualiza los permisos de un usuario para un área específica
func (r *UserRepository) UpdateUserPermissions(ctx context.Context, userID string, areaID string, permission models.Permission) error {
	objectID, err := primitive.ObjectIDFromHex(userID)
	if err != nil {
		return err
	}

	filter := bson.M{"_id": objectID}
	update := bson.M{
		"$set": bson.M{
			"area_permissions." + areaID: permission,
			"updated_at":                 time.Now(),
		},
	}

	_, err = r.collection.UpdateOne(ctx, filter, update)
	return err
}
