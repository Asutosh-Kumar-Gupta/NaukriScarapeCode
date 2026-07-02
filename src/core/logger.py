from __future__ import annotations

import sys

from loguru import logger

from src.core.config import get_settings


def setup_logger() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(sys.stderr, level="INFO", colorize=True,
               format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan> - <level>{message}</level>")
    logger.add(settings.log_path, level="DEBUG", rotation="10 MB", retention="7 days",
               format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}")


setup_logger()
