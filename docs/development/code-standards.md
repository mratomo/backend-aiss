# Estándares de Código

Este documento define los estándares de código y las mejores prácticas para el desarrollo en el proyecto Backend AISS.

## Índice

1. [Principios Generales](#principios-generales)
2. [Estándares para Go](#estándares-para-go)
3. [Estándares para Python](#estándares-para-python)
4. [Control de Versiones](#control-de-versiones)
5. [Documentación de Código](#documentación-de-código)
6. [Gestión de Errores](#gestión-de-errores)
7. [Seguridad](#seguridad)
8. [Rendimiento](#rendimiento)

## Principios Generales

### Legibilidad y Mantenibilidad

- Priorizar la legibilidad y claridad del código sobre la brevedad.
- Seguir el principio DRY (Don't Repeat Yourself).
- Aplicar el principio SOLID, especialmente la responsabilidad única.
- Mantener funciones y métodos pequeños y enfocados en una sola tarea.

### Nomenclatura

- Usar nombres descriptivos que reflejen el propósito.
- Evitar abreviaciones poco claras.
- Ser consistente con el patrón de nomenclatura en todo el proyecto.
- Utilizar prefijos o sufijos estándar para tipos específicos.

### Estructura de Archivos

- Organizar archivos por funcionalidad o dominio.
- Mantener consistencia en la organización de directorios.
- Limitar el tamaño de los archivos (máximo ~500 líneas como referencia).

## Estándares para Go

### Formateo y Estilo

- Utilizar `gofmt` o `goimports` para formatear todo el código.
- Seguir las recomendaciones de [Effective Go](https://golang.org/doc/effective_go).
- Respetar las convenciones de [Go Code Review Comments](https://github.com/golang/go/wiki/CodeReviewComments).

### Nomenclatura en Go

- Usar camelCase para variables y funciones privadas: `userCount`, `calculateTotal`.
- Usar PascalCase para exportar funciones y tipos: `UserService`, `GetUser`.
- Usar acrónimos consistentemente en mayúsculas: `HTTPClient`, `JSONParser`.
- Para interfaces de un solo método, usar el nombre del método con el sufijo 'er': `Reader`, `Writer`.

### Estructura de Código

- Organizar paquetes por funcionalidad, no por tipo.
- Colocar la interfaz junto a su implementación cuando sea posible.
- Mantener las dependencias del paquete al mínimo.
- Utilizar mocks para interfaces en pruebas.

### Manejo de Errores

- Comprobar errores inmediatamente después de llamadas que pueden fallar.
- Devolver errores en lugar de usar panic (excepto en casos críticos irrecuperables).
- Usar `errors.Wrap` para añadir contexto a los errores.
- Implementar tipos de error personalizados cuando sea necesario para una gestión específica.

```go
// Ejemplo de manejo de errores
if err != nil {
    return nil, fmt.Errorf("failed to process request: %w", err)
}
```

### Patrones Recomendados

- Utilizar el patrón de opciones funcionales para configuración.
- Implementar el patrón de repositorio para acceso a datos.
- Preferir inyección de dependencias sobre inicialización estática.
- Utilizar context.Context para operaciones que pueden cancelarse.

## Estándares para Python

### Formateo y Estilo

- Seguir [PEP 8](https://www.python.org/dev/peps/pep-0008/).
- Utilizar herramientas como Black, Flake8 e isort.
- Mantener líneas a un máximo de 88 caracteres (compatible con Black).

### Nomenclatura en Python

- Usar snake_case para funciones y variables: `user_count`, `calculate_total`.
- Usar PascalCase para clases: `UserService`, `DocumentProcessor`.
- Usar UPPER_CASE para constantes: `MAX_RETRIES`, `DEFAULT_TIMEOUT`.
- Usar nombres descriptivos para funciones, evitando términos genéricos.

### Type Hints

- Utilizar anotaciones de tipo para todos los parámetros y valores de retorno.
- Importar tipos de `typing` o `collections.abc` según sea necesario.
- Usar tipos opcionales con `Optional[T]` en lugar de valores predeterminados `None`.
- Documentar cualquier comportamiento especial con respecto a tipos.

```python
def process_document(document_id: str, options: Optional[Dict[str, Any]] = None) -> DocumentResult:
    """
    Process a document with the given options.
    
    Args:
        document_id: The ID of the document to process
        options: Optional processing configuration
        
    Returns:
        ProcessingResult object with status and metadata
        
    Raises:
        DocumentNotFoundError: If document doesn't exist
    """
    # Implementation
```

### Estructura de Código Python

- Organizar código en módulos por funcionalidad.
- Usar clases para encapsular estado y lógica relacionada.
- Preferir composición sobre herencia.
- Implementar interfaces abstractas con `ABC` cuando sea apropiado.

### Asincronía

- Utilizar `async/await` para operaciones I/O bound.
- Evitar bloquear el bucle de eventos con operaciones CPU intensivas.
- No mezclar código síncrono y asíncrono en las mismas funciones.
- Usar `asyncio.gather` para operaciones paralelas.

## Control de Versiones

### Estructura de Ramas

- `main` o `master`: Rama principal, siempre estable.
- `develop`: Rama de desarrollo, integración continua.
- `feature/*`: Ramas para nuevas características.
- `bugfix/*`: Ramas para corrección de errores.
- `release/*`: Ramas para preparar lanzamientos.

### Commits

- Escribir mensajes de commit claros y descriptivos.
- Seguir el formato: `<tipo>: <descripción>` (ej: "fix: corregir error en autenticación").
- Tipos comunes: `feat`, `fix`, `docs`, `style`, `refactor`, `test`, `chore`.
- Limitar la primera línea a 72 caracteres.
- Incluir un cuerpo detallado para cambios complejos.

### Pull Requests

- Crear PR pequeños y enfocados en un solo cambio o característica.
- Incluir una descripción clara de los cambios y la motivación.
- Asociar a issues si corresponde.
- Asegurarse de que todas las pruebas pasen antes de solicitar revisión.

## Documentación de Código

### Go

- Documentar todos los paquetes, tipos, constantes y funciones exportadas.
- Seguir el formato de documentación estándar de Go.
- Los comentarios de documentación deben comenzar con el nombre del elemento.

```go
// UserService provides functionality for managing users in the system.
type UserService struct {
    // Fields...
}

// GetUser retrieves a user by their ID.
// Returns ErrUserNotFound if the user doesn't exist.
func (s *UserService) GetUser(id string) (*User, error) {
    // Implementation...
}
```

### Python

- Utilizar docstrings en formato Google para clases, métodos y funciones.
- Documentar parámetros, retornos y excepciones.
- Incluir ejemplos para funcionalidades complejas o no obvias.

```python
def get_user(user_id: str) -> User:
    """
    Retrieve a user by ID.
    
    Args:
        user_id: The unique identifier of the user.
        
    Returns:
        User object with the user's information.
        
    Raises:
        UserNotFoundError: If no user exists with the given ID.
        
    Example:
        >>> user = get_user("user123")
        >>> print(user.name)
        "John Doe"
    """
    # Implementation
```

## Gestión de Errores

### Principios Generales

- Fallar rápido: detectar errores lo antes posible.
- Errores explícitos: no silenciar errores, manejarlos o propagarlos.
- Mensajes descriptivos: incluir información útil para diagnóstico.
- Evitar condiciones excepcionales para flujo de control normal.

### En Go

- Devolver errores como último valor de retorno.
- Usar paquetes como `errors` o `github.com/pkg/errors` para contexto adicional.
- Implementar tipos de error personalizados cuando sea necesario.
- Utilizar `errors.Is` y `errors.As` para inspeccionar errores.

### En Python

- Utilizar excepciones para condiciones excepcionales.
- Crear jerarquías de excepciones personalizadas.
- No atrapar excepciones genéricas sin re-lanzarlas.
- Usar bloques `try/except` con el ámbito más estrecho posible.

## Seguridad

- Nunca almacenar credenciales en código o control de versiones.
- Validar todas las entradas de usuario.
- Utilizar consultas parametrizadas para bases de datos.
- Implementar control de acceso en todos los endpoints.
- Seguir el principio de privilegio mínimo.
- Utilizar bibliotecas de seguridad establecidas en lugar de implementaciones propias.

## Rendimiento

- Optimizar para claridad primero, rendimiento después.
- Perfilar antes de optimizar.
- Documentar las decisiones de optimización no obvias.
- Considerar caching para operaciones costosas.
- Diseñar para escalabilidad horizontal cuando sea posible.
- Limitar recursos (memoria, CPU, red) para prevenir abusos.