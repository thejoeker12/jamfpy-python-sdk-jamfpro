"""
Default logging module for this library
"""

import logging


def get_logger(
        name,
        level: int = None,
        format: str = None,
        config: str = None
    ):
    """
    Returns default logger configuration for JamfAPI Client
    Prioritises Config over individual values
    Defaults to default values in either context
    """

    DEFAULT_LEVEL = 30
    DEFAULT_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'

    if config:
        level = config["logging_level"] or DEFAULT_LEVEL
        format = config["logging_format"] or DEFAULT_FORMAT
    elif not config:
        level = level or DEFAULT_LEVEL
        format = format or DEFAULT_FORMAT

    active_loggers = list(logging.root.manager.loggerDict.keys())
    if name not in active_loggers:
        pass
    elif name in active_loggers:
        tnt, mode, increment = name.split("-", maxsplit=2)
        increment = int(increment)
        increment += 1
        name = f"{tnt}-{mode}-{increment}"
       
    print(name)
    print(level)

    logger = logging.getLogger(name)
    print(logger.handlers)
    if not logger.handlers:
        logger.setLevel(level)

        ch = logging.StreamHandler()
        ch.setLevel(level)

        formatter = logging.Formatter(format)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    return logger
