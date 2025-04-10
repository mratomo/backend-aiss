# services/agent_service.py
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any
from bson import ObjectId

from models.models import (
    DBAgent, DBAgentUpdate, AgentPrompts, ConnectionAssignment,
    ConnectionAssignmentResponse, DBConnection
)
from config.settings import Settings
from services.connection_service import ConnectionService

logger = logging.getLogger(__name__)

class AgentService:
    """Servicio para gestionar agentes DB"""

    def __init__(self, db, connection_service: ConnectionService, settings: Settings):
        """
        Inicializar servicio con la base de datos y servicios dependientes
        
        Args:
            db: Instancia de la base de datos MongoDB
            connection_service: Servicio de conexiones
            settings: Configuración de la aplicación
        """
        self.db = db
        self.agents_collection = db[settings.mongodb.agents_collection]
        self.connections_collection = db[settings.mongodb.agent_connections_collection]
        self.connection_service = connection_service
        self.settings = settings
    
    async def get_all_agents(self) -> List[DBAgent]:
        """
        Obtener todos los agentes DB
        
        Returns:
            Lista de agentes
        """
        agents = await self.agents_collection.find().to_list(length=100)
        return [self._to_agent(agent) for agent in agents]
    
    async def get_agent(self, agent_id: str) -> Optional[DBAgent]:
        """
        Obtener un agente específico por ID
        
        Args:
            agent_id: ID del agente
            
        Returns:
            Agente si existe, None en caso contrario
        """
        try:
            obj_id = ObjectId(agent_id)
        except Exception:
            return None
        
        agent = await self.agents_collection.find_one({"_id": obj_id})
        if not agent:
            return None
        
        return self._to_agent(agent)
    
    async def create_agent(self, agent: DBAgent) -> DBAgent:
        """
        Crear un nuevo agente DB
        
        Args:
            agent: Datos del agente
            
        Returns:
            Agente creado
            
        Raises:
            ValueError: Si hay errores de validación
        """
        # Preparar documento
        agent_dict = agent.model_dump(exclude={"id"})
        agent_dict["created_at"] = datetime.utcnow()
        agent_dict["updated_at"] = datetime.utcnow()
        
        # Establecer prompts predeterminados
        if not agent_dict.get("prompts"):
            agent_dict["prompts"] = {
                "system_prompt": "Eres un asistente especializado en consultas a bases de datos. Tu tarea es analizar consultas en lenguaje natural y convertirlas en consultas estructuradas SQL/NoSQL según corresponda.",
                "query_evaluation_prompt": "Evalúa si esta consulta requiere acceso a base de datos o puede resolverse con RAG convencional.",
                "query_generation_prompt": f"Convierte la siguiente consulta en lenguaje natural a una consulta estructurada para {{tipo_bd}}.",
                "result_formatting_prompt": "Formatea los resultados de la consulta de manera clara y concisa."
            }
        
        # Insertar en MongoDB
        result = await self.agents_collection.insert_one(agent_dict)
        
        # Obtener documento insertado
        agent_dict["id"] = str(result.inserted_id)
        agent_dict["_id"] = result.inserted_id
        
        return self._to_agent(agent_dict)
    
    async def update_agent(self, agent_id: str, update: DBAgentUpdate) -> Optional[DBAgent]:
        """
        Actualizar un agente existente
        
        Args:
            agent_id: ID del agente
            update: Datos a actualizar
            
        Returns:
            Agente actualizado si existe, None en caso contrario
            
        Raises:
            ValueError: Si hay errores de validación
        """
        try:
            obj_id = ObjectId(agent_id)
        except Exception:
            return None
        
        # Obtener agente existente
        agent = await self.agents_collection.find_one({"_id": obj_id})
        if not agent:
            return None
        
        # Preparar actualización
        update_dict = update.model_dump(exclude_none=True)
        
        # Añadir timestamp de actualización
        update_dict["updated_at"] = datetime.utcnow()
        
        # Actualizar en MongoDB
        await self.agents_collection.update_one(
            {"_id": obj_id},
            {"$set": update_dict}
        )
        
        # Obtener documento actualizado
        updated = await self.agents_collection.find_one({"_id": obj_id})
        return self._to_agent(updated)
    
    async def delete_agent(self, agent_id: str) -> bool:
        """
        Eliminar un agente
        
        Args:
            agent_id: ID del agente
            
        Returns:
            True si se eliminó, False si no existía
        """
        try:
            obj_id = ObjectId(agent_id)
        except Exception:
            return False
        
        # Eliminar asignaciones de conexiones
        await self.connections_collection.delete_many({"agent_id": agent_id})
        
        # Eliminar agente
        result = await self.agents_collection.delete_one({"_id": obj_id})
        return result.deleted_count > 0
    
    async def get_agent_prompts(self, agent_id: str) -> Optional[AgentPrompts]:
        """
        Obtener los prompts configurados para un agente
        
        Args:
            agent_id: ID del agente
            
        Returns:
            Prompts configurados si existe, None en caso contrario
        """
        agent = await self.get_agent(agent_id)
        if not agent:
            return None
        
        # Extraer prompts
        prompts = agent.prompts or {}
        
        return AgentPrompts(
            system_prompt=prompts.get("system_prompt"),
            query_evaluation_prompt=prompts.get("query_evaluation_prompt"),
            query_generation_prompt=prompts.get("query_generation_prompt"),
            result_formatting_prompt=prompts.get("result_formatting_prompt"),
            example_db_queries=prompts.get("example_db_queries")
        )
    
    async def update_agent_prompts(self, agent_id: str, prompts: AgentPrompts) -> Optional[AgentPrompts]:
        """
        Actualizar los prompts para un agente
        
        Args:
            agent_id: ID del agente
            prompts: Nuevos prompts
            
        Returns:
            Prompts actualizados si existe, None en caso contrario
        """
        try:
            obj_id = ObjectId(agent_id)
        except Exception:
            return None
        
        # Obtener agente existente
        agent = await self.agents_collection.find_one({"_id": obj_id})
        if not agent:
            return None
        
        # Preparar actualización
        prompts_dict = prompts.model_dump(exclude_none=True)
        
        # Actualizar en MongoDB
        await self.agents_collection.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "prompts": prompts_dict,
                    "updated_at": datetime.utcnow()
                }
            }
        )
        
        # Obtener documento actualizado
        updated = await self.agents_collection.find_one({"_id": obj_id})
        return self.get_agent_prompts(agent_id)
    
    async def get_agent_connections(self, agent_id: str) -> List[ConnectionAssignmentResponse]:
        """
        Obtener las conexiones asignadas a un agente
        
        Args:
            agent_id: ID del agente
            
        Returns:
            Lista de asignaciones de conexión
        """
        assignments = await self.connections_collection.find({"agent_id": agent_id}).to_list(length=100)
        
        result = []
        for assignment in assignments:
            # Obtener detalles de la conexión
            connection = await self.connection_service.get_connection(assignment["connection_id"])
            if connection:
                result.append(ConnectionAssignmentResponse(
                    id=str(assignment["_id"]),
                    agent_id=assignment["agent_id"],
                    connection=connection,
                    permissions=assignment["permissions"],
                    assigned_at=assignment.get("assigned_at", datetime.utcnow()),
                    assigned_by=assignment.get("assigned_by")
                ))
        
        return result
    
    async def assign_connection(self, assignment: ConnectionAssignment) -> ConnectionAssignmentResponse:
        """
        Asignar una conexión a un agente
        
        Args:
            assignment: Datos de asignación
            
        Returns:
            Asignación creada
            
        Raises:
            ValueError: Si hay errores de validación
        """
        # Verificar que el agente existe
        agent = await self.get_agent(assignment.agent_id)
        if not agent:
            raise ValueError(f"Agente no encontrado: {assignment.agent_id}")
        
        # Verificar que la conexión existe
        connection = await self.connection_service.get_connection(assignment.connection_id)
        if not connection:
            raise ValueError(f"Conexión no encontrada: {assignment.connection_id}")
        
        # Verificar si ya existe la asignación
        existing = await self.connections_collection.find_one({
            "agent_id": assignment.agent_id,
            "connection_id": assignment.connection_id
        })
        
        if existing:
            # Actualizar permisos
            await self.connections_collection.update_one(
                {"_id": existing["_id"]},
                {
                    "$set": {
                        "permissions": [p for p in assignment.permissions],
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            assignment_id = str(existing["_id"])
        else:
            # Crear nueva asignación
            assignment_dict = assignment.model_dump(exclude={"id"})
            assignment_dict["assigned_at"] = datetime.utcnow()
            
            result = await self.connections_collection.insert_one(assignment_dict)
            assignment_id = str(result.inserted_id)
        
        # Devolver objeto de respuesta
        return ConnectionAssignmentResponse(
            id=assignment_id,
            agent_id=assignment.agent_id,
            connection=connection,
            permissions=assignment.permissions,
            assigned_at=datetime.utcnow(),
            assigned_by=assignment.assigned_by
        )
    
    async def remove_connection(self, agent_id: str, connection_id: str) -> bool:
        """
        Eliminar una asignación de conexión
        
        Args:
            agent_id: ID del agente
            connection_id: ID de la conexión
            
        Returns:
            True si se eliminó, False si no existía
        """
        result = await self.connections_collection.delete_one({
            "agent_id": agent_id,
            "connection_id": connection_id
        })
        
        return result.deleted_count > 0
    
    def _to_agent(self, agent: Dict[str, Any]) -> DBAgent:
        """
        Convertir documento de agente a modelo
        
        Args:
            agent: Documento de agente
            
        Returns:
            Modelo de agente
        """
        agent_id = str(agent["_id"])
        
        # Eliminar _id
        if "_id" in agent:
            del agent["_id"]
        
        # Crear agente
        return DBAgent(id=agent_id, **agent)