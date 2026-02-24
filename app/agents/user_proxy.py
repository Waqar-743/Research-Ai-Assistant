"""
User Proxy Agent
Handles human-in-the-loop oversight and feedback collection.
"""

from typing import Dict, Any, Optional, Callable
from datetime import datetime
from enum import Enum

from app.agents.base_agent import BaseAgent, AgentStatus
from app.config import settings
from app.utils.logging import logger


class ApprovalStatus(str, Enum):
    """Status of human approval."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"


class UserProxyAgent(BaseAgent):
    """
    User Proxy Agent - Human oversight and feedback mediator.
    
    Responsibilities:
    - Clarify ambiguous queries
    - Approve research directions
    - Collect feedback at checkpoints
    - Request changes when needed
    - Mediate between user and AI agents
    
    Supports two modes:
    - AUTO: Research runs without intervention
    - SUPERVISED: Pauses at checkpoints for approval
    """
    
    def __init__(self):
        system_prompt = """You are a User Proxy agent representing human oversight in the research process.

Your responsibilities:
1. Clarify ambiguous or unclear research queries
2. Ensure the research direction aligns with user intent
3. Collect and process user feedback
4. Request modifications when needed
5. Approve or reject research outcomes

Guidelines:
- Always prioritize user intent and satisfaction
- Ask for clarification when queries are vague
- Suggest improvements to research scope
- Ensure ethical and appropriate research conduct
- Mediate between user needs and AI capabilities"""
        
        super().__init__(
            name="User Proxy",
            role="Human oversight and feedback mediator",
            system_prompt=system_prompt,
            model=settings.researcher_model,  # Lightweight model
            temperature=0.3,
            max_tokens=1000,
            timeout=60
        )
        
        self.approval_status = ApprovalStatus.PENDING
        self.feedback: Optional[str] = None
        self.modifications: Dict[str, Any] = {}
        
        # Callback for requesting human input (WebSocket)
        self._human_input_callback: Optional[Callable] = None
        self._approval_received = False
    
    def set_human_input_callback(self, callback: Callable):
        """Set callback for requesting human input via WebSocket."""
        self._human_input_callback = callback
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute user proxy tasks - query clarification and approval.
        
        Args:
            context: Contains 'query', 'research_mode', 'focus_areas'
            
        Returns:
            Dictionary with approved/modified query and research parameters
        """
        query = context.get("query", "")
        research_mode = context.get("research_mode", "auto")
        focus_areas = context.get("focus_areas", [])
        source_preferences = context.get("source_preferences", [])
        
        logger.info(f"User Proxy processing query: {query}")
        
        try:
            await self._set_status(AgentStatus.IN_PROGRESS)
            await self._update_progress(10, "Analyzing research query...")
            
            # Step 1: Analyze query clarity
            query_analysis = await self._analyze_query(query)
            
            await self._update_progress(30, "Generating research plan...")
            
            # Step 2: Generate research plan
            research_plan = await self._generate_research_plan(
                query, focus_areas, source_preferences
            )
            
            await self._update_progress(50, "Preparing for approval...")
            
            # Step 3: Handle based on mode
            if research_mode == "supervised":
                # Request human approval
                approval_result = await self._request_approval(
                    query, query_analysis, research_plan
                )
                
                if approval_result.get("approved"):
                    self.approval_status = ApprovalStatus.APPROVED
                    # Apply any modifications
                    if approval_result.get("modifications"):
                        self.modifications = approval_result["modifications"]
                        self.approval_status = ApprovalStatus.MODIFIED
                else:
                    self.approval_status = ApprovalStatus.REJECTED
                    await self._set_status(AgentStatus.COMPLETED)
                    return {
                        "status": "rejected",
                        "message": approval_result.get("feedback", "Research not approved"),
                        "approved": False
                    }
            else:
                # Auto mode - approve automatically
                self.approval_status = ApprovalStatus.APPROVED
            
            await self._update_progress(80, "Finalizing research parameters...")
            
            # Step 4: Prepare final context
            final_context = self._prepare_final_context(
                query, query_analysis, research_plan, context
            )
            
            await self._update_progress(100, "Research query approved!")
            await self._set_status(AgentStatus.COMPLETED)
            
            return {
                "status": "approved",
                "approved": True,
                "original_query": query,
                "clarified_query": query_analysis.get("clarified_query", query),
                "research_plan": research_plan,
                "final_context": final_context,
                "approval_status": self.approval_status.value,
                "modifications": self.modifications,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"User Proxy execution failed: {e}")
            await self._set_status(AgentStatus.FAILED, str(e))
            return {
                "status": "error",
                "approved": False,
                "error": str(e)
            }
    
    async def _analyze_query(self, query: str) -> Dict[str, Any]:
        """Analyze query for clarity and completeness."""
        
        prompt = f"""Analyze this research query for clarity and completeness.

QUERY: {query}

Evaluate:
1. Is the query clear and specific?
2. What is the main research objective?
3. Are there any ambiguities that need clarification?
4. What implicit assumptions might exist?
5. Suggest a slightly clarified version ONLY if genuinely unclear.

CRITICAL RULES for CLARIFIED_QUERY:
- You MUST keep the EXACT SAME TOPIC as the original query.
- Do NOT invent a new topic, broaden it, or replace it with a generic question.
- If the query is already clear, return it UNCHANGED.
- Only rephrase for search optimization (e.g., fixing typos or adding precision).
- The clarified query must be recognizably about the same subject.

Respond in this format:
CLARITY: [clear/somewhat_clear/unclear]
OBJECTIVE: [main research objective]
AMBIGUITIES: [list any ambiguities]
ASSUMPTIONS: [list implicit assumptions]
CLARIFIED_QUERY: [the original query, only rephrased if genuinely needed]
SUGGESTIONS: [any suggestions for improvement]"""
        
        try:
            response = await self.think(prompt)
            
            # Parse response
            analysis = {
                "original_query": query,
                "clarity": "clear",
                "objective": query,
                "ambiguities": [],
                "assumptions": [],
                "clarified_query": query,
                "suggestions": []
            }
            
            for line in response.split('\n'):
                if line.startswith('CLARITY:'):
                    analysis["clarity"] = line[8:].strip().lower()
                elif line.startswith('OBJECTIVE:'):
                    analysis["objective"] = line[10:].strip()
                elif line.startswith('AMBIGUITIES:'):
                    analysis["ambiguities"] = [a.strip() for a in line[12:].split(',') if a.strip()]
                elif line.startswith('ASSUMPTIONS:'):
                    analysis["assumptions"] = [a.strip() for a in line[12:].split(',') if a.strip()]
                elif line.startswith('CLARIFIED_QUERY:'):
                    analysis["clarified_query"] = line[16:].strip()
                elif line.startswith('SUGGESTIONS:'):
                    analysis["suggestions"] = [s.strip() for s in line[12:].split(',') if s.strip()]
            
            return analysis
            
        except Exception as e:
            logger.warning(f"Query analysis failed: {e}")
            return {
                "original_query": query,
                "clarity": "clear",
                "clarified_query": query,
                "objective": query
            }
    
    async def _generate_research_plan(
        self,
        query: str,
        focus_areas: list,
        source_preferences: list
    ) -> Dict[str, Any]:
        """Generate a research plan for user review."""
        
        plan = {
            "query": query,
            "focus_areas": focus_areas if focus_areas else ["general"],
            "source_preferences": source_preferences if source_preferences else [
                "academic", "news", "official"
            ],
            "research_phases": [
                {
                    "phase": 1,
                    "name": "Information Gathering",
                    "description": "Search multiple sources for relevant information",
                    "agent": "Researcher"
                },
                {
                    "phase": 2,
                    "name": "Analysis & Synthesis",
                    "description": "Analyze and consolidate findings",
                    "agent": "Analyst"
                },
                {
                    "phase": 3,
                    "name": "Fact-Checking",
                    "description": "Verify claims and assess credibility",
                    "agent": "Fact-Checker"
                },
                {
                    "phase": 4,
                    "name": "Report Generation",
                    "description": "Create comprehensive research report",
                    "agent": "Report Generator"
                }
            ],
            "estimated_time": "3-5 minutes",
            "expected_outputs": [
                "Comprehensive research report",
                "Verified findings with confidence scores",
                "Source citations",
                "Executive summary"
            ]
        }
        
        return plan
    
    async def _request_approval(
        self,
        query: str,
        analysis: Dict[str, Any],
        plan: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Request approval from human user (supervised mode)."""
        
        if self._human_input_callback:
            # Send approval request via WebSocket
            approval_request = {
                "type": "approval_request",
                "query": query,
                "analysis": analysis,
                "research_plan": plan,
                "awaiting_response": True
            }
            
            try:
                # This would wait for user response via WebSocket
                response = await self._human_input_callback(approval_request)
                return response
            except Exception as e:
                logger.warning(f"Human approval request failed: {e}")
                # Fall back to auto-approval
                return {"approved": True}
        
        # No callback set - auto approve
        return {"approved": True}
    
    def _prepare_final_context(
        self,
        query: str,
        analysis: Dict[str, Any],
        plan: Dict[str, Any],
        original_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Prepare final context for research execution.

        CRITICAL: The user's original query is always preserved as the
        primary ``query``.  The LLM-generated 'clarified_query' is stored
        separately as ``search_hints`` so the Researcher can optionally
        use it as additional search terms — but it NEVER replaces the
        user's query.
        """
        
        # ALWAYS keep the user's original query as the primary query.
        # The clarified version is kept only as an optional search hint.
        final_query = query
        clarified = analysis.get("clarified_query", query)
        
        # Apply supervised-mode modifications (user explicitly changed query)
        if self.modifications:
            if "query" in self.modifications:
                final_query = self.modifications["query"]
            if "focus_areas" in self.modifications:
                plan["focus_areas"] = self.modifications["focus_areas"]
        
        logger.info(f"UserProxy final_query='{final_query}' | clarified='{clarified}'")
        
        return {
            "query": final_query,
            "original_query": query,
            "search_hints": clarified if clarified != query else "",
            "focus_areas": plan.get("focus_areas", []),
            "source_preferences": plan.get("source_preferences", []),
            "max_sources": original_context.get("max_sources", 300),
            "report_format": original_context.get("report_format", "markdown"),
            "citation_style": original_context.get("citation_style", "APA"),
            "research_mode": original_context.get("research_mode", "auto"),
            "research_plan": plan
        }
    
    async def receive_feedback(
        self,
        feedback: str,
        approved: bool,
        modifications: Optional[Dict[str, Any]] = None
    ):
        """Receive feedback from human user."""
        
        self.feedback = feedback
        self._approval_received = True
        
        if approved:
            self.approval_status = ApprovalStatus.APPROVED
            if modifications:
                self.modifications = modifications
                self.approval_status = ApprovalStatus.MODIFIED
        else:
            self.approval_status = ApprovalStatus.REJECTED
        
        logger.info(f"User Proxy received feedback: {self.approval_status.value}")
