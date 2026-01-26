"""
Report Generator Agent
Responsible for creating professional formatted reports.
"""

from typing import Dict, Any, List, Optional
from datetime import datetime
import json
import re

from app.agents.base_agent import BaseAgent, AgentStatus
from app.tools.formatting_tools import FormattingTools
from app.config import settings
from app.utils.logging import logger


class ReportGeneratorAgent(BaseAgent):
    """
    Report Generator Agent - Report writing and formatting specialist.
    
    Responsibilities:
    - Structure findings into logical report sections
    - Write coherent narrative from research data
    - Generate reports in multiple formats (Markdown, HTML, PDF)
    - Format citations properly (APA, MLA, Chicago)
    - Create executive summaries
    """
    
    def __init__(self):
        system_prompt = """You are an expert report writer who creates professional research reports.

Your responsibilities:
1. Structure findings into logical, well-organized sections
2. Write clear, coherent narrative that tells the research story
3. Include proper citations and source attribution
4. Create compelling executive summaries
5. Ensure reports are accessible and easy to read

Guidelines:
- Use clear, professional language
- Organize content from most to least important
- Use headings and subheadings for navigation
- Include visual breaks (lists, emphasis) for readability
- Cite sources consistently throughout
- Write for your target audience
- Balance comprehensiveness with conciseness

Your reports should be publication-ready."""
        
        super().__init__(
            name="Report Generator",
            role="Report writing and formatting specialist",
            system_prompt=system_prompt,
            model=settings.report_generator_model,
            temperature=0.4,
            max_tokens=8192,
            timeout=settings.agent_timeout
        )
        
        self.formatting_tools = FormattingTools()
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute report generation from validated findings.
        
        Args:
            context: Contains 'query', 'validated_findings', 'sources', 
                    'confidence_summary', 'report_format', 'citation_style'
            
        Returns:
            Dictionary with generated report in multiple formats
        """
        query = context.get("query", "")
        findings = context.get("validated_findings", [])
        sources = context.get("sources", [])
        key_insights = context.get("key_insights", [])
        confidence_summary = context.get("confidence_summary", {})
        report_format = context.get("report_format", "markdown")
        citation_style = context.get("citation_style", "APA")
        
        logger.info(f"Report Generator starting for: {query}")
        
        try:
            await self._set_status(AgentStatus.IN_PROGRESS)
            await self._update_progress(5, "Planning report structure...")
            
            # Step 1: Generate report title
            title = await self._generate_title(query)
            
            # Step 2: Structure sections
            await self._update_progress(15, "Structuring report sections...")
            sections = await self._structure_sections(query, findings, key_insights)
            
            # Step 3: Write section content
            await self._update_progress(30, "Writing report content...")
            written_sections = await self._write_sections(query, sections, findings, sources)
            
            # Step 4: Generate executive summary
            await self._update_progress(55, "Creating executive summary...")
            summary = await self._generate_executive_summary(
                query, written_sections, confidence_summary
            )
            
            # Step 5: Generate Markdown report
            await self._update_progress(70, "Generating Markdown report...")
            markdown_content = await self.formatting_tools.generate_markdown(
                title=title,
                sections=written_sections,
                sources=sources[:100],  # Limit citations
                citation_style=citation_style
            )
            
            # Insert summary after title
            markdown_with_summary = self._insert_summary(markdown_content, summary)
            
            # Step 6: Generate HTML if needed
            await self._update_progress(85, "Generating HTML version...")
            html_content = await self.formatting_tools.generate_html(
                title=title,
                markdown_content=markdown_with_summary
            )
            
            # Step 7: Generate PDF if requested
            pdf_bytes = None
            if report_format == "pdf":
                await self._update_progress(92, "Generating PDF version...")
                pdf_bytes = await self.formatting_tools.generate_pdf(
                    title=title,
                    html_content=html_content
                )
            
            # Calculate quality score
            quality_score = self._calculate_quality_score(
                findings, sources, confidence_summary
            )
            
            await self._update_progress(100, "Report generation complete!")
            await self._set_status(AgentStatus.COMPLETED)
            
            return {
                "status": "completed",
                "query": query,
                "report": {
                    "title": title,
                    "summary": summary,
                    "markdown_content": markdown_with_summary,
                    "html_content": html_content,
                    "pdf_bytes": pdf_bytes,
                    "sections": written_sections,
                    "citation_style": citation_style,
                    "quality_score": quality_score
                },
                "metadata": {
                    "total_sources": len(sources),
                    "total_findings": len(findings),
                    "confidence_level": confidence_summary.get("confidence_level", "medium"),
                    "generated_at": datetime.utcnow().isoformat()
                },
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Report Generator execution failed: {e}")
            await self._set_status(AgentStatus.FAILED, str(e))
            return {
                "status": "failed",
                "error": str(e),
                "report": None
            }
    
    async def _generate_title(self, query: str) -> str:
        """Generate a professional report title."""
        
        prompt = f"""Generate a professional, concise report title for this research query.

