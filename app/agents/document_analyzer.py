"""
Document Analyzer Agent
Specialized agent for analyzing uploaded documents: extracting topics, 
entities, key findings, and generating summaries.
"""

from typing import Dict, Any, List, Optional
import json
import re

from app.agents.base_agent import BaseAgent, AgentStatus
from app.config import settings
from app.utils.logging import logger
from app.tools.document_tools import DocumentTools


class DocumentAnalyzer(BaseAgent):
    """
    Agent specialized in document analysis.
    Extracts insights, topics, entities, and summaries from documents.
    """
    
    def __init__(self, model: Optional[str] = None):
        """Initialize the Document Analyzer agent."""
        system_prompt = """You are an expert document analyst with deep expertise in:
- Information extraction and summarization
- Topic identification and categorization
- Entity recognition (people, organizations, concepts)
- Key insight extraction
- Academic and technical document analysis

Your analysis should be:
- Accurate and fact-based
- Well-structured and organized
- Comprehensive yet concise
- Suitable for research purposes

When analyzing documents:
1. Identify the main themes and topics
2. Extract key entities (people, organizations, places, concepts)
3. Highlight important findings, statistics, and claims
4. Generate a clear, comprehensive summary
5. Note any limitations or caveats in the document

Always provide structured output in the requested JSON format."""

        super().__init__(
            name="Document Analyzer",
            role="Analyzes documents to extract topics, entities, findings, and generate summaries",
            system_prompt=system_prompt,
            model=model or settings.analyst_model,
            temperature=0.3,
            max_tokens=4096,
            timeout=180
        )
        
        self.document_tools = DocumentTools()
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute document analysis.
        
        Context should contain:
            - document_id: ID of the document
            - extracted_text: Text content of the document
            - filename: Original filename
            - analysis_depth: quick | thorough | deep (optional)
        """
        try:
            await self._set_status(AgentStatus.IN_PROGRESS)
            await self._update_progress(0, "Starting document analysis...")
            
            document_id = context.get("document_id")
            text = context.get("extracted_text", "")
            filename = context.get("filename", "document")
            depth = context.get("analysis_depth", "thorough")
            
            if not text:
                raise ValueError("No text content provided for analysis")
            
            logger.info(f"Analyzing document {document_id} ({len(text)} chars, depth={depth})")
            
            # Step 1: Extract topics (20%)
            await self._update_progress(10, "Extracting topics...")
            topics = await self._extract_topics(text, depth)
            
            # Step 2: Extract entities (40%)
            await self._update_progress(30, "Identifying entities...")
            entities = await self._extract_entities(text, depth)
            
            # Step 3: Extract key findings (60%)
            await self._update_progress(50, "Extracting key findings...")
            findings = await self._extract_findings(text, depth)
            
            # Step 4: Generate summary (80%)
            await self._update_progress(70, "Generating summary...")
            summary = await self._generate_summary(text, topics, findings, depth)
            
            # Step 5: Compile results (100%)
            await self._update_progress(90, "Compiling analysis results...")
            
            results = {
                "document_id": document_id,
                "filename": filename,
                "topics": topics,
                "entities": entities,
                "key_findings": findings,
                "summary": summary,
                "analysis_depth": depth,
                "word_count": len(text.split()),
                "status": "completed"
            }
            
            await self._set_status(AgentStatus.COMPLETED)
            await self._update_progress(100, "Document analysis complete")
            
            return results
            
        except Exception as e:
            logger.error(f"Document analysis failed: {e}")
            await self._set_status(AgentStatus.FAILED, str(e))
            return {
                "document_id": context.get("document_id"),
                "error": str(e),
                "status": "failed"
            }
    
    async def _extract_topics(self, text: str, depth: str) -> List[str]:
        """Extract main topics from the document."""
        # Use shorter text for quick analysis
        text_sample = text[:8000] if depth == "quick" else text[:20000]
        
        prompt = f"""Analyze the following document text and identify the main topics discussed.

Document Text:
{text_sample}

