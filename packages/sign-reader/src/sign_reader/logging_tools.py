import logging
from datetime import datetime

import dummylog


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


def get_logger() -> logging.Logger:
    """
    Return a logger instance.
    """
    return dummylog.DummyLog(log_name=f"sign-reader-{get_today()}").logger
