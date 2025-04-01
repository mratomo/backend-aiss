# Guía de Contribución

Esta guía describe cómo contribuir al proyecto Backend AISS de manera efectiva.

## Índice

1. [Código de Conducta](#código-de-conducta)
2. [Cómo Empezar](#cómo-empezar)
3. [Proceso de Desarrollo](#proceso-de-desarrollo)
4. [Envío de Cambios](#envío-de-cambios)
5. [Estándares de Código](#estándares-de-código)
6. [Pruebas](#pruebas)
7. [Documentación](#documentación)
8. [Proceso de Revisión](#proceso-de-revisión)
9. [Política de Versiones](#política-de-versiones)

## Código de Conducta

Este proyecto se adhiere a un código de conducta que fomenta un ambiente inclusivo y respetuoso. Los participantes deben:

- Usar lenguaje acogedor e inclusivo
- Respetar diferentes puntos de vista y experiencias
- Aceptar críticas constructivas
- Enfocarse en lo mejor para la comunidad
- Mostrar empatía hacia otros miembros

## Cómo Empezar

### Requisitos Previos

- Docker y Docker Compose
- Go 1.18+ (para servicios Go)
- Python 3.10+ (para servicios Python)
- Git

### Configuración del Entorno de Desarrollo

1. **Fork del repositorio**

   Cree un fork del repositorio principal en GitHub.

2. **Clonar el repositorio**

   ```bash
   git clone https://github.com/TU-USUARIO/backend-aiss.git
   cd backend-aiss
   ```

3. **Configurar el repositorio remoto upstream**

   ```bash
   git remote add upstream https://github.com/ORGANIZACION-ORIGINAL/backend-aiss.git
   ```

4. **Instalar dependencias**

   Para servicios Go:
   ```bash
   cd api-gateway  # o cualquier otro servicio Go
   go mod download
   ```

   Para servicios Python:
   ```bash
   cd rag-agent  # o cualquier otro servicio Python
   python -m venv venv
   source venv/bin/activate  # o .\venv\Scripts\activate en Windows
   pip install -r requirements.txt
   ```

5. **Configurar variables de entorno**

   Copie el archivo de ejemplo y ajuste según sea necesario:
   ```bash
   cp .env.example .env
   ```

6. **Iniciar servicios con Docker**

   ```bash
   docker-compose -f docker-compose.dev.yml up
   ```

## Proceso de Desarrollo

### Flujo de Trabajo

Seguimos un flujo de trabajo basado en Git Flow:

1. **Ramas principales**
   - `main`: Código estable, listo para producción
   - `dev`: Rama de desarrollo, base para nuevas características

2. **Ramas de características**
   - Crear desde `dev`
   - Nombrar con prefijos según el tipo de cambio:
     - `feature/` para nuevas características
     - `fix/` para correcciones de errores
     - `docs/` para cambios en documentación
     - `refactor/` para refactorizaciones
     - `test/` para cambios relacionados con pruebas

   Ejemplo:
   ```bash
   git checkout dev
   git pull upstream dev
   git checkout -b feature/nueva-funcionalidad
   ```

3. **Commits**
   - Haga commits pequeños y enfocados
   - Use mensajes descriptivos que expliquen el *por qué* del cambio
   - Formato recomendado:
     ```
     tipo: descripción corta (50 caracteres máx)
     
     Explicación detallada si es necesario. Mantenga las líneas
     a 72 caracteres. El primer párrafo es el resumen.
     
     - Puntos adicionales si son necesarios
     - Otro punto
     
     Referencia a issues: #123
     ```

4. **Mantenerse actualizado**
   ```bash
   git fetch upstream
   git rebase upstream/dev
   ```

## Envío de Cambios

1. **Preparar la solicitud de cambios**
   - Asegúrese de que su código cumple con los estándares
   - Ejecute las pruebas localmente
   - Actualice la documentación si es necesario

2. **Enviar los cambios a su fork**
   ```bash
   git push origin feature/nueva-funcionalidad
   ```

3. **Crear Pull Request**
   - Vaya a GitHub y cree un nuevo Pull Request desde su rama a la rama `dev` del repositorio original
   - Use un título claro y descriptivo
   - Complete la plantilla de PR proporcionada
   - Vincule cualquier issue relacionado

4. **Responder a la revisión**
   - Esté atento a comentarios de los revisores
   - Realice los cambios solicitados en la misma rama
   - Responda a todos los comentarios

## Estándares de Código

Consulte nuestra [guía de estándares de código](development/code-standards.md) para información detallada. En resumen:

### Para Go

- Seguir [Effective Go](https://golang.org/doc/effective_go)
- Usar `gofmt` para formateo automático
- Implementar manejo adecuado de errores
- Documentar código exportado
- Seguir principios de diseño de Go

### Para Python

- Seguir [PEP 8](https://www.python.org/dev/peps/pep-0008/)
- Usar type hints
- Documentar con docstrings (estilo Google)
- Seguir principios de programación pythónica

## Pruebas

Todos los cambios deben incluir pruebas adecuadas. Vea nuestra [guía de pruebas](development/testing.md) para detalles completos.

### Reglas Básicas

1. **Cobertura mínima**: Apunte a una cobertura de pruebas del 70% para código nuevo
2. **Tipos de pruebas**:
   - Pruebas unitarias para funciones/métodos
   - Pruebas de integración para interacciones entre componentes
   - Pruebas funcionales para APIs y flujos completos

3. **Ejecución de pruebas**:
   
   Para servicios Go:
   ```bash
   go test -v ./...
   ```

   Para servicios Python:
   ```bash
   pytest
   ```

## Documentación

La documentación es crucial para la usabilidad y mantenibilidad del proyecto.

### Requisitos de Documentación

1. **Documentación de código**:
   - Todas las funciones públicas/exportadas deben tener documentación
   - Los comentarios deben explicar el "por qué", no solo el "qué"
   - Ejemplos para APIs públicas

2. **Documentación de APIs**:
   - Actualizar api-reference.md cuando se modifican endpoints
   - Incluir ejemplos de peticiones y respuestas

3. **Documentación general**:
   - Actualizar la documentación relevante para cambios en arquitectura, configuración, etc.
   - Crear nuevos documentos para funcionalidades importantes

## Proceso de Revisión

### Criterios de Revisión

Las solicitudes de cambios se evalúan según:

1. **Funcionalidad**: El código hace lo que se supone que debe hacer
2. **Calidad**: Bien estructurado, legible y mantenible
3. **Pruebas**: Cobertura adecuada con pruebas relevantes
4. **Documentación**: Documentación actualizada y clara
5. **Integración**: Se integra correctamente con el resto del sistema

### Proceso de Aprobación

1. Se requiere al menos una aprobación de un mantenedor del proyecto
2. Los cambios mayores requieren múltiples revisiones
3. Los comentarios deben abordarse antes de la fusión
4. El código debe pasar todas las verificaciones automatizadas

## Política de Versiones

Seguimos [Versionado Semántico](https://semver.org/):

- **MAJOR.MINOR.PATCH** (e.g., 1.2.3)
- **MAJOR**: Cambios incompatibles con versiones anteriores
- **MINOR**: Funcionalidad nueva compatible con versiones anteriores
- **PATCH**: Correcciones de errores compatibles con versiones anteriores

### Ciclo de Lanzamiento

- Versiones de parche: Según sea necesario para correcciones
- Versiones menores: Aproximadamente cada 1-2 meses
- Versiones mayores: Planificadas según la hoja de ruta, generalmente cada 6-12 meses

---

¡Gracias por contribuir al proyecto Backend AISS! Si tiene preguntas o necesita ayuda, no dude en abrir un issue o contactar a los mantenedores.