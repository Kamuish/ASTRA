"""Setup the logger, handling terminal and disk output."""

import sys

from loguru import logger
from pathlib import Path

# Keep a reference to ASTRA's sink IDs so we can remove them later if needed
_AST_SINKS = []
_AST_INITIALIZED = False

# Default logger (can be reconfigured later)
astra_logger = logger.bind(module="ASTRA")
logger.disable("ASTRA")


def setup_ASTRA_logger(
    storage_path=None,
    level="INFO",
    log_to_terminal=True,
    write_to_file=True,
    append_to_file=True,
):
    """Configure ASTRA's logger dynamically.

    Parameters
    ----------
    log_path : str or Path or None
        Path to the log file. If None, file logging is skipped.
    level : str
        Minimum level to log ("DEBUG", "INFO", "WARNING", etc.)
    console : bool
        Whether to also log to stdout.
    """
    global _AST_INITIALIZED, _AST_SINKS

    if _AST_INITIALIZED:
        # Clean up previous sinks (safe for reconfiguration)
        for sink_id in _AST_SINKS:
            logger.remove(sink_id)
        _AST_SINKS.clear()

    # Define filter so only ASTRA messages appear
    def astra_filter(record):
        return record["extra"].get("module") == "ASTRA"

    astra_logger = logger.bind(module="ASTRA")
    logger.enable("ASTRA")
    # Optional console logging

    if log_to_terminal:
        _AST_SINKS.append(
            astra_logger.add(
                sys.stdout,
                level=level,
                filter=astra_filter,
                format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> {name} <level>{message}</level>",
            )
        )

    # Optional file logging
    if storage_path is not None and write_to_file:
        storage_path = Path(storage_path)
        _AST_SINKS.append(
            astra_logger.add(
                (storage_path / "ASTRA.log").as_posix(),
                level=level,
                filter=astra_filter,
                format="{time:YYYY-MM-DD HH:mm:ss} | {name} {level} | {message}",
                enqueue=True,
                mode="a" if append_to_file else "w",
            )
        )

    _AST_INITIALIZED = True
    return astra_logger
