import json
import time
import uuid
import logging
import asyncio
import aiohttp
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from config.settings import settings
from models.suggestion import (
    Suggestion, 
    SuggestionType, 
    SuggestionRisk
)

logger = logging.getLogger(__name__)

class SuggestionCache:
    """Simple in-memory cache for suggestions"""
    _cache: Dict[str, Dict[str, Any]] = {}
    _timestamps: Dict[str, datetime] = {}
    
    def get(self, key: str) -> Optional[List[Suggestion]]:
        """Get suggestions from cache if not expired"""
        now = datetime.utcnow()
        if key in self._timestamps:
            # Check if expired
            if now - self._timestamps[key] > timedelta(minutes=settings.CACHE_EXPIRY_MINUTES):
                # Expired, remove from cache
                if key in self._cache:
                    del self._cache[key]
                del self._timestamps[key]
                return None
            
            # Not expired, return cached suggestions
            if key in self._cache:
                return self._cache[key].get("suggestions")
        
        return None
    
    def set(self, key: str, value: Dict[str, Any]):
        """Set suggestions in cache"""
        self._cache[key] = value
        self._timestamps[key] = datetime.utcnow()
    
    def invalidate(self, key: str):
        """Invalidate cache for key"""
        if key in self._cache:
            del self._cache[key]
        if key in self._timestamps:
            del self._timestamps[key]
    
    def cleanup(self):
        """Remove expired entries"""
        now = datetime.utcnow()
        expired_keys = []
        for key, timestamp in self._timestamps.items():
            if now - timestamp > timedelta(minutes=settings.CACHE_EXPIRY_MINUTES):
                expired_keys.append(key)
        
        for key in expired_keys:
            if key in self._cache:
                del self._cache[key]
            del self._timestamps[key]
        
        return len(expired_keys)

