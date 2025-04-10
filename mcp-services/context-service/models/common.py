# mcp-services/context-service/models/common.py
from bson import ObjectId

class PyObjectId(str):
    """
    Una clase personalizada para convertir ObjectIds de MongoDB a/desde strings.
    Esta implementación es compatible con Pydantic v2.
    """
    
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