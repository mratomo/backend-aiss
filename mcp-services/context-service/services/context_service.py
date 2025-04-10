# services/context_service.py
from datetime import datetime
from typing import Dict, List, Optional

from bson import ObjectId
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.context import Context, ContextCreate, ContextUpdate


class ContextService:
    """Servicio para gestionar contextos MCP"""

    def __init__(self, database: AsyncIOMotorDatabase):
        """Inicializar servicio con la base de datos"""
        self.db = database
        self.collection = database.contexts

    async def create_context(self, context_data: ContextCreate, context_id: str) -> Context:
        """
        Crear un nuevo contexto MCP en la base de datos

        Args:
            context_data: Datos del contexto a crear
            context_id: ID del contexto generado por el servicio MCP

        Returns:
            El contexto creado
        """
        now = datetime.utcnow()

        # Verificar si ya existe un contexto con el mismo ID
        existing = await self.collection.find_one({"context_id": context_id})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un contexto con el ID: {context_id}"
            )

        # Crear documento de contexto
        context_dict = context_data.model_dump()
        context_dict["context_id"] = context_id
        context_dict["created_at"] = now
        context_dict["updated_at"] = now
        context_dict["is_active"] = False

        # Insertar en la base de datos
        result = await self.collection.insert_one(context_dict)

        # Obtener el documento creado
        created_context = await self.collection.find_one({"_id": result.inserted_id})

        return Context(**created_context)

    async def get_context(self, context_id: str) -> Optional[Context]:
        """
        Obtener un contexto por su ID

        Args:
            context_id: ID del contexto (puede ser el ID de MongoDB o el context_id del MCP)

        Returns:
            El contexto encontrado o None
        """
        # Primero intentar buscar por context_id (ID de MCP)
        context_dict = await self.collection.find_one({"context_id": context_id})

        # Si no se encuentra, intentar buscar por _id (asumiendo que es un ObjectId)
        if not context_dict:
            try:
                obj_id = ObjectId(context_id)
                context_dict = await self.collection.find_one({"_id": obj_id})
            except:
                # Si no es un ObjectId válido, simplemente retornar None
                pass

        if context_dict:
            return Context(**context_dict)
        return None

    async def list_contexts(self, skip: int = 0, limit: int = 100) -> List[Context]:
        """
        Listar todos los contextos

        Args:
            skip: Número de documentos a saltar
            limit: Número máximo de documentos a retornar

        Returns:
            Lista de contextos
        """
        cursor = self.collection.find().skip(skip).limit(limit)
        contexts = await cursor.to_list(length=limit)
        return [Context(**context) for context in contexts]

    async def list_contexts_by_area(self, area_id: str) -> List[Context]:
        """
        Listar los contextos asociados a un área específica

        Args:
            area_id: ID del área

        Returns:
            Lista de contextos asociados al área
        """
        cursor = self.collection.find({"area_id": area_id})
        contexts = await cursor.to_list(length=100)
        return [Context(**context) for context in contexts]

    async def list_contexts_by_owner(self, owner_id: str) -> List[Context]:
        """
        Listar los contextos personales de un usuario específico

        Args:
            owner_id: ID del propietario

        Returns:
            Lista de contextos personales del usuario
        """
        cursor = self.collection.find({
            "owner_id": owner_id,
            "is_personal": True
        })
        contexts = await cursor.to_list(length=100)
        return [Context(**context) for context in contexts]

    async def update_context(self, context_id: str, update_data: ContextUpdate) -> Context:
        """
        Actualizar un contexto

        Args:
            context_id: ID del contexto (puede ser el ID de MongoDB o el context_id del MCP)
            update_data: Datos a actualizar

        Returns:
            El contexto actualizado
        """
        # Primero obtener el contexto
        context = await self.get_context(context_id)
        if not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contexto no encontrado: {context_id}"
            )

        # Preparar datos de actualización
        update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
        update_dict["updated_at"] = datetime.utcnow()

        # Actualizar en la base de datos
        await self.collection.update_one(
            {"_id": context.id},
            {"$set": update_dict}
        )

        # Obtener el documento actualizado
        updated_context = await self.collection.find_one({"_id": context.id})

        return Context(**updated_context)

    async def delete_context(self, context_id: str) -> bool:
        """
        Eliminar un contexto

        Args:
            context_id: ID del contexto (puede ser el ID de MongoDB o el context_id del MCP)

        Returns:
            True si se eliminó correctamente
        """
        # Primero obtener el contexto
        context = await self.get_context(context_id)
        if not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contexto no encontrado: {context_id}"
            )

        # Eliminar de la base de datos
        result = await self.collection.delete_one({"_id": context.id})

        return result.deleted_count > 0

    async def update_context_activation(self, context_id: str, is_active: bool) -> Context:
        """
        Actualizar el estado de activación de un contexto

        Args:
            context_id: ID del contexto (puede ser el ID de MongoDB o el context_id del MCP)
            is_active: True si el contexto está activo, False en caso contrario

        Returns:
            El contexto actualizado
        """
        # Primero obtener el contexto
        context = await self.get_context(context_id)
        if not context:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Contexto no encontrado: {context_id}"
            )

        # Preparar datos de actualización
        update_dict = {
            "is_active": is_active,
            "updated_at": datetime.utcnow(),
        }

        # Si se está activando, actualizar también la fecha de última activación
        if is_active:
            update_dict["last_activated"] = datetime.utcnow()

        # Actualizar en la base de datos
        await self.collection.update_one(
            {"_id": context.id},
            {"$set": update_dict}
        )

        # Obtener el documento actualizado
        updated_context = await self.collection.find_one({"_id": context.id})

        return Context(**updated_context)

    async def get_active_contexts(self) -> List[Context]:
        """
        Obtener la lista de contextos activos

        Returns:
            Lista de contextos activos
        """
        cursor = self.collection.find({"is_active": True})
        contexts = await cursor.to_list(length=100)
        return [Context(**context) for context in contexts]