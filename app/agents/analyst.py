"""
Analyst Agent
Responsible for synthesizing and analyzing collected information.
"""

from typing import Dict, Any, List
from datetime import datetime
import json
import re

from app.agents.base_agent import BaseAgent, AgentStatus
from app.config import settings
from app.utils.logging import logger


class AnalystAgent(BaseAgent):
    """
    Analyst Agent - Information synthesis and analysis specialist.
    
    Responsibilities:
    - Consolidate findings from multiple sources
    - Identify patterns and common themes
    - Detect contradictions across sources
    - Extract key insights
    - Organize findings hierarchically
    """
    
    def __init__(self):
        system_prompt = """You are an expert analyst who synthesizes information from multiple sources.

Your responsibilities:
1. Consolidate findings from various sources into coherent themes
2. Identify patterns, trends, and common threads
3. Detect and flag contradictions or conflicting information
4. Extract the most important insights
5. Organize information in a logical, hierarchical structure

Guidelines:
- Be objective and balanced in your analysis
- Weigh evidence based on source credibility
- Clearly distinguish between facts and interpretations
- Note areas of consensus and disagreement
- Highlight gaps in the available information
- Prioritize findings by importance and reliability

Your analysis should be thorough yet accessible."""
        
        super().__init__(
            name="Analyst",
            role="Information synthesis and analysis specialist",
            system_prompt=system_prompt,
            model=settings.analyst_model,
            temperature=0.5,
            max_tokens=4096,
            timeout=settings.agent_timeout
        )
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute analysis on collected sources and findings.
        
        Args:
            context: Contains 'query', 'sources', 'raw_findings'
            
        Returns:
            Dictionary with consolidated findings, patterns, and insights
        """
        query = context.get("query", "")
        sources = context.get("sources", [])
        raw_findings = context.get("raw_findings", [])
        
        logger.info(f"Analyst starting analysis for: {query}")
        
        try:
            await self._set_status(AgentStatus.IN_PROGRESS)
            await self._update_progress(5, "Beginning analysis of collected data...")
            
            # Step 1: Consolidate findings
            await self._update_progress(15, "Consolidating findings from sources...")
            consolidated = await self._consolidate_findings(query, sources, raw_findings)
            
            # Step 2: Identify patterns
            await self._update_progress(35, "Identifying patterns and themes...")
            patterns = await self._identify_patterns(query, consolidated)
            
            # Step 3: Detect contradictions
            await self._update_progress(55, "Detecting contradictions...")
            contradictions = await self._detect_contradictions(consolidated)
            
            # Step 4: Extract key insights
            await self._update_progress(75, "Extracting key insights...")
            insights = await self._extract_insights(query, consolidated, patterns)
            
            # Step 5: Organize hierarchically
            await self._update_progress(90, "Organizing findings...")
            organized_findings = await self._organize_findings(
                query, consolidated, patterns, insights
            )
            
            await self._update_progress(100, f"Analysis complete: {len(organized_findings)} findings organized")
            await self._set_status(AgentStatus.COMPLETED)
            
            return {
                "status": "completed",
                "query": query,
                "consolidated_findings": consolidated,
                "patterns": patterns,
                "contradictions": contradictions,
                "key_insights": insights,
                "organized_findings": organized_findings,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Analyst execution failed: {e}")
            await self._set_status(AgentStatus.FAILED, str(e))
            return {
                "status": "failed",
                "error": str(e),
                "consolidated_findings": [],
                "patterns": [],
                "contradictions": [],
                "key_insights": [],
                "organized_findings": []
            }
    
    async def _consolidate_findings(
        self,
        query: str,
        sources: List[Dict[str, Any]],
        raw_findings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Consolidate findings from multiple sources into unified themes."""
        
        # Build context from sources and findings
        source_context = []
        for i, source in enumerate(sources[:25]):
            title = source.get("title", "Untitled")
            snippet = source.get("snippet", "")[:250]
            source_type = source.get("source_type", "unknown")
            source_context.append(f"[S{i+1}] ({source_type}) {title}: {snippet}")
        
        findings_context = []
        for i, finding in enumerate(raw_findings):
            content = finding.get("content", "")
            findings_context.append(f"[F{i+1}] {content}")
        
        prompt = f"""Consolidate these findings and sources into unified themes for the research query.

QUERY: {query}

SOURCES:
{chr(10).join(source_context)}

RAW FINDINGS:
{chr(10).join(findings_context)}

Group related information into 5-8 consolidated findings. For each:
1. Create a clear, descriptive title
2. Write a comprehensive summary combining related information
3. List supporting source references
4. Assess the finding type (fact, insight, statistic, claim)

Respond in JSON format:
{{
    "consolidated_findings": [
        {{
            "title": "Finding title",
            "content": "Comprehensive summary",
            "finding_type": "fact|insight|statistic|claim",
            "source_refs": ["S1", "S2"],
            "confidence": "high|medium|low"
        }}
    ]
}}"""
        
        try:
            response = await self.think(prompt)
            
            # Parse JSON response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("consolidated_findings", [])
        except Exception as e:
            logger.warning(f"Consolidation parsing failed: {e}")
        
        # Fallback: return raw findings as-is
        return raw_findings
    
    async def _identify_patterns(
        self,
        query: str,
        findings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Identify patterns and common themes across findings."""
        
        findings_text = "\n".join([
            f"- {f.get('title', 'Finding')}: {f.get('content', '')[:200]}"
            for f in findings
        ])
        
        prompt = f"""Identify patterns and common themes across these research findings.

QUERY: {query}

FINDINGS:
{findings_text}

Identify 3-5 key patterns or themes. For each pattern:
1. Name the pattern clearly
2. Explain how it manifests across findings
3. Assess how strong/consistent the pattern is
4. List which findings support this pattern

Respond in JSON:
{{
    "patterns": [
        {{
            "name": "Pattern name",
            "description": "How this pattern appears",
            "strength": "strong|moderate|weak",
            "supporting_findings": [0, 1, 2],
            "examples": ["specific example 1", "example 2"]
        }}
    ]
}}"""
        
        try:
            response = await self.think(prompt)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("patterns", [])
        except Exception as e:
            logger.warning(f"Pattern identification failed: {e}")
        
        return []
    
    async def _detect_contradictions(
        self,
        findings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Detect contradictions or conflicting information."""
        
        if len(findings) < 2:
            return []
        
        findings_text = "\n".join([
            f"[{i}] {f.get('title', 'Finding')}: {f.get('content', '')[:200]}"
            for i, f in enumerate(findings)
        ])
        
        prompt = f"""Analyze these findings for contradictions or conflicting claims.

FINDINGS:
{findings_text}

Identify any contradictions where different findings make conflicting claims.
For each contradiction found:
1. Describe what the conflict is about
2. Identify which findings are in conflict
3. Explain the nature of the disagreement
4. Suggest which might be more reliable (if determinable)

Respond in JSON:
{{
    "contradictions": [
        {{
            "topic": "What the contradiction is about",
            "finding_indices": [0, 2],
            "claim_1": "First position",
            "claim_2": "Contradicting position",
            "analysis": "Why they conflict and which seems more reliable"
        }}
    ]
}}

If no significant contradictions exist, return empty array."""
        
        try:
            response = await self.think(prompt)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("contradictions", [])
        except Exception as e:
            logger.warning(f"Contradiction detection failed: {e}")
        
        return []
    
    async def _extract_insights(
        self,
        query: str,
        findings: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]]
    ) -> List[str]:
        """Extract the most important insights."""
        
        context = f"""Query: {query}

Key Findings:
{chr(10).join([f"- {f.get('title', '')}: {f.get('content', '')[:150]}" for f in findings[:10]])}

Patterns Identified:
{chr(10).join([f"- {p.get('name', '')}: {p.get('description', '')[:100]}" for p in patterns])}"""
        
        prompt = f"""Based on this analysis, extract the 5-7 most important insights.

{context}

Each insight should:
1. Be a clear, actionable statement
2. Represent a key takeaway from the research
3. Be supported by multiple findings
4. Provide value to someone researching this topic

List the insights in order of importance, one per line."""
        
        try:
            response = await self.think(prompt)
            insights = [
                line.strip().lstrip('0123456789.-) ')
                for line in response.strip().split('\n')
                if line.strip() and len(line.strip()) > 10
            ]
            return insights[:7]
        except Exception as e:
            logger.warning(f"Insight extraction failed: {e}")
        
        return []
    
    async def _organize_findings(
        self,
        query: str,
        findings: List[Dict[str, Any]],
        patterns: List[Dict[str, Any]],
        insights: List[str]
    ) -> List[Dict[str, Any]]:
        """Organize all findings into a hierarchical structure."""
        
        organized = []
        
        # Add main findings with their supporting data
        for i, finding in enumerate(findings):
            organized_finding = {
                "id": f"finding_{i+1}",
                "title": finding.get("title", f"Finding {i+1}"),
                "content": finding.get("content", ""),
                "finding_type": finding.get("finding_type", "insight"),
                "confidence": finding.get("confidence", "medium"),
                "source_refs": finding.get("source_refs", []),
                "related_patterns": [],
                "agent_generated_by": "analyst"
            }
            
            # Link to relevant patterns
            for j, pattern in enumerate(patterns):
                if i in pattern.get("supporting_findings", []):
                    organized_finding["related_patterns"].append(pattern.get("name", f"Pattern {j+1}"))
            
            organized.append(organized_finding)
        
        return organized
