"""Utility functions for logging."""

import logging
import sys
from typing import Optional
from datetime import datetime


def setup_logging(level: int = logging.INFO, log_file: Optional[str] = None):
    """Setup application logging."""
    setup_logger(level=level, log_file=log_file)


class CustomFormatter(logging.Formatter):
    """Custom formatter with colors for console output."""
    
    grey = "\x1b[38;20m"
    yellow = "\x1b[33;20m"
    red = "\x1b[31;20m"
    bold_red = "\x1b[31;1m"
    green = "\x1b[32;20m"
    blue = "\x1b[34;20m"
    reset = "\x1b[0m"
    
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    FORMATS = {
        logging.DEBUG: grey + format_str + reset,
        logging.INFO: green + format_str + reset,
        logging.WARNING: yellow + format_str + reset,
        logging.ERROR: red + format_str + reset,
        logging.CRITICAL: bold_red + format_str + reset
    }
    
    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno)
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)


def setup_logger(
    name: str = "research_assistant",
    level: int = logging.INFO,
    log_file: Optional[str] = None
) -> logging.Logger:
    """
    Set up and configure logger.
    
    Args:
        name: Logger name
        level: Logging level
        log_file: Optional file path for file logging
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Avoid adding handlers multiple times
    if logger.handlers:
        return logger
    
    # Console handler with custom formatter
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(CustomFormatter())
    logger.addHandler(console_handler)
    
    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        file_handler.setFormatter(file_formatter)
        logger.addHandler(file_handler)
    
    return logger


# Create default logger instance
logger = setup_logger()


def get_logger(name: str = "research_assistant") -> logging.Logger:
    """Get logger by name."""
    return logging.getLogger(name)


def log_agent_activity(
    agent_name: str,
    action: str,
    details: Optional[str] = None
):
    """Log agent activity with consistent format."""
    message = f"[{agent_name}] {action}"
    if details:
        message += f" - {details}"
    logger.info(message)


def log_api_call(
    api_name: str,
    endpoint: str,
    status_code: int,
    response_time_ms: float
):
    """Log API call with performance metrics."""
    logger.info(
        f"API Call: {api_name} | {endpoint} | "
        f"Status: {status_code} | Time: {response_time_ms:.2f}ms"
    )


def log_research_progress(
    session_id: str,
    phase: str,
    progress: int,
    message: Optional[str] = None
):
    """Log research progress update."""
    log_msg = f"Session {session_id[:8]}... | Phase: {phase} | Progress: {progress}%"
    if message:
        log_msg += f" | {message}"
    logger.info(log_msg)
