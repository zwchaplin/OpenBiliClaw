"""Tests for logging setup."""

import logging
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
