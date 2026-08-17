"""
logging_config.py — Cấu hình logging cho API (console + file logs/api.log)

Sử dụng:
  from api.logging_config import get_logger
  logger = get_logger(__name__)
  logger.info(...)
"""

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LOG_DIR = PROJECT_ROOT / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "api.log"

_FORMAT = logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def get_logger(name: str) -> logging.Logger:
    """Lấy logger đã cấu hình sẵn (console + file, idempotent)."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(_FORMAT)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
