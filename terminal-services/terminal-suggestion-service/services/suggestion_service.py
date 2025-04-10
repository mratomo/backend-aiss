import json
import time
import uuid
import logging
import asyncio
import aiohttp
import httpx
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from config.settings import settings
from models.suggestion import (
    Suggestion, 
    SuggestionType, 
    SuggestionRisk
)
from services.mcp_service import MCPService

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
        self.mcp_service = MCPService()
        
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
        """Get suggestions for a terminal command and output using MCP context when available"""
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
        
        # Check MCP service status asynchronously to avoid delaying critical suggestion generation
        mcp_status_task = asyncio.create_task(self.mcp_service.get_status())
        
        # Basic suggestions using rules - generate these immediately while waiting for LLM
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
        
        # Wait for MCP status check to complete if it's not done yet
        try:
            # Use a short timeout to avoid blocking
            mcp_status = await asyncio.wait_for(mcp_status_task, timeout=0.5)
            mcp_available = isinstance(mcp_status, dict) and "name" in mcp_status
        except (asyncio.TimeoutError, Exception) as e:
            logger.warning(f"MCP status check timed out or failed: {str(e)}")
            mcp_available = False
        
        # Calculate processing time
        processing_time = time.time() - start_time
        
        # Prepare response
        result = {
            "session_id": session_id,
            "suggestions": all_suggestions,
            "processing_time_ms": processing_time * 1000,
            "context_used": bool(context),
            "mcp_available": mcp_available,
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
        """Get suggestions using LLM service with MCP context enhancement"""
        try:
            # Enrich context with MCP if context wasn't provided
            mcp_context = None
            if not context or len(context) == 0:
                try:
                    # Try to get relevant context from MCP for this command
                    mcp_result = await self.mcp_service.get_command_context(session_id, command)
                    
                    if mcp_result.get("enriched", False):
                        # Extract relevant context from MCP
                        relevant_items = mcp_result.get("relevant_context", [])
                        if relevant_items:
                            # Convert MCP context to a format that can be used in the prompt
                            mcp_context = {
                                "command_history": [],
                                "mcp_context": []
                            }
                            
                            # Process each context item
                            for item in relevant_items:
                                if isinstance(item, dict):
                                    text = item.get("text", "")
                                    if "Command History:" in text:
                                        # Extract command history
                                        cmd_history_section = text.split("Command History:")[1].strip()
                                        commands = [cmd.strip() for cmd in cmd_history_section.split("\n") if cmd.strip()]
                                        mcp_context["command_history"].extend(commands[-5:])  # Last 5 commands
                                    
                                    # Add the relevant context
                                    mcp_context["mcp_context"].append(text)
                                elif isinstance(item, str):
                                    mcp_context["mcp_context"].append(item)
                except Exception as e:
                    logger.warning(f"Failed to get MCP context: {e}")
                    # Continue without MCP context
            
            # Merge existing context with MCP context
            merged_context = context or {}
            if mcp_context:
                # If both have command_history, combine them
                if "command_history" in merged_context and "command_history" in mcp_context:
                    # Get unique commands from both sources, prioritizing existing context
                    existing_cmds = set(merged_context["command_history"])
                    merged_context["command_history"] = merged_context["command_history"] + [
                        cmd for cmd in mcp_context["command_history"] if cmd not in existing_cmds
                    ]
                elif "command_history" in mcp_context:
                    merged_context["command_history"] = mcp_context["command_history"]
                
                # Add MCP-specific context
                if "mcp_context" in mcp_context:
                    merged_context["mcp_context"] = mcp_context["mcp_context"]
            
            # Build prompt with enhanced context
            prompt = self._build_llm_prompt(command, output, exit_code, merged_context)
            
            # Call LLM service
            async with httpx.AsyncClient() as client:
                response = await client.post(
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
                
                if response.status_code != 200:
                    logger.warning(f"LLM service returned error: {response.status_code}")
                    return []
                
                result = response.json()
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
                            
                            # Store quality suggestions in MCP for future reference
                            if suggestion.command and suggestion.type in [SuggestionType.COMMAND, SuggestionType.ERROR_FIX]:
                                # Store asynchronously without waiting for result
                                asyncio.create_task(
                                    self.mcp_service.store_suggestion(session_id, command, suggestion)
                                )
                                
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
        """Build prompt for LLM with enhanced MCP context"""
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
            
            # Add recent commands (from terminal-context-aggregator or MCP)
            command_history = []
            if "last_commands" in context and context["last_commands"]:
                command_history.extend(context["last_commands"])
            elif "command_history" in context and context["command_history"]:
                command_history.extend(context["command_history"])
                
            if command_history:
                # Get unique commands, limit to most recent 5
                unique_commands = []
                for cmd in reversed(command_history):
                    if cmd not in unique_commands and cmd != command:  # Exclude current command
                        unique_commands.append(cmd)
                        if len(unique_commands) >= 5:
                            break
                            
                if unique_commands:
                    context_str += "\nRecent commands:\n" + "\n".join(reversed(unique_commands))
            
            # Add detected applications
            if "detected_applications" in context and context["detected_applications"]:
                context_str += f"\nDetected applications: {', '.join(context['detected_applications'])}"
            
            # Add MCP context if available
            if "mcp_context" in context and context["mcp_context"]:
                mcp_context_items = context["mcp_context"]
                # Filter to avoid too much redundancy or irrelevant information
                filtered_items = []
                for item in mcp_context_items:
                    # Extract useful segments and avoid duplicating information already in context
                    if isinstance(item, str):
                        # Only include if likely to be relevant to current command
                        if any(term in command.lower() for term in item.lower().split()[:10]):
                            filtered_items.append(item)
                    elif isinstance(item, dict) and "text" in item:
                        if any(term in command.lower() for term in item["text"].lower().split()[:10]):
                            filtered_items.append(item["text"])
                
                if filtered_items:
                    context_str += "\n\nRelevant historical context:\n"
                    for item in filtered_items[:3]:  # Limit to 3 items to avoid too much context
                        context_str += f"\n---\n{item[:300]}..."  # Truncate long items
            
            prompt += context_str
        
        return system_prompt + prompt
    
    async def cleanup_cache(self) -> int:
        """Clean up expired cache entries"""
        return self.cache.cleanup()
