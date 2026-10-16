"""Logging for jamfpy: the ``jamfpy`` logger hierarchy, ``configure_logging()`` and its two formats.

Every tenant logs through three children of the ``jamfpy`` logger: ``jamfpy.{tenant}-auth``,
``jamfpy.{tenant}-pro`` and ``jamfpy.{tenant}-clc``. They carry no handlers and propagate, so output goes wherever
the application sends it. ``jamfpy`` itself has only a ``NullHandler`` until ``configure_logging()`` is called, so
an application that configures no logging sees nothing (not even Python's last-resort WARNING output).
"""

import copy
import datetime
import json
import logging
import sys
from collections.abc import Mapping
from typing import Any, TextIO

from .redaction import redact

LOGGER_NAME = "jamfpy"
TEXT_FORMAT = "%(asctime)s [%(levelname)s] (%(name)s): %(message)s"
# Compatibility aliases: both names were public in this module on 2.x, so code that imported them keeps working.
DEFAULT_FORMAT = TEXT_FORMAT
DEFAULT_LEVEL = logging.INFO
# The structured fields API.do() passes as ``extra=``; the JSON format emits each one only when a record has it.
STRUCTURED_FIELDS = ("method", "url", "status", "duration_ms", "attempt")
# Longest header or body rendering a DEBUG line carries, in characters.
MAX_LOGGED_CHARS = 1024

_PREFIX = f"{LOGGER_NAME}."

logging.getLogger(LOGGER_NAME).addHandler(logging.NullHandler())


def sender(name: str) -> str:
    """A logger name without the ``jamfpy.`` prefix: ``jamfpy.acme-pro`` -> ``acme-pro``."""
    return name.removeprefix(_PREFIX)


def tenant_logger(tenant: str, kind: str, level: int) -> logging.Logger:
    """The ``jamfpy.{tenant}-{kind}`` child logger, set to ``level``; it keeps no handlers and propagates."""
    logger = logging.getLogger(f"{_PREFIX}{tenant}-{kind}")
    logger.setLevel(level)
    return logger


class TextFormatter(logging.Formatter):
    """``%(asctime)s [%(levelname)s] (%(name)s): %(message)s`` with the ``jamfpy.`` prefix dropped from the name."""

    def __init__(self) -> None:
        super().__init__(TEXT_FORMAT)

    def format(self, record: logging.LogRecord) -> str:
        # A copy, because the same record goes on to other handlers (the root's, pytest's caplog) with its real name.
        shown = copy.copy(record)
        shown.name = sender(record.name)
        return super().format(shown)


class JsonFormatter(logging.Formatter):
    """One JSON object per line: ``ts``, ``level``, ``sender``, ``message`` and any structured fields the record has."""

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()
        if record.exc_info:
            # Folded into the message so every line keeps the same keys; json.dumps escapes the newlines.
            message = f"{message}\n{self.formatException(record.exc_info)}"

        created = datetime.datetime.fromtimestamp(record.created, tz=datetime.timezone.utc)
        payload: dict[str, Any] = {
            "ts": created.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            "level": record.levelname,
            "sender": sender(record.name),
            "message": message,
        }
        for field in STRUCTURED_FIELDS:
            if field in record.__dict__:
                payload[field] = record.__dict__[field]
        return json.dumps(payload, default=str)


class _ConfiguredHandler(logging.StreamHandler[TextIO]):
    """The handler ``configure_logging()`` installs; its own type, so a later call replaces only this one."""


_FORMATTERS: dict[str, type[logging.Formatter]] = {"text": TextFormatter, "json": JsonFormatter}


def configure_logging(level: int = logging.INFO, fmt: str = "text", stream: TextIO | None = None) -> logging.Handler:
    """Send jamfpy's logs to ``stream`` (``sys.stdout`` when ``None``) at ``level`` and above, as ``fmt``.

    ``fmt`` is ``"text"`` (``2026-10-15 14:34:41,571 [INFO] (acme-pro): GET https://... -> 200 (84 ms)``) or
    ``"json"`` (one object per line, see ``JsonFormatter``); anything else raises ``ValueError``. Installs one
    handler on the ``jamfpy`` logger and sets both its level and the logger's. Calling it again replaces the
    handler it installed before; handlers added by anyone else are left alone. Returns the new handler.

    ``level`` is the output threshold. A tenant only emits what its own loggers let through, which
    ``Tenant(log_level=...)`` sets (INFO by default), so DEBUG output needs both set to DEBUG.
    """
    formatter_type = _FORMATTERS.get(fmt)
    if formatter_type is None:
        raise ValueError(f"fmt must be one of {', '.join(repr(name) for name in _FORMATTERS)}, got {fmt!r}")

    root = logging.getLogger(LOGGER_NAME)
    for existing in [h for h in root.handlers if isinstance(h, _ConfiguredHandler)]:
        root.removeHandler(existing)
        existing.close()

    # Looked up per call rather than bound as a default, so a sys.stdout replaced after import is the one used.
    handler = _ConfiguredHandler(stream if stream is not None else sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(formatter_type())
    root.addHandler(handler)
    root.setLevel(level)
    return handler


def render_headers(headers: Mapping[str, Any], safe_mode: bool) -> str:
    """Headers for a DEBUG line: JSON, redacted under ``safe_mode``, truncated to ``MAX_LOGGED_CHARS``."""
    shown = redact(headers) if safe_mode else dict(headers)
    return truncate(json.dumps(shown, default=str))


def render_body(body: object, safe_mode: bool) -> str:
    """A request or response body for a DEBUG line: redacted under ``safe_mode``, truncated to ``MAX_LOGGED_CHARS``."""
    if body is None:
        return "<none>"
    if not isinstance(body, (str, bytes)):
        # A file or generator body is streamed by requests; reading it here would leave nothing to send.
        return f"<streamed {type(body).__name__} body, not logged>"
    # Truthiness rather than ``body in ("", b"")``: comparing bytes with str raises BytesWarning under ``python -bb``.
    if not body:
        return "<none>"
    if safe_mode:
        return truncate(redact(body))
    return truncate(body.decode("utf-8", errors="replace") if isinstance(body, bytes) else body)


def truncate(text: str, limit: int = MAX_LOGGED_CHARS) -> str:
    """``text`` cut to ``limit`` characters, with ``… (truncated, N chars)`` appended when it was longer."""
    if len(text) <= limit:
        return text
    return f"{text[:limit]}… (truncated, {len(text)} chars)"
