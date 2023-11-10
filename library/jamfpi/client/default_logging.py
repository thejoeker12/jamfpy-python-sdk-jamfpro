"""
Default logging module for this library
"""

import logging


def default_logger(
        logger_name,
        logging_level: int = None,
        logging_format: str = None
    ):
    """Returns default logger configuration for JamfAPI Client"""
    logging_level = logging_level or 30
    logging_format = logging_format or '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    logger = logging.getLogger(logger_name)
    logger.setLevel(logging_level)

    ch = logging.StreamHandler()
    ch.setLevel(logging_level)

    formatter = logging.Formatter(logging_format)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    return logger
