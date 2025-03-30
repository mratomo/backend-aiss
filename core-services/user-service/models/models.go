package models

import (
	"time"

	"go.mongodb.org/mongo-driver/bson/primitive"
)

// User representa un usuario en el sistema
type User struct {
	ID              primitive.ObjectID    `bson:"_id,omitempty" json:"id,omitempty"`
	Username        string                `bson:"username" json:"username" binding:"required"`
	Email           string                `bson:"email" json:"email" binding:"required,email"`
	PasswordHash    string                `bson:"password_hash" json:"-"`
	Role            string                `bson:"role" json:"role"` // admin, user
	Active          bool                  `bson:"active" json:"active"`
	CreatedAt       time.Time             `bson:"created_at" json:"created_at"`
	UpdatedAt       time.Time             `bson:"updated_at" json:"updated_at"`
	LastLogin       *time.Time            `bson:"last_login,omitempty" json:"last_login,omitempty"`
	AreaPermissions map[string]Permission `bson:"area_permissions" json:"area_permissions"`
}

// Permission define los permisos de un usuario para un área específica
type Permission struct {
	Read  bool `bson:"read" json:"read"`
	Write bool `bson:"write" json:"write"`
}

// UserRegisterRequest representa la solicitud para registrar un nuevo usuario
type UserRegisterRequest struct {
	Username string `json:"username" binding:"required"`
	Email    string `json:"email" binding:"required,email"`
	Password string `json:"password" binding:"required,min=8"`
}

// UserLoginRequest representa la solicitud para iniciar sesión
type UserLoginRequest struct {
	Username string `json:"username" binding:"required"`
	Password string `json:"password" binding:"required"`
}

// TokenResponse representa la respuesta con tokens de autenticación
type TokenResponse struct {
	AccessToken  string `json:"access_token"`
	RefreshToken string `json:"refresh_token"`
	ExpiresIn    int    `json:"expires_in"` // Tiempo de expiración en segundos
	TokenType    string `json:"token_type"`
}

// RefreshTokenRequest representa la solicitud para refrescar el token
type RefreshTokenRequest struct {
	RefreshToken string `json:"refresh_token" binding:"required"`
}

// UpdateUserRequest representa la solicitud para actualizar un usuario
type UpdateUserRequest struct {
	Username string `json:"username"`
	Email    string `json:"email" binding:"omitempty,email"`
	Active   *bool  `json:"active,omitempty"`
}

// UpdatePasswordRequest representa la solicitud para cambiar la contraseña
type UpdatePasswordRequest struct {
	CurrentPassword string `json:"current_password" binding:"required"`
	NewPassword     string `json:"new_password" binding:"required,min=8"`
}

// UpdatePermissionsRequest representa la solicitud para actualizar permisos
type UpdatePermissionsRequest struct {
	AreaID string `json:"area_id" binding:"required"`
	Read   bool   `json:"read"`
	Write  bool   `json:"write"`
}

// VerifyAdminRequest representa la solicitud para verificar si un usuario es admin
type VerifyAdminRequest struct {
	UserID string `json:"user_id" binding:"required"`
}

// VerifyAdminResponse representa la respuesta a la verificación de admin
type VerifyAdminResponse struct {
	UserID  string `json:"user_id"`
	IsAdmin bool   `json:"is_admin"`
}

// UserResponse representa la información pública del usuario
type UserResponse struct {
	ID              string                `json:"id"`
	Username        string                `json:"username"`
	Email           string                `json:"email"`
	Role            string                `json:"role"`
	Active          bool                  `json:"active"`
	CreatedAt       time.Time             `json:"created_at"`
	LastLogin       *time.Time            `json:"last_login,omitempty"`
	AreaPermissions map[string]Permission `json:"area_permissions"`
}

// ToUserResponse convierte un User a UserResponse
func (u *User) ToUserResponse() UserResponse {
	return UserResponse{
		ID:              u.ID.Hex(),
		Username:        u.Username,
		Email:           u.Email,
		Role:            u.Role,
		Active:          u.Active,
		CreatedAt:       u.CreatedAt,
		LastLogin:       u.LastLogin,
		AreaPermissions: u.AreaPermissions,
	}
}
