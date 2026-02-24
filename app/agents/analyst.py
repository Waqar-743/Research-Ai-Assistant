"""
Analyst Agent
Responsible for synthesizing and analyzing collected information.

Phase 1: reads sources / raw findings from MongoDB by session_id
instead of receiving them in the context dict.
"""

from typing import Dict, Any, List
from datetime import datetime
import json
import re

from app.agents.base_agent import BaseAgent, AgentStatus
from app.config import settings
from app.utils.logging import logger
from app.database.repositories import SourceRepository, FindingRepository


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
        system_prompt = """You are an expert research analyst who synthesizes information from multiple sources into actionable findings.

Your responsibilities:
1. Consolidate findings from various sources into coherent, well-supported themes
2. Identify patterns, trends, and common threads with SPECIFIC EVIDENCE
3. Detect and flag contradictions or conflicting information
4. Extract the most important insights with concrete data
5. Organize information in a logical, hierarchical structure

Guidelines:
- ALWAYS produce substantive analysis — never say "no findings identified"
- Every finding must be supported by specific data, quotes, or statistics from sources
- Be objective and balanced in your analysis
- Weigh evidence based on source credibility and recency
- Clearly distinguish between established facts, emerging trends, and speculative claims
- Quantify findings wherever possible (percentages, numbers, timeframes)
- Highlight areas of strong consensus vs areas of debate
- Note gaps in available information as a finding itself
- Prioritize findings by importance and reliability

Your analysis MUST be substantive and data-driven. Abstract statements without evidence are unacceptable."""
        
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
        
        Phase 1: Loads sources and raw findings from MongoDB by session_id
        instead of receiving them in the context dict.
        """
        query = context.get("query", "")
        session_id = context.get("session_id", "")
        
        logger.info(f"Analyst starting analysis for: {query} (session={session_id})")
        
        try:
            await self._set_status(AgentStatus.IN_PROGRESS)
            await self._update_progress(5, "Loading data from database...")

            # ── Phase 1: query MongoDB ────────────────────────────────
            sources: List[Dict[str, Any]] = []
            raw_findings: List[Dict[str, Any]] = []

            if session_id:
                source_docs = await SourceRepository.get_by_research(session_id)
                sources = [self._source_doc_to_dict(s) for s in source_docs]

                finding_docs = await FindingRepository.get_by_research(session_id)
                raw_findings = [self._finding_doc_to_dict(f) for f in finding_docs]
            else:
                # Fallback for backward compat / tests
                sources = context.get("sources", [])
                raw_findings = context.get("raw_findings", [])

            logger.info(
                f"Analyst loaded {len(sources)} sources and "
                f"{len(raw_findings)} findings from DB"
            )
            # ──────────────────────────────────────────────────────────
            
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
        
        # Build source URL map so we can resolve "S1" etc. to {title, url} later
        source_url_map: Dict[str, Dict[str, str]] = {
            f"S{i+1}": {
                "title": s.get("title", ""),
                "url": s.get("url", ""),
                "api_source": s.get("api_source", "")
            }
            for i, s in enumerate(sources[:60])
        }

        # Build context from sources — up to 60, 500-char snippets with URL
        source_context = []
        for i, source in enumerate(sources[:60]):
            title = source.get("title", "Untitled")
            snippet = source.get("snippet", "")[:500]
            url = source.get("url", "")
            source_type = source.get("source_type", "unknown")
            author = source.get("author", "") or ", ".join(source.get("authors", [])[:2])
            source_context.append(f"[S{i+1}] ({source_type}) {title} by {author} | {url}\n  {snippet}")
        
        findings_context = []
        for i, finding in enumerate(raw_findings):
            content = finding.get("content", "")
            cred = finding.get("preliminary_credibility", "unknown")
            findings_context.append(f"[F{i+1}] ({cred} credibility) {content}")
        
        prompt = f"""Consolidate these sources and extracted findings into a comprehensive analysis for the research query.

QUERY: {query}

SOURCES ({len(source_context)} total):
{chr(10).join(source_context)}

EXTRACTED FINDINGS ({len(findings_context)} total):
{chr(10).join(findings_context) if findings_context else 'No pre-extracted findings available — analyze directly from sources.'}

INSTRUCTIONS:
- Group related information into 4-8 consolidated findings
- EVERY finding must include specific data points, statistics, or concrete evidence from the sources
- If sources contain relevant data, extract and synthesize it — do NOT say "no findings"
- If sources are tangential, still identify what they reveal about the broader topic
- Include both areas of consensus and areas of debate/contradiction
- Rate confidence based on number and quality of supporting sources

