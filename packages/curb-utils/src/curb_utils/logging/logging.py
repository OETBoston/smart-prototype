import logging
from datetime import datetime
from logging import Logger, LogRecord
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.logging import RichHandler

DEFAULT_LOG_FILE = "logs/log-{day}.log"


class ContextFilter(logging.Filter):
    """Filter that adds context attribute to log records."""

    def __init__(self, manager: "LoggerManager") -> None:
        super().__init__()
        self.manager = manager

    def filter(self, record: LogRecord) -> bool:
        # Add context attribute to the record
        record.context = self.manager.context or record.name
        return True


class BufferedLogger:
    """Logger wrapper that queues messages and writes them on flush or destruction."""

    def __init__(self, logger: Logger) -> None:
        self.logger = logger
        self.queue: list[tuple[str, str]] = []

    def debug(self, message: str) -> None:
        """Queue a debug message."""
        self.queue.append(("debug", message))

    def info(self, message: str) -> None:
        """Queue an info message."""
        self.queue.append(("info", message))

    def warning(self, message: str) -> None:
        """Queue a warning message."""
        self.queue.append(("warning", message))

    def error(self, message: str) -> None:
        """Queue an error message."""
        self.queue.append(("error", message))

    def critical(self, message: str) -> None:
        """Queue a critical message."""
        self.queue.append(("critical", message))

    def flush(self) -> None:
        """Write all queued messages to the logger and clear the queue."""
        for level, message in self.queue:
            getattr(self.logger, level)(message)
        self.queue.clear()

    def __del__(self) -> None:
        """Flush messages when the object is destroyed."""
        self.flush()


class LoggerManager:
    """Singleton class that manages loggers and a shared console rich instance for."""

    _instance: Optional["LoggerManager"] = None
    _loggers: dict[str, Logger] = {}
    _console: Optional[Console] = None
    _default_log_file: Optional[Path] = None
    context: Optional[str] = None

    def __new__(cls) -> "LoggerManager":
        """Ensure only one instance of LoggerManager exists"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def get_console(self) -> Console:
        """Get the shared console instance."""
        if self._console is None:
            self._console = Console()
        return self._console

    def set_context(self, context: str) -> None:
        """Set the logging context. All logs will show this context name."""
        self.context = context

    def clear_context(self) -> None:
        """Clear the logging context, reverting to actual module names."""
        self.context = None

    def get_logger(
        self,
        name: str,
        log_file: Path | str | None = None,
        level: int = logging.INFO,
    ) -> Logger:
        """
        Get or create a logger. All loggers share the same console.

        Args:
            name: Logger name (typically __name__)
            log_file: Path to log file. If None, uses the default log file
                     (logs/log[day].log where [day] is the current date).
            level: Logging level

        Returns:
            Logger instance that shares the global console
        """
        if name in self._loggers:
            return self._loggers[name]

        # Set the default log file if not already set
        if self._default_log_file is None:
            if log_file is not None:
                self._default_log_file = Path(log_file)
            else:
                # Use default filename with current date
                day = datetime.today().strftime("%Y%m%d")
                self._default_log_file = Path(DEFAULT_LOG_FILE.format(day=day))

        # Determine which log file to use for this logger
        effective_log_file = (
            log_file if log_file is not None else self._default_log_file
        )

        console = self.get_console()
        logger = logging.getLogger(name)
        logger.setLevel(level)

        # Add context filter to include context in log records
        context_filter = ContextFilter(self)
        logger.addFilter(context_filter)

        # Rich screen handler
        rich_handler = RichHandler(
            console=console,
            rich_tracebacks=True,
            tracebacks_show_locals=True,
            show_time=True,
            show_path=True,
        )
        logger.addHandler(rich_handler)

        # File handler with custom format that uses %(context)s
        if effective_log_file is not None:
            effective_log_file = Path(effective_log_file)
            effective_log_file.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.FileHandler(effective_log_file, encoding="utf-8")
            file_handler.setFormatter(
                logging.Formatter(
                    fmt="%(asctime)s | %(levelname)-8s | %(context)s - %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S",
                )
            )
            logger.addHandler(file_handler)

        logger.propagate = False
        self._loggers[name] = logger
        return logger


# Convenience functions
_manager = LoggerManager()


def get_logger(
    name: str, log_file: Path | str | None = None, level: int = logging.INFO
) -> Logger:
    """Get a logger that shares the global console."""
    return _manager.get_logger(name, log_file, level)


def get_logger_aio(
    name: str, log_file: Path | str | None = None, level: int = logging.INFO
) -> BufferedLogger:
    """
    Get a buffered logger that queues messages and writes them on flush or destruction.

    The returned logger collects log messages in a queue and writes them when:
    - flush() is called explicitly
    - The object goes out of scope (automatic cleanup)

    Usage:
        logger = get_logger_aio(__name__)
        logger.info("This is queued")
        logger.info("This too")
        logger.flush()  # Both messages written now

    """
    logger = get_logger(name, log_file, level)
    return BufferedLogger(logger)


def get_console() -> Console:
    """Get the shared console instance."""
    return _manager.get_console()


def set_log_context(context: str) -> None:
    """Set the logging context. All logs will show this context name."""
    _manager.set_context(context)


def clear_log_context() -> None:
    """Clear the logging context, reverting to actual module names."""
    _manager.clear_context()
