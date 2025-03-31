from enum import Enum
from typing import Dict, List, Optional, Union, Any
from datetime import datetime
from pydantic import BaseModel, Field

class OutputType(str, Enum):
    STDOUT = "stdout"
    STDERR = "stderr"
    INFO = "info"
    ERROR = "error"

class CommandOrigin(str, Enum):
    USER = "user"
    SUGGESTED = "suggested"
    SCRIPT = "script"
    SYSTEM = "system"

class ErrorType(str, Enum):
    PERMISSION_DENIED = "permission_denied"
    COMMAND_NOT_FOUND = "command_not_found"
    SYNTAX_ERROR = "syntax_error"
    NETWORK_ERROR = "network_error"
    OTHER = "other"

class TerminalCommand(BaseModel):
    command_id: str
    session_id: str
    command_text: str
    origin: CommandOrigin = CommandOrigin.USER
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    working_directory: str
    user: str = "unknown"
    hostname: str = "unknown"
    environment_variables: Dict[str, str] = Field(default_factory=dict)

class TerminalOutput(BaseModel):
    command_id: str
    session_id: str
    output_text: str
    output_type: OutputType
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    exit_code: Optional[int] = None
    error_detected: bool = False
    error_type: Optional[ErrorType] = None

class TerminalContext(BaseModel):
    session_id: str
    user_id: str
    current_directory: str = "/"
    current_user: str = "unknown"
    hostname: str = "unknown"
    last_commands: List[str] = Field(default_factory=list)
    last_outputs: List[str] = Field(default_factory=list)
    environment_variables: Dict[str, str] = Field(default_factory=dict)
    last_exit_code: int = 0
    detected_applications: List[str] = Field(default_factory=list)
    detected_errors: List[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=datetime.utcnow)

class AnalysisRequest(BaseModel):
    session_id: str
    user_id: str
    command: Optional[TerminalCommand] = None
    output: Optional[TerminalOutput] = None
    full_context: bool = False

class ContextResponse(BaseModel):
    session_id: str
    context: TerminalContext
    analysis: Dict[str, Any] = Field(default_factory=dict)
    suggestions: List[Dict[str, Any]] = Field(default_factory=list)
