"""
Search Tools for the Researcher Agent.
Integrates with SerpAPI, Google, NewsAPI, ArXiv, PubMed, and Wikipedia.
"""

import asyncio
import httpx
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import feedparser
from urllib.parse import urlencode, quote_plus
import xml.etree.ElementTree as ET

from app.config import settings
from app.utils.logging import logger


class SearchTools:
    """Collection of search tools for gathering information from multiple sources."""
    
    def __init__(self):
        self.timeout = httpx.Timeout(30.0, connect=10.0)
        self.headers = {
            "User-Agent": "Multi-Agent-Research-Assistant/1.0"
        }
    
    async def search_all(
        self,
        query: str,
        max_results_per_source: int = 20
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Search all available sources in parallel.
        
        Args:
            query: Search query string
            max_results_per_source: Maximum results from each source
            
        Returns:
            Dictionary with results from each source
        """
        logger.info(f"Starting parallel search for: {query}")
        
        tasks = [
            self.web_search(query, max_results_per_source),  # Uses SerpAPI or Google
            self.newsapi_search(query, max_results_per_source),
            self.arxiv_search(query, max_results_per_source),
            self.pubmed_search(query, max_results_per_source),
            self.wikipedia_search(query)
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            "google": results[0] if not isinstance(results[0], Exception) else [],
            "newsapi": results[1] if not isinstance(results[1], Exception) else [],
            "arxiv": results[2] if not isinstance(results[2], Exception) else [],
            "pubmed": results[3] if not isinstance(results[3], Exception) else [],
            "wikipedia": results[4] if not isinstance(results[4], Exception) else []
        }
    
    async def web_search(
        self,
        query: str,
        num_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search the web using SerpAPI (preferred) or Google Custom Search API.
        
        Args:
            query: Search query
            num_results: Number of results to return
            
        Returns:
            List of search results with title, url, snippet
        """
        # Try SerpAPI first (preferred)
        if settings.serpapi_key:
            return await self.serpapi_search(query, num_results)
        
        # Fallback to Google Custom Search
        if settings.google_api_key and settings.google_search_engine_id:
            return await self.google_search(query, num_results)
        
        logger.warning("No web search API configured (SerpAPI or Google)")
        return []
    
    async def serpapi_search(
        self,
        query: str,
        num_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search using SerpAPI (Google Search Results API).
        
        Args:
            query: Search query
            num_results: Number of results to return
            
        Returns:
            List of search results with title, url, snippet
        """
        if not settings.serpapi_key:
            logger.warning("SerpAPI key not configured")
            return []
        
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {
                    "api_key": settings.serpapi_key,
                    "engine": "google",
                    "q": query,
                    "num": min(num_results, 100),
                    "hl": "en",
                    "gl": "us"
                }
                
                response = await client.get(
                    "https://serpapi.com/search",
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    # Get organic results
                    organic_results = data.get("organic_results", [])
                    
                    for item in organic_results[:num_results]:
                        results.append({
                            "title": item.get("title", ""),
                            "url": item.get("link", ""),
                            "snippet": item.get("snippet", ""),
                            "displayed_link": item.get("displayed_link", ""),
                            "source_type": "web",
                            "api_source": "serpapi",
                            "retrieved_at": datetime.utcnow().isoformat()
                        })
                    
                    # Also include knowledge graph if available
                    knowledge_graph = data.get("knowledge_graph", {})
                    if knowledge_graph:
                        kg_result = {
                            "title": knowledge_graph.get("title", "Knowledge Graph Result"),
                            "url": knowledge_graph.get("website", knowledge_graph.get("source", {}).get("link", "")),
                            "snippet": knowledge_graph.get("description", ""),
                            "source_type": "knowledge_graph",
                            "api_source": "serpapi",
                            "retrieved_at": datetime.utcnow().isoformat()
                        }
                        if kg_result["url"]:
                            results.insert(0, kg_result)
                    
                else:
                    logger.error(f"SerpAPI search error: {response.status_code} - {response.text}")
                    
            logger.info(f"SerpAPI search returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"SerpAPI search failed: {e}")
            
        return results[:num_results]
    
    async def google_search(
        self,
        query: str,
        num_results: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Search using Google Custom Search API.
        
        Args:
            query: Search query
            num_results: Number of results to return (max 100)
            
        Returns:
            List of search results with title, url, snippet
        """
        if not settings.google_api_key or not settings.google_search_engine_id:
            logger.warning("Google API credentials not configured")
            return []
        
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Google allows max 10 results per request
                for start in range(1, min(num_results + 1, 101), 10):
                    params = {
                        "key": settings.google_api_key,
                        "cx": settings.google_search_engine_id,
                        "q": query,
                        "start": start,
                        "num": min(10, num_results - len(results))
                    }
                    
                    response = await client.get(
                        "https://www.googleapis.com/customsearch/v1",
                        params=params
                    )
                    
                    if response.status_code == 200:
                        data = response.json()
                        items = data.get("items", [])
                        
                        for item in items:
                            results.append({
                                "title": item.get("title", ""),
                                "url": item.get("link", ""),
                                "snippet": item.get("snippet", ""),
                                "source_type": "web",
                                "api_source": "google",
                                "retrieved_at": datetime.utcnow().isoformat()
                            })
                    else:
                        logger.error(f"Google search error: {response.status_code}")
                        break
                        
                    if len(results) >= num_results:
                        break
                        
            logger.info(f"Google search returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"Google search failed: {e}")
            
        return results[:num_results]
    
    async def newsapi_search(
        self,
        query: str,
        num_results: int = 20,
        language: str = "en",
        sort_by: str = "relevancy"
    ) -> List[Dict[str, Any]]:
        """
        Search using NewsAPI for latest news articles.
        
        Args:
            query: Search query
            num_results: Number of results
            language: Language code
            sort_by: Sort order (relevancy, publishedAt, popularity)
            
        Returns:
            List of news articles
        """
        if not settings.newsapi_key:
            logger.warning("NewsAPI key not configured")
            return []
        
        results = []
        
        try:
            # Limit to last 30 days to avoid stale/irrelevant results
            from_date = (datetime.utcnow() - timedelta(days=30)).strftime('%Y-%m-%d')
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                params = {
                    "q": query,
                    "language": language,
                    "sortBy": sort_by,
                    "pageSize": min(num_results, 100),
                    "from": from_date,
                    "apiKey": settings.newsapi_key
                }
                
                response = await client.get(
                    "https://newsapi.org/v2/everything",
                    params=params
                )
                
                if response.status_code == 200:
                    data = response.json()
                    articles = data.get("articles", [])
                    
                    for article in articles:
                        results.append({
                            "title": article.get("title", ""),
                            "url": article.get("url", ""),
                            "snippet": article.get("description", ""),
                            "content": article.get("content", ""),
                            "author": article.get("author"),
                            "source_name": article.get("source", {}).get("name"),
                            "published_at": article.get("publishedAt"),
                            "source_type": "news",
                            "api_source": "newsapi",
                            "retrieved_at": datetime.utcnow().isoformat()
                        })
                else:
                    logger.error(f"NewsAPI error: {response.status_code} - {response.text}")
                    
            logger.info(f"NewsAPI returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"NewsAPI search failed: {e}")
            
        return results
    
    async def arxiv_search(
        self,
        query: str,
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search ArXiv for academic papers.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of academic papers with metadata
        """
        results = []
        
        try:
            search_query = quote_plus(query)
            url = f"{settings.arxiv_api_base}?search_query=all:{search_query}&start=0&max_results={max_results}"
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers)
                
                if response.status_code == 200:
                    # Parse Atom feed
                    feed = feedparser.parse(response.text)
                    
                    for entry in feed.entries:
                        # Extract authors
                        authors = [author.get("name", "") for author in entry.get("authors", [])]
                        
                        # Get PDF link
                        pdf_link = ""
                        for link in entry.get("links", []):
                            if link.get("type") == "application/pdf":
                                pdf_link = link.get("href", "")
                                break
                        
                        results.append({
                            "title": entry.get("title", "").replace("\n", " "),
                            "url": entry.get("link", ""),
                            "pdf_url": pdf_link,
                            "snippet": entry.get("summary", "").replace("\n", " ")[:500],
                            "authors": authors,
                            "published_at": entry.get("published"),
                            "updated_at": entry.get("updated"),
                            "categories": [tag.get("term") for tag in entry.get("tags", [])],
                            "arxiv_id": entry.get("id", "").split("/abs/")[-1],
                            "source_type": "academic",
                            "api_source": "arxiv",
                            "retrieved_at": datetime.utcnow().isoformat()
                        })
                else:
                    logger.error(f"ArXiv search error: {response.status_code}")
                    
            logger.info(f"ArXiv search returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"ArXiv search failed: {e}")
            
        return results
    
    async def pubmed_search(
        self,
        query: str,
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Search PubMed for medical/scientific research.
        
        Args:
            query: Search query
            max_results: Maximum number of results
            
        Returns:
            List of medical research papers
        """
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Step 1: Search for IDs
                search_params = {
                    "db": "pubmed",
                    "term": query,
                    "retmax": max_results,
                    "retmode": "json",
                    "sort": "relevance"
                }
                
                search_response = await client.get(
                    f"{settings.pubmed_api_base}/esearch.fcgi",
                    params=search_params
                )
                
                if search_response.status_code != 200:
                    logger.error(f"PubMed search error: {search_response.status_code}")
                    return results
                
                search_data = search_response.json()
                id_list = search_data.get("esearchresult", {}).get("idlist", [])
                
                if not id_list:
                    return results
                
                # Step 2: Fetch details for each ID
                fetch_params = {
                    "db": "pubmed",
                    "id": ",".join(id_list),
                    "retmode": "xml"
                }
                
                fetch_response = await client.get(
                    f"{settings.pubmed_api_base}/efetch.fcgi",
                    params=fetch_params
                )
                
                if fetch_response.status_code == 200:
                    # Parse XML response
                    root = ET.fromstring(fetch_response.text)
                    
                    for article in root.findall(".//PubmedArticle"):
                        try:
                            medline = article.find(".//MedlineCitation")
                            article_data = medline.find(".//Article") if medline is not None else None
                            
                            if article_data is None:
                                continue
                            
                            # Extract title
                            title_elem = article_data.find(".//ArticleTitle")
                            title = title_elem.text if title_elem is not None else ""
                            
                            # Extract abstract
                            abstract_elem = article_data.find(".//Abstract/AbstractText")
                            abstract = abstract_elem.text if abstract_elem is not None else ""
                            
                            # Extract authors
                            authors = []
                            for author in article_data.findall(".//Author"):
                                last_name = author.find("LastName")
                                first_name = author.find("ForeName")
                                if last_name is not None:
                                    name = last_name.text
                                    if first_name is not None:
                                        name = f"{first_name.text} {name}"
                                    authors.append(name)
                            
                            # Extract PMID
                            pmid_elem = medline.find(".//PMID")
                            pmid = pmid_elem.text if pmid_elem is not None else ""
                            
                            # Extract publication date
                            pub_date = article_data.find(".//PubDate")
                            year = pub_date.find("Year").text if pub_date is not None and pub_date.find("Year") is not None else ""
                            
                            results.append({
                                "title": title,
                                "url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                                "snippet": abstract[:500] if abstract else "",
                                "authors": authors,
                                "pmid": pmid,
                                "published_at": year,
                                "source_type": "academic",
                                "api_source": "pubmed",
                                "retrieved_at": datetime.utcnow().isoformat()
                            })
                        except Exception as e:
                            logger.warning(f"Error parsing PubMed article: {e}")
                            continue
                            
            logger.info(f"PubMed search returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"PubMed search failed: {e}")
            
        return results
    
    async def wikipedia_search(
        self,
        query: str,
        num_results: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search Wikipedia for general knowledge.
        
        Args:
            query: Search query
            num_results: Number of results
            
        Returns:
            List of Wikipedia articles with summaries
        """
        results = []
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                # Search for pages
                search_params = {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "srlimit": num_results,
                    "format": "json"
                }
                
                search_response = await client.get(
                    "https://en.wikipedia.org/w/api.php",
                    params=search_params
                )
                
                if search_response.status_code != 200:
                    return results
                
                search_data = search_response.json()
                pages = search_data.get("query", {}).get("search", [])
                
                # Get summaries for each page
                for page in pages:
                    title = page.get("title", "")
                    
                    # Get page summary
                    summary_response = await client.get(
                        f"{settings.wikipedia_api_base}/page/summary/{quote_plus(title)}"
                    )
                    
                    if summary_response.status_code == 200:
                        summary_data = summary_response.json()
                        
                        results.append({
                            "title": summary_data.get("title", title),
                            "url": summary_data.get("content_urls", {}).get("desktop", {}).get("page", ""),
                            "snippet": summary_data.get("extract", ""),
                            "description": summary_data.get("description", ""),
                            "source_type": "wikipedia",
                            "api_source": "wikipedia",
                            "retrieved_at": datetime.utcnow().isoformat()
                        })
                        
            logger.info(f"Wikipedia search returned {len(results)} results")
            
        except Exception as e:
            logger.error(f"Wikipedia search failed: {e}")
            
        return results
    
    async def fetch_full_content(self, url: str) -> Optional[str]:
        """
        Fetch full content from a URL.
        
        Args:
            url: URL to fetch
            
        Returns:
            Extracted text content or None
        """
        try:
            from bs4 import BeautifulSoup
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.get(url, headers=self.headers, follow_redirects=True)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.text, 'lxml')
                    
                    # Remove script and style elements
                    for script in soup(["script", "style", "nav", "footer", "header"]):
                        script.decompose()
                    
                    # Get text
                    text = soup.get_text(separator='\n', strip=True)
                    
                    # Clean up whitespace
                    lines = [line.strip() for line in text.splitlines() if line.strip()]
                    return '\n'.join(lines)
                    
        except Exception as e:
            logger.error(f"Failed to fetch content from {url}: {e}")
            
        return None


# Singleton instance
search_tools = SearchTools()
