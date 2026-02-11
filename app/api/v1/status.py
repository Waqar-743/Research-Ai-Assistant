"""
Status API Endpoints
Real-time status information for research sessions.
"""

from fastapi import APIRouter, HTTPException
from typing import Optional

from app.models import APIResponse
from app.database.schemas import ResearchSession
from app.database.repositories import ResearchRepository
from app.services.research_service import ResearchService
from app.utils.logging import logger


router = APIRouter()


@router.get("/{session_id}", response_model=APIResponse)
async def get_session_status(session_id: str):
    """
    Get detailed real-time status of a research session.
    """
    try:
        session = await ResearchRepository.get_by_session_id(session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Research session {session_id} not found"
            )
        
        # Build status response
        status_data = {
            "session_id": session.research_id,
            "query": session.query,
            "status": session.status.value,
            "progress": session.progress or 0,
            "current_phase": session.current_phase or session.current_stage,
            "research_mode": session.research_mode.value if session.research_mode else "auto",
            "agent_statuses": session.agent_statuses or {
                "user_proxy": {"status": "idle", "progress": 0},
                "researcher": {"status": "idle", "progress": 0},
                "analyst": {"status": "idle", "progress": 0},
                "fact_checker": {"status": "idle", "progress": 0},
                "report_generator": {"status": "idle", "progress": 0}
            },
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "updated_at": session.updated_at.isoformat() if session.updated_at else None,
            "error_message": session.error_message or session.error
        }
        
        return APIResponse(
            status=200,
            message="Status retrieved successfully",
            data=status_data
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get session status: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get session status: {str(e)}"
        )


@router.get("/{session_id}/agents", response_model=APIResponse)
async def get_agent_statuses(session_id: str):
    """
    Get the status of all agents for a research session.
    """
    try:
        session = await ResearchRepository.get_by_session_id(session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Research session {session_id} not found"
            )
        
        agent_statuses = session.agent_statuses or {}
        
        # Build detailed agent status
        agents = []
        agent_order = ["user_proxy", "researcher", "analyst", "fact_checker", "report_generator"]
        agent_names = {
            "user_proxy": "User Proxy",
            "researcher": "Researcher",
            "analyst": "Analyst",
            "fact_checker": "Fact-Checker",
            "report_generator": "Report Generator"
        }
        
        for agent_key in agent_order:
            status = agent_statuses.get(agent_key, {})
            agents.append({
                "key": agent_key,
                "name": agent_names.get(agent_key, agent_key),
                "status": status.get("status", "idle"),
                "progress": status.get("progress", 0),
                "output": status.get("output"),
                "error": status.get("error"),
                "start_time": status.get("start_time"),
                "end_time": status.get("end_time")
            })
        
        return APIResponse(
            status=200,
            message="Agent statuses retrieved successfully",
            data={
                "session_id": session_id,
                "agents": agents,
                "current_phase": session.current_phase or session.current_stage
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get agent statuses: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get agent statuses: {str(e)}"
        )


@router.get("/{session_id}/progress", response_model=APIResponse)
async def get_progress(session_id: str):
    """
    Get a simplified progress view for UI display.
    """
    try:
        session = await ResearchRepository.get_by_session_id(session_id)
        
        if not session:
            raise HTTPException(
                status_code=404,
                detail=f"Research session {session_id} not found"
            )
        
        # Calculate phase progress
        phases = [
            {"name": "Query Processing", "agent": "user_proxy", "weight": 10},
            {"name": "Research", "agent": "researcher", "weight": 30},
            {"name": "Analysis", "agent": "analyst", "weight": 25},
            {"name": "Fact-Checking", "agent": "fact_checker", "weight": 20},
            {"name": "Report Generation", "agent": "report_generator", "weight": 15}
        ]
        
        agent_statuses = session.agent_statuses or {}
        overall_progress = 0
        phase_details = []
        
        for phase in phases:
            agent_status = agent_statuses.get(phase["agent"], {})
            phase_progress = agent_status.get("progress", 0)
            phase_status = agent_status.get("status", "pending")
            
            # Contribute to overall progress
            if phase_status == "completed":
                overall_progress += phase["weight"]
            elif phase_status == "in_progress":
                overall_progress += int(phase["weight"] * (phase_progress / 100))
            
            phase_details.append({
                "name": phase["name"],
                "status": phase_status,
                "progress": phase_progress
            })
        
        return APIResponse(
            status=200,
            message="Progress retrieved successfully",
            data={
                "session_id": session_id,
                "status": session.status.value,
                "overall_progress": min(overall_progress, 100),
                "phases": phase_details,
                "estimated_time_remaining": _estimate_time(session.status.value, overall_progress)
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get progress: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get progress: {str(e)}"
        )


def _estimate_time(status: str, progress: int) -> Optional[str]:
    """Estimate remaining time based on progress."""
    if status == "completed":
        return None
    if status == "failed":
        return None
    if progress >= 95:
        return "Less than 30 seconds"
    if progress >= 80:
        return "About 1 minute"
    if progress >= 50:
        return "About 2 minutes"
    if progress >= 20:
        return "About 3 minutes"
    return "About 5 minutes"