Return a JSON array of 5-10 main topics, ordered by relevance.
Each topic should be a concise phrase (2-5 words).

Example format:
["Artificial Intelligence", "Machine Learning Ethics", "Data Privacy"]

Return ONLY the JSON array, no other text."""

        try:
            response = await self.think(prompt)
            # Parse JSON from response
            topics = self._parse_json_array(response)
            return topics[:10] if topics else ["General Content"]
        except Exception as e:
            logger.warning(f"Topic extraction failed: {e}")
            return ["Document Content"]
    
    async def _extract_entities(self, text: str, depth: str) -> List[Dict[str, Any]]:
        """Extract named entities from the document."""
        text_sample = text[:6000] if depth == "quick" else text[:15000]
        
        prompt = f"""Analyze the following document and extract key named entities.

Document Text:
{text_sample}

For each entity, identify:
- name: The entity name
- type: One of [person, organization, location, concept, technology, event, date]
- relevance: high, medium, or low
- context: Brief context of how it appears in the document

Return a JSON array of entities (max 20 most important ones).

Example format:
[
  {{"name": "OpenAI", "type": "organization", "relevance": "high", "context": "AI research company discussed as leader"}}
]

Return ONLY the JSON array, no other text."""

        try:
            response = await self.think(prompt)
            entities = self._parse_json_array(response)
            return entities[:20] if entities else []
        except Exception as e:
            logger.warning(f"Entity extraction failed: {e}")
            return []
    
    async def _extract_findings(self, text: str, depth: str) -> List[str]:
        """Extract key findings, claims, and important points."""
        text_sample = text[:10000] if depth == "quick" else text[:25000]
        
        prompt = f"""Analyze the following document and extract the key findings, claims, and important points.

Document Text:
{text_sample}

Focus on:
- Main arguments or theses
- Important statistics or data points
- Key conclusions
- Notable claims (with caveats if needed)
- Actionable insights

Return a JSON array of 5-15 key findings as strings.
Each finding should be a complete, clear sentence.

Example format:
["AI adoption increased by 40% in 2024", "The study found a correlation between X and Y"]

Return ONLY the JSON array, no other text."""

        try:
            response = await self.think(prompt)
            findings = self._parse_json_array(response)
            return findings[:15] if findings else []
        except Exception as e:
            logger.warning(f"Findings extraction failed: {e}")
            return []
    
    async def _generate_summary(
        self,
        text: str,
        topics: List[str],
        findings: List[str],
        depth: str
    ) -> str:
        """Generate a comprehensive summary of the document."""
        # Determine summary length based on depth
        length_guide = {
            "quick": "2-3 paragraphs (150-250 words)",
            "thorough": "4-5 paragraphs (300-500 words)",
            "deep": "6-8 paragraphs (500-800 words)"
        }
        
        text_sample = text[:15000] if depth == "quick" else text[:30000]
        topics_str = ", ".join(topics[:5])
        findings_str = "\n".join(f"- {f}" for f in findings[:10])
        
        prompt = f"""Generate a comprehensive summary of the following document.

Main Topics: {topics_str}

Key Findings:
{findings_str}

Document Text:
{text_sample}

Guidelines:
- Length: {length_guide.get(depth, length_guide['thorough'])}
- Start with the main purpose/thesis of the document
- Cover all major points and arguments
- Include important statistics or data if present
- Note any limitations or caveats
- End with key conclusions or implications
- Use clear, professional language

