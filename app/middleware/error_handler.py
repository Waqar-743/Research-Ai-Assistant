"""
Error Handler Middleware
Handles exceptions and formats error responses.
"""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
import traceback

from app.utils.logging import logger


async def error_handler_middleware(request: Request, call_next):
    """
    Global error handling middleware.
    Catches all unhandled exceptions and returns formatted error responses.
    """
    try:
        response = await call_next(request)
        return response
        
    except Exception as e:
        # Log the error with full traceback
        logger.error(f"Unhandled exception: {e}")
        logger.error(traceback.format_exc())
        
        # Return a generic error response
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "Internal server error",
                "error": str(e) if logger.level <= 10 else "An unexpected error occurred"
            }
        )


class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Error handler as a class-based middleware.
    Alternative implementation using BaseHTTPMiddleware.
    """
    
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
            
        except Exception as e:
            logger.error(f"Unhandled exception: {e}")
            logger.error(traceback.format_exc())
            
            return JSONResponse(
                status_code=500,
                content={
                    "success": False,
                    "message": "Internal server error",
                    "error": "An unexpected error occurred"
                }
            )
