"""
LLM Tools for interacting with language models via OpenRouter.
"""

import httpx
from typing import Optional, Dict, Any, List
import json

from app.config import settings
from app.utils.logging import logger


class LLMTools:
    """Tools for interacting with LLMs via OpenRouter API."""
    
    def __init__(self):
        self.base_url = settings.openrouter_base_url
        self.api_key = settings.openrouter_api_key
        self.timeout = httpx.Timeout(120.0, connect=10.0)
    
    async def generate(
        self,
        prompt: str,
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 2000,
        stop: Optional[List[str]] = None
    ) -> str:
        """
        Generate text using the specified LLM.
        
        Args:
            prompt: User prompt
            model: Model identifier (e.g., "deepseek/deepseek-chat")
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens to generate
            stop: Stop sequences
            
        Returns:
            Generated text
        """
        if not self.api_key:
            logger.error("OpenRouter API key not configured")
            raise ValueError("OpenRouter API key not configured")
        
        model = model or settings.researcher_model
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        
        if stop:
            payload["stop"] = stop
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://research-assistant.app",
            "X-Title": "Multi-Agent Research Assistant"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    
                    # Log token usage
                    usage = data.get("usage", {})
                    logger.debug(
                        f"LLM call - Model: {model}, "
                        f"Input: {usage.get('prompt_tokens', 0)}, "
                        f"Output: {usage.get('completion_tokens', 0)}"
                    )
                    
                    return content
                else:
                    error_text = response.text
                    logger.error(f"LLM API error: {response.status_code} - {error_text}")
                    raise Exception(f"LLM API error: {response.status_code}")
                    
        except httpx.TimeoutException:
            logger.error("LLM request timed out")
            raise
        except Exception as e:
            logger.error(f"LLM generation failed: {e}")
            raise
    
    async def generate_with_functions(
        self,
        prompt: str,
        functions: List[Dict[str, Any]],
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        temperature: float = 0.3
    ) -> Dict[str, Any]:
        """
        Generate with function calling capability.
        
        Args:
            prompt: User prompt
            functions: List of function definitions
            model: Model identifier
            system_prompt: Optional system prompt
            temperature: Sampling temperature
            
        Returns:
            Response with potential function call
        """
        if not self.api_key:
            raise ValueError("OpenRouter API key not configured")
        
        model = model or settings.researcher_model
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "tools": [{"type": "function", "function": f} for f in functions]
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://research-assistant.app",
            "X-Title": "Multi-Agent Research Assistant"
        }
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers=headers,
                    json=payload
                )
                
                if response.status_code == 200:
                    data = response.json()
                    choice = data["choices"][0]
                    message = choice["message"]
                    
                    result = {
                        "content": message.get("content"),
                        "tool_calls": message.get("tool_calls"),
                        "usage": data.get("usage", {})
                    }
                    
                    return result
                else:
                    logger.error(f"LLM API error: {response.status_code}")
                    raise Exception(f"LLM API error: {response.status_code}")
                    
        except Exception as e:
            logger.error(f"LLM function call failed: {e}")
            raise
    
    async def extract_json(
        self,
        text: str,
        schema_description: str,
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract structured JSON from text.
        
        Args:
            text: Text to extract from
            schema_description: Description of expected JSON schema
            model: Model to use
            
        Returns:
            Extracted JSON data
        """
        prompt = f"""Extract structured information from the following text and return as JSON.

TEXT:
{text}

EXPECTED FORMAT:
{schema_description}

Return ONLY valid JSON, no other text."""
        
        result = await self.generate(
            prompt=prompt,
            model=model,
            temperature=0.1,
            max_tokens=2000
        )
        
        # Try to parse JSON
        try:
            # Find JSON in response
            import re
            json_match = re.search(r'[\{\[][\s\S]*[\}\]]', result)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
        
        return {"raw": result, "error": "Could not parse JSON"}
    
    async def analyze_text(
        self,
        text: str,
        analysis_type: str = "general",
        model: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze text for various purposes.
        
        Args:
            text: Text to analyze
            analysis_type: Type of analysis (general, sentiment, topics, entities)
            model: Model to use
            
        Returns:
            Analysis results
        """
        prompts = {
            "general": "Provide a comprehensive analysis of this text including main themes, key points, and notable insights.",
            "sentiment": "Analyze the sentiment of this text. Determine if it's positive, negative, or neutral, and identify emotional tones.",
            "topics": "Extract the main topics and themes from this text. List them in order of prominence.",
            "entities": "Extract named entities (people, organizations, locations, dates, etc.) from this text."
        }
        
        analysis_prompt = prompts.get(analysis_type, prompts["general"])
        
        prompt = f"""{analysis_prompt}

TEXT:
{text[:3000]}

Respond in JSON format with your analysis."""
        
        result = await self.generate(
            prompt=prompt,
            model=model,
            temperature=0.3,
            max_tokens=1500
        )
        
        return await self.extract_json(result, "Analysis results with relevant fields")


# Singleton instance
llm_tools = LLMTools()
