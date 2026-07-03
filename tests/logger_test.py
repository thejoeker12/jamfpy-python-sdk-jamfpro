"""Unit tests for new_logger."""
# pylint: disable=missing-function-docstring
import logging

from jamfpy.client.logger import new_logger


def test_returns_logger_at_default_info_level():
    logger = new_logger("logger_default_name")
    assert isinstance(logger, logging.Logger)
    assert logger.level == logging.INFO


def test_custom_level_is_applied():
    logger = new_logger("logger_debug_name", level=logging.DEBUG)
    assert logger.level == logging.DEBUG


def test_short_names_are_padded_to_six_chars():
    # Padding aligns terminal output; a 4-char name gains two trailing spaces.
    logger = new_logger("ulog")
    assert logger.name == "ulog  "


def test_long_names_are_not_padded():
    logger = new_logger("logger_long_name")
    assert logger.name == "logger_long_name"


def test_attaches_a_stream_handler():
    logger = new_logger("logger_handler_name")
    assert any(isinstance(h, logging.StreamHandler) for h in logger.handlers)


def test_repeated_calls_stack_handlers_quirk():
    # KNOWN QUIRK: every call adds a fresh StreamHandler for the same name,
    # so repeated construction duplicates log lines.
    name = "logger_dup_name"
    new_logger(name)
    logger = new_logger(name)
    assert len(logger.handlers) == 2
