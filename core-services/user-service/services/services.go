package services

import (
	"context"
	"errors"
	"fmt"
	"log"
	"time"
	"user-service/models"
	"user-service/repositories"

	"github.com/golang-jwt/jwt/v4"
	"golang.org/x/crypto/bcrypt"
)

// UserService proporciona funcionalidad para operaciones de usuario
type UserService struct {
	repo            *repositories.UserRepository
	jwtSecret       string
	expirationHours int
}

// NewUserService crea un nuevo servicio de usuario
func NewUserService(repo *repositories.UserRepository, jwtSecret string, expirationHours int) *UserService {
	return &UserService{
		repo:            repo,
		jwtSecret:       jwtSecret,
		expirationHours: expirationHours,
	}
}

// RegisterUser registra un nuevo usuario
func (s *UserService) RegisterUser(ctx context.Context, user *models.User, password string) (*models.TokenResponse, error) {
	// Validar fortaleza de la contraseña
	if err := validatePasswordStrength(password); err != nil {
		return nil, err
	}

	// Generar hash de la contraseña
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return nil, err
	}

	// Asignar hash a usuario
	user.PasswordHash = string(hashedPassword)

	// Inicializar mapa de permisos si no existe
	if user.AreaPermissions == nil {
		user.AreaPermissions = make(map[string]models.Permission)
	}

	// Guardar usuario en base de datos
	savedUser, err := s.repo.CreateUser(ctx, user)
	if err != nil {
		return nil, err
	}

	// Generar token de autenticación
	return s.generateTokens(savedUser)
}

// validatePasswordStrength valida que la contraseña cumpla requisitos mínimos de seguridad
func validatePasswordStrength(password string) error {
	if len(password) < 8 {
		return errors.New("la contraseña debe tener al menos 8 caracteres")
	}

	var (
		hasUpper   bool
		hasLower   bool
		hasNumber  bool
		hasSpecial bool
	)

	for _, char := range password {
		switch {
		case 'A' <= char && char <= 'Z':
			hasUpper = true
		case 'a' <= char && char <= 'z':
			hasLower = true
		case '0' <= char && char <= '9':
			hasNumber = true
		case char == '!' || char == '@' || char == '#' || char == '$' || char == '%' || char == '^' || char == '&' || char == '*':
			hasSpecial = true
		}
	}

	if !hasUpper || !hasLower || !hasNumber || !hasSpecial {
		return errors.New("la contraseña debe contener al menos una letra mayúscula, una minúscula, un número y un carácter especial (!@#$%^&*)")
	}

	return nil
}

// LoginUser autentica un usuario
func (s *UserService) LoginUser(ctx context.Context, username, password string) (*models.TokenResponse, error) {
	// Buscar usuario por nombre de usuario
	user, err := s.repo.GetUserByUsername(ctx, username)
	if err != nil {
		return nil, errors.New("credenciales inválidas")
	}

	// Verificar contraseña
	err = bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(password))
	if err != nil {
		return nil, errors.New("credenciales inválidas")
	}

	// Verificar si el usuario está activo
	if !user.Active {
		return nil, errors.New("usuario desactivado")
	}

	// Actualizar fecha de último login
	err = s.repo.UpdateLastLogin(ctx, user.ID)
	if err != nil {
		// No devolver error al cliente si falla la actualización
		// pero registrar en logs
		log.Printf("Error al actualizar último login para usuario %s: %v", user.ID.Hex(), err)
	}

	// Generar token de autenticación
	return s.generateTokens(user)
}

