# src/core/local_news_filter.py
from datetime import datetime, timezone
from src.core.logger import setup_logger

logger = setup_logger("LocalNewsFilter")

# 📅 CALENDARIO ECONÓMICO LOCAL (ACTUALIZAR CADA DOMINGO)
# Formato: 'YYYY-MM-DD HH:MM': {'event': 'Nombre', 'countries': ['US', 'EUR'], 'impact': 'HIGH'}
# Consulta investing.com/economic-calendar cada domingo y actualiza esta lista.

LOCAL_NEWS_CALENDAR = {
    # MARTES 10 NOV - HOY (CPI/PPI ya pasaron o están activos)
    '2026-11-10 13:30': {'event': 'US PPI m/m', 'countries': ['US'], 'impact': 'HIGH'},
    '2026-11-10 13:30': {'event': 'US Core PPI m/m', 'countries': ['US'], 'impact': 'HIGH'},

    # MIÉRCOLES 11 NOV - Desempleo Semanal
    '2026-11-11 13:30': {'event': 'US Initial Jobless Claims', 'countries': ['US'], 'impact': 'HIGH'},

    # JUEVES 12 NOV - Ventas Minoristas (Retail Sales) ⚠️ CRÍTICO
    '2026-11-12 13:30': {'event': 'US Retail Sales m/m', 'countries': ['US'], 'impact': 'HIGH'},
    '2026-11-12 13:30': {'event': 'US Core Retail Sales m/m', 'countries': ['US'], 'impact': 'HIGH'},
    '2026-11-12 14:15': {'event': 'US Industrial Production m/m', 'countries': ['US'], 'impact': 'HIGH'},

    # VIERNES 13 NOV - Sentimiento y Vivienda
    '2026-11-13 13:30': {'event': 'US Philly Fed Manufacturing Index', 'countries': ['US'], 'impact': 'HIGH'},
    '2026-11-13 13:30': {'event': 'US Building Permits', 'countries': ['US'], 'impact': 'HIGH'},
    '2026-11-13 15:00': {'event': 'US Michigan Consumer Sentiment', 'countries': ['US'], 'impact': 'HIGH'},
}
    
    # Agrega más eventos según necesites...


# Mapeo de símbolos a países/divisas relevantes
SYMBOL_COUNTRY_MAP = {
    "EURUSD": ["US", "EUR"],
    "AUDUSD": ["US", "AUD"],
    "XAUUSD": ["US"]
}

class LocalNewsFilter:
    def __init__(self, risk_minutes=30, protect_minutes=15):
        self.risk_minutes = int(risk_minutes)
        self.protect_minutes = int(protect_minutes)
        
    def is_safe_to_trade(self, symbol: str) -> bool:
        """Verifica si es seguro abrir nuevas posiciones."""
        relevant_countries = SYMBOL_COUNTRY_MAP.get(symbol, [])
        now_utc = datetime.now(timezone.utc)
        
        for time_str, event_data in LOCAL_NEWS_CALENDAR.items():
            try:
                event_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                diff_minutes = abs((now_utc - event_time).total_seconds() / 60)
                
                # Solo bloquear si es ALTO impacto y está dentro de la ventana de riesgo
                if diff_minutes <= self.risk_minutes and event_data['impact'] == 'HIGH':
                    country_match = any(c in event_data['countries'] for c in relevant_countries)
                    if country_match:
                        logger.warning(
                            f"[LOCAL NEWS] BLOQUEADO {symbol}: {event_data['event']} "
                            f"en {int(diff_minutes)} min."
                        )
                        return False
            except Exception:
                continue
                
        return True
    
    def check_open_positions_risk(self, positions, executor):
        """Protege posiciones abiertas ante noticias inminentes."""
        if not positions:
            return
            
        now_utc = datetime.now(timezone.utc)
        
        for pos in positions:
            symbol = pos.get('symbol', '') if isinstance(pos, dict) else pos.symbol
            ticket = pos.get('ticket', 0) if isinstance(pos, dict) else pos.ticket
            profit = pos.get('profit', 0) if isinstance(pos, dict) else pos.profit
            sl = pos.get('sl', 0) if isinstance(pos, dict) else pos.sl
            price_open = pos.get('price_open', 0) if isinstance(pos, dict) else pos.price_open
            pos_type = pos.get('type', 0) if isinstance(pos, dict) else pos.type
            
            relevant_countries = SYMBOL_COUNTRY_MAP.get(symbol, [])
            
            for time_str, event_data in LOCAL_NEWS_CALENDAR.items():
                try:
                    event_time = datetime.strptime(time_str, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
                    minutes_until = (event_time - now_utc).total_seconds() / 60
                    
                    # Solo actuar si la noticia es FUTURA y está en zona de protección
                    if 0 < minutes_until <= self.protect_minutes and event_data['impact'] == 'HIGH':
                        country_match = any(c in event_data['countries'] for c in relevant_countries)
                        if country_match and profit > 0:
                            logger.warning(
                                f"[LOCAL PROTECT]  Noticia {event_data['event']} en {int(minutes_until)} min "
                                f"para {symbol} #{ticket}"
                            )
                            
                            pip_offset = 0.0005 if 'JPY' not in symbol else 0.05
                            new_sl = price_open + pip_offset if pos_type == 0 else price_open - pip_offset
                            
                            is_buy = pos_type == 0
                            if (is_buy and new_sl > sl) or (not is_buy and (sl == 0 or new_sl < sl)):
                                executor.modify_position(ticket, sl=new_sl)
                                logger.info(f"[LOCAL PROTECT]  SL movido a BE+5pips en {symbol} #{ticket}")
                                
                except Exception:
                    continue