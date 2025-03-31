from enum import Enum
from typing import Dict, List, Optional, Union, Any
from datetime import datetime
from pydantic import BaseModel, Field

class SuggestionType(str, Enum):
    COMMAND = "command"            # Suggested commands to run
    ERROR_FIX = "error_fix"        # Fix for error in last command
    EXPLANATION = "explanation"    # Explanation of output or command
    OPTIMIZATION = "optimization"  # Optimization for the last command
    WARNING = "warning"           # Warning about command or its impact
    EDUCATION = "education"       # Educational information
    SECURITY = "security"         # Security concerns or improvements

class SuggestionRisk(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"

class Suggestion(BaseModel):
    id: str = Field(..., description="Unique identifier for the suggestion")
    type: SuggestionType = Field(..., description="Type of suggestion")
    title: str = Field(..., description="Short title for the suggestion")
    content: str = Field(..., description="Detailed suggestion content")
    command: Optional[str] = Field(None, description="Command to execute if applicable")
    risk_level: SuggestionRisk = Field(default=SuggestionRisk.LOW, description="Risk level of the suggestion")
    risk_explanation: Optional[str] = Field(None, description="Explanation of risks if applicable")
    requires_confirmation: bool = Field(default=False, description="Whether user confirmation is required")
    timestamp: datetime = Field(default_factory=datetime.utcnow, description="When the suggestion was generated")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")

class SuggestionRequest(BaseModel):
    session_id: str
    user_id: str
    command: str
    output: str
    exit_code: int = 0
    context: Optional[Dict[str, Any]] = None

class SuggestionResponse(BaseModel):
    session_id: str
    suggestions: List[Suggestion]
    processing_time_ms: float
    context_used: bool = True
