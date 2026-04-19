"""Central logging initialization for OpenBiliClaw."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
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


def _build_file_handler(
    log_file: object,  # Path, but typed loose to avoid import
    *,
    max_file_size_mb: int,
    backup_count: int,
    level: int,
) -> logging.Handler:
    """Return a rotating file handler when rotation is enabled, else a plain one.

    Rotation triggers when the active file reaches ``max_file_size_mb`` MB; at
    that point ``RotatingFileHandler`` moves it to ``<name>.1`` (older backups
    shift to ``.2``, ``.3``, ...) and older-than-``backup_count`` copies are
    deleted. Setting ``backup_count=1`` caps total disk usage at roughly
    ``2 * max_file_size_mb`` MB.
    """
    from pathlib import Path

    log_path = Path(str(log_file))

    if max_file_size_mb <= 0 or backup_count < 1:
        handler: logging.Handler = logging.FileHandler(log_path, encoding="utf-8")
    else:
        handler = RotatingFileHandler(
            log_path,
            maxBytes=max_file_size_mb * 1024 * 1024,
            backupCount=backup_count,
            encoding="utf-8",
        )

    handler.setLevel(level)
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    return handler


def _enforce_size_budget_once(log_file: object, max_file_size_mb: int) -> None:
    """Truncate an oversized log on startup so we don't resume 7 GB files.

    ``RotatingFileHandler`` only rotates on *new* writes, so an already-oversized
    file keeps growing until the next rollover boundary. On startup we proactively
    rotate once if the existing file is already over budget — this is the
    "清理超过 1G 的历史日志" behavior the user asked for.
    """
    from pathlib import Path

    if max_file_size_mb <= 0:
        return

    log_path = Path(str(log_file))
    if not log_path.exists():
        return

    try:
        size = log_path.stat().st_size
    except OSError:
        return

    if size <= max_file_size_mb * 1024 * 1024:
        return

    # Preserve at most one "before cleanup" snapshot so debugging is still
    # possible, then delete further backups. Matches RotatingFileHandler naming
    # (<name>.1 is the freshest backup).
    snapshot = log_path.with_name(log_path.name + ".1")
    try:
        if snapshot.exists():
            snapshot.unlink()
        log_path.rename(snapshot)
    except OSError:
        # Fall back to truncation if rename fails (e.g. cross-device).
        try:
            log_path.unlink()
        except OSError:
            return


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

    _enforce_size_budget_once(log_file, config.logging.max_file_size_mb)
    file_handler = _build_file_handler(
        log_file,
        max_file_size_mb=config.logging.max_file_size_mb,
        backup_count=config.logging.backup_count,
        level=file_level,
    )

    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)
