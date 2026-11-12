import random
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import logging
import time
import MetaTrader5 as mt5

logger = logging.getLogger("NewsFilter")

# ✅ CONFIGURACIÓN PARAMETRIZABLE (Fácil de mantener)
NEWS_CONFIG = {
    'url': 'https://es.investing.com/economic-calendar/',
    'headers': {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Accept-Language': 'es-ES,es;q=0.9'
    },
    'timeout_seconds': 10,          # Máximo tiempo de espera
    'max_retries': 2,               # Intentos antes de dar por fallida la petición
    'retry_delay': 3,               # Segundos entre intentos
    'selectors': {                  # Selectores CSS (fáciles de actualizar si cambia la web)
        'row': '.js-event-item',
        'time': '.first.left.time',
        'event': '.left.event',
        'impact': '.left:nth-child(4)', 
    },
    'impact_mapping': {             # Mapeo de texto/iconos a niveles
        'Alto': 'HIGH',
        'Medio': 'MEDIUM', 
        'Bajo': 'LOW'
    }
}

# ✅ CALENDARIO MANUAL DE RESPALDO (ACTUALIZAR CADA DOMINGO)
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
}

class RobustNewsFetcher:
    """Obtiene noticias de Investing.com con validación y fallback."""
    
    def __init__(self, config=None):
        self.config = config or NEWS_CONFIG
        
    def fetch_calendar(self, days_ahead=3):
        """Obtiene calendario con reintentos y fallback automático."""
        for attempt in range(self.config['max_retries']):
            try:
                logger.info(f"[NEWS] Intento {attempt+1}/{self.config['max_retries']} conectando a Investing...")
                
                response = requests.get(
                    self.config['url'], 
                    headers=self.config['headers'],
                    timeout=self.config['timeout_seconds']
                )
                
                if response.status_code != 200:
                    raise Exception(f"HTTP {response.status_code}")
                    
                if 'captcha' in response.text.lower() or 'verify' in response.text.lower():
                    raise Exception("Detectado CAPTCHA/Bloqueo")
                
                soup = BeautifulSoup(response.text, 'html.parser')
                events = []
                
                for row in soup.select(self.config['selectors']['row']):
                    try:
                        time_str = row.select_one(self.config['selectors']['time']).get_text(strip=True)
                        event_name = row.select_one(self.config['selectors']['event']).get_text(strip=True)
                        impact_text = row.select_one(self.config['selectors']['impact']).get_text(strip=True)
                        
                        impact_level = self.config['impact_mapping'].get(impact_text, 'UNKNOWN')
                        
                        if impact_level == 'HIGH':
                            event_time = self._parse_time(time_str, days_ahead)
                            events.append({
                                'time': event_time,
                                'name': event_name,
                                'impact': impact_level,
                                'source': 'INVESTING_WEB'
                            })
                    except Exception:
                        continue
                
                if len(events) > 0:
                    logger.info(f"[NEWS] ✅ Éxito Web: {len(events)} eventos cargados")
                    return events
                    
            except Exception as e:
                logger.warning(f"[NEWS] Intento {attempt+1} falló: {e}")
                if attempt < self.config['max_retries'] - 1:
                    time.sleep(self.config['retry_delay'])
        
        logger.error("[NEWS] ❌ Web falló. Usando FALLBACK LOCAL.")
        return self._get_local_fallback()
    
    def _get_local_fallback(self):
        """Convierte diccionario local a lista de eventos estandarizada."""
        events = []
        for date_str, data in LOCAL_NEWS_CALENDAR.items():
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M')
                events.append({
                    'time': dt,
                    'name': data['event'],
                    'impact': data['impact'],
                    'countries': data.get('countries', []),
                    'source': 'LOCAL_MANUAL'
                })
            except Exception:
                continue
        return events
    
    def _parse_time(self, time_str, days_ahead):
        """Parsea formatos de tiempo de investing.com."""
        try:
            today = datetime.now().date()
            if "Mañana" in time_str:
                target_date = today + timedelta(days=1)
                time_part = time_str.replace("Mañana", "").strip()
            else:
                target_date = today
                time_part = time_str.strip()
            
            hour, minute = map(int, time_part.split(':'))
            return datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
        except:
            return datetime.now() + timedelta(hours=1)


class LocalNewsFilter:
    """Filtro principal que usa RobustNewsFetcher internamente."""
    
    def __init__(self, risk_minutes=30, protect_minutes=15):
        self.risk_minutes = risk_minutes
        self.protect_minutes = protect_minutes
        self.fetcher = RobustNewsFetcher()
        self.news_events = self.fetcher.fetch_calendar()
        
    def refresh_calendar(self):
        """Permite recargar noticias sin reiniciar el bot (ej: cada domingo)."""
        logger.info("[NEWS] 🔄 Recargando calendario económico...")
        self.news_events = self.fetcher.fetch_calendar()
        
    def is_safe_to_trade(self, symbol):
        """Verifica si es seguro operar basado en noticias próximas."""
        now = datetime.now()
        
        currency_map = {
            'EURUSD': ['EUR', 'USD', 'EU', 'US'],
            'AUDUSD': ['AUD', 'USD', 'AU', 'US'],
            'USDJPY': ['USD', 'JPY', 'US', 'JP'],
            'GBPUSD': ['GBP', 'USD', 'GB', 'US'],
            'XAUUSD': ['USD', 'US']
        }
        
        relevant_keywords = currency_map.get(symbol, [])
        if not relevant_keywords:
            return True

        for news in self.news_events:
            time_diff = abs((news['time'] - now).total_seconds()) / 60
            
            if time_diff <= self.risk_minutes:
                name_lower = news['name'].lower()
                countries = news.get('countries', [])
                
                # Verificar si alguna palabra clave está en el nombre o países
                is_relevant = any(kw.lower() in name_lower for kw in relevant_keywords) or \
                              any(c in countries for c in relevant_keywords)
                              
                if is_relevant:
                    source_tag = news.get('source', 'UNKNOWN')
                    logger.warning(f"[NEWS BLOCK] {symbol} bloqueado por {news['name']} ({source_tag}) en {news['time']}")
                    return False
                    
        return True

    def check_open_positions_risk(self, positions, executor):
        """Gestiona riesgo de noticias para posiciones YA ABIERTAS."""
        now = datetime.now()
        for pos in positions:
            ticket = pos.ticket if hasattr(pos, 'ticket') else pos.get('ticket', 0)
            symbol = pos.symbol if hasattr(pos, 'symbol') else pos.get('symbol', '')
            
            if not self.is_safe_to_trade(symbol):
                logger.warning(f"[NEWS RISK] Cerrando {symbol} #{ticket} por noticia inminente.")
                executor.close_position(ticket)