import logging
import logging.config
from pathlib import Path

LOG_FILE_PATH = Path(__file__).resolve().parents[2] / "logs" / "app.log"
_LOGGING_CONFIGURED = False


def configure_logging(log_level: str) -> None:
    global _LOGGING_CONFIGURED

    if _LOGGING_CONFIGURED:
        return

    LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)

    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "standard": {
                    "format": "%(asctime)s | %(levelname)s | %(name)s | %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "standard",
                    "level": log_level.upper(),
                },
                "file": {
                    "class": "logging.FileHandler",
                    "filename": str(LOG_FILE_PATH),
                    "formatter": "standard",
                    "level": log_level.upper(),
                    "encoding": "utf-8",
                },
            },
            "root": {
                "handlers": ["console", "file"],
                "level": log_level.upper(),
            },
            "loggers": {
                "app": {
                    "handlers": ["console", "file"],
                    "level": log_level.upper(),
                    "propagate": False,
                },
                "uvicorn": {
                    "handlers": ["console", "file"],
                    "level": log_level.upper(),
                    "propagate": False,
                },
                "uvicorn.error": {
                    "handlers": ["console", "file"],
                    "level": log_level.upper(),
                    "propagate": False,
                },
                "uvicorn.access": {
                    "handlers": ["console", "file"],
                    "level": log_level.upper(),
                    "propagate": False,
                },
            },
        }
    )

    _LOGGING_CONFIGURED = True
