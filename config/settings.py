import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / 'data'
LOG_DIR = BASE_DIR / 'logs'

# Crear directorios si no existen
DATA_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

# MT5 Configuration
MT5_CONFIG = {
    'login': int(os.getenv('MT5_LOGIN', 0)),
    'password': os.getenv('MT5_PASSWORD', ''),
    'server': os.getenv('MT5_SERVER', ''),
    'path': os.getenv('MT5_PATH', '')
}

# Database Configuration
DB_TYPE = os.getenv('DB_TYPE', 'sqlite')
if DB_TYPE == 'sqlite':
    DATABASE_URL = f"sqlite:///{DATA_DIR}/trading.db"
else:
    DATABASE_URL = (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD')}"
        f"@{os.getenv('DB_HOST')}:{os.getenv('DB_PORT')}/{os.getenv('DB_NAME')}"
    )

# Trading Configuration
TRADING_CONFIG = {
    'default_risk_percent': float(os.getenv('DEFAULT_RISK_PERCENT', 1.0)),
    'max_daily_loss_percent': float(os.getenv('MAX_DAILY_LOSS_PERCENT', 3.0)),
    'max_open_positions': int(os.getenv('MAX_OPEN_POSITIONS', 5)),
    'min_risk_reward_ratio': float(os.getenv('MIN_RISK_REWARD_RATIO', 1.5))
}

# Supported Pairs
SUPPORTED_PAIRS = [
    'EURUSD', 'GBPUSD', 'USDJPY', 'USDCHF',
    'AUDUSD', 'NZDUSD', 'USDCAD',
    'EURGBP', 'EURJPY', 'GBPJPY'
]

# Timeframes
TIMEFRAMES = {
    'M1': 1, 'M5': 5, 'M15': 15, 'M30': 30,
    'H1': 60, 'H4': 240, 'D1': 1440
}

# Logging Configuration
LOGGING_CONFIG = {
    'level': os.getenv('LOG_LEVEL', 'INFO'),
    'file': LOG_DIR / os.getenv('LOG_FILE', 'trading.log'),
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
}

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")