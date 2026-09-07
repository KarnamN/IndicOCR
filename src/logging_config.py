"""
Logging Configuration Module
Centralized logging setup for the PDF to EPUB converter
"""
import logging
from logging.handlers import RotatingFileHandler
import sys
from pathlib import Path
import config

# converter.log rotation cap: 20MB per file, 5 backups kept (100MB max total).
# Previously an unbounded plain FileHandler — the log had grown to 17.9MB with
# no ceiling at all across the app's lifetime.
LOG_MAX_BYTES = 20 * 1024 * 1024
LOG_BACKUP_COUNT = 5

def setup_logging(level=None):
    """Global logging configuration"""
    log_level = level or getattr(config, 'LOG_LEVEL', 'INFO')
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Configure root logger
    root = logging.getLogger()
    root.setLevel(numeric_level)

    # Clear existing handlers to avoid duplicates
    if root.handlers:
        for handler in root.handlers[:]:
            root.removeHandler(handler)

    # File handler with thread info (rotating — see LOG_MAX_BYTES/LOG_BACKUP_COUNT above)
    try:
        file_handler = RotatingFileHandler(
            config.LOG_FILE, encoding='utf-8',
            maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT
        )
        file_formatter = logging.Formatter(
            '%(asctime)s - [%(threadName)s] - %(name)s - %(levelname)s - %(message)s'
        )
        file_handler.setFormatter(file_formatter)
        root.addHandler(file_handler)
    except Exception as e:
        print(f"Warning: Could not initialize file logging: {e}")

    # Console handler with simpler format
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    console_handler.setFormatter(console_formatter)

    root.addHandler(console_handler)

    # Werkzeug's per-request access log ("GET /socket.io/... 200") is routed
    # through this same root logger/file — quiet it to WARNING so routine HTTP
    # traffic doesn't mix into converter.log alongside actual conversion events.
    logging.getLogger('werkzeug').setLevel(logging.WARNING)

    return root

def get_logger(name: str) -> logging.Logger:
    """Get a logger instance"""
    return logging.getLogger(name)

# Auto-initialize on import
setup_logging()

