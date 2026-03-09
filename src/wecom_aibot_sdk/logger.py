"""Logger module"""

from datetime import datetime
from typing import Any, Protocol


class Logger(Protocol):
    """Logger interface protocol"""

    def debug(self, message: str, *args: Any) -> None: ...
    def info(self, message: str, *args: Any) -> None: ...
    def warn(self, message: str, *args: Any) -> None: ...
    def error(self, message: str, *args: Any) -> None: ...


class DefaultLogger:
    """Default logger implementation with timestamps"""

    def _format(self, level: str, message: str, *args: Any) -> str:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_msg = message % args if args else message
        return f"[{timestamp}] [{level}] {formatted_msg}"

    def debug(self, message: str, *args: Any) -> None:
        print(self._format("DEBUG", message, *args))

    def info(self, message: str, *args: Any) -> None:
        print(self._format("INFO", message, *args))

    def warn(self, message: str, *args: Any) -> None:
        print(self._format("WARN", message, *args))

    def error(self, message: str, *args: Any) -> None:
        print(self._format("ERROR", message, *args))
