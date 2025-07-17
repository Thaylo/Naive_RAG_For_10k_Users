import logging
import logging.handlers
import os
from datetime import datetime


def setup_logger(service_name: str, log_level: str = "INFO") -> logging.Logger:
    """
    Setup a logger with rotating file handler and console output
    
    Args:
        service_name: Name of the service for log identification
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR)
    
    Returns:
        Configured logger instance
    """
    # Create logs directory if it doesn't exist
    # Use local logs directory when not in Docker container
    log_dir = os.environ.get("LOG_DIR", "./logs")
    os.makedirs(log_dir, exist_ok=True)
    
    # Create logger
    logger = logging.getLogger(service_name)
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Remove existing handlers to avoid duplicates
    logger.handlers.clear()
    
    # Console handler with detailed format
    console_handler = logging.StreamHandler()
    console_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)
    
    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        filename=os.path.join(log_dir, f"{service_name}.log"),
        maxBytes=10 * 1024 * 1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_format = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(funcName)s() - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_format)
    logger.addHandler(file_handler)
    
    # Log startup message
    logger.info(f"Logger initialized for {service_name}")
    logger.info(f"Log level: {log_level}")
    logger.info(f"Log directory: {log_dir}")
    
    return logger


def log_request(logger: logging.Logger, method: str, endpoint: str, **kwargs):
    """Helper function to log API requests"""
    extra_info = " ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"REQUEST: {method} {endpoint} {extra_info}")


def log_response(logger: logging.Logger, method: str, endpoint: str, status_code: int, **kwargs):
    """Helper function to log API responses"""
    extra_info = " ".join([f"{k}={v}" for k, v in kwargs.items()])
    logger.info(f"RESPONSE: {method} {endpoint} status={status_code} {extra_info}")


def log_error(logger: logging.Logger, error: Exception, context: str = ""):
    """Helper function to log errors with context"""
    logger.error(f"ERROR in {context}: {type(error).__name__}: {str(error)}", exc_info=True)