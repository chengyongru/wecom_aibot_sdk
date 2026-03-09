"""Logger module"""

import logging
from typing import Any, Protocol


class Logger(Protocol):
    """Logger interface protocol"""

    def debug(self, message: str, *args: Any) -> None: ...
    def info(self, message: str, *args: Any) -> None: ...
    def warn(self, message: str, *args: Any) -> None: ...
    def error(self, message: str, *args: Any) -> None: ...


class DefaultLogger:
    """Default logger using Python's built-in logging module"""

    def __init__(self, level: int = logging.WARNING):
        """
        Initialize logger with specified level

        Args:
            level: Log level (logging.DEBUG, INFO, WARNING, ERROR, CRITICAL)
                   Defaults to WARNING
        """
        self._logger = logging.getLogger("wecom_aibot_sdk")
        self._logger.setLevel(level)

        # Add handler only if not already configured
        if not self._logger.handlers:
            handler = logging.StreamHandler()
            handler.setLevel(level)
            formatter = logging.Formatter(
                "%(asctime)s [%(levelname)s] %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S"
            )
            handler.setFormatter(formatter)
            self._logger.addHandler(handler)

    def set_level(self, level: int) -> None:
        """
        Set log level

        Args:
            level: Log level (logging.DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self._logger.setLevel(level)
        for handler in self._logger.handlers:
            handler.setLevel(level)

    def debug(self, message: str, *args: Any) -> None:
        self._logger.debug(message, *args)

    def info(self, message: str, *args: Any) -> None:
        self._logger.info(message, *args)

    def warn(self, message: str, *args: Any) -> None:
        self._logger.warning(message, *args)

    def error(self, message: str, *args: Any) -> None:
        self._logger.error(message, *args)
