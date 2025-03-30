
from typing import List, Optional

from datetime import datetime

from bson import ObjectId
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from models.area import Area, AreaCreate, AreaUpdate


class AreaService:
    """Servicio para gestionar áreas de conocimiento"""

    def __init__(self, database: AsyncIOMotorDatabase):
        """Inicializar servicio con la base de datos"""
        self.db = database
        self.collection = database.areas

    async def create_area(self, area_data: AreaCreate) -> Area:
        """Crear una nueva área de conocimiento"""
        now = datetime.utcnow()

        # Verificar si ya existe un área con el mismo nombre
        existing = await self.collection.find_one({"name": area_data.name})
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Ya existe un área con el nombre: {area_data.name}"
            )

        # Crear nuevo documento de área
        area_dict = area_data.dict()
        area_dict["created_at"] = now
        area_dict["updated_at"] = now
        area_dict["active"] = True

        # Insertar en la base de datos
        result = await self.collection.insert_one(area_dict)

        # Obtener el documento creado
        created_area = await self.collection.find_one({"_id": result.inserted_id})

        return Area(**created_area)

    async def get_area(self, area_id: str) -> Optional[Area]:
        """Obtener un área por su ID"""
        try:
            obj_id = ObjectId(area_id)
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ID de área inválido: {area_id}"
            )

        area_dict = await self.collection.find_one({"_id": obj_id})
        if area_dict:
            return Area(**area_dict)
        return None

    async def list_areas(self, skip: int = 0, limit: int = 100) -> List[Area]:
        """Listar todas las áreas de conocimiento"""
        cursor = self.collection.find().skip(skip).limit(limit)
        areas = await cursor.to_list(length=limit)
        return [Area(**area) for area in areas]

    async def update_area(self, area_id: str, area_update: AreaUpdate) -> Area:
        """Actualizar un área de conocimiento"""
        try:
            obj_id = ObjectId(area_id)
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ID de área inválido: {area_id}"
            )

        # Verificar si el área existe
        existing = await self.collection.find_one({"_id": obj_id})
        if not existing:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Área no encontrada: {area_id}"
            )

        # Preparar actualización
        update_data = {k: v for k, v in area_update.dict().items() if v is not None}
        update_data["updated_at"] = datetime.utcnow()

        # Si se va a actualizar el nombre, verificar que no exista otro con ese nombre
        if "name" in update_data:
            name_exists = await self.collection.find_one({
                "name": update_data["name"],
                "_id": {"$ne": obj_id}
            })
            if name_exists:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Ya existe un área con el nombre: {update_data['name']}"
                )

        # Actualizar en la base de datos
        await self.collection.update_one(
            {"_id": obj_id},
            {"$set": update_data}
        )

        # Obtener documento actualizado
        updated_area = await self.collection.find_one({"_id": obj_id})

        return Area(**updated_area)

    async def delete_area(self, area_id: str) -> bool:
        """Eliminar un área de conocimiento"""
        try:
            obj_id = ObjectId(area_id)
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ID de área inválido: {area_id}"
            )

        # Eliminar de la base de datos
        result = await self.collection.delete_one({"_id": obj_id})

        if result.deleted_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Área no encontrada: {area_id}"
            )

        return True

    async def update_area_context(self, area_id: str, context_id: str) -> Area:
        """Actualizar el ID de contexto MCP de un área"""
        try:
            obj_id = ObjectId(area_id)
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ID de área inválido: {area_id}"
            )

        # Actualizar en la base de datos
        await self.collection.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "mcp_context_id": context_id,
                    "updated_at": datetime.utcnow()
                }
            }
        )

        # Obtener documento actualizado
        updated_area = await self.collection.find_one({"_id": obj_id})

        return Area(**updated_area)

    async def update_area_system_prompt(self, area_id: str, system_prompt: str) -> Area:
        """Actualizar específicamente el prompt de sistema de un área"""
        try:
            obj_id = ObjectId(area_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ID de área inválido: {area_id}"
            )

        update_data = {
            "system_prompt": system_prompt,
            "updated_at": datetime.utcnow()
        }

        result = await self.collection.update_one(
            {"_id": obj_id},
            {"$set": update_data}
        )

        if result.matched_count == 0:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Área no encontrada: {area_id}"
            )

        updated_area = await self.collection.find_one({"_id": obj_id})
        return Area(**updated_area)

    # Corrección: Implementación del método get_area_system_prompt
    async def get_area_system_prompt(self, area_id: str) -> Optional[str]:
        """Obtener el prompt de sistema asociado a un área"""
        try:
            obj_id = ObjectId(area_id)
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"ID de área inválido: {area_id}"
            )

        area = await self.collection.find_one({"_id": obj_id})
        if not area:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Área no encontrada: {area_id}"
            )

        return area.get("system_prompt")