import logging

LOG_FORMAT = '%(asctime)s %(levelname)s %(name)s %(message)s'


def configure_logging(level: str = 'INFO') -> None:
    """Configure root logging once for CLI and pipeline runs."""
    numeric_level = getattr(logging, level.upper(), None)
    if not isinstance(numeric_level, int):
        raise ValueError(f'Unsupported log level: {level}')
    logging.basicConfig(level=numeric_level, format=LOG_FORMAT, force=True)
