"""Structured logging configuration using JSON format."""

import logging
import sys
from pythonjsonlogger import jsonlogger
from app.config import settings


def setup_logging() -> logging.Logger:
    """
    Configure structured JSON logging for the application.

    Returns:
        logging.Logger: Configured logger instance
    """
    logger = logging.getLogger("trader_bot")
    logger.setLevel(getattr(logging, settings.log_level.upper()))

    # Remove existing handlers
    logger.handlers = []

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, settings.log_level.upper()))

    # Create JSON formatter
    formatter = jsonlogger.JsonFormatter(
        fmt="%(asctime)s %(name)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S"
    )
    handler.setFormatter(formatter)

    # Add handler to logger
    logger.addHandler(handler)

    return logger


# Global logger instance
logger = setup_logging()