// RefreshToken renueva un token de acceso
func (s *UserService) RefreshToken(ctx context.Context, refreshTokenStr string) (*models.TokenResponse, error) {
	// Validar refresh token
	token, err := jwt.Parse(refreshTokenStr, func(token *jwt.Token) (interface{}, error) {
		if _, ok := token.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, errors.New("método de firma inesperado")
		}
		return []byte(s.jwtSecret), nil
	})

	if err != nil {
		return nil, errors.New("token inválido")
	}

	// Extraer claims
	if claims, ok := token.Claims.(jwt.MapClaims); ok && token.Valid {
		// Verificar tipo de token
		if tokenType, ok := claims["type"].(string); !ok || tokenType != "refresh" {
			return nil, errors.New("tipo de token inválido")
		}

		// Obtener ID de usuario
		userID, ok := claims["user_id"].(string)
		if !ok {
			// Registrar información para facilitar depuración
			actualType := fmt.Sprintf("%T", claims["user_id"])
			actualValue := fmt.Sprintf("%v", claims["user_id"])
			log.Printf("Error en token refresh: campo user_id con tipo incorrecto, tipo: %s, valor: %s", 
				actualType, actualValue)
			return nil, errors.New("token inválido: formato de user_id incorrecto")
		}

		// Obtener versión del token
		tokenVersion, ok := claims["token_version"].(float64)
		if !ok {
			log.Printf("Error en token refresh: no hay versión de token o formato incorrecto")
			// Si no hay versión de token, podría ser un token antiguo antes de la implementación
			// de este sistema, por lo que podemos proceder con precaución
		}

		// Buscar usuario
		user, err := s.GetUserByID(ctx, userID)
		if err != nil {
			return nil, errors.New("usuario no encontrado")
		}

		// Verificar si el usuario está activo
		if !user.Active {
			return nil, errors.New("usuario desactivado")
		}

		// Verificar versión del token
		if ok && int(tokenVersion) != user.TokenVersionNumber {
			log.Printf("Intento de uso de token revocado para usuario %s, versión del token: %d, versión actual: %d", 
				userID, int(tokenVersion), user.TokenVersionNumber)
			return nil, errors.New("token revocado")
		}

		// Generar nuevos tokens
		return s.generateTokens(user)
	}

	return nil, errors.New("token inválido")
}

// GetUserByID obtiene un usuario por su ID
func (s *UserService) GetUserByID(ctx context.Context, id string) (*models.User, error) {
	return s.repo.GetUserByID(ctx, id)
}

// GetAllUsers obtiene todos los usuarios
func (s *UserService) GetAllUsers(ctx context.Context) ([]*models.User, error) {
	return s.repo.GetAllUsers(ctx)
}

// UpdateUser actualiza un usuario
func (s *UserService) UpdateUser(ctx context.Context, id string, update *models.UpdateUserRequest) (*models.User, error) {
	// Obtener usuario actual
	user, err := s.repo.GetUserByID(ctx, id)
	if err != nil {
		return nil, err
	}

	// Validar actualizaciones
	if update.Username != "" && update.Username != user.Username {
		// Verificar si el nuevo username ya está en uso
		existingUser, err := s.repo.GetUserByUsername(ctx, update.Username)
		if err == nil && existingUser.ID != user.ID {
			return nil, errors.New("el nombre de usuario ya está en uso")
		}
		// Si hay error y no es por "no encontrado", es un error real
		if err != nil && !errors.Is(err, errors.New("usuario no encontrado")) {
			return nil, fmt.Errorf("error al verificar nombre de usuario: %w", err)
		}
		user.Username = update.Username
	}

	if update.Email != "" && update.Email != user.Email {
		// Verificar si el nuevo email ya está en uso
		existingUser, err := s.repo.GetUserByEmail(ctx, update.Email)
		if err == nil && existingUser.ID != user.ID {
			return nil, errors.New("el correo electrónico ya está en uso")
		}
		// Si hay error y no es por "no encontrado", es un error real
		if err != nil && !errors.Is(err, errors.New("usuario no encontrado")) {
			return nil, fmt.Errorf("error al verificar correo electrónico: %w", err)
		}
		user.Email = update.Email
	}

	if update.Active != nil {
		// Si se está desactivando un usuario que estaba activo, invalidar sus tokens
		if user.Active && !(*update.Active) {
			user.TokenVersionNumber++
			log.Printf("Usuario %s desactivado, incrementada versión de token a %d", 
				user.ID.Hex(), user.TokenVersionNumber)
		}
		user.Active = *update.Active
	}

	// Guardar cambios
	err = s.repo.UpdateUser(ctx, user)
	if err != nil {
		return nil, err
	}

	return user, nil
}

// DeleteUser elimina un usuario
func (s *UserService) DeleteUser(ctx context.Context, id string) error {
	return s.repo.DeleteUser(ctx, id)
}

// UpdateUserPermissions actualiza los permisos de un usuario para un área
func (s *UserService) UpdateUserPermissions(ctx context.Context, userID string, areaID string, permission models.Permission) error {
	return s.repo.UpdateUserPermissions(ctx, userID, areaID, permission)
}