Respond in JSON format:
{{
    "consolidated_findings": [
        {{
            "title": "Clear descriptive title of the finding",
            "content": "Comprehensive summary with SPECIFIC data points, statistics, and evidence from sources. Must be 2-4 sentences minimum.",
            "finding_type": "fact|insight|statistic|trend|debate",
            "source_refs": ["S1", "S2"],
            "confidence": "high|medium|low",
            "key_data_points": ["specific stat or data point 1", "specific stat or data point 2"]
        }}
    ]
}}"""
        
        try:
            response = await self.think(prompt)
            
            # Parse JSON response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                findings = data.get("consolidated_findings", [])
                if findings:
                    # Resolve "S1"-style source refs to structured {title, url} dicts
                    for finding in findings:
                        raw_refs = finding.get("source_refs", [])
                        resolved = []
                        if isinstance(raw_refs, list):
                            for ref in raw_refs:
                                if isinstance(ref, str) and ref in source_url_map:
                                    resolved.append(source_url_map[ref])
                                elif isinstance(ref, dict):
                                    resolved.append(ref)
                                else:
                                    resolved.append({"title": str(ref), "url": ""})
                        finding["resolved_sources"] = resolved
                    return findings
        except Exception as e:
            logger.warning(f"Consolidation parsing failed: {e}")
        
        # Fallback: if raw findings exist, restructure them and carry resolved_sources
        if raw_findings:
            return [{
                "title": f.get("content", "Finding")[:80],
                "content": f.get("content", ""),
                "finding_type": f.get("type", "insight"),
                "source_refs": [f.get("source_refs", "")],
                "resolved_sources": f.get("resolved_sources", []),
                "confidence": f.get("preliminary_credibility", "medium")
            } for f in raw_findings if f.get("content")]
        
        # Last resort fallback: generate findings directly from sources
        if sources:
            return await self._emergency_findings_from_sources(query, sources)
        
        return []
    
    async def _emergency_findings_from_sources(
        self,
        query: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Emergency fallback: generate findings directly from source data when other methods fail."""
        
        source_text = "\n".join([
            f"- {s.get('title', 'Untitled')}: {(s.get('snippet', '') or '')[:200]}"
            for s in sources[:30]
        ])
        
        prompt = f"""Based on these sources, what can we learn about: {query}

{source_text}

Extract 3-5 concrete findings. Each must contain specific information from the sources.
Respond in JSON:
{{
    "consolidated_findings": [
        {{
            "title": "Finding title",
            "content": "Detailed finding with specific data",
            "finding_type": "insight",
            "source_refs": [],
            "confidence": "medium"
        }}
    ]
}}"""
        
        try:
            response = await self.think(prompt)
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("consolidated_findings", [])
        except Exception as e:
            logger.warning(f"Emergency findings extraction failed: {e}")
        
        return []
    
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
1. Name the pattern clearly and specifically (not generic)
2. Explain HOW it manifests with specific examples and data from findings
3. Assess how strong/consistent the evidence is
4. List which findings support this pattern

IMPORTANT: Every pattern must be grounded in specific evidence from the findings above. Do not invent patterns not supported by the data.

Respond in JSON:
{{
    "patterns": [
        {{
            "name": "Specific pattern name",
            "description": "How this pattern appears, with specific evidence and data points",
            "strength": "strong|moderate|weak",
            "supporting_findings": [0, 1, 2],
            "examples": ["specific example with data 1", "specific example with data 2"]
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
1. Be a clear, specific, actionable statement (NOT generic or vague)
2. Include specific data, statistics, or evidence that supports it
3. Be supported by multiple findings 
4. Provide genuine value to someone researching this topic
5. NEVER use placeholder text like [topic] or [finding]

Write each insight as a complete, self-contained statement with evidence.
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
                "resolved_sources": finding.get("resolved_sources", []),
                "related_patterns": [],
                "agent_generated_by": "analyst"
            }
            
            # Link to relevant patterns
            for j, pattern in enumerate(patterns):
                if i in pattern.get("supporting_findings", []):
                    organized_finding["related_patterns"].append(pattern.get("name", f"Pattern {j+1}"))
            
            organized.append(organized_finding)
        
        return organized

    # ── Phase 1 helpers: MongoDB doc → plain dict ─────────────────
    @staticmethod
    def _source_doc_to_dict(doc) -> Dict[str, Any]:
        """Convert a Source Beanie document to the dict format agents expect."""
        return {
            "title": doc.title,
            "url": doc.url,
            "snippet": doc.content_preview or "",
            "source_type": doc.source_type.value if hasattr(doc.source_type, "value") else str(doc.source_type or "other"),
            "api_source": doc.api_source or "unknown",
            "author": doc.author or "",
            "published_at": str(doc.published_at) if doc.published_at else "",
            "credibility_score": doc.credibility_score,
            **(doc.metadata or {}),
        }

    @staticmethod
    def _finding_doc_to_dict(doc) -> Dict[str, Any]:
        """Convert a Finding Beanie document to the dict format agents expect."""
        meta = doc.metadata or {}
        return {
            "content": doc.content,
            "title": doc.title,
            "type": doc.finding_type.value if hasattr(doc.finding_type, "value") else str(doc.finding_type or "insight"),
            "source_refs": meta.get("source_refs", ""),
            "resolved_sources": meta.get("resolved_sources", []),
            "preliminary_credibility": meta.get("preliminary_credibility", "medium"),
            "confidence_score": doc.confidence_score,
            "verified": doc.verified,
        }
