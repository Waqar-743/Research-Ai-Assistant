"""
Agent Orchestrator
Coordinates the multi-agent research workflow.
"""

from typing import Dict, Any, Optional, Callable, List
from datetime import datetime
from enum import Enum
import asyncio

from app.agents.base_agent import AgentStatus
from app.agents.researcher import ResearcherAgent
from app.agents.analyst import AnalystAgent
from app.agents.fact_checker import FactCheckerAgent
from app.agents.report_generator import ReportGeneratorAgent
from app.agents.user_proxy import UserProxyAgent
from app.config import settings
from app.utils.logging import logger


class WorkflowPhase(str, Enum):
    """Workflow execution phases."""
    INITIALIZATION = "initialization"
    QUERY_PROCESSING = "query_processing"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    FACT_CHECKING = "fact_checking"
    REPORT_GENERATION = "report_generation"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentOrchestrator:
    """
    Agent Orchestrator - Coordinates multi-agent research workflow.
    
    Workflow Sequence:
    1. User Proxy: Clarify query and get approval (if supervised)
    2. Researcher: Gather information from multiple sources
    3. Analyst: Synthesize and analyze findings
    4. Fact-Checker: Verify claims and assess credibility
    5. Report Generator: Create comprehensive research report
    
    Supports:
    - Auto mode: Full autonomous execution
    - Supervised mode: Checkpoints for human approval
    - Real-time progress updates via WebSocket
    """
    
    def __init__(self):
        """Initialize the orchestrator and all agents."""
        self.session_id: Optional[str] = None
        self.current_phase = WorkflowPhase.INITIALIZATION
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        
        # Initialize all agents
        self.user_proxy = UserProxyAgent()
        self.researcher = ResearcherAgent()
        self.analyst = AnalystAgent()
        self.fact_checker = FactCheckerAgent()
        self.report_generator = ReportGeneratorAgent()
        
        # Callback for progress updates
        self._progress_callback: Optional[Callable] = None
        
        # Execution state
        self.is_running = False
        self.is_cancelled = False
        self.results: Dict[str, Any] = {}
        self.errors: List[str] = []
    
    def set_progress_callback(self, callback: Callable):
        """
        Set callback for real-time progress updates.
        
        Callback signature:
        async def callback(
            agent_name: str,
            status: str,
            progress: int,
            output: Optional[str] = None,
            error: Optional[str] = None
        )
        """
        self._progress_callback = callback
        
        # Set callback on all agents
        self.user_proxy.set_progress_callback(callback)
        self.researcher.set_progress_callback(callback)
        self.analyst.set_progress_callback(callback)
        self.fact_checker.set_progress_callback(callback)
        self.report_generator.set_progress_callback(callback)
    
    async def _notify_progress(
        self,
        agent_name: str,
        status: str,
        progress: int,
        output: Optional[str] = None,
        error: Optional[str] = None
    ):
        """Send progress notification."""
        if self._progress_callback:
            await self._progress_callback(
                agent_name=agent_name,
                status=status,
                progress=progress,
                output=output,
                error=error
            )
    
    async def execute(
        self,
        session_id: str,
        query: str,
        focus_areas: Optional[List[str]] = None,
        source_preferences: Optional[List[str]] = None,
        max_sources: int = 300,
        research_mode: str = "auto",
        report_format: str = "markdown",
        citation_style: str = "APA"
    ) -> Dict[str, Any]:
        """
        Execute the complete research workflow.
        
        Args:
            session_id: Unique session identifier
            query: Research query
            focus_areas: Specific areas to focus on
            source_preferences: Preferred source types
            max_sources: Maximum sources to collect
            research_mode: "auto" or "supervised"
            report_format: "markdown", "html", or "pdf"
            citation_style: "APA", "MLA", or "Chicago"
            
        Returns:
            Complete research results including report
        """
        self.session_id = session_id
        self.started_at = datetime.utcnow()
        self.is_running = True
        self.is_cancelled = False
        self.results = {}
        self.errors = []
        
        logger.info(f"Starting research workflow for session {session_id}: {query}")
        
        context = {
            "query": query,
            "focus_areas": focus_areas or [],
            "source_preferences": source_preferences or [],
            "max_sources": max_sources,
            "research_mode": research_mode,
            "report_format": report_format,
            "citation_style": citation_style
        }
        
        try:
            # Phase 1: Query Processing (User Proxy)
            self.current_phase = WorkflowPhase.QUERY_PROCESSING
            await self._notify_progress(
                "orchestrator", "in_progress", 5,
                "Phase 1: Processing research query..."
            )
            
            user_proxy_result = await self._execute_agent(
                self.user_proxy, context, "user_proxy"
            )
            
            if not user_proxy_result.get("approved"):
                return await self._handle_rejection(user_proxy_result)
            
            # Update context with clarified query
            final_context = user_proxy_result.get("final_context", context)
            self.results["user_proxy"] = user_proxy_result
            
            # Phase 2: Research (Researcher)
            self.current_phase = WorkflowPhase.RESEARCH
            await self._notify_progress(
                "orchestrator", "in_progress", 20,
                "Phase 2: Gathering information..."
            )
            
            researcher_result = await self._execute_agent(
                self.researcher, final_context, "researcher"
            )
            
            if researcher_result.get("status") == "failed":
                return await self._handle_failure("researcher", researcher_result)
            
            self.results["researcher"] = researcher_result
            
            # Add sources and findings to context
            final_context["sources"] = researcher_result.get("sources", [])
            final_context["raw_findings"] = researcher_result.get("raw_findings", [])
            
            # Supervised checkpoint after research
            if research_mode == "supervised":
                await self._checkpoint("research_complete", researcher_result)
            
            # Phase 3: Analysis (Analyst)
            self.current_phase = WorkflowPhase.ANALYSIS
            await self._notify_progress(
                "orchestrator", "in_progress", 45,
                "Phase 3: Analyzing findings..."
            )
            
            analyst_result = await self._execute_agent(
                self.analyst, final_context, "analyst"
            )
            
            if analyst_result.get("status") == "failed":
                return await self._handle_failure("analyst", analyst_result)
            
            self.results["analyst"] = analyst_result
            
            # Add analysis to context
            final_context["organized_findings"] = analyst_result.get("organized_findings", [])
            final_context["patterns"] = analyst_result.get("patterns", [])
            final_context["key_insights"] = analyst_result.get("key_insights", [])
            final_context["contradictions"] = analyst_result.get("contradictions", [])
            
            # Supervised checkpoint after analysis
            if research_mode == "supervised":
                await self._checkpoint("analysis_complete", analyst_result)
            
            # Phase 4: Fact-Checking (Fact-Checker)
            self.current_phase = WorkflowPhase.FACT_CHECKING
            await self._notify_progress(
                "orchestrator", "in_progress", 65,
                "Phase 4: Verifying facts..."
            )
            
            fact_checker_result = await self._execute_agent(
                self.fact_checker, final_context, "fact_checker"
            )
            
            if fact_checker_result.get("status") == "failed":
                # Non-critical failure - continue with unverified
                logger.warning("Fact-checking failed, continuing with unverified data")
                self.errors.append("Fact-checking incomplete")
            else:
                self.results["fact_checker"] = fact_checker_result
                
                # Update with validated findings
                final_context["validated_findings"] = fact_checker_result.get("validated_findings", [])
                final_context["confidence_summary"] = fact_checker_result.get("confidence_summary", {})
            
            # Phase 5: Report Generation (Report Generator)
            self.current_phase = WorkflowPhase.REPORT_GENERATION
            await self._notify_progress(
                "orchestrator", "in_progress", 85,
                "Phase 5: Generating report..."
            )
            
            report_result = await self._execute_agent(
                self.report_generator, final_context, "report_generator"
            )
            
            if report_result.get("status") == "failed":
                return await self._handle_failure("report_generator", report_result)
            
            self.results["report_generator"] = report_result
            
            # Complete
            self.current_phase = WorkflowPhase.COMPLETED
            self.completed_at = datetime.utcnow()
            self.is_running = False
            
            await self._notify_progress(
                "orchestrator", "completed", 100,
                "Research completed successfully!"
            )
            
            return self._build_final_response()
            
        except asyncio.CancelledError:
            logger.info(f"Research cancelled for session {session_id}")
            self.is_cancelled = True
            self.is_running = False
            self.current_phase = WorkflowPhase.FAILED
            return {
                "status": "cancelled",
                "session_id": session_id,
                "message": "Research was cancelled by user"
            }
            
        except Exception as e:
            logger.error(f"Orchestrator error: {e}")
            self.current_phase = WorkflowPhase.FAILED
            self.is_running = False
            return {
                "status": "failed",
                "session_id": session_id,
                "error": str(e),
                "phase": self.current_phase.value
            }
    
    async def _execute_agent(
        self,
        agent,
        context: Dict[str, Any],
        agent_key: str
    ) -> Dict[str, Any]:
        """Execute a single agent with error handling."""
        
        if self.is_cancelled:
            raise asyncio.CancelledError()
        
        try:
            agent.reset()
            result = await asyncio.wait_for(
                agent.execute(context),
                timeout=agent.timeout
            )
            return result
            
        except asyncio.TimeoutError:
            logger.error(f"Agent {agent.name} timed out")
            await self._notify_progress(
                agent_key, "failed", 0,
                error=f"{agent.name} timed out"
            )
            return {
                "status": "failed",
                "error": f"{agent.name} execution timed out"
            }
        except Exception as e:
            logger.error(f"Agent {agent.name} failed: {e}")
            await self._notify_progress(
                agent_key, "failed", 0,
                error=str(e)
            )
            return {
                "status": "failed",
                "error": str(e)
            }
    
    async def _checkpoint(self, checkpoint_name: str, data: Dict[str, Any]):
        """Handle checkpoint in supervised mode."""
        
        logger.info(f"Checkpoint: {checkpoint_name}")
        
        await self._notify_progress(
            "orchestrator", "awaiting_approval", 0,
            f"Checkpoint: {checkpoint_name}. Awaiting approval..."
        )
        
        # In a full implementation, this would wait for user approval
        # For now, we auto-continue after a brief pause
        await asyncio.sleep(0.5)
    
    async def _handle_rejection(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Handle research rejection."""
        
        self.current_phase = WorkflowPhase.FAILED
        self.is_running = False
        
        return {
            "status": "rejected",
            "session_id": self.session_id,
            "message": result.get("message", "Research not approved"),
            "started_at": self.started_at.isoformat() if self.started_at else None
        }
    
    async def _handle_failure(
        self,
        agent_name: str,
        result: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Handle agent failure."""
        
        self.current_phase = WorkflowPhase.FAILED
        self.is_running = False
        
        error_msg = result.get("error", "Unknown error")
        self.errors.append(f"{agent_name}: {error_msg}")
        
        await self._notify_progress(
            "orchestrator", "failed", 0,
            error=f"Research failed at {agent_name}: {error_msg}"
        )
        
        return {
            "status": "failed",
            "session_id": self.session_id,
            "phase": self.current_phase.value,
            "failed_at": agent_name,
            "error": error_msg,
            "partial_results": self.results
        }
    
    def _build_final_response(self) -> Dict[str, Any]:
        """Build the final response with all results."""
        
        report_data = self.results.get("report_generator", {}).get("report", {})
        fact_check_data = self.results.get("fact_checker", {})
        
        return {
            "status": "completed",
            "session_id": self.session_id,
            
            # Core report
            "report": {
                "title": report_data.get("title", ""),
                "summary": report_data.get("summary", ""),
                "markdown_content": report_data.get("markdown_content", ""),
                "html_content": report_data.get("html_content", ""),
                "sections": report_data.get("sections", []),
                "citation_style": report_data.get("citation_style", "APA"),
                "quality_score": report_data.get("quality_score", 0)
            },
            
            # Research data
            "sources": self.results.get("researcher", {}).get("sources", []),
            "sources_count": self.results.get("researcher", {}).get("sources_count", {}),
            
            # Analysis data
            "findings": fact_check_data.get("validated_findings", []),
            "patterns": self.results.get("analyst", {}).get("patterns", []),
            "key_insights": self.results.get("analyst", {}).get("key_insights", []),
            "contradictions": self.results.get("analyst", {}).get("contradictions", []),
            
            # Confidence data
            "confidence_summary": fact_check_data.get("confidence_summary", {}),
            "bias_analysis": fact_check_data.get("bias_analysis", {}),
            
            # Metadata
            "metadata": {
                "started_at": self.started_at.isoformat() if self.started_at else None,
                "completed_at": self.completed_at.isoformat() if self.completed_at else None,
                "duration_seconds": (
                    (self.completed_at - self.started_at).total_seconds()
                    if self.completed_at and self.started_at else None
                ),
                "agents_executed": list(self.results.keys()),
                "errors": self.errors if self.errors else None
            }
        }
    
    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        
        agent_states = {
            "user_proxy": self.user_proxy.get_state(),
            "researcher": self.researcher.get_state(),
            "analyst": self.analyst.get_state(),
            "fact_checker": self.fact_checker.get_state(),
            "report_generator": self.report_generator.get_state()
        }
        
        # Calculate overall progress
        total_progress = sum(a["progress"] for a in agent_states.values())
        overall_progress = total_progress // 5
        
        return {
            "session_id": self.session_id,
            "phase": self.current_phase.value,
            "is_running": self.is_running,
            "is_cancelled": self.is_cancelled,
            "overall_progress": overall_progress,
            "agents": agent_states,
            "started_at": self.started_at.isoformat() if self.started_at else None
        }
    
    async def cancel(self):
        """Cancel the current research execution."""
        
        logger.info(f"Cancelling research session {self.session_id}")
        self.is_cancelled = True
        
        await self._notify_progress(
            "orchestrator", "cancelled", 0,
            "Research cancelled by user"
        )