// SetAdminPassword establece la contraseña para el admin inicial
func (s *UserService) SetAdminPassword(ctx context.Context, password string) error {
	// Validar fortaleza de la contraseña
	if err := validatePasswordStrength(password); err != nil {
		return err
	}

	// Buscar usuario admin
	user, err := s.repo.GetUserByUsername(ctx, "admin")
	if err != nil {
		return fmt.Errorf("error al buscar usuario admin: %w", err)
	}
	
	// Generar hash de la contraseña
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return fmt.Errorf("error al generar hash de contraseña: %w", err)
	}
	
	// Actualizar contraseña
	user.PasswordHash = string(hashedPassword)
	
	// Incrementar la versión del token (si había una contraseña anterior)
	if user.PasswordHash != "" {
		user.TokenVersionNumber++
		log.Printf("Contraseña de admin actualizada, incrementada versión de token a %d", 
			user.TokenVersionNumber)
	}
	
	return s.repo.UpdateUser(ctx, user)
}

// ChangePassword cambia la contraseña de un usuario
func (s *UserService) ChangePassword(ctx context.Context, userID string, currentPassword string, newPassword string) error {
	// Validar fortaleza de la nueva contraseña
	if err := validatePasswordStrength(newPassword); err != nil {
		return err
	}

	// Obtener usuario
	user, err := s.repo.GetUserByID(ctx, userID)
	if err != nil {
		return err
	}

	// Verificar contraseña actual
	err = bcrypt.CompareHashAndPassword([]byte(user.PasswordHash), []byte(currentPassword))
	if err != nil {
		return errors.New("contraseña actual incorrecta")
	}

	// Generar hash de la nueva contraseña
	hashedPassword, err := bcrypt.GenerateFromPassword([]byte(newPassword), bcrypt.DefaultCost)
	if err != nil {
		return err
	}

	// Actualizar contraseña
	user.PasswordHash = string(hashedPassword)
	
	// Incrementar la versión del token para invalidar todos los tokens existentes
	user.TokenVersionNumber++
	
	// Registrar el cambio de contraseña
	log.Printf("Cambio de contraseña para usuario %s, incrementada versión de token a %d", 
		user.ID.Hex(), user.TokenVersionNumber)

	return s.repo.UpdateUser(ctx, user)
}

// generateTokens genera tokens de acceso y refresco
func (s *UserService) generateTokens(user *models.User) (*models.TokenResponse, error) {
	// Calcular tiempo de expiración
	expirationTime := time.Now().Add(time.Duration(s.expirationHours) * time.Hour)

	// Crear claims para access token
	accessClaims := jwt.MapClaims{
		"user_id":        user.ID.Hex(),
		"username":       user.Username,
		"email":          user.Email,
		"role":           user.Role,
		"type":           "access",
		"token_version":  user.TokenVersionNumber,
		"exp":            expirationTime.Unix(),
	}

	// Crear token de acceso
	accessToken := jwt.NewWithClaims(jwt.SigningMethodHS256, accessClaims)
	accessTokenString, err := accessToken.SignedString([]byte(s.jwtSecret))
	if err != nil {
		return nil, err
	}

	// Calcular tiempo de expiración para refresh token (más largo)
	refreshExpirationTime := time.Now().Add(time.Duration(s.expirationHours*24) * time.Hour) // 24 veces más largo

	// Crear claims para refresh token
	refreshClaims := jwt.MapClaims{
		"user_id":        user.ID.Hex(),
		"type":           "refresh",
		"token_version":  user.TokenVersionNumber,
		"exp":            refreshExpirationTime.Unix(),
	}

	// Crear refresh token
	refreshToken := jwt.NewWithClaims(jwt.SigningMethodHS256, refreshClaims)
	refreshTokenString, err := refreshToken.SignedString([]byte(s.jwtSecret))
	if err != nil {
		return nil, err
	}

	// Crear respuesta
	return &models.TokenResponse{
		AccessToken:  accessTokenString,
		RefreshToken: refreshTokenString,
		ExpiresIn:    s.expirationHours * 3600, // Convertir horas a segundos
		TokenType:    "Bearer",
	}, nil
}
