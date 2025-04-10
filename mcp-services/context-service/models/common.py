# mcp-services/context-service/models/common.py
from bson import ObjectId

class PyObjectId(str):
    """
    Una clase personalizada para convertir ObjectIds de MongoDB a/desde strings.
    Esta implementación es compatible con Pydantic v2.
    """
    
    @classmethod
    def __get_pydantic_core_schema__(cls, _source_type, _handler):
        """
        Método necesario para validación de tipos en Pydantic v2.
        """
        from pydantic_core import PydanticCustomError, core_schema
        
        def validate_from_str(value: str) -> str:
            if not ObjectId.is_valid(value):
                raise PydanticCustomError("invalid_objectid", "Invalid ObjectId format")
            return value
            
        def validate_from_objectid(value: ObjectId) -> str:
            return str(value)
            
        schema = core_schema.union_schema([
            # Validación desde str
            core_schema.chain_schema([
                core_schema.str_schema(),
                core_schema.no_info_plain_validator_function(validate_from_str),
            ]),
            # Validación desde ObjectId
            core_schema.chain_schema([
                core_schema.is_instance_schema(ObjectId),
                core_schema.no_info_plain_validator_function(validate_from_objectid),
            ]),
        ])
        
        return schema
        
    # Mantener métodos antiguos para retrocompatibilidad    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
        
    @classmethod
    def validate(cls, v):
        if not isinstance(v, (str, ObjectId)):
            raise TypeError("ObjectId required")
        
        if isinstance(v, str):
            if not ObjectId.is_valid(v):
                raise ValueError("Invalid ObjectId format")
            return str(v)
            
        return str(v)
    
    @classmethod
    def __modify_schema__(cls, field_schema):
        field_schema.update(type="string")
    
    @classmethod
    def __get_pydantic_json_schema__(cls, field_schema, **kwargs):
        field_schema.update(type="string")
        return field_schema