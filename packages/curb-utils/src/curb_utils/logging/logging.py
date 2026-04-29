import logging
from datetime import datetime
from logging import Logger
from pathlib import Path

from rich.console import Console
from rich.logging import RichHandler


def setup_logger(
    name: str,
    log_file: Path | str | None = None,
    level: int = logging.INFO,
    console: Console | None = None,
) -> tuple[logging.Logger, Console]:
    """
    Set up a logger that writes to both the screen (via Rich) and optionally a file.

    Args:
        name:      Logger name, typically __name__ of the calling module.
        log_file:  Path to log file. If None, file logging is disabled.
        level:     Logging level (default: INFO).
        console:   Existing Rich Console to use. If None, a new one is created.
                   Pass your Progress instance's console to keep them in sync.

    Returns:
        A (logger, console) tuple. Pass the console to your Rich Progress instance.

    Usage:
        log, console = setup_logger(__name__, log_file="app.log")
        log.info("Hello!")

        # With a Progress bar:
        with Progress(..., console=console) as progress:
            ...
    """
    console = console or Console()

    logger = logging.getLogger(name)

    # Avoid adding duplicate handlers if called multiple times
    if logger.handlers:
        return logger, console

    logger.setLevel(level)

    # --- Rich screen handler ---
    rich_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        tracebacks_show_locals=True,
        show_time=True,
        show_path=True,
    )
    logger.addHandler(rich_handler)

    # --- File handler ---
    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(
            logging.Formatter(
                fmt="%(asctime)s | %(levelname)-8s | %(name)s - %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
        logger.addHandler(file_handler)

    # Prevent log messages from propagating to the root logger
    logger.propagate = False

    return logger, console


def get_today(sep: str = "", include_time: bool = False) -> str:
    """
    Get the current date, optionally including time in HHMMSS format.
    """
    now = datetime.today()
    date_part = now.strftime(f"%Y{sep}%m{sep}%d")

    if include_time:
        time_part = now.strftime("%H%M%S")
        return f"{date_part}-{time_part}"

    return date_part


def log_list(logger: Logger, log_messages: list[tuple[str, str]]) -> None:
    """Log a list of collected messages.
    Each element must be a log level followed by a message"""
    for level, message in log_messages:
        getattr(logger, level)(message)
