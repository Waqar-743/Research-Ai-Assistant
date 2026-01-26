"""
Researcher Agent
Responsible for searching and gathering information from multiple sources.
"""

from typing import Dict, Any, List
from datetime import datetime

from app.agents.base_agent import BaseAgent, AgentStatus
from app.tools.search_tools import SearchTools
from app.config import settings
from app.utils.logging import logger


class ResearcherAgent(BaseAgent):
    """
    Researcher Agent - Search and information gathering specialist.
    
    Responsibilities:
    - Search multiple sources (Google, NewsAPI, ArXiv, PubMed, Wikipedia)
    - Collect raw information
    - Track sources and metadata
    - Parallel search execution
    """
    
    def __init__(self):
        system_prompt = """You are a research expert who searches multiple sources to gather comprehensive information.

Your responsibilities:
1. Analyze the research query to identify key search terms
2. Search across multiple sources (web, news, academic, encyclopedic)
3. Collect and organize raw information from all sources
4. Track source metadata for attribution
5. Identify the most relevant and authoritative sources

Guidelines:
- Cast a wide net to ensure comprehensive coverage
- Prioritize authoritative and credible sources
- Note publication dates for recency
- Preserve original source attribution
- Flag potentially unreliable sources

Output structured findings with clear source attribution."""
        
        super().__init__(
            name="Researcher",
            role="Search and information gathering specialist",
            system_prompt=system_prompt,
            model=settings.researcher_model,
            temperature=0.3,
            max_tokens=4096,
            timeout=settings.agent_timeout
        )
        
        self.search_tools = SearchTools()
        self.sources_found: Dict[str, int] = {}
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute research across all sources.
        
        Args:
            context: Contains 'query', 'focus_areas', 'source_preferences', 'max_sources'
            
        Returns:
            Dictionary with sources and raw findings
        """
        query = context.get("query", "")
        focus_areas = context.get("focus_areas", [])
        source_preferences = context.get("source_preferences", [])
        max_sources = context.get("max_sources", 300)
        
        logger.info(f"Researcher starting search for: {query}")
        
        try:
            await self._set_status(AgentStatus.IN_PROGRESS)
            await self._update_progress(5, "Analyzing query and preparing search strategy...")
            
            # Generate search queries based on focus areas
            search_queries = await self._generate_search_queries(query, focus_areas)
            
            await self._update_progress(10, f"Generated {len(search_queries)} search queries")
            
            # Execute parallel searches
            all_sources = []
            sources_by_api = {
                "google": [],
                "newsapi": [],
                "arxiv": [],
                "pubmed": [],
                "wikipedia": []
            }
            
            # Calculate results per source
            results_per_source = max(10, max_sources // (len(search_queries) * 5))
            
            for i, search_query in enumerate(search_queries):
                progress = 10 + int((i / len(search_queries)) * 60)
                await self._update_progress(
                    progress,
                    f"Searching: {search_query[:50]}..."
                )
                
                # Execute parallel search across all APIs
                results = await self.search_tools.search_all(
                    query=search_query,
                    max_results_per_source=results_per_source
                )
                
                # Aggregate results
                for api, items in results.items():
                    sources_by_api[api].extend(items)
                    all_sources.extend(items)
                
                # Check if we have enough sources
                if len(all_sources) >= max_sources:
                    break
            
            await self._update_progress(75, f"Collected {len(all_sources)} sources, deduplicating...")
            
            # Deduplicate sources by URL
            seen_urls = set()
            unique_sources = []
            for source in all_sources:
                url = source.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_sources.append(source)
            
            # Limit to max_sources
            unique_sources = unique_sources[:max_sources]
            
            await self._update_progress(85, f"Processing {len(unique_sources)} unique sources...")
            
            # Count sources by API
            self.sources_found = {
                api: len([s for s in unique_sources if s.get("api_source") == api])
                for api in sources_by_api.keys()
            }
            self.sources_found["total"] = len(unique_sources)
            
            # Extract key information using LLM
            await self._update_progress(90, "Extracting key information from sources...")
            
            raw_findings = await self._extract_key_info(query, unique_sources[:50])
            
            await self._update_progress(100, f"Research complete: {len(unique_sources)} sources found")
            await self._set_status(AgentStatus.COMPLETED)
            
            return {
                "status": "completed",
                "query": query,
                "sources": unique_sources,
                "sources_count": self.sources_found,
                "raw_findings": raw_findings,
                "search_queries_used": search_queries,
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Researcher execution failed: {e}")
            await self._set_status(AgentStatus.FAILED, str(e))
            return {
                "status": "failed",
                "error": str(e),
                "sources": [],
                "sources_count": {"total": 0}
            }
    
    async def _generate_search_queries(
        self,
        query: str,
        focus_areas: List[str]
    ) -> List[str]:
        """Generate optimized search queries based on the main query and focus areas."""
        
        queries = [query]  # Always include original query
        
        # Add focus area variations
        for area in focus_areas:
            queries.append(f"{query} {area}")
        
        # Use LLM to generate additional relevant queries
        prompt = f"""Generate 3-5 additional search queries to comprehensively research this topic.

Main Query: {query}
Focus Areas: {', '.join(focus_areas) if focus_areas else 'General'}

Generate specific, targeted search queries that would help gather comprehensive information.
Return only the queries, one per line, no numbering or explanation."""
        
        try:
            response = await self.think(prompt)
            additional_queries = [q.strip() for q in response.strip().split('\n') if q.strip()]
            queries.extend(additional_queries[:5])
        except Exception as e:
            logger.warning(f"Query generation failed: {e}")
        
        return queries[:8]  # Limit to 8 queries
    
    async def _extract_key_info(
        self,
        query: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract key information and findings from sources."""
        
        if not sources:
            return []
        
        # Build source summary
        source_summaries = []
        for i, source in enumerate(sources[:30]):
            title = source.get("title", "Untitled")
            snippet = source.get("snippet", "")[:300]
            source_summaries.append(f"[{i+1}] {title}\n{snippet}")
        
        context = "\n\n".join(source_summaries)
        
        prompt = f"""Based on these sources, extract the key findings related to the query.

QUERY: {query}

SOURCES:
{context}

Extract 5-10 key findings. For each finding:
1. State the finding clearly
2. Note which source(s) support it [using source numbers]
3. Assess preliminary credibility (high/medium/low)

Format each finding as:
FINDING: [statement]
SOURCES: [1, 2, ...]
CREDIBILITY: [high/medium/low]
---"""
        
        try:
            response = await self.think(prompt)
            
            # Parse findings
            findings = []
            current_finding = {}
            
            for line in response.split('\n'):
                line = line.strip()
                if line.startswith('FINDING:'):
                    if current_finding:
                        findings.append(current_finding)
                    current_finding = {"content": line[8:].strip(), "type": "insight"}
                elif line.startswith('SOURCES:'):
                    current_finding["source_refs"] = line[8:].strip()
                elif line.startswith('CREDIBILITY:'):
                    cred = line[12:].strip().lower()
                    current_finding["preliminary_credibility"] = cred
                elif line == '---' and current_finding:
                    findings.append(current_finding)
                    current_finding = {}
            
            if current_finding:
                findings.append(current_finding)
            
            return findings
            
        except Exception as e:
            logger.warning(f"Key info extraction failed: {e}")
            return []
