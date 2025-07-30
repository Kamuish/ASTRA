"""Setup the logger, handling terminal and disk output."""

import os
import sys

from loguru import logger


def setup_ASTRA_logger(
    storage_path: str,
    log_to_terminal: bool = True,
    terminal_log_level: str = "DEBUG",
    write_to_file: bool = True,
    append_to_file: bool = True,
) -> None:
    """Setups the logger of ASTRA.

    Args:
        storage_path (str): FOlder in which the logger should be stored
        log_to_terminal (bool, optional): If True, logs to terminal. Defaults to True.
        terminal_log_level (str, optional): Log level of terminal. Defaults to "DEBUG".
        write_to_file (bool, optional): If True, write logs to disk. Defaults to True.
        append_to_file (bool, optional): If True, append to file, rather than creating a new one. Defaults to True.

    """
    logger.enable("ASTRA")
    logger.complete()

    logger.remove()

    logger.level("DEBUG", color="<fg #d0d3d4>")
    logger.level("INFO", color="<fg #28b463>")
    logger.level("WARNING", color="<fg #f1c40f>")
    logger.level("CRITICAL", color="<fg #e74c3c>")

    fmt = "{time:YYYY-MM-DDTHH:mm:ss} - {name} - {level} - {message}"
    if log_to_terminal:
        logger.add(
            sys.stdout,
            level=terminal_log_level,
            colorize=True,
            format="{time:YYYY-MM-DDTHH:mm:ss} - <level>{level:8s}</> - <c>{name}</> - {message}",
        )
        # but we do want to see the values, so I don't really care about this!
        logger.add(sys.stderr, level="ERROR", format=fmt)

    if not write_to_file:
        logger.warning("Not storing logs to disk")
        return

    logger.add(
        os.path.join(storage_path, "ASTRA.log"),
        level="DEBUG",
        format=fmt,
        enqueue=True,
        filter="ASTRA",
        backtrace=False,
        diagnose=True,
        mode="a" if append_to_file else "w",
    )

    return
