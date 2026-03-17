import logging
import colorlog


def setup_logging(level: int = logging.INFO) -> None:
    """
    Set up colorful logging with meaningful colors for different parts of the log line.
    """
    # Create a colored formatter with different colors for each part
    formatter = colorlog.ColoredFormatter(
        '%(thin_white)s%(asctime)s%(reset)s - '
        '%(cyan)s%(name)s%(reset)s - '
        '%(log_color)s%(levelname)s%(reset)s - '
        '%(message)s',
        datefmt='%Y-%m-%d %H:%M:%S',
        log_colors={
            'DEBUG': 'light_blue',
            'INFO': 'green',
            'WARNING': 'yellow',
            'ERROR': 'red',
            'CRITICAL': 'bold_red',
        },
        reset=True,
        style='%'
    )
    
    # Create a console handler with the colored formatter
    handler = colorlog.StreamHandler()
    handler.setFormatter(formatter)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Remove any existing handlers to avoid duplicates
    root_logger.handlers = []
    
    # Add our colored handler
    root_logger.addHandler(handler)

