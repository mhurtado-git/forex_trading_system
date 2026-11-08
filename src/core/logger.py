import logging
import colorlog
from config.settings import LOG_DIR, LOGGING_CONFIG

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(getattr(logging, LOGGING_CONFIG['level']))
        
        # Console handler with colors
        console_handler = colorlog.StreamHandler()
        console_handler.setFormatter(colorlog.ColoredFormatter(
            '%(log_color)s%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            log_colors={
                'DEBUG': 'cyan',
                'INFO': 'green',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bold_red'
            }
        ))
        logger.addHandler(console_handler)
        
        # File handler
        file_handler = logging.FileHandler(LOG_DIR / 'trading.log')
        file_handler.setFormatter(logging.Formatter(LOGGING_CONFIG['format']))
        logger.addHandler(file_handler)
    
    return logger