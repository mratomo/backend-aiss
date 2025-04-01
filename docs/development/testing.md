# Pruebas

Esta guía describe las estrategias, herramientas y prácticas de prueba para el proyecto Backend AISS.

## Índice

1. [Filosofía de Pruebas](#filosofía-de-pruebas)
2. [Tipos de Pruebas](#tipos-de-pruebas)
3. [Herramientas de Prueba](#herramientas-de-prueba)
4. [Pruebas en Servicios Go](#pruebas-en-servicios-go)
5. [Pruebas en Servicios Python](#pruebas-en-servicios-python)
6. [Pruebas de Integración](#pruebas-de-integración)
7. [Pruebas de Carga](#pruebas-de-carga)
8. [Integración Continua](#integración-continua)
9. [Mejores Prácticas](#mejores-prácticas)

## Filosofía de Pruebas

En Backend AISS, seguimos estos principios para las pruebas:

- **Pruebas como documentación**: Las pruebas deben servir como ejemplos claros de cómo usar el código.
- **Pruebas como red de seguridad**: Deben detectar regresiones y garantizar que los cambios no rompan funcionalidades existentes.
- **Pruebas como guía de diseño**: Escribir pruebas primero (TDD) cuando sea apropiado para mejorar el diseño del código.
- **Pruebas proporcionales al riesgo**: Mayor cobertura para código crítico, menos para utilitarios simples.
- **Pruebas automatizadas**: Deben poder ejecutarse sin intervención manual.

## Tipos de Pruebas

### Pruebas Unitarias

- Prueban componentes individuales de manera aislada
- Rápidas y enfocadas
- Usan mocks/stubs para dependencias
- Verifican casos normales y casos de borde
- Deben cubrir al menos el 70% del código

### Pruebas de Integración

- Prueban la interacción entre múltiples componentes
- Verifican que los componentes funcionan juntos correctamente
- Pueden implicar bases de datos reales o simuladas
- Cubren flujos principales de datos

### Pruebas de API

- Validan los endpoints REST
- Verifican formatos de solicitud/respuesta
- Comprueban códigos de estado HTTP
- Validan autenticación y autorización

### Pruebas End-to-End (E2E)

- Prueban flujos completos del sistema
- Simulan interacciones reales del usuario
- Más lentas pero más completas
- Cubren escenarios principales de uso

### Pruebas de Rendimiento

- Miden tiempos de respuesta bajo carga
- Verifican límites de recursos (memoria, CPU)
- Identifican cuellos de botella
- Establecen líneas base para comparaciones

## Herramientas de Prueba

### Para Go

- **testing**: Paquete estándar para pruebas unitarias
- **testify**: Biblioteca de aserciones y mocks
- **gomock**: Generador de mocks
- **httptest**: Para probar APIs HTTP
- **go-sqlmock**: Para simular bases de datos SQL

### Para Python

- **pytest**: Framework principal de pruebas
- **unittest.mock**: Para crear mocks
- **pytest-cov**: Para medir cobertura de código
- **requests-mock**: Para simular respuestas HTTP
- **pytest-asyncio**: Para probar código asíncrono

### Herramientas Generales

- **Postman/Newman**: Para pruebas de API
- **locust**: Para pruebas de carga
- **Docker**: Para entornos aislados de prueba
- **GitHub Actions/GitLab CI**: Para integración continua

## Pruebas en Servicios Go

### Estructura de Pruebas

Las pruebas en Go siguen la convención estándar: archivos `*_test.go` junto a los archivos que prueban.

```
service/
  ├── user.go
  ├── user_test.go
  ├── document.go
  └── document_test.go
```

### Ejemplo de Prueba Unitaria

```go
package service

import (
    "testing"
    "github.com/stretchr/testify/assert"
    "github.com/stretchr/testify/mock"
)

// MockUserRepository es un mock del repositorio de usuarios
type MockUserRepository struct {
    mock.Mock
}

func (m *MockUserRepository) GetByID(id string) (*User, error) {
    args := m.Called(id)
    if args.Get(0) == nil {
        return nil, args.Error(1)
    }
    return args.Get(0).(*User), args.Error(1)
}

// Test para UserService.GetUser
func TestGetUser(t *testing.T) {
    // Configurar mock
    mockRepo := new(MockUserRepository)
    mockRepo.On("GetByID", "123").Return(&User{ID: "123", Name: "Test User"}, nil)
    
    // Crear servicio con mock
    service := NewUserService(mockRepo)
    
    // Llamar al método a probar
    user, err := service.GetUser("123")
    
    // Verificaciones
    assert.NoError(t, err)
    assert.NotNil(t, user)
    assert.Equal(t, "123", user.ID)
    assert.Equal(t, "Test User", user.Name)
    
    // Verificar que el mock fue llamado correctamente
    mockRepo.AssertExpectations(t)
}
```

### Ejecutar Pruebas Go

```bash
# Ejecutar todas las pruebas en un paquete
go test ./...

# Ejecutar pruebas con cobertura
go test -cover ./...

# Ejecutar con reporte de cobertura detallado
go test -coverprofile=coverage.out ./...
go tool cover -html=coverage.out
```

## Pruebas en Servicios Python

### Estructura de Pruebas

En Python, las pruebas se organizan en un directorio `tests` con estructura similar al código:

```
my_service/
  ├── __init__.py
  ├── models.py
  ├── service.py
  └── tests/
      ├── __init__.py
      ├── test_models.py
      └── test_service.py
```

### Ejemplo de Prueba Unitaria

```python
import pytest
from unittest.mock import Mock, patch
from my_service.service import UserService
from my_service.models import User

class TestUserService:
    def setup_method(self):
        # Configurar el mock del repositorio
        self.repo_mock = Mock()
        self.service = UserService(repository=self.repo_mock)
    
    def test_get_user_success(self):
        # Configurar comportamiento del mock
        self.repo_mock.get_by_id.return_value = User(id="123", name="Test User")
        
        # Llamar al método a probar
        result = self.service.get_user("123")
        
        # Verificaciones
        assert result is not None
        assert result.id == "123"
        assert result.name == "Test User"
        self.repo_mock.get_by_id.assert_called_once_with("123")
    
    def test_get_user_not_found(self):
        # Configurar mock para simular usuario no encontrado
        self.repo_mock.get_by_id.return_value = None
        
        # Verificar que se lanza la excepción esperada
        with pytest.raises(UserNotFoundError):
            self.service.get_user("456")
        
        self.repo_mock.get_by_id.assert_called_once_with("456")
```

### Ejecutar Pruebas Python

```bash
# Ejecutar todas las pruebas
pytest

# Ejecutar con cobertura
pytest --cov=my_service

# Generar reporte HTML de cobertura
pytest --cov=my_service --cov-report=html
```

## Pruebas de Integración

Las pruebas de integración verifican que los componentes funcionan correctamente juntos. Para Backend AISS usamos dos enfoques:

### Docker Compose para Entornos de Prueba

Usamos un archivo `docker-compose.test.yml` que configura todos los servicios necesarios con bases de datos para pruebas.

```yaml
version: '3.8'

services:
  mongodb:
    image: mongo:4.4
    environment:
      MONGO_INITDB_DATABASE: test_db
    volumes:
      - ./test/init-mongo.js:/docker-entrypoint-initdb.d/init-mongo.js:ro
    ports:
      - "27017:27017"
    
  api-gateway:
    build:
      context: ./api-gateway
      dockerfile: Dockerfile.test
    environment:
      MONGODB_URI: mongodb://mongodb:27017/test_db
      # Otras variables de entorno para pruebas
    ports:
      - "8080:8080"
    depends_on:
      - mongodb
```

### Pruebas Entre Servicios

```go
// Ejemplo en Go (api-gateway/integration_test.go)
func TestUserServiceIntegration(t *testing.T) {
    // Omitir prueba si no se ejecuta en CI o modo de integración
    if os.Getenv("INTEGRATION_TEST") != "true" {
        t.Skip("Skipping integration test in non-integration mode")
    }
    
    client := NewUserServiceClient("http://user-service:8081")
    
    // Crear un nuevo usuario para la prueba
    user, err := client.CreateUser(&CreateUserRequest{
        Username: "testuser",
        Email: "test@example.com",
        Password: "securepassword",
    })
    
    require.NoError(t, err)
    assert.NotEmpty(t, user.ID)
    
    // Obtener el usuario creado
    fetchedUser, err := client.GetUser(user.ID)
    require.NoError(t, err)
    assert.Equal(t, user.ID, fetchedUser.ID)
    assert.Equal(t, "testuser", fetchedUser.Username)
}
```

### Ejecutar Pruebas de Integración

```bash
# Iniciar entorno de prueba
docker-compose -f docker-compose.test.yml up -d

# Ejecutar pruebas de integración
INTEGRATION_TEST=true go test -tags=integration ./...

# Limpiar después
docker-compose -f docker-compose.test.yml down -v
```

## Pruebas de Carga

Usamos Locust para pruebas de carga, simulando usuarios reales interactuando con el sistema.

### Ejemplo de Script Locust

```python
# locustfile.py
from locust import HttpUser, task, between

class APIUser(HttpUser):
    wait_time = between(1, 3)
    
    def on_start(self):
        # Autenticar antes de las pruebas
        response = self.client.post("/api/v1/auth/login", json={
            "username": "testuser",
            "password": "testpassword"
        })
        data = response.json()
        self.token = data["data"]["access_token"]
        self.client.headers = {"Authorization": f"Bearer {self.token}"}
    
    @task(3)
    def get_documents(self):
        self.client.get("/api/v1/documents")
    
    @task(1)
    def search_documents(self):
        self.client.get("/api/v1/documents/search?query=example")
    
    @task(1)
    def rag_query(self):
        self.client.post("/api/v1/rag/query", json={
            "query": "¿Cómo funciona el sistema?",
            "context_window": 3
        })
```

### Métricas Clave

- **Tiempo de respuesta**: Promedio, mediana, percentiles 95 y 99
- **Throughput**: Solicitudes por segundo que puede manejar el sistema
- **Tasa de error**: Porcentaje de solicitudes fallidas
- **Uso de recursos**: CPU, memoria, red, IO de disco

### Umbrales Recomendados

- Tiempo de respuesta P95 < 1000ms para operaciones normales
- Tiempo de respuesta P95 < 3000ms para operaciones complejas (RAG)
- Tasa de error < 1% bajo carga normal
- Capacidad para manejar al menos 100 usuarios concurrentes

## Integración Continua

Usamos GitHub Actions para ejecutar pruebas automáticamente:

```yaml
# .github/workflows/test.yml
name: Tests

on:
  push:
    branches: [ main, dev ]
  pull_request:
    branches: [ main, dev ]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      
      - name: Set up Go
        uses: actions/setup-go@v2
        with:
          go-version: 1.18
      
      - name: Set up Python
        uses: actions/setup-python@v2
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          go mod download
          pip install -r requirements.txt
      
      - name: Run Go tests
        run: go test -race -coverprofile=coverage.txt -covermode=atomic ./...
      
      - name: Run Python tests
        run: pytest --cov=.
      
      - name: Upload coverage
        uses: codecov/codecov-action@v1
```

## Mejores Prácticas

1. **Prueba los requisitos, no la implementación**:
   - Enfocarse en el comportamiento esperado, no en detalles de implementación.
   - Esto permite refactorizar el código sin romper las pruebas.

2. **Mantener las pruebas rápidas**:
   - Las pruebas unitarias deben ser muy rápidas (milisegundos).
   - Separar pruebas lentas en suites específicas.

3. **Datos de prueba consistentes**:
   - Usar fixtures o factories para crear datos de prueba.
   - No depender de datos externos o el estado global.

4. **Limpieza automática**:
   - Cada prueba debe limpiar después de sí misma.
   - Usar setup/teardown o fixtures con gestión de contexto.

5. **Una aserción por prueba**:
   - Idealmente, cada prueba verifica una cosa específica.
   - Facilita encontrar la causa raíz cuando fallan.

6. **Nomenclatura descriptiva**:
   - Nombrar pruebas con formato `test_Función_Escenario_ResultadoEsperado`.
   - Ejemplo: `test_GetUser_UserExists_ReturnsUser`.

7. **Pruebas deterministas**:
   - Las pruebas deben tener el mismo resultado cada vez que se ejecutan.
   - Evitar dependencias de tiempo o recursos externos variables.

8. **Verificar casos de error**:
   - Probar tanto escenarios exitosos como condiciones de error.
   - Verificar mensajes de error y códigos de retorno.