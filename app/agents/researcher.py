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
    - Filter for relevance to the query
    - Track sources and metadata
    - Parallel search execution
    """
    
    def __init__(self):
        system_prompt = """You are a research expert who searches multiple sources to gather comprehensive, RELEVANT information.

Your responsibilities:
1. Analyze the research query to identify key search terms and concepts
2. Search across multiple sources (web, news, academic, encyclopedic)
3. CRITICALLY evaluate each source for relevance to the specific query
4. Discard sources that are not directly related to the research topic
5. Extract concrete data points, statistics, and findings from relevant sources
6. Track source metadata for attribution

Guidelines:
- QUALITY over quantity — 20 highly relevant sources beat 200 irrelevant ones
- Only include sources that directly address the research query
- Prioritize sources with specific data, statistics, or expert analysis
- Prioritize authoritative and credible sources (academic, government, established media)
- Note publication dates for recency
- Preserve original source attribution
- NEVER include sources just to increase count — every source must add value

Output structured findings with clear source attribution and concrete data points."""
        
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
            
            # Calculate results per source — keep moderate to avoid noise
            results_per_source = max(5, min(15, max_sources // (len(search_queries) * 3)))
            
            for i, search_query in enumerate(search_queries):
                progress = 10 + int((i / len(search_queries)) * 40)
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
                
                # Don't over-collect — we'll filter for quality
                if len(all_sources) >= max_sources * 2:
                    break
            
            await self._update_progress(55, f"Collected {len(all_sources)} sources, deduplicating...")
            
            # Deduplicate sources by URL
            seen_urls = set()
            unique_sources = []
            for source in all_sources:
                url = source.get("url", "")
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    unique_sources.append(source)
            
            await self._update_progress(60, f"Filtering {len(unique_sources)} sources for relevance...")
            
            # CRITICAL: Filter sources for relevance to the query
            relevant_sources = await self._filter_relevant_sources(query, unique_sources)
            
            # Limit to max_sources
            relevant_sources = relevant_sources[:max_sources]
            
            await self._update_progress(80, f"{len(relevant_sources)} relevant sources found (filtered from {len(unique_sources)})...")
            
            # Count sources by API
            self.sources_found = {
                api: len([s for s in relevant_sources if s.get("api_source") == api])
                for api in sources_by_api.keys()
            }
            self.sources_found["total"] = len(relevant_sources)
            self.sources_found["total_before_filtering"] = len(unique_sources)
            
            # Extract key information using LLM — pass all relevant sources
            await self._update_progress(85, "Extracting key information from relevant sources...")
            
            raw_findings = await self._extract_key_info(query, relevant_sources[:40])
            
            await self._update_progress(100, f"Research complete: {len(relevant_sources)} relevant sources, {len(raw_findings)} findings extracted")
            await self._set_status(AgentStatus.COMPLETED)
            
            return {
                "status": "completed",
                "query": query,
                "sources": relevant_sources,
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
        prompt = f"""Generate 3-5 highly specific search queries to research this topic THOROUGHLY.

Main Query: {query}
Focus Areas: {', '.join(focus_areas) if focus_areas else 'General'}

Rules:
- Each query must be DIRECTLY relevant to the main topic
- Include queries that would find statistics, data, and expert analysis
- Include queries that would find recent studies and reports
- Make queries specific enough to avoid irrelevant results
- DO NOT generate generic or tangential queries

