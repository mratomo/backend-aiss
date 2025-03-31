import re
import json
import asyncio
import logging
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from config.settings import settings
from models.terminal import (
    TerminalCommand, 
    TerminalOutput, 
    TerminalContext,
    ErrorType
)

logger = logging.getLogger(__name__)

class ContextService:
    _contexts: Dict[str, TerminalContext] = {}
    _last_access: Dict[str, datetime] = {}
    
    def __init__(self):
        # Pattern for common error messages
        self.error_patterns = {
            ErrorType.PERMISSION_DENIED: [
                r"permission denied",
                r"cannot open.*access",
                r"operation not permitted"
            ],
            ErrorType.COMMAND_NOT_FOUND: [
                r"command not found",
                r"not recognized as .* command",
                r"unknown command"
            ],
            ErrorType.SYNTAX_ERROR: [
                r"syntax error",
                r"invalid syntax",
                r"unexpected.*token"
            ],
            ErrorType.NETWORK_ERROR: [
                r"network is unreachable",
                r"connection refused",
                r"could not resolve host"
            ]
        }
        
        # Common Linux/Unix command patterns for extracting working directory
        self.cd_pattern = re.compile(r"^\s*cd\s+([^;&|<>]*)")
        
        # Detect common applications/tools
        self.app_patterns = {
            "docker": r"\bdocker\b",
            "kubernetes": r"\b(kubectl|k8s|kubernetes)\b",
            "git": r"\bgit\b",
            "python": r"\b(python|python3|pip|pip3|virtualenv|venv)\b",
            "node": r"\b(node|npm|yarn|npx)\b",
            "database": r"\b(mysql|psql|postgresql|mongodb|mongo)\b",
            "aws": r"\b(aws|s3|ec2|lambda)\b",
            "azure": r"\b(az|azure)\b",
            "gcp": r"\b(gcloud|gsutil)\b"
        }
    
    async def get_context(self, session_id: str, user_id: str) -> TerminalContext:
        """Get or create terminal context for session"""
        now = datetime.utcnow()
        
        # Update last access time
        self._last_access[session_id] = now
        
        # Check if context exists
        if session_id in self._contexts:
            return self._contexts[session_id]
        
        # Create new context
        context = TerminalContext(session_id=session_id, user_id=user_id)
        self._contexts[session_id] = context
        return context
    
    async def update_context_from_command(self, command: TerminalCommand) -> TerminalContext:
        """Update context with information from command"""
        # Get context
        context = await self.get_context(command.session_id, command.user_id)
        
        # Update basic information
        context.current_directory = command.working_directory
        context.current_user = command.user
        context.hostname = command.hostname
        context.last_updated = datetime.utcnow()
        
        # Update environment variables if provided
        if command.environment_variables:
            context.environment_variables.update(command.environment_variables)
        
        # Add command to history
        context.last_commands.append(command.command_text)
        if len(context.last_commands) > 20:  # Keep only last 20 commands
            context.last_commands = context.last_commands[-20:]
        
        # Detect applications
        self._detect_applications(context, command.command_text)
        
        # Update context in storage
        self._contexts[command.session_id] = context
        
        return context
    
    async def update_context_from_output(self, output: TerminalOutput) -> TerminalContext:
        """Update context with information from command output"""
        # Get context
        context = await self.get_context(output.session_id, "unknown")
        
        # Update basic information
        context.last_exit_code = output.exit_code or 0
        context.last_updated = datetime.utcnow()
        
        # Add output to history
        truncated_output = output.output_text[:1000]  # Limit size
        context.last_outputs.append(truncated_output)
        if len(context.last_outputs) > 10:  # Keep only last 10 outputs
            context.last_outputs = context.last_outputs[-10:]
        
        # Detect errors
        if output.error_detected or output.exit_code != 0:
            error_type = output.error_type or self._detect_error_type(output.output_text)
            if error_type:
                error_info = {
                    "pattern": str(error_type),
                    "count": 1,
                    "last_seen": datetime.utcnow()
                }
                
                # Check if error already exists in detected_errors
                error_exists = False
                for i, error in enumerate(context.detected_errors):
                    if error["pattern"] == str(error_type):
                        context.detected_errors[i]["count"] += 1
                        context.detected_errors[i]["last_seen"] = datetime.utcnow()
                        error_exists = True
                        break
                
                if not error_exists:
                    context.detected_errors.append(error_info)
        
        # Update context in storage
        self._contexts[output.session_id] = context
        
        return context
    
    async def analyze_terminal_output(self, session_id: str, user_id: str, command_text: str, output_text: str, exit_code: int = 0) -> Dict[str, Any]:
        """Analyze terminal output and update context"""
        # Create command and output objects
        command = TerminalCommand(
            command_id=f"{session_id}-{int(datetime.utcnow().timestamp())}",
            session_id=session_id,
            command_text=command_text,
            working_directory="/",  # Default, would be updated from real data
            user="unknown",
            hostname="unknown"
        )
        
        output = TerminalOutput(
            command_id=command.command_id,
            session_id=session_id,
            output_text=output_text,
            output_type="stdout",
            exit_code=exit_code,
            error_detected=exit_code != 0
        )
        
        # Update context from command and output
        await self.update_context_from_command(command)
        context = await self.update_context_from_output(output)
        
        # Analyze context
        analysis_results = await self._analyze_context(context)
        
        # Get suggestions
        suggestions = await self._get_suggestions(context, command_text, output_text)
        
        return {
            "session_id": session_id,
            "context": context.dict(),
            "analysis": analysis_results,
            "suggestions": suggestions
        }
    
    async def _analyze_context(self, context: TerminalContext) -> Dict[str, Any]:
        """Analyze terminal context for insights"""
        # Basic analysis
        analysis = {
            "patterns": [],
            "identified_tools": context.detected_applications,
            "common_errors": [e["pattern"] for e in context.detected_errors],
            "session_analysis": {
                "command_count": len(context.last_commands),
                "error_rate": sum(e["count"] for e in context.detected_errors) / max(1, len(context.last_commands))
            }
        }
        
        # Try to identify command patterns
        if len(context.last_commands) >= 3:
            last_three = context.last_commands[-3:]
            if all(cmd.startswith("git ") for cmd in last_three):
                analysis["patterns"].append("git_workflow")
            elif any("build" in cmd for cmd in last_three) and any("test" in cmd for cmd in last_three):
                analysis["patterns"].append("build_test_cycle")
        
        return analysis
    
    async def _get_suggestions(self, context: TerminalContext, command: str, output: str) -> List[Dict[str, Any]]:
        """Get suggestions based on context, command and output"""
        try:
            # If suggestion service is available, call it
            async with aiohttp.ClientSession() as session:
                try:
                    response = await session.post(
                        f"{settings.SUGGESTION_SERVICE_URL}/api/v1/suggest",
                        json={
                            "session_id": context.session_id,
                            "user_id": context.user_id,
                            "command": command,
                            "output": output,
                            "context": context.dict()
                        },
                        timeout=settings.SUGGESTION_TIMEOUT_SECONDS  # Use configurable timeout from settings
                    )
                    
                    if response.status == 200:
                        result = await response.json()
                        return result.get("suggestions", [])
                    
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    logger.warning(f"Failed to get suggestions: {str(e)}")
        except Exception as e:
            logger.exception(f"Error getting suggestions: {str(e)}")
        
        # Fallback to basic suggestions
        suggestions = []
        
        # Error suggestions
        if context.last_exit_code != 0:
            if "permission denied" in output.lower():
                suggestions.append({
                    "type": "error_fix",
                    "title": "Permission denied",
                    "content": "Try using sudo for this command",
                    "command": f"sudo {command}"
                })
            elif "command not found" in output.lower():
                suggestions.append({
                    "type": "error_fix",
                    "title": "Command not found",
                    "content": "This command might not be installed",
                    "meta": {"install_info": True}
                })
        
        return suggestions
    
    def _detect_applications(self, context: TerminalContext, command_text: str) -> None:
        """Detect applications being used"""
        for app, pattern in self.app_patterns.items():
            if re.search(pattern, command_text, re.IGNORECASE) and app not in context.detected_applications:
                context.detected_applications.append(app)
    
    def _detect_error_type(self, output_text: str) -> Optional[ErrorType]:
        """Detect type of error from output text"""
        lowered = output_text.lower()
        
        for error_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if re.search(pattern, lowered, re.IGNORECASE):
                    return error_type
        
        return ErrorType.OTHER if "error" in lowered else None
    
    async def cleanup_old_contexts(self) -> int:
        """Remove contexts that haven't been accessed recently"""
        now = datetime.utcnow()
        expiry_time = now - timedelta(minutes=settings.CONTEXT_EXPIRY_MINUTES)
        
        to_remove = []
        for session_id, last_access in self._last_access.items():
            if last_access < expiry_time:
                to_remove.append(session_id)
        
        for session_id in to_remove:
            if session_id in self._contexts:
                del self._contexts[session_id]
            del self._last_access[session_id]
        
        return len(to_remove)
