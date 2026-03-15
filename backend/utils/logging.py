import logging
import sys
from config import LOG_LEVEL, APP_NAME


def setup_logging():
    level = getattr(logging, LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)
    return logging.getLogger(APP_NAME)
