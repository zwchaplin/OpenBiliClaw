"""Tests for logging setup."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from openbiliclaw.config import Config, LoggingConfig
from openbiliclaw.logging_setup import configure_logging


def test_configure_logging_creates_log_directory_and_file(tmp_path: Path) -> None:
    config = Config(
        logging=LoggingConfig(
            level="INFO",
            file_level="DEBUG",
            directory=str(tmp_path / "logs"),
            filename="openbiliclaw.log",
        )
    )

    configure_logging(config)
    logger = logging.getLogger("openbiliclaw.test")
    logger.info("hello from logging test")

    log_file = tmp_path / "logs" / "openbiliclaw.log"
    assert log_file.exists()
    assert "hello from logging test" in log_file.read_text(encoding="utf-8")


def test_configure_logging_replaces_existing_handlers(tmp_path: Path) -> None:
    config = Config(
        logging=LoggingConfig(
            level="INFO",
            file_level="DEBUG",
            directory=str(tmp_path / "logs"),
            filename="openbiliclaw.log",
        )
    )

    configure_logging(config)
    first_count = len(logging.getLogger().handlers)

    configure_logging(config)
    second_count = len(logging.getLogger().handlers)

    assert first_count == second_count


def test_configure_logging_uses_rotating_handler_when_enabled(tmp_path: Path) -> None:
    config = Config(
        logging=LoggingConfig(
            directory=str(tmp_path / "logs"),
            filename="app.log",
            max_file_size_mb=5,
            backup_count=2,
        )
    )

    configure_logging(config)
    file_handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)
    ]

    assert len(file_handlers) == 1
    handler = file_handlers[0]
    assert isinstance(handler, RotatingFileHandler)
    assert handler.maxBytes == 5 * 1024 * 1024
    assert handler.backupCount == 2


def test_configure_logging_disables_rotation_when_size_is_zero(tmp_path: Path) -> None:
    config = Config(
        logging=LoggingConfig(
            directory=str(tmp_path / "logs"),
            filename="app.log",
            max_file_size_mb=0,
            backup_count=3,
        )
    )

    configure_logging(config)
    file_handlers = [
        h for h in logging.getLogger().handlers if isinstance(h, logging.FileHandler)
    ]

    assert len(file_handlers) == 1
    handler = file_handlers[0]
    assert not isinstance(handler, RotatingFileHandler)


def test_configure_logging_rotates_oversized_existing_file(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "app.log"
    # Seed a 3 MB file so the 1 MB budget triggers cleanup on startup.
    log_file.write_bytes(b"A" * (3 * 1024 * 1024))

    config = Config(
        logging=LoggingConfig(
            directory=str(log_dir),
            filename="app.log",
            max_file_size_mb=1,
            backup_count=1,
        )
    )

    configure_logging(config)
    logging.getLogger("openbiliclaw.test").info("fresh line")

    assert (log_dir / "app.log.1").exists(), "oversized file should be rotated to .1"
    assert log_file.exists()
    # Fresh file should be tiny — the pre-existing 3 MB went into .1
    assert log_file.stat().st_size < 100 * 1024


def test_configure_logging_leaves_small_existing_file_intact(tmp_path: Path) -> None:
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / "app.log"
    log_file.write_text("earlier session line\n", encoding="utf-8")
    original_size = log_file.stat().st_size

    config = Config(
        logging=LoggingConfig(
            directory=str(log_dir),
            filename="app.log",
            max_file_size_mb=10,
            backup_count=1,
        )
    )

    configure_logging(config)

    assert not (log_dir / "app.log.1").exists()
    # Existing content preserved — startup should only rotate if oversized.
    assert log_file.stat().st_size >= original_size