Write the summary directly without any JSON formatting or preamble."""

        try:
            summary = await self.think(prompt)
            return summary.strip()
        except Exception as e:
            logger.warning(f"Summary generation failed: {e}")
            return "Summary could not be generated due to an error."
    
    async def compare_documents(
        self,
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Compare multiple documents and identify similarities and differences.
        
        Args:
            documents: List of document dicts with 'document_id', 'summary', 'topics', 'key_findings'
        """
        if len(documents) < 2:
            raise ValueError("At least 2 documents required for comparison")
        
        await self._set_status(AgentStatus.IN_PROGRESS)
        await self._update_progress(10, "Preparing document comparison...")
        
        # Build comparison context
        doc_summaries = []
        for i, doc in enumerate(documents):
            doc_summaries.append(f"""
Document {i+1}: {doc.get('filename', f'Document {i+1}')}
Topics: {', '.join(doc.get('topics', [])[:5])}
Key Findings:
{chr(10).join('- ' + f for f in doc.get('key_findings', [])[:5])}
Summary: {doc.get('summary', 'No summary available')[:1000]}
""")
        
        await self._update_progress(30, "Analyzing similarities...")
        
        prompt = f"""Compare the following documents and provide a detailed analysis.

{chr(10).join(doc_summaries)}

Provide your analysis in the following JSON format:
{{
  "similarities": [
    {{"topic": "shared topic", "description": "how documents are similar on this topic"}}
  ],
  "differences": [
    {{"topic": "differing topic", "doc1_position": "position in doc 1", "doc2_position": "position in doc 2"}}
  ],
  "recommendation": "which document(s) to use for what purpose",
  "overall_analysis": "2-3 paragraph comparison summary"
}}

Return ONLY the JSON object."""

        try:
            await self._update_progress(60, "Generating comparison analysis...")
            response = await self.think(prompt)
            
            # Parse response
            comparison = self._parse_json_object(response)
            
            if not comparison:
                comparison = {
                    "similarities": [],
                    "differences": [],
                    "recommendation": "Unable to generate recommendation",
                    "overall_analysis": response
                }
            
            await self._set_status(AgentStatus.COMPLETED)
            await self._update_progress(100, "Comparison complete")
            
            return {
                "document_ids": [d.get("document_id") for d in documents],
                **comparison,
                "status": "completed"
            }
            
        except Exception as e:
            logger.error(f"Document comparison failed: {e}")
            await self._set_status(AgentStatus.FAILED, str(e))
            return {
                "document_ids": [d.get("document_id") for d in documents],
                "error": str(e),
                "status": "failed"
            }
    
    async def answer_question(
        self,
        question: str,
        document_context: str,
        chat_history: Optional[List[Dict[str, str]]] = None
    ) -> Dict[str, Any]:
        """
        Answer a question based on document context.
        
        Args:
            question: User's question
            document_context: Relevant text from documents
            chat_history: Previous conversation messages
        """
        # Build chat context
        history_str = ""
        if chat_history:
            for msg in chat_history[-10:]:  # Last 10 messages
                role = "User" if msg.get("role") == "user" else "Assistant"
                history_str += f"\n{role}: {msg.get('content', '')}"
        
        prompt = f"""Based on the following document context, answer the user's question.

Document Context:
{document_context[:15000]}

{f"Previous Conversation:{history_str}" if history_str else ""}

User Question: {question}

Guidelines:
- Answer based ONLY on the provided document context
- If the answer is not in the context, say so clearly
- Cite specific parts of the document when relevant
- Be concise but thorough
- If asked for opinions, clarify these are interpretations of the document

Provide your response directly without JSON formatting."""

        try:
            response = await self.think(prompt)
            return {
                "answer": response.strip(),
                "agent": "document_analyzer",
                "sources": ["document_context"],
                "status": "completed"
            }
        except Exception as e:
            logger.error(f"Question answering failed: {e}")
            return {
                "answer": f"I apologize, but I encountered an error: {str(e)}",
                "agent": "document_analyzer",
                "error": str(e),
                "status": "failed"
            }
    
    def _parse_json_array(self, response: str) -> List[Any]:
        """Parse a JSON array from LLM response."""
        try:
            # Try direct parse
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to find array in response
        match = re.search(r'\[[\s\S]*\]', response)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        # Last resort: try to extract items
        items = re.findall(r'"([^"]+)"', response)
        return items if items else []
    
    def _parse_json_object(self, response: str) -> Optional[Dict[str, Any]]:
        """Parse a JSON object from LLM response."""
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        
        # Try to find object in response
        match = re.search(r'\{[\s\S]*\}', response)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        return None
