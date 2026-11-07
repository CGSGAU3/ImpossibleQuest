import logging
from logging.handlers import RotatingFileHandler
import os


def configure_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL должен быть DEBUG, INFO, WARNING, ERROR или CRITICAL")
    handlers = [logging.StreamHandler()]
    try:
        handlers.append(RotatingFileHandler(
            os.getenv("LOG_PATH", "quest.log"), maxBytes=2_000_000,
            backupCount=3, encoding="utf-8",
        ))
    except OSError:
        file_unavailable = True
    else:
        file_unavailable = False
    logging.basicConfig(
        level=logging.INFO, handlers=handlers,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True,
    )
    logger = logging.getLogger("quest_bot")
    logger.setLevel(level)
    if file_unavailable:
        logging.getLogger().warning("Файл журнала недоступен, сообщения идут в stderr")
