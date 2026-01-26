"""
Logging Middleware
Logs incoming requests and response times.
"""

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
import time
from datetime import datetime

from app.utils.logging import logger


async def logging_middleware(request: Request, call_next):
    """
    Request/response logging middleware.
    Logs request details and response times for monitoring.
    """
    start_time = time.time()
    
    # Log request
    logger.info(
        f"Request: {request.method} {request.url.path} "
        f"| Client: {request.client.host if request.client else 'unknown'}"
    )
    
    # Process request
    response = await call_next(request)
    
    # Calculate response time
    process_time = (time.time() - start_time) * 1000
    
    # Log response
    logger.info(
        f"Response: {request.method} {request.url.path} "
        f"| Status: {response.status_code} "
        f"| Time: {process_time:.2f}ms"
    )
    
    # Add response time header
    response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
    
    return response


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Logging middleware as a class-based implementation.
    """
    
    async def dispatch(self, request: Request, call_next):
        start_time = time.time()
        
        logger.info(
            f"Request: {request.method} {request.url.path}"
        )
        
        response = await call_next(request)
        
        process_time = (time.time() - start_time) * 1000
        
        logger.info(
            f"Response: {response.status_code} | Time: {process_time:.2f}ms"
        )
        
        response.headers["X-Process-Time"] = f"{process_time:.2f}ms"
        
        return response
