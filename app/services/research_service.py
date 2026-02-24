"""
Research Service
Main service coordinating the research workflow.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
import asyncio

from app.agents.orchestrator import AgentOrchestrator
from app.database.schemas import (
    ResearchSession, ResearchStatus, Source, Finding, Report,
    SourceType, FindingType
)
from app.database.repositories import (
    ResearchRepository, SourceRepository, FindingRepository, ReportRepository
)
from app.api.websocket import (
    send_agent_update, send_phase_update,
    send_research_complete, send_research_error,
    manager as ws_manager
)
from app.utils.logging import logger, log_research_progress


# Global service instance
_research_service: Optional["ResearchService"] = None


def get_research_service() -> "ResearchService":
    """Get the global research service instance."""
    global _research_service
    if _research_service is None:
        _research_service = ResearchService()
    return _research_service


class ResearchService:
    """
    Research Service - Coordinates the entire research workflow.
    
    Responsibilities:
    - Manage research session lifecycle
    - Coordinate with AgentOrchestrator
    - Persist results to database
    - Send real-time updates via WebSocket
    - Handle user feedback for supervised mode
    """
    
    def __init__(self):
        self.active_orchestrators: Dict[str, AgentOrchestrator] = {}
        self.feedback_queues: Dict[str, asyncio.Queue] = {}
    
    async def execute_research(
        self,
        session_id: str,
        query: str,
        focus_areas: Optional[List[str]] = None,
        source_preferences: Optional[List[str]] = None,
        max_sources: int = 300,
        research_mode: str = "auto",
        report_format: str = "markdown",
        citation_style: str = "APA"
    ):
        """
        Execute the complete research workflow.
        
        This is called as a background task from the API endpoint.
        """
        logger.info(f"Starting research execution for session {session_id}")
        
        # Update session status
        session = await ResearchRepository.get_by_session_id(session_id)
        if session:
            session.status = ResearchStatus.RUNNING
            session.updated_at = datetime.utcnow()
            await session.save()
        
        # Create orchestrator
        orchestrator = AgentOrchestrator()
        self.active_orchestrators[session_id] = orchestrator
        
        # Set up progress callback for WebSocket updates
        # Track each agent's progress locally so we can compute a
        # monotonically-increasing overall_progress in every WS message.
        _local_agent_statuses: Dict[str, Any] = {}
        _agent_weights = {
            "user_proxy": 10,
            "researcher": 30,
            "analyst": 25,
            "fact_checker": 20,
            "report_generator": 15
        }

        async def progress_callback(
            agent_name: str,
            status: str,
            progress: int,
            output: Optional[str] = None,
            error: Optional[str] = None
        ):
            # Keep a local snapshot of every named agent
            if agent_name in _agent_weights:
                _local_agent_statuses[agent_name] = {
                    "status": status,
                    "progress": progress
                }

            # Compute weighted overall progress (same formula as DB layer)
            overall = 0
            for _name, _weight in _agent_weights.items():
                _state = _local_agent_statuses.get(_name, {})
                if _state.get("status") == "completed":
                    overall += _weight
                elif _state.get("status") == "in_progress":
                    overall += int(_weight * (_state.get("progress", 0) / 100))
            overall_progress = min(overall, 100)

            # Send WebSocket update — include overall_progress in data so the
            # frontend never needs to guess which progress value is "pipeline-wide"
            await send_agent_update(
                session_id=session_id,
                agent_name=agent_name,
                status=status,
                progress=progress,
                output=output,
                error=error,
                data={"overall_progress": overall_progress}
            )
            
            # Update database
            await self._update_session_progress(
                session_id, agent_name, status, progress, output, error
            )
            
            # Log progress
            log_research_progress(session_id, agent_name, progress, output)
        
        orchestrator.set_progress_callback(progress_callback)
        
        try:
            # Send phase update
            await send_phase_update(session_id, "initialization", "started")
            
            # Execute research
            results = await orchestrator.execute(
                session_id=session_id,
                query=query,
                focus_areas=focus_areas,
                source_preferences=source_preferences,
                max_sources=max_sources,
                research_mode=research_mode,
                report_format=report_format,
                citation_style=citation_style
            )
            
            if results.get("status") == "completed":
                # Save results to database
                await self._save_research_results(session_id, results)
                
                # Update session as completed
                session = await ResearchRepository.get_by_session_id(session_id)
                if session:
                    session.status = ResearchStatus.COMPLETED
                    session.progress = 100
                    session.completed_at = datetime.utcnow()
                    session.final_report = results.get("report", {})
                    session.sources_count = results.get("sources_count", {})
                    session.findings_count = len(results.get("findings", []))
                    session.confidence_summary = results.get("confidence_summary", {})
                    await session.save()
                
                # Send completion notification
                await send_research_complete(session_id, results)
                
                logger.info(f"Research completed successfully for session {session_id}")
                
            elif results.get("status") == "failed":
                # Update session as failed
                session = await ResearchRepository.get_by_session_id(session_id)
                if session:
                    session.status = ResearchStatus.FAILED
                    session.error_message = results.get("error", "Unknown error")
                    await session.save()
                
                # Send error notification
                await send_research_error(
                    session_id,
                    results.get("error", "Research failed"),
                    results.get("phase")
                )
                
                logger.error(f"Research failed for session {session_id}: {results.get('error')}")
            
            elif results.get("status") == "cancelled":
                session = await ResearchRepository.get_by_session_id(session_id)
                if session:
                    session.status = ResearchStatus.CANCELLED
                    await session.save()
                
                logger.info(f"Research cancelled for session {session_id}")
            
        except Exception as e:
            logger.error(f"Research execution error: {e}")
            
            # Update session as failed
            session = await ResearchRepository.get_by_session_id(session_id)
            if session:
                session.status = ResearchStatus.FAILED
                session.error_message = str(e)
                await session.save()
            
            await send_research_error(session_id, str(e))
            
        finally:
            # Clean up
            if session_id in self.active_orchestrators:
                del self.active_orchestrators[session_id]
    
    async def _update_session_progress(
        self,
        session_id: str,
        agent_name: str,
        status: str,
        progress: int,
        output: Optional[str],
        error: Optional[str]
    ):
        """Update session progress in database."""
        try:
            session = await ResearchRepository.get_by_session_id(session_id)
            if session:
                # Update agent status
                if session.agent_statuses is None:
                    session.agent_statuses = {}

                session.agent_statuses[agent_name] = {
                    "status": status,
                    "progress": progress,
                    "output": output[:500] if output else None,
                    "error": error,
                    "updated_at": datetime.utcnow().isoformat()
                }
                
                # Update current phase
                session.current_phase = agent_name
                
                # Calculate overall progress
                agent_weights = {
                    "user_proxy": 10,
                    "researcher": 30,
                    "analyst": 25,
                    "fact_checker": 20,
                    "report_generator": 15
                }
                
                overall = 0
                for agent, weight in agent_weights.items():
                    agent_status = session.agent_statuses.get(agent, {})
                    if agent_status.get("status") == "completed":
                        overall += weight
                    elif agent_status.get("status") == "in_progress":
                        overall += int(weight * (agent_status.get("progress", 0) / 100))
                
                session.progress = min(overall, 100)
                session.updated_at = datetime.utcnow()
                
                await session.save()
                
        except Exception as e:
            logger.warning(f"Failed to update session progress: {e}")
    
    async def _save_research_results(
        self,
        session_id: str,
        results: Dict[str, Any]
    ):
        """Save research results to database."""
        try:
            # Save sources
            sources = results.get("sources", [])
            for source_data in sources[:200]:  # Limit to 200 sources
                source = Source(
                    research_id=session_id,
                    title=source_data.get("title", ""),
                    url=source_data.get("url", ""),
                    content_preview=source_data.get("snippet", "") or source_data.get("description", ""),
                    full_content=source_data.get("content", "") or None,
                    api_source=source_data.get("api_source", "unknown"),
                    source_type=self._map_source_type(source_data.get("source_type")),
                    credibility_score=source_data.get("credibility_score", 0.5),
                    author=source_data.get("author"),
                    published_at=source_data.get("published_at"),
                    metadata=source_data
                )
                await source.insert()
            
            logger.info(f"Saved {min(len(sources), 200)} sources for session {session_id}")
            
            # Save findings
            findings = results.get("findings", [])
            for finding_data in findings:
                content = finding_data.get("content") or finding_data.get("statement") or ""
                title = finding_data.get("title") or (content[:80] + "..." if len(content) > 80 else content)
                finding = Finding(
                    research_id=session_id,
                    title=title,
                    content=content,
                    finding_type=self._map_finding_type(finding_data.get("finding_type")),
                    confidence_score=finding_data.get("confidence_score", 0.5),
                    verified=finding_data.get("verified", False),
                    supporting_sources=finding_data.get("supporting_sources", []) or finding_data.get("source_refs", []),
                    contradicting_sources=finding_data.get("contradicting_sources", []),
                    agent_generated_by=finding_data.get("agent_generated_by", "fact_checker")
                )
                await finding.insert()
            
            logger.info(f"Saved {len(findings)} findings for session {session_id}")
            
            # Save report
            report_data = results.get("report", {})
            if report_data:
                report = Report(
                    research_id=session_id,
                    title=report_data.get("title", ""),
                    summary=report_data.get("summary", ""),
                    markdown_content=report_data.get("markdown_content", ""),
                    html_content=report_data.get("html_content", ""),
                    sections=report_data.get("sections", []),
                    citation_style=report_data.get("citation_style", "APA"),
                    quality_score=report_data.get("quality_score", 0),
                    generated_at=datetime.utcnow()
                )
                await report.insert()
                
                logger.info(f"Saved report for session {session_id}")
                
        except Exception as e:
            logger.error(f"Failed to save research results: {e}")
    
    def _map_source_type(self, source_type: Optional[str]) -> Optional[SourceType]:
        """Map source type string to enum."""
        if not source_type:
            return None
        
        mapping = {
            "academic": SourceType.ACADEMIC,
            "news": SourceType.NEWS,
            "official": SourceType.OFFICIAL,
            "wikipedia": SourceType.WIKIPEDIA,
            "wiki": SourceType.WIKIPEDIA,
            "blog": SourceType.BLOG,
            "social": SourceType.OTHER,
            "other": SourceType.OTHER
        }
        return mapping.get(source_type.lower(), SourceType.OTHER)
    
    def _map_finding_type(self, finding_type: Optional[str]) -> Optional[FindingType]:
        """Map finding type string to enum."""
        if not finding_type:
            return FindingType.INSIGHT
        
        mapping = {
            "fact": FindingType.FACT,
            "statistic": FindingType.STATISTIC,
            "definition": FindingType.DEFINITION,
            "insight": FindingType.INSIGHT,
            "claim": FindingType.CLAIM
        }
        return mapping.get(finding_type.lower(), FindingType.INSIGHT)
    
    async def cancel_research(self, session_id: str):
        """Cancel an in-progress research session."""
        if session_id in self.active_orchestrators:
            orchestrator = self.active_orchestrators[session_id]
            await orchestrator.cancel()
            logger.info(f"Cancelled research for session {session_id}")
    
    async def process_feedback(
        self,
        session_id: str,
        approved: bool,
        feedback: str,
        modifications: Optional[Dict[str, Any]] = None
    ):
        """Process user feedback for supervised mode."""
        logger.info(f"Processing feedback for session {session_id}: approved={approved}")
        
        if session_id in self.active_orchestrators:
            orchestrator = self.active_orchestrators[session_id]
            
            # Pass feedback to user proxy agent
            if hasattr(orchestrator, 'user_proxy'):
                await orchestrator.user_proxy.receive_feedback(
                    feedback=feedback,
                    approved=approved,
                    modifications=modifications
                )
    
    def get_active_sessions(self) -> List[str]:
        """Get list of active session IDs."""
        return list(self.active_orchestrators.keys())
    
    def is_session_active(self, session_id: str) -> bool:
        """Check if a session is currently active."""
        return session_id in self.active_orchestrators
