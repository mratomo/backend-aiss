from enum import Enum

class EmbeddingType(str, Enum):
    """Tipos de embeddings soportados (duplicacion controlada con embedding-service"""
    GENERAL = "general"     # Conocimiento general (áreas)
    PERSONAL = "personal"   # Conocimiento personal (usuario)
