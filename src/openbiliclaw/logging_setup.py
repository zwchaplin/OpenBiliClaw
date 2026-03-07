"""Central logging initialization for OpenBiliClaw."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from rich.logging import RichHandler

if TYPE_CHECKING:
    from openbiliclaw.config import Config


def _coerce_level(level_name: str) -> int:
    """Convert a level name to a logging level."""
    level = logging.getLevelName(level_name.upper())
    if isinstance(level, int):
        return level
    return logging.INFO


def configure_logging(config: Config, console_level_override: str | None = None) -> None:
    """Configure root logging for console and file output."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)
        handler.close()

    console_level = _coerce_level(console_level_override or config.logging.level)
    file_level = _coerce_level(config.logging.file_level)

    console_handler = RichHandler(rich_tracebacks=True, show_path=False)
    console_handler.setLevel(console_level)
    console_handler.setFormatter(logging.Formatter("%(message)s"))

    log_file = config.logging.file_path
    log_file.parent.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(file_level)
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
