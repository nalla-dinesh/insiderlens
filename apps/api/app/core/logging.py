"""structlog setup: pretty console in development, JSON in production.

Every log line automatically carries contextvars bound by RequestIDMiddleware
(request_id, method, path).
"""

import logging
import sys
from typing import Literal

import structlog


def configure_logging(environment: Literal["development", "production"] = "development") -> None:
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.dev.ConsoleRenderer(colors=True)
        if environment == "development"
        else structlog.processors.JSONRenderer()
    )

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        logger_factory=structlog.PrintLoggerFactory(sys.stdout),
        cache_logger_on_first_use=True,
    )

    # Keep chatty third-party loggers (uvicorn access, sqlalchemy) from drowning our JSON.
    logging.basicConfig(level=logging.WARNING, stream=sys.stdout, force=True)


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
