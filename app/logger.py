"""Logging setup for the automation application."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any


def setup_logging(config: dict[str, Any]) -> logging.Logger:
    """Configure application logging from the ``logging`` config section."""
    logging_config = config.get("logging", {})

    level_name = str(logging_config.get("level", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    log_format = "%(asctime)s %(levelname)s %(message)s"
    date_format = "%Y-%m-%d %H:%M:%S"

    logger = logging.getLogger("youtube_teams_automation")
    logger.setLevel(level)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(log_format, datefmt=date_format)

    if logging_config.get("log_to_console", True):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

    if logging_config.get("log_to_file", True):
        log_file = Path(logging_config.get("file", "logs/app.log"))
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