Query: {query}

The title should:
1. Be clear and descriptive
2. Be professional in tone
3. Be 5-12 words maximum
4. Not include quotes or special characters

Return only the title, nothing else."""
        
        try:
            title = await self.think(prompt)
            return title.strip().strip('"\'')
        except Exception as e:
            logger.warning(f"Title generation failed: {e}")
            return f"Research Report: {query[:50]}"
    
    async def _structure_sections(
        self,
        query: str,
        findings: List[Dict[str, Any]],
        insights: List[str]
    ) -> List[Dict[str, Any]]:
        """Create logical section structure for the report."""
        
        # Use formatting tools to structure findings
        sections = await self.formatting_tools.structure_findings(findings, query)
        
        # Ensure we have key sections
        section_titles = [s.get("title", "").lower() for s in sections]
        
        # Add methodology section if not present
        if not any("method" in t for t in section_titles):
            sections.insert(0, {
                "title": "Research Methodology",
                "content": "",
                "order": 0
            })
        
        # Add conclusions section if not present
        if not any("conclusion" in t for t in section_titles):
            sections.append({
                "title": "Conclusions and Recommendations",
                "content": "",
                "order": len(sections)
            })
        
        # Reorder
        for i, section in enumerate(sections):
            section["order"] = i + 1
        
        return sections
    
    async def _write_sections(
        self,
        query: str,
        sections: List[Dict[str, Any]],
        findings: List[Dict[str, Any]],
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Write detailed content for each section."""
        
        written_sections = []
        
        for i, section in enumerate(sections):
            title = section.get("title", f"Section {i+1}")
            existing_content = section.get("content", "")
            
            # Progress update
            progress = 30 + int((i / len(sections)) * 25)
            await self._update_progress(progress, f"Writing: {title}...")
            
            # Generate content based on section type
            if "methodology" in title.lower():
                content = await self._write_methodology_section(sources)
            elif "conclusion" in title.lower():
                content = await self._write_conclusions_section(query, findings)
            elif existing_content:
                content = await self._enhance_section_content(
                    title, existing_content, findings
                )
            else:
                content = await self._write_section_content(
                    title, query, findings
                )
            
            written_sections.append({
                "title": title,
                "content": content,
                "order": section.get("order", i + 1)
            })
        
        return written_sections
    
    async def _write_methodology_section(
        self,
        sources: List[Dict[str, Any]]
    ) -> str:
        """Write the methodology section."""
        
        # Count sources by type
        source_types = {}
        for source in sources:
            stype = source.get("api_source", "other")
            source_types[stype] = source_types.get(stype, 0) + 1
        
        source_summary = ", ".join([
            f"{count} from {stype.title()}"
            for stype, count in source_types.items()
        ])
        
        content = f"""This research was conducted using a multi-agent AI system that employs specialized agents for different aspects of the research process:

1. **Information Gathering**: The Researcher Agent collected information from multiple sources including academic databases (ArXiv, PubMed), news sources (NewsAPI), web search (Google), and encyclopedic sources (Wikipedia).

2. **Analysis**: The Analyst Agent synthesized the collected information, identified patterns, and consolidated findings into coherent themes.

3. **Verification**: The Fact-Checker Agent validated claims through cross-referencing, assessed source credibility, and detected potential bias.

4. **Report Generation**: The Report Generator Agent structured and wrote this comprehensive report.

**Sources Analyzed**: A total of {len(sources)} sources were analyzed, including {source_summary}.

**Quality Assurance**: All findings have been cross-referenced against multiple sources, and confidence scores have been assigned based on the level of corroboration."""
        
        return content
    
    async def _write_conclusions_section(
        self,
        query: str,
        findings: List[Dict[str, Any]]
    ) -> str:
        """Write the conclusions section."""
        
        verified_findings = [f for f in findings if f.get("verified", False)]
        high_confidence = [f for f in findings if f.get("confidence_score", 0) > 0.7]
        
        findings_summary = "\n".join([
            f"- {f.get('title', 'Finding')}"
            for f in verified_findings[:5]
        ])
        
        prompt = f"""Write a conclusions section for a research report on: {query}

Key Verified Findings:
{findings_summary}

The conclusions should:
1. Summarize the main findings
2. Discuss implications
3. Note any limitations
4. Suggest areas for further research
5. Be 2-3 paragraphs long

Write in a professional, objective tone."""
        
        try:
            return await self.think(prompt)
        except Exception as e:
            logger.warning(f"Conclusions generation failed: {e}")
            return f"This research on \"{query}\" identified {len(verified_findings)} verified findings. Further investigation is recommended to explore emerging developments in this area."
    
    async def _enhance_section_content(
        self,
        title: str,
        existing_content: str,
        findings: List[Dict[str, Any]]
    ) -> str:
        """Enhance existing section content."""
        
        prompt = f"""Enhance this section content to be more comprehensive and professional.

Section Title: {title}

Current Content:
{existing_content[:2000]}

Enhance the content to:
1. Be well-written and professional
2. Include relevant details from findings
3. Use clear paragraph structure
4. Be 2-4 paragraphs long

Write the enhanced content:"""
        
        try:
            return await self.think(prompt)
        except Exception:
            return existing_content
    
    async def _write_section_content(
        self,
        title: str,
        query: str,
        findings: List[Dict[str, Any]]
    ) -> str:
        """Write new section content from scratch."""
        
        relevant_findings = "\n".join([
            f"- {f.get('title', '')}: {f.get('content', '')[:150]}"
            for f in findings[:8]
        ])
        
        prompt = f"""Write content for this report section.

Report Topic: {query}
Section Title: {title}

Available Findings:
{relevant_findings}

Write 2-4 paragraphs that:
1. Address the section topic thoroughly
2. Incorporate relevant findings
3. Are well-organized and professional
4. Include specific details and examples

Write the section content:"""
        
        try:
            return await self.think(prompt)
        except Exception as e:
            logger.warning(f"Section writing failed: {e}")
            return f"[Content for {title} section]"
    
    async def _generate_executive_summary(
        self,
        query: str,
        sections: List[Dict[str, Any]],
        confidence_summary: Dict[str, Any]
    ) -> str:
        """Generate executive summary."""
        
        # Combine section content
        full_content = "\n\n".join([
            f"{s.get('title', '')}\n{s.get('content', '')[:500]}"
            for s in sections
        ])
        
        summary = await self.formatting_tools.create_summary(
            content=full_content,
            max_length=600
        )
        
        # Add confidence note
        confidence_level = confidence_summary.get("confidence_level", "medium")
        summary += f"\n\n*Research Confidence Level: {confidence_level.upper()}*"
        
        return summary
    
    def _insert_summary(self, markdown: str, summary: str) -> str:
        """Insert executive summary after the title."""
        
        lines = markdown.split('\n')
        
        # Find where to insert (after title and metadata)
        insert_index = 0
        for i, line in enumerate(lines):
            if line.startswith('---'):
                insert_index = i + 1
                break
        
        summary_section = f"\n## Executive Summary\n\n{summary}\n"
        lines.insert(insert_index, summary_section)
        
        return '\n'.join(lines)
    
    def _calculate_quality_score(
        self,
        findings: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        confidence_summary: Dict[str, Any]
    ) -> float:
        """Calculate overall quality score (0-5)."""
        
        # Factors
        source_count_score = min(len(sources) / 100, 1.0)  # Max at 100 sources
        
        verified_ratio = confidence_summary.get("verified_findings", 0) / max(len(findings), 1)
        
        confidence = confidence_summary.get("overall_confidence", 0.5)
        
        # Calculate weighted score
        quality = (
            source_count_score * 1.5 +
            verified_ratio * 2.0 +
            confidence * 1.5
        )
        
        return round(min(quality, 5.0), 1)
