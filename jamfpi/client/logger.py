"""
Default logging module for this library
"""

import logging

DEFAULT_LEVEL = 20
DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

def get_logger(
        name,
        level: int = None,
        log_format: str = None,
        config: str = None
    ) -> logging.Logger:
    """
    Returns default logger configuration for JamfAPI Client
    Prioritises Config over individual values
    Defaults to default values in either context
    """

    # // TODO Probably move these values to default config


    if config:
        level = config["logging_level"] or DEFAULT_LEVEL
        log_format = config["logging_format"] or DEFAULT_FORMAT
    elif not config:
        level = level or DEFAULT_LEVEL
        log_format = log_format or DEFAULT_FORMAT

    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(level)

        ch = logging.StreamHandler()
        ch.setLevel(level)

        formatter = logging.Formatter(log_format)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger
