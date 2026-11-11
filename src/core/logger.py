import logging
import colorlog
from logging.handlers import RotatingFileHandler  # <--- AGREGAR ESTE IMPORT
from config.settings import LOG_DIR, LOGGING_CONFIG

def setup_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    
    if not logger.handlers:
        logger.setLevel(getattr(logging, LOGGING_CONFIG['level']))
        
        # 1. Console handler with colors (SE MANTIENE IGUAL)
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
        
        # 2. File handler CON ROTACIÓN AUTOMÁTICA (CAMBIO AQUÍ)
        # maxBytes=5MB: Cuando llega a 5MB, crea uno nuevo
        # backupCount=3: Guarda los últimos 3 archivos viejos (trading.log.1, .2, .3)
        file_handler = RotatingFileHandler(
            LOG_DIR / 'trading.log', 
            maxBytes=5 * 1024 * 1024, 
            backupCount=3, 
            encoding='utf-8'
        )
        file_handler.setFormatter(logging.Formatter(LOGGING_CONFIG['format']))
        logger.addHandler(file_handler)
    
    return logger