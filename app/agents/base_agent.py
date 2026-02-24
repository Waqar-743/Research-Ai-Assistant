"""
Base Agent Class
Provides common functionality for all specialized agents.

Phase 3: Sentry integration — agent execution and LLM calls are
wrapped with Sentry spans for tracing and error capture.
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List, Callable
from datetime import datetime
from enum import Enum

import sentry_sdk

from app.config import settings
from app.utils.logging import logger
from app.tools.llm_tools import LLMTools


class AgentStatus(str, Enum):
    """Agent execution status."""
    IDLE = "idle"
    QUEUED = "queued"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class BaseAgent(ABC):
    """
    Base class for all research agents.
    Provides common functionality and interface.
    """
    
    def __init__(
        self,
        name: str,
        role: str,
        system_prompt: str,
        model: str,
        temperature: float = 0.5,
        max_tokens: int = 4096,
        timeout: int = 120
    ):
        """
        Initialize the base agent.
        
        Args:
            name: Agent name
            role: Agent role description
            system_prompt: System prompt for the LLM
            model: LLM model to use
            temperature: Sampling temperature
            max_tokens: Maximum tokens for generation
            timeout: Execution timeout in seconds
        """
        self.name = name
        self.role = role
        self.system_prompt = system_prompt
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        
        self.llm = LLMTools()
        self.status = AgentStatus.IDLE
        self.progress = 0
        self.output: Optional[str] = None
        self.error: Optional[str] = None
        
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # Callback for progress updates
        self._progress_callback: Optional[Callable] = None
    
    def set_progress_callback(self, callback: Callable):
        """Set callback for progress updates."""
        self._progress_callback = callback
    
    async def _update_progress(self, progress: int, message: Optional[str] = None):
        """Update progress and notify callback."""
        self.progress = progress
        if message:
            self.output = message
        
        if self._progress_callback:
            await self._progress_callback(
                agent_name=self.name.lower().replace(" ", "_"),
                status=self.status.value,
                progress=progress,
                output=message
            )
    
    async def _set_status(self, status: AgentStatus, error: Optional[str] = None):
        """Update agent status."""
        self.status = status
        if error:
            self.error = error
        
        if status == AgentStatus.IN_PROGRESS and self.start_time is None:
            self.start_time = datetime.utcnow()
        elif status in [AgentStatus.COMPLETED, AgentStatus.FAILED]:
            self.end_time = datetime.utcnow()
        
        if self._progress_callback:
            await self._progress_callback(
                agent_name=self.name.lower().replace(" ", "_"),
                status=status.value,
                progress=self.progress,
                output=self.output,
                error=error
            )
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute the agent's main task.
        
        Args:
            context: Execution context with input data
            
        Returns:
            Results dictionary
        """
        pass
    
    async def think(self, prompt: str, context: Optional[str] = None) -> str:
        """
        Use LLM for reasoning/thinking.
        
        Phase 3: wrapped with Sentry span for tracing.
        """
        full_prompt = prompt
        if context:
            full_prompt = f"Context:\n{context}\n\n{prompt}"
        
        with sentry_sdk.start_span(op="llm.generate", description=f"{self.name} think") as span:
            span.set_data("agent", self.name)
            span.set_data("model", self.model)
            span.set_data("prompt_length", len(full_prompt))
            try:
                response = await self.llm.generate(
                    prompt=full_prompt,
                    model=self.model,
                    system_prompt=self.system_prompt,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )
                span.set_data("response_length", len(response))
                return response
            except Exception as e:
                sentry_sdk.capture_exception(e)
                logger.error(f"Agent {self.name} thinking failed: {e}")
                raise
    
    def get_state(self) -> Dict[str, Any]:
        """Get current agent state."""
        return {
            "name": self.name,
            "status": self.status.value,
            "progress": self.progress,
            "output": self.output,
            "error": self.error,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None
        }
    
    def reset(self):
        """Reset agent state for new execution."""
        self.status = AgentStatus.IDLE
        self.progress = 0
        self.output = None
        self.error = None
        self.start_time = None
        self.end_time = None
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(name={self.name}, status={self.status.value})>"