Return only the queries, one per line, no numbering or explanation."""
        
        try:
            response = await self.think(prompt)
            additional_queries = [q.strip() for q in response.strip().split('\n') if q.strip() and len(q.strip()) > 5]
            queries.extend(additional_queries[:5])
        except Exception as e:
            logger.warning(f"Query generation failed: {e}")
        
        return queries[:8]  # Limit to 8 queries
    
    async def _filter_relevant_sources(
        self,
        query: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter sources for relevance to the research query using keyword matching + LLM."""
        
        if not sources:
            return []
        
        # Step 1: Quick keyword-based pre-filtering
        query_lower = query.lower()
        query_words = set(query_lower.split())
        # Remove common stop words
        stop_words = {'the', 'a', 'an', 'is', 'are', 'was', 'were', 'of', 'in', 'on', 'at', 'to', 'for', 'and', 'or', 'but', 'not', 'with', 'how', 'what', 'why', 'when', 'where', 'which', 'who', 'does', 'do', 'can', 'could', 'would', 'should', 'its', 'it', 'this', 'that', 'these', 'those', 'has', 'have', 'had', 'will', 'be', 'been', 'being', 'from', 'by', 'about', 'into', 'through', 'during', 'before', 'after', 'above', 'below', 'between', 'under', 'over', 'then', 'than', 'so', 'if'}
        query_keywords = query_words - stop_words
        
        scored_sources = []
        for source in sources:
            title = (source.get("title", "") or "").lower()
            snippet = (source.get("snippet", "") or "").lower()
            combined = f"{title} {snippet}"
            
            # Count keyword matches
            keyword_hits = sum(1 for kw in query_keywords if kw in combined)
            keyword_ratio = keyword_hits / max(len(query_keywords), 1)
            
            # Boost academic sources
            source_type = source.get("source_type", "")
            type_boost = 1.2 if source_type == "academic" else 1.0
            
            relevance_score = keyword_ratio * type_boost
            source["_relevance_score"] = relevance_score
            scored_sources.append(source)
        
        # Sort by relevance score descending
        scored_sources.sort(key=lambda s: s.get("_relevance_score", 0), reverse=True)
        
        # Take top candidates (generous to allow LLM to refine)
        candidates = scored_sources[:min(80, len(scored_sources))]
        
        # Step 2: LLM-based relevance filtering on top candidates
        # Process in batches of 20
        relevant_sources = []
        batch_size = 20
        
        for batch_start in range(0, len(candidates), batch_size):
            batch = candidates[batch_start:batch_start + batch_size]
            
            source_list = []
            for i, source in enumerate(batch):
                title = source.get("title", "Untitled")
                snippet = (source.get("snippet", "") or "")[:200]
                source_list.append(f"[{i}] {title} — {snippet}")
            
            prompt = f"""You are a research relevance filter. Evaluate which sources are DIRECTLY relevant to this research query.

RESEARCH QUERY: {query}

SOURCES:
{chr(10).join(source_list)}

For each source, respond with ONLY the index numbers of sources that are DIRECTLY relevant to the research query.
A source is relevant if it contains information, data, analysis, or insights that directly help answer or inform the research query.
A source is NOT relevant if it's about a completely different topic, even if it shares some keywords.

Respond with ONLY a comma-separated list of relevant source indices (e.g., "0, 2, 5, 7").
If none are relevant, respond with "NONE"."""
            
            try:
                response = await self.think(prompt)
                response = response.strip()
                
                if response.upper() != "NONE":
                    # Parse indices
                    import re
                    indices = re.findall(r'\d+', response)
                    for idx_str in indices:
                        idx = int(idx_str)
                        if 0 <= idx < len(batch):
                            relevant_sources.append(batch[idx])
            except Exception as e:
                logger.warning(f"LLM relevance filtering failed for batch: {e}")
                # Fallback: include sources with decent keyword score
                for source in batch:
                    if source.get("_relevance_score", 0) >= 0.3:
                        relevant_sources.append(source)
        
        # Clean up temporary score field
        for source in relevant_sources:
            source.pop("_relevance_score", None)
        
        # Ensure we have at least some sources (fallback to keyword-filtered)
        if len(relevant_sources) < 5:
            logger.warning(f"LLM filtering returned only {len(relevant_sources)} sources, using keyword fallback")
            for source in scored_sources[:30]:
                source.pop("_relevance_score", None)
                if source not in relevant_sources:
                    relevant_sources.append(source)
                if len(relevant_sources) >= 30:
                    break
        
        logger.info(f"Relevance filtering: {len(sources)} → {len(relevant_sources)} relevant sources")
        return relevant_sources
    
    async def _extract_key_info(
        self,
        query: str,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Extract key information and findings from sources."""
        
        if not sources:
            return []
        
        # Process in batches to cover more sources
        all_findings = []
        batch_size = 15
        
        for batch_start in range(0, min(len(sources), 45), batch_size):
            batch = sources[batch_start:batch_start + batch_size]
            batch_findings = await self._extract_from_batch(query, batch, batch_start)
            all_findings.extend(batch_findings)
        
        # Deduplicate similar findings
        if len(all_findings) > 10:
            all_findings = await self._deduplicate_findings(query, all_findings)
        
        return all_findings
    
    async def _extract_from_batch(
        self,
        query: str,
        sources: List[Dict[str, Any]],
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """Extract findings from a batch of sources."""
        
        if not sources:
            return []
        
        # Build source summary
        source_summaries = []
        for i, source in enumerate(sources):
            title = source.get("title", "Untitled")
            snippet = source.get("snippet", "")[:400]
            author = source.get("author", "") or ", ".join(source.get("authors", [])[:2])
            year = source.get("published_at", "")
            if year and len(str(year)) > 4:
                year = str(year)[:4]
            source_summaries.append(f"[{offset + i + 1}] ({year}) {title} by {author}\n{snippet}")
        
        context = "\n\n".join(source_summaries)
        
        prompt = f"""You are a research analyst. Extract SPECIFIC, CONCRETE findings from these sources that are directly relevant to the research query.

RESEARCH QUERY: {query}

SOURCES:
{context}

INSTRUCTIONS:
- Extract 3-7 key findings that DIRECTLY answer or inform the research query
- Each finding MUST contain specific data, statistics, expert opinions, or concrete insights
- DO NOT generate generic statements — every finding must cite specific information from the sources
- DO NOT say "no findings" — extract whatever relevant information exists, even if partial
- If a source mentions a specific percentage, number, study result, or expert quote, include it
- Distinguish between well-established facts and preliminary/contested claims

Format each finding as:
FINDING: [specific, data-rich statement directly related to the query]
SOURCES: [{offset + 1}, {offset + 2}, ...]
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
    
    async def _deduplicate_findings(
        self,
        query: str,
        findings: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Remove duplicate/overlapping findings and merge their source refs."""
        
        if len(findings) <= 5:
            return findings
        
        findings_list = "\n".join([
            f"[{i}] {f.get('content', '')[:150]}"
            for i, f in enumerate(findings)
        ])
        
        prompt = f"""These are research findings for: {query}

{findings_list}

Identify which findings are saying essentially the same thing (duplicates or near-duplicates).
Return the indices of findings to KEEP (the best/most complete version of each unique finding).
Respond with ONLY a comma-separated list of indices to keep (e.g., "0, 2, 4, 7, 9")."""
        
        try:
            response = await self.think(prompt)
            import re
            indices = [int(x) for x in re.findall(r'\d+', response)]
            
            kept = []
            for idx in indices:
                if 0 <= idx < len(findings):
                    kept.append(findings[idx])
            
            if len(kept) >= 3:
                return kept
        except Exception as e:
            logger.warning(f"Deduplication failed: {e}")
        
        return findings
