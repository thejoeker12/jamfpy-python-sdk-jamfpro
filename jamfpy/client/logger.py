"""
Default logging module for this library
"""

import logging
import sys

DEFAULT_LEVEL = logging.DEBUG
DEFAULT_FORMAT = '%(asctime)s [%(levelname)s] (%(name)s): %(message)s'

def get_logger(
        name,
        format: str = DEFAULT_FORMAT,
        level: int = DEFAULT_LEVEL,
    ) -> logging.Logger:
    """
    Compartmentalised logger init
    """

    logger = logging.getLogger(name)

    logger.setLevel(level)

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)

    formatter = logging.Formatter(format)
    ch.setFormatter(formatter)

    logger.addHandler(ch)

    # This standardises the name length so the terminal output is aligned.
    # There is definitely a more elegant algorithm for appending spaces.
    if len(logger.name) < 6:
        for _ in range(6 - len(logger.name)):
            logger.name = logger.name + " "

    return logger
