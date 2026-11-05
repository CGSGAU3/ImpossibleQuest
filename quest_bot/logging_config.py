import logging
from logging.handlers import RotatingFileHandler
import os


def configure_logging():
    handler = RotatingFileHandler(
        os.getenv("LOG_PATH", "quest.log"), maxBytes=2_000_000,
        backupCount=3, encoding="utf-8",
    )
    logging.basicConfig(
        level=logging.INFO, handlers=[logging.StreamHandler(), handler],
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True,
    )
