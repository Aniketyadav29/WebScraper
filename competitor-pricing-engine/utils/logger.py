"""
utils/logger.py
================
Centralised logging configuration for the Competitor Pricing Engine.

Provides a ``setup_logger()`` function that configures:
- Colourised, human-readable console output (via ``rich``)
- Structured plain-text file logging with automatic rotation

Call ``setup_logger()`` ONCE at the application entry point.
All other modules simply call ``logging.getLogger(__name__)``.

Author : Aniket Yadav | BBD
Version: 1.0.0
"""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from rich.logging import RichHandler

# ---------------------------------------------------------------------------
# Defaults (overridden by environment variables)
# ---------------------------------------------------------------------------
_LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO").upper()
_LOG_DIR: Path = Path("logs")
_LOG_FILE: str = "pricing_engine.log"
_MAX_BYTES: int = 10 * 1024 * 1024  # 10 MB per file
_BACKUP_COUNT: int = 5              # Keep last 5 rotated files


def setup_logger(
    level: str = _LOG_LEVEL,
    log_dir: Path = _LOG_DIR,
    log_file: str = _LOG_FILE,
) -> logging.Logger:
    """
    Configure the root logger with a Rich console handler and a
    rotating file handler.

    Call this function ONCE at the start of your application / script.
    Subsequent ``logging.getLogger(__name__)`` calls in any module will
    automatically inherit this configuration.

    Args:
        level   : Logging level string (``"DEBUG"``, ``"INFO"``, etc.).
        log_dir : Directory where log files are written.
        log_file: Name of the main log file.

    Returns:
        The configured root :class:`logging.Logger` instance.

    Example::

        from utils.logger import setup_logger
        setup_logger()
        logger = logging.getLogger(__name__)
        logger.info("Application started.")
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / log_file

    numeric_level = getattr(logging, level, logging.INFO)

    # ---- Rich Console Handler (colourised, human-readable) --------------
    console_handler = RichHandler(
        level=numeric_level,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        show_time=True,
        show_path=True,
        markup=True,
    )
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    # ---- Rotating File Handler (plain-text, structured) -----------------
    file_handler = RotatingFileHandler(
        filename=log_path,
        maxBytes=_MAX_BYTES,
        backupCount=_BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(
        logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    # ---- Root Logger Configuration --------------------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    # Prevent duplicate handlers if called more than once
    if not root_logger.handlers:
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)
    else:
        root_logger.handlers.clear()
        root_logger.addHandler(console_handler)
        root_logger.addHandler(file_handler)

    root_logger.info(
        "Logger initialised — level: %s, log file: %s", level, log_path
    )
    return root_logger