class SuggestionService:
    """Service for generating terminal command suggestions"""
    
    def __init__(self):
        self.cache = SuggestionCache()
        
        # Simple rules for pattern matching
        self.error_patterns = {
            "permission_denied": ["permission denied", "access denied", "operation not permitted"],
            "command_not_found": ["command not found", "not recognized", "unknown command"],
            "syntax_error": ["syntax error", "invalid syntax", "unexpected token"],
            "network_error": ["network is unreachable", "connection refused", "could not resolve host"],
        }
        
        # Common tools and their install commands
        self.common_tools = {
            "git": {
                "debian": "apt-get install git",
                "rhel": "yum install git",
                "alpine": "apk add git",
                "arch": "pacman -S git",
            },
            "curl": {
                "debian": "apt-get install curl",
                "rhel": "yum install curl",
                "alpine": "apk add curl",
                "arch": "pacman -S curl",
            },
            "python": {
                "debian": "apt-get install python3",
                "rhel": "yum install python3",
                "alpine": "apk add python3",
                "arch": "pacman -S python",
            },
            "docker": {
                "debian": "apt-get install docker.io",
                "rhel": "yum install docker",
                "alpine": "apk add docker",
                "arch": "pacman -S docker",
            },
        }
        
        # Common error fixes
        self.error_fixes = {
            "permission_denied": lambda cmd: f"sudo {cmd}",
            "command_not_found": lambda cmd: self._suggest_install_command(cmd),
        }
    
    def _suggest_install_command(self, command: str) -> str:
        """Suggest installation command for common tools"""
        # Extract first word of command (the actual command)
        cmd_parts = command.strip().split()
        if not cmd_parts:
            return ""
        
        tool = cmd_parts[0]
        
        # Check if it's a common tool
        if tool in self.common_tools:
            return "# Try installing the command first:\n" + self.common_tools[tool]["debian"] + "\n# or\n" + self.common_tools[tool]["rhel"]
        
        return "# You might need to install this command first"
    
    def _make_cache_key(self, session_id: str, command: str) -> str:
        """Create a cache key for the session and command"""
        # Simple command normalization - remove leading/trailing whitespace
        normalized_cmd = command.strip()
        return f"{session_id}:{normalized_cmd}"
    
    async def get_suggestions(self, 
                             session_id: str, 
                             user_id: str, 
                             command: str, 
                             output: str, 
                             exit_code: int = 0, 
                             context: Optional[Dict[str, Any]] = None,
                             use_cache: bool = True) -> Dict[str, Any]:
        """Get suggestions for a terminal command and output"""
        start_time = time.time()
        
        # Check cache if enabled
        if use_cache:
            cache_key = self._make_cache_key(session_id, command)
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"Using cached suggestions for {cache_key}")
                processing_time = time.time() - start_time
                return {
                    "session_id": session_id,
                    "suggestions": cached,
                    "processing_time_ms": processing_time * 1000,
                    "context_used": True,
                    "cached": True,
                }
        
        # Basic suggestions using rules
        rule_suggestions = self._get_rule_based_suggestions(command, output, exit_code)
        
        # Try to get LLM-based suggestions with timeout
        llm_suggestions = []
        try:
            # Run with timeout
            llm_task = self._get_llm_suggestions(session_id, user_id, command, output, exit_code, context)
            llm_suggestions = await asyncio.wait_for(llm_task, timeout=settings.SUGGESTION_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            logger.warning(f"LLM suggestion generation timed out for session {session_id}")
        except Exception as e:
            logger.exception(f"Error getting LLM suggestions: {str(e)}")
        
        # Combine suggestions, prioritizing LLM suggestions
        all_suggestions = llm_suggestions if llm_suggestions else rule_suggestions
        
        # Limit to max suggestions
        all_suggestions = all_suggestions[:settings.MAX_SUGGESTIONS]
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Prepare response
        result = {
            "session_id": session_id,
            "suggestions": all_suggestions,
            "processing_time_ms": processing_time * 1000,
            "context_used": bool(context),
            "source": "llm" if llm_suggestions else "rules",
        }
        
        # Cache result if enabled
        if use_cache:
            cache_key = self._make_cache_key(session_id, command)
            self.cache.set(cache_key, result)
        
        return result
    
    def _get_rule_based_suggestions(self, command: str, output: str, exit_code: int) -> List[Suggestion]:
        """Generate suggestions based on predefined rules"""
        suggestions = []
        
        # Error handling suggestions
        if exit_code != 0:
            error_type = self._detect_error_type(output)
            if error_type and error_type in self.error_fixes:
                fix_fn = self.error_fixes[error_type]
                fixed_command = fix_fn(command)
                if fixed_command:
                    suggestions.append(Suggestion(
                        id=str(uuid.uuid4()),
                        type=SuggestionType.ERROR_FIX,
                        title=f"Fix {error_type.replace('_', ' ')}",
                        content=f"The command failed due to {error_type.replace('_', ' ')}. Try using the suggested command.",
                        command=fixed_command,
                        risk_level=SuggestionRisk.LOW if error_type != "permission_denied" else SuggestionRisk.MEDIUM,
                        requires_confirmation=error_type == "permission_denied"
                    ))
        
        # Simple command suggestions for common patterns
        if "directory not empty" in output.lower() and "rm" in command:
            suggestions.append(Suggestion(
                id=str(uuid.uuid4()),
                type=SuggestionType.COMMAND,
                title="Force remove directory",
                content="The directory is not empty. Use -rf to force remove it and its contents.",
                command=command.replace("rm", "rm -rf"),
                risk_level=SuggestionRisk.HIGH,
                risk_explanation="This will permanently delete the directory and all its contents.",
                requires_confirmation=True
            ))
        
        # Explanation suggestions
        if len(output) > 500:
            suggestions.append(Suggestion(
                id=str(uuid.uuid4()),
                type=SuggestionType.EXPLANATION,
                title="Explain output",
                content="The output is quite long. Would you like me to explain it?",
                metadata={"output_length": len(output)}
            ))
        
        return suggestions
    
    def _detect_error_type(self, output: str) -> Optional[str]:
        """Detect the type of error from output"""
        output_lower = output.lower()
        
        for error_type, patterns in self.error_patterns.items():
            for pattern in patterns:
                if pattern in output_lower:
                    return error_type
        
        return None
    
    async def _get_llm_suggestions(self, 
                                  session_id: str, 
                                  user_id: str, 
                                  command: str, 
                                  output: str, 
                                  exit_code: int,
                                  context: Optional[Dict[str, Any]]) -> List[Suggestion]:
        """Get suggestions using LLM service"""
        try:
            # Build prompt with context
            prompt = self._build_llm_prompt(command, output, exit_code, context)
            
            # Call LLM service
            async with aiohttp.ClientSession() as session:
                response = await session.post(
                    settings.LLM_SERVICE_URL,
                    json={
                        "prompt": prompt,
                        "model": settings.LLM.model,
                        "temperature": settings.LLM.temperature,
                        "max_tokens": settings.LLM.max_tokens,
                        "response_format": {"type": "json_object"},
                    },
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status != 200:
                    logger.warning(f"LLM service returned error: {response.status}")
                    return []
                
                result = await response.json()
                response_text = result.get("response", "")
                
                try:
                    # Parse LLM response as JSON
                    suggestions_data = json.loads(response_text)
                    suggestions_list = suggestions_data.get("suggestions", [])
                    
                    # Convert to Suggestion objects
                    suggestions = []
                    for item in suggestions_list:
                        try:
                            # Extract optional fields with defaults
                            risk_level = item.get("risk_level", "low")
                            suggestion_type = item.get("type", "command")
                            
                            # Create suggestion
                            suggestion = Suggestion(
                                id=str(uuid.uuid4()),
                                type=suggestion_type,
                                title=item["title"],
                                content=item["content"],
                                command=item.get("command"),
                                risk_level=risk_level,
                                risk_explanation=item.get("risk_explanation"),
                                requires_confirmation=item.get("requires_confirmation", False),
                                metadata=item.get("metadata", {})
                            )
                            suggestions.append(suggestion)
                        except KeyError as e:
                            logger.warning(f"Invalid suggestion data, missing key: {e}")
                    
                    return suggestions
                    
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse LLM response as JSON: {e}")
                    return []
                
        except Exception as e:
            logger.exception(f"Error getting LLM suggestions: {str(e)}")
            return []
    
    def _build_llm_prompt(self, 
                         command: str, 
                         output: str, 
                         exit_code: int,
                         context: Optional[Dict[str, Any]]) -> str:
        """Build prompt for LLM"""
        system_prompt = """
        You are an AI assistant specialized in terminal operations. Generate helpful suggestions for the user based on their recent terminal command and its output.
        Focus on providing actionable, specific suggestions that will help the user achieve their goal.
        
        You must return your answer in valid JSON format with a 'suggestions' array. Each suggestion should include:
        - 'type': The type of suggestion (command, error_fix, explanation, optimization, warning, education, security)
        - 'title': A short, descriptive title
        - 'content': Detailed explanation of the suggestion
        - 'command': (optional) A command to execute if applicable
        - 'risk_level': (optional) Risk level (low, medium, high) - default is 'low'
        - 'risk_explanation': (optional) An explanation of any risks if applicable
        - 'requires_confirmation': (optional) Whether confirmation is needed (true/false) - default is false
        
        Provide suggestions that are:
        1. Relevant to the user's command and its output
        2. Technically accurate
        3. Prioritized by usefulness
        4. Security-conscious (mark anything potentially risky)
        5. Educational (help the user learn)
        
        Limit to 1-3 high-quality suggestions that are most relevant.  
        """
        
        # Construct the prompt
        prompt = f"""
        Command: {command}
        
        Exit code: {exit_code}
        
        Output:
        {output[:1000]}  # Truncate output if too long
        """
        
        # Add context information if available
        if context:
            context_str = """
Context information:
"""
            if "current_directory" in context:
                context_str += f"\nCurrent directory: {context['current_directory']}"
            if "current_user" in context:
                context_str += f"\nCurrent user: {context['current_user']}"
            if "hostname" in context:
                context_str += f"\nHostname: {context['hostname']}"
            if "last_commands" in context and context["last_commands"]:
                commands = context["last_commands"][-5:]  # Last 5 commands
                context_str += "\nRecent commands:\n" + "\n".join(commands)
            if "detected_applications" in context and context["detected_applications"]:
                context_str += f"\nDetected applications: {', '.join(context['detected_applications'])}"
            
            prompt += context_str
        
        return system_prompt + prompt
    
    async def cleanup_cache(self) -> int:
        """Clean up expired cache entries"""
        return self.cache.cleanup()
