import requests
from typing import Optional
from src.core.logger import setup_logger
from config.settings import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

logger = setup_logger("TelegramNotifier")


class TelegramNotifier:
    """Envía notificaciones de trading a Telegram usando Bot API."""

    BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    def __init__(self):
        self.chat_id = TELEGRAM_CHAT_ID
        self.enabled = bool(TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID)
        
        if not self.enabled:
            logger.warning("[WARNING] Telegram no configurado. Verifica TELEGRAM_BOT_TOKEN y CHAT_ID en .env")

    def send_message(self, message: str, parse_mode: str = "HTML") -> bool:
        """Envía mensaje HTML formateado a Telegram."""
        if not self.enabled:
            return False
            
        url = f"{self.BASE_URL}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": message,
            "parse_mode": parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code == 200:
                return True
            else:
                logger.error(f"[ERROR] Telegram API error {response.status_code}: {response.text}")
                return False
        except Exception as e:
            logger.error(f"[ERROR] Fallo enviando Telegram: {e}")
            return False

    def notify_signal(self, signal_data: dict) -> bool:
        """Notificación especializada para señales de trading."""
        direction = signal_data.get('direction', 'UNKNOWN')
        symbol = signal_data.get('symbol', 'EURUSD')
        entry = signal_data.get('entry_price', 0)
        sl = signal_data.get('stop_loss', 0)
        tp = signal_data.get('take_profit', 0)
        strategy = signal_data.get('strategy', 'EMA_Trend')
        strength = signal_data.get('strength', 0)
        
        # Emoji según dirección
        emoji = "🟢" if direction == "BUY" else "🔴"
        
        msg = (
            f"<b>{emoji} NUEVA SEÑAL {direction}</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Par:</b> {symbol}\n"
            f"<b>Estrategia:</b> {strategy}\n"
            f"<b>Fuerza:</b> {strength:.0%}\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Entrada:</b> <code>{entry:.5f}</code>\n"
            f"<b>SL:</b> <code>{sl:.5f}</code>\n"
            f"<b>TP:</b> <code>{tp:.5f}</code>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<i>⏰ {signal_data.get('timestamp', '')}</i>"
        )
        
        return self.send_message(msg)

    def notify_execution(self, exec_data: dict) -> bool:
        """Notificación de ejecución confirmada."""
        status = exec_data.get('status', 'UNKNOWN')
        ticket = exec_data.get('ticket', 0)
        price = exec_data.get('price_filled', 0)
        lots = exec_data.get('volume_filled', 0)
        
        emoji = "✅" if status == "FILLED" else "❌"
        
        msg = (
            f"<b>{emoji} ORDEN EJECUTADA</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"<b>Ticket:</b> <code>{ticket}</code>\n"
            f"<b>Precio:</b> <code>{price:.5f}</code>\n"
            f"<b>Lotes:</b> {lots}\n"
            f"<b>Estado:</b> {status}\n"
            f"━━━━━━━━━━━━━━━━━━━━"
        )
        
        return self.send_message(msg)


# Instancia singleton global
telegram_notifier = TelegramNotifier()