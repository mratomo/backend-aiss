# services/encryption_service.py
import base64
import logging
import os
import time
from typing import Optional

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)

class EncryptionService:
    """Servicio para encriptar y desencriptar datos sensibles"""
    
    def __init__(self, encryption_key: str = None):
        """
        Inicializar servicio con clave de encriptación
        
        Args:
            encryption_key: Clave de encriptación (opcional)
        """
        self.is_available = False
        try:
            # Si no se proporciona clave, usar variable de entorno o generar una
            if not encryption_key:
                encryption_key = os.getenv("DB_ENCRYPTION_KEY", "")
            
            # Si sigue sin haber clave, generar una
            if not encryption_key:
                salt = os.urandom(16)
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                encryption_key = base64.urlsafe_b64encode(kdf.derive(b"default-key"))
                logger.warning("No encryption key provided, using generated key")
            
            # Si la clave no está en formato correcto, derivarla
            if not encryption_key.endswith("="):
                # Generar un salt único para esta instancia específica
                # Usamos una combinación de timestamp y datos aleatorios
                instance_id = str(time.time()).encode() + os.urandom(8)
                # Crear un hash determinístico pero único para esta instancia
                instance_hash = hashes.Hash(hashes.SHA256())
                instance_hash.update(instance_id)
                salt = instance_hash.finalize()[:16]  # Usar los primeros 16 bytes como salt
                
                logger.info(f"Generando nueva clave con salt único para esta instancia")
                
                kdf = PBKDF2HMAC(
                    algorithm=hashes.SHA256(),
                    length=32,
                    salt=salt,
                    iterations=100000,
                )
                encryption_key = base64.urlsafe_b64encode(kdf.derive(encryption_key.encode()))
            
            # Crear instancia de Fernet
            self.cipher = Fernet(encryption_key)
            self.is_available = True
        except Exception as e:
            logger.error(f"Error initializing encryption service: {e}")
            # Fallback a una implementación segura
            self.cipher = None
    
    def encrypt(self, text: str) -> str:
        """
        Encriptar texto
        
        Args:
            text: Texto a encriptar
            
        Returns:
            Texto encriptado en base64
        """
        if not text:
            return text
        
        if not self.is_available:
            logger.error("Encryption service not available - refusing to proceed with insecure operation")
            raise ValueError("Encryption service is required but not available. Cannot proceed with sensitive data.")
        
        try:
            # Encriptar
            encrypted = self.cipher.encrypt(text.encode())
            return base64.b64encode(encrypted).decode()
        except Exception as e:
            logger.error(f"Error encrypting text: {e}")
            # No intentar un fallback inseguro, reportar el error
            raise ValueError(f"Error durante encriptación: {e}. Operación abortada por seguridad.")
    
    def decrypt(self, encrypted_text: str) -> str:
        """
        Desencriptar texto
        
        Args:
            encrypted_text: Texto encriptado en base64
            
        Returns:
            Texto original
        """
        if not encrypted_text:
            return encrypted_text
        
        # Detectar fallback
        if encrypted_text.startswith("encoded_"):
            try:
                # Extraer parte codificada
                encoded = encrypted_text[8:]  # Quitar "encoded_"
                return base64.b64decode(encoded).decode()
            except Exception as e:
                logger.error(f"Error decoding fallback text: {e}")
                return "[Error decoding]"
        
        if not self.is_available:
            logger.warning("Encryption service not available, cannot decrypt text")
            return "[Encrypted]"
        
        try:
            # Decodificar base64 y desencriptar
            decoded = base64.b64decode(encrypted_text)
            decrypted = self.cipher.decrypt(decoded)
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Error decrypting text: {e}")
            return "[Error decrypting]"