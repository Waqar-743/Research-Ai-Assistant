"""
Validation Tools for the Fact-Checker Agent.
Provides fact-checking, source credibility, and bias detection.
"""

import asyncio
import httpx
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
from urllib.parse import urlparse
import re

from app.config import settings
from app.utils.logging import logger
from app.tools.llm_tools import LLMTools


class ValidationTools:
    """Collection of validation tools for fact-checking and verification."""
    
    def __init__(self):
        self.llm = LLMTools()
        self.timeout = httpx.Timeout(30.0, connect=10.0)
        
        # Domain credibility database (simplified)
        self.credible_domains = {
            # Government
            ".gov": 0.95,
            ".gov.uk": 0.95,
            ".edu": 0.90,
            
            # Academic
            "nature.com": 0.95,
            "science.org": 0.95,
            "sciencedirect.com": 0.90,
            "springer.com": 0.90,
            "wiley.com": 0.90,
            "arxiv.org": 0.85,
            "pubmed.ncbi.nlm.nih.gov": 0.95,
            
            # News (mainstream)
            "reuters.com": 0.90,
            "apnews.com": 0.90,
            "bbc.com": 0.85,
            "bbc.co.uk": 0.85,
            "nytimes.com": 0.80,
            "washingtonpost.com": 0.80,
            "theguardian.com": 0.80,
            
            # Tech
            "wired.com": 0.75,
            "arstechnica.com": 0.75,
            "techcrunch.com": 0.70,
            
            # Reference
            "wikipedia.org": 0.70,
            "britannica.com": 0.85,
        }
        
        # Known bias indicators
        self.bias_indicators = {
            "extreme_left": ["socialist", "marxist", "far-left"],
            "left": ["progressive", "liberal"],
            "center": ["moderate", "centrist", "bipartisan"],
            "right": ["conservative", "traditional"],
            "extreme_right": ["far-right", "nationalist"],
        }
    
    async def cross_reference_claim(
        self,
        claim: str,
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Cross-reference a claim across multiple sources.
        
        Args:
            claim: The claim to verify
            sources: List of source documents to check against
            
        Returns:
            Verification result with confidence score
        """
        logger.info(f"Cross-referencing claim: {claim[:100]}...")
        
        supporting = []
        contradicting = []
        neutral = []
        
        # Build context from sources
        source_texts = []
        for i, source in enumerate(sources[:10]):  # Limit to 10 sources
            snippet = source.get("snippet", "") or source.get("content", "")[:500]
            source_texts.append(f"Source {i+1} ({source.get('title', 'Unknown')}):\n{snippet}")
        
        context = "\n\n".join(source_texts)
        
        # Use LLM to analyze
        prompt = f"""Analyze whether the following sources support, contradict, or are neutral to this claim.

CLAIM: {claim}

SOURCES:
{context}

For each source, determine if it:
1. SUPPORTS the claim (provides evidence in favor)
2. CONTRADICTS the claim (provides evidence against)
3. NEUTRAL (doesn't directly address the claim)

Respond in JSON format:
{{
    "analysis": [
        {{"source_index": 1, "verdict": "supports|contradicts|neutral", "explanation": "brief reason"}}
    ],
    "overall_verdict": "verified|partially_verified|unverified|contradicted",
    "confidence": 0.0-1.0,
    "summary": "brief summary of findings"
}}"""
        
        try:
            result = await self.llm.generate(
                prompt=prompt,
                model=settings.fact_checker_model,
                temperature=0.2,
                max_tokens=1500
            )
            
            # Parse JSON response
            import json
            # Extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                analysis = json.loads(json_match.group())
                
                # Categorize sources
                for item in analysis.get("analysis", []):
                    idx = item.get("source_index", 1) - 1
                    if 0 <= idx < len(sources):
                        src = sources[idx]
                        # Store structured {title, url} dicts so downstream agents
                        # can generate real hyperlink citations in the report
                        src_ref = {
                            "title": src.get("title", ""),
                            "url": src.get("url", ""),
                            "api_source": src.get("api_source", "")
                        }
                        verdict = item.get("verdict", "neutral")
                        if verdict == "supports":
                            supporting.append(src_ref)
                        elif verdict == "contradicts":
                            contradicting.append(src_ref)
                        else:
                            neutral.append(src_ref)
                
                return {
                    "claim": claim,
                    "verified": analysis.get("overall_verdict") in ["verified", "partially_verified"],
                    "verdict": analysis.get("overall_verdict", "unverified"),
                    "confidence": analysis.get("confidence", 0.5),
                    "supporting_sources": supporting,
                    "contradicting_sources": contradicting,
                    "neutral_sources": neutral,
                    "summary": analysis.get("summary", ""),
                    "analysis_details": analysis.get("analysis", [])
                }
                
        except Exception as e:
            logger.error(f"Claim verification failed: {e}")
        
        return {
            "claim": claim,
            "verified": False,
            "verdict": "error",
            "confidence": 0.0,
            "supporting_sources": [],
            "contradicting_sources": [],
            "neutral_sources": [],
            "summary": "Verification failed due to processing error",
            "error": str(e) if 'e' in locals() else "Unknown error"
        }
    
    async def check_source_credibility(
        self,
        url: str
    ) -> Dict[str, Any]:
        """
        Check source credibility and authority.
        
        Args:
            url: URL of the source
            
        Returns:
            Credibility assessment with score and warnings
        """
        warnings = []
        credibility_score = 0.5  # Default neutral score
        
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower()
            
            # Remove www prefix
            if domain.startswith("www."):
                domain = domain[4:]
            
            # Check against known domains
            for known_domain, score in self.credible_domains.items():
                if domain.endswith(known_domain) or domain == known_domain:
                    credibility_score = score
                    break
            
            # Check for suspicious patterns
            if any(x in domain for x in ["blog", "wordpress", "medium", "substack"]):
                credibility_score = min(credibility_score, 0.5)
                warnings.append("Personal blog or opinion platform")
            
            if any(x in domain for x in ["news", "daily", "times"]) and domain not in self.credible_domains:
                warnings.append("Unverified news source")
                credibility_score = min(credibility_score, 0.6)
            
            # Check HTTPS
            if parsed.scheme != "https":
                warnings.append("Not using secure connection (HTTPS)")
                credibility_score -= 0.1
            
            # Check domain age and availability (simplified)
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                try:
                    response = await client.head(url, follow_redirects=True)
                    if response.status_code >= 400:
                        warnings.append(f"Source returned error: {response.status_code}")
                        credibility_score -= 0.2
                except Exception:
                    warnings.append("Source is unreachable")
                    credibility_score -= 0.3
            
            # Determine source type
            source_type = "unknown"
            if ".gov" in domain or ".edu" in domain:
                source_type = "official"
            elif domain in ["arxiv.org", "pubmed.ncbi.nlm.nih.gov", "nature.com", "science.org"]:
                source_type = "academic"
            elif any(x in domain for x in ["news", "times", "post", "reuters", "bbc"]):
                source_type = "news"
            elif any(x in domain for x in ["blog", "medium", "substack"]):
                source_type = "blog"
            
            return {
                "url": url,
                "domain": domain,
                "credibility_score": max(0.0, min(1.0, credibility_score)),
                "source_type": source_type,
                "warnings": warnings,
                "is_credible": credibility_score >= 0.7
            }
            
        except Exception as e:
            logger.error(f"Credibility check failed for {url}: {e}")
            return {
                "url": url,
                "domain": "",
                "credibility_score": 0.3,
                "source_type": "unknown",
                "warnings": ["Failed to analyze source"],
                "is_credible": False,
                "error": str(e)
            }
    
    async def verify_statistics(
        self,
        statistic: str,
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Verify statistical claims with source verification.
        
        Args:
            statistic: The statistical claim to verify
            sources: Sources to check against
            
        Returns:
            Verification result for the statistic
        """
        logger.info(f"Verifying statistic: {statistic[:100]}...")
        
        # Build context
        source_texts = []
        for i, source in enumerate(sources[:8]):
            snippet = source.get("snippet", "") or source.get("content", "")[:400]
            source_texts.append(f"Source {i+1}: {snippet}")
        
        context = "\n\n".join(source_texts)
        
        prompt = f"""Verify this statistical claim against the provided sources.

STATISTICAL CLAIM: {statistic}

SOURCES:
{context}

Analyze:
1. Is this statistic mentioned or supported by any source?
2. Are there any conflicting numbers?
3. What is the original source of this statistic (if identifiable)?

Respond in JSON:
{{
    "verified": true/false,
    "confidence": 0.0-1.0,
    "original_value": "the statistic as stated",
    "found_values": ["values found in sources"],
    "discrepancies": ["any differences noted"],
    "source_indices": [indices of supporting sources],
    "notes": "additional context"
}}"""
        
        try:
            result = await self.llm.generate(
                prompt=prompt,
                model=settings.fact_checker_model,
                temperature=0.2,
                max_tokens=1000
            )
            
            import json
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                analysis = json.loads(json_match.group())
                return {
                    "statistic": statistic,
                    "verified": analysis.get("verified", False),
                    "confidence": analysis.get("confidence", 0.5),
                    "original_value": analysis.get("original_value", statistic),
                    "found_values": analysis.get("found_values", []),
                    "discrepancies": analysis.get("discrepancies", []),
                    "supporting_sources": analysis.get("source_indices", []),
                    "notes": analysis.get("notes", "")
                }
                
        except Exception as e:
            logger.error(f"Statistic verification failed: {e}")
        
        return {
            "statistic": statistic,
            "verified": False,
            "confidence": 0.0,
            "original_value": statistic,
            "found_values": [],
            "discrepancies": [],
            "supporting_sources": [],
            "notes": "Verification failed"
        }
    
    async def detect_bias(
        self,
        text: str
    ) -> Dict[str, Any]:
        """
        Detect potential bias in text content.
        
        Args:
            text: Text to analyze for bias
            
        Returns:
            Bias analysis with score and type
        """
        prompt = f"""Analyze the following text for potential bias.

TEXT:
{text[:2000]}

Evaluate:
1. Political bias (left/center/right)
2. Emotional language vs objective reporting
3. Missing perspectives or one-sided presentation
4. Use of loaded words or framing

Respond in JSON:
{{
    "bias_score": 0.0-1.0 (0=neutral, 1=highly biased),
    "bias_direction": "left|center-left|center|center-right|right|none",
    "bias_types": ["list of bias types detected"],
    "loaded_words": ["emotionally charged words found"],
    "missing_perspectives": ["perspectives not represented"],
    "explanation": "brief explanation of bias assessment"
}}"""
        
        try:
            result = await self.llm.generate(
                prompt=prompt,
                model=settings.fact_checker_model,
                temperature=0.3,
                max_tokens=800
            )
            
            import json
            json_match = re.search(r'\{[\s\S]*\}', result)
            if json_match:
                analysis = json.loads(json_match.group())
                return {
                    "bias_score": analysis.get("bias_score", 0.5),
                    "bias_direction": analysis.get("bias_direction", "unknown"),
                    "bias_types": analysis.get("bias_types", []),
                    "loaded_words": analysis.get("loaded_words", []),
                    "missing_perspectives": analysis.get("missing_perspectives", []),
                    "explanation": analysis.get("explanation", ""),
                    "is_biased": analysis.get("bias_score", 0.5) > 0.6
                }
                
        except Exception as e:
            logger.error(f"Bias detection failed: {e}")
        
        return {
            "bias_score": 0.5,
            "bias_direction": "unknown",
            "bias_types": [],
            "loaded_words": [],
            "missing_perspectives": [],
            "explanation": "Analysis failed",
            "is_biased": False
        }
    
    async def validate_findings(
        self,
        findings: List[Dict[str, Any]],
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Validate a list of findings against sources.
        
        Args:
            findings: List of findings to validate
            sources: List of sources for verification
            
        Returns:
            List of findings with validation results
        """
        validated_findings = []
        
        for finding in findings:
            content = finding.get("content", "") or finding.get("title", "")
            
            # Cross-reference the finding
            verification = await self.cross_reference_claim(content, sources)
            
            validated_findings.append({
                **finding,
                "verified": verification.get("verified", False),
                "confidence_score": verification.get("confidence", 0.5),
                "verification_verdict": verification.get("verdict", "unverified"),
                "supporting_sources": verification.get("supporting_sources", []),
                "contradicting_sources": verification.get("contradicting_sources", []),
                "verification_summary": verification.get("summary", "")
            })
        
        return validated_findings


# Singleton instance
validation_tools = ValidationTools()
