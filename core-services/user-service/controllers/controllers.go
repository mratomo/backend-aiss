package controllers

import (
	"context"
	"net/http"
	"time"
	"user-service/models"
	"user-service/services"

	"github.com/gin-gonic/gin"
)

// UserController gestiona las solicitudes relacionadas con usuarios
type UserController struct {
	userService *services.UserService
}

// NewUserController crea un nuevo controlador de usuarios
func NewUserController(userService *services.UserService) *UserController {
	return &UserController{
		userService: userService,
	}
}

// Register maneja el registro de nuevos usuarios
func (ctrl *UserController) Register(c *gin.Context) {
	var req models.UserRegisterRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Crear usuario con datos de la solicitud
	user := &models.User{
		Username:        req.Username,
		Email:           req.Email,
		Role:            "user", // Por defecto es usuario regular
		Active:          true,
		AreaPermissions: make(map[string]models.Permission),
	}

	// Registrar usuario
	tokenResponse, err := ctrl.userService.RegisterUser(ctx, user, req.Password)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, tokenResponse)
}

// Login maneja el inicio de sesión
func (ctrl *UserController) Login(c *gin.Context) {
	var req models.UserLoginRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Autenticar usuario
	tokenResponse, err := ctrl.userService.LoginUser(ctx, req.Username, req.Password)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, tokenResponse)
}

// RefreshToken maneja la renovación de tokens
func (ctrl *UserController) RefreshToken(c *gin.Context) {
	var req models.RefreshTokenRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Renovar token
	tokenResponse, err := ctrl.userService.RefreshToken(ctx, req.RefreshToken)
	if err != nil {
		c.JSON(http.StatusUnauthorized, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, tokenResponse)
}

// GetUserByID obtiene un usuario por su ID
func (ctrl *UserController) GetUserByID(c *gin.Context) {
	id := c.Param("id")

	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Obtener usuario
	user, err := ctrl.userService.GetUserByID(ctx, id)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, user.ToUserResponse())
}

// GetAllUsers obtiene todos los usuarios
func (ctrl *UserController) GetAllUsers(c *gin.Context) {
	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Obtener usuarios
	users, err := ctrl.userService.GetAllUsers(ctx)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Convertir a respuesta
	var responses []models.UserResponse
	for _, user := range users {
		responses = append(responses, user.ToUserResponse())
	}

	c.JSON(http.StatusOK, responses)
}

// UpdateUser actualiza un usuario
func (ctrl *UserController) UpdateUser(c *gin.Context) {
	id := c.Param("id")
	var req models.UpdateUserRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Actualizar usuario
	user, err := ctrl.userService.UpdateUser(ctx, id, &req)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, user.ToUserResponse())
}

// DeleteUser elimina un usuario
func (ctrl *UserController) DeleteUser(c *gin.Context) {
	id := c.Param("id")

	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Eliminar usuario
	err := ctrl.userService.DeleteUser(ctx, id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusNoContent, nil)
}

// UpdatePermissions actualiza los permisos de un usuario para un área
func (ctrl *UserController) UpdatePermissions(c *gin.Context) {
	id := c.Param("id")
	var req models.UpdatePermissionsRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Actualizar permisos
	permission := models.Permission{
		Read:  req.Read,
		Write: req.Write,
	}

	err := ctrl.userService.UpdateUserPermissions(ctx, id, req.AreaID, permission)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	// Obtener usuario actualizado
	user, err := ctrl.userService.GetUserByID(ctx, id)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusOK, user.ToUserResponse())
}

// VerifyAdmin verifica si un usuario es administrador
func (ctrl *UserController) VerifyAdmin(c *gin.Context) {
	var req models.VerifyAdminRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": err.Error()})
		return
	}

	// Crear contexto con timeout
	ctx, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()

	// Obtener usuario
	user, err := ctrl.userService.GetUserByID(ctx, req.UserID)
	if err != nil {
		c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
		return
	}

	// Verificar si es admin
	isAdmin := user.Role == "admin"

	response := models.VerifyAdminResponse{
		UserID:  req.UserID,
		IsAdmin: isAdmin,
	}

	c.JSON(http.StatusOK, response)
}
