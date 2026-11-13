import time
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, time as TimeClass
import time as sleep_time
import os

# Imports del sistema
from src.trading.broker_mt5 import mt5_connector
from src.data.data_fetcher import DataFetcher
from src.analysis.indicators import TechnicalIndicators
from src.analysis.signals import SignalGenerator
from src.risk.calculator import RiskCalculator, RiskValidationResult
from src.trading.order_executor import ExecutionStatus, OrderExecutor  # ✅ Import unificado
from src.notifications.telegram_bot import telegram_notifier
from src.core.logger import setup_logger
from src.data.database import db_manager 
from src.core.local_news_filter import LocalNewsFilter

logger = setup_logger("MainTrader")

# Inicializar tabla de trades al arrancar
db_manager.create_trade_log_table()

# ✅ INICIALIZACIÓN DEL FILTRO DE NOTICIAS ROBUSTO (Web + Fallback Local)
local_news_filter = LocalNewsFilter(
    risk_minutes=int(os.getenv("NEWS_RISK_MINUTES", 30)),
    protect_minutes=int(os.getenv("NEWS_PROTECT_MINUTES", 15))
)

# Variable para controlar la actualización semanal (evita recargas múltiples el mismo día)
last_calendar_refresh_week = None

# ✅ CONFIGURACIÓN DE HORARIOS OPERATIVOS PERMANENTES (Hora Colombia)
TRADING_HOURS = {
    "EURUSD": {"start": 2, "end": 17},   # 02:00 - 17:00 (Londres + NY)
    "AUDUSD": {"start": 19, "end": 16},  # 19:00 - 16:00 (Sydney/Tokio/Londres/NY) *Cruza medianoche*
    "USDJPY": {"start": 3, "end": 20}    # 03:00 - 20:00 (Londres + NY)
}

# ✅ VENTANA DE SILENCIO: Minutos antes del cierre donde NO se abren nuevas posiciones
PRE_CLOSE_BUFFER_MINUTES = 15 

# CONFIGURACIÓN MULTI-PAR
ACTIVE_PAIRS = {
    "EURUSD": {"strategy_func": SignalGenerator.generate_all_signals},
    "AUDUSD": {"strategy_func": SignalGenerator.aud_trend_strategy},
    # ✅ NUEVO: Estrategia aprobada con SL 2.0 ATR / TP 3.0 ATR
    "USDJPY": {"strategy_func": SignalGenerator.usdjpy_trend_pullback}, 
}

def manage_trailing_stops():
    """Gestiona Trailing Stops dinámicos basados en EMA 21 para operaciones activas."""
    positions = mt5_connector.get_positions()
    if not positions:
        return
        
    executor = OrderExecutor(mt5_connector)
    
    for pos in positions:
        try:
            ticket = pos.ticket if hasattr(pos, 'ticket') else pos.get('ticket', 0)
            symbol = pos.symbol if hasattr(pos, 'symbol') else pos.get('symbol', '')
            pos_type = pos.type if hasattr(pos, 'type') else pos.get('type', 0)
            current_sl = pos.sl if hasattr(pos, 'sl') else pos.get('sl', 0)
            
            # Solo procesar USDJPY
            if symbol != "USDJPY":
                continue
                
            df = DataFetcher(mt5_connector).get_historical_data(symbol, "H1", bars=30)
            if df is None or len(df) < 21:
                continue
                
            df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
            current_ema21 = df.iloc[-1]['ema_21']
            
            tick = mt5.symbol_info_tick(symbol)
            if tick is None: 
                continue
                
            new_sl = None
            
            if pos_type == 0:  # BUY
                if current_ema21 > current_sl and current_ema21 < tick.bid:
                    new_sl = round(current_ema21 - 0.00005, 3)
                    
            elif pos_type == 1:  # SELL
                if current_ema21 < current_sl and current_ema21 > tick.ask:
                    new_sl = round(current_ema21 + 0.00005, 3)
            
            if new_sl is not None and abs(new_sl - current_sl) > 0.00001:
                executor.modify_position(ticket, sl=new_sl)
                logger.info(f"[TS LIVE] {symbol} #{ticket} | Nuevo SL: {new_sl} | EMA21: {current_ema21:.5f}")
                
        except Exception as e:
            logger.error(f"[ERROR] Gestionando TS para {symbol} #{ticket}: {e}")

def check_end_of_day_risk():
    """Gestiona riesgos de fin de día: swaps, gaps y protección de capital."""
    now = datetime.now()
    current_time = now.time()
    current_day = now.weekday()  # 0=Lunes, 4=Viernes
    
    is_eod_window = TimeClass(15, 45) <= current_time <= TimeClass(16, 0)
    is_friday_afternoon = current_day == 4 and current_time >= TimeClass(14, 0)
    
    if not (is_eod_window or is_friday_afternoon):
        return
        
    positions = mt5_connector.get_positions()
    if not positions:
        return
        
    executor = OrderExecutor(mt5_connector)
    logger.info(f"[EOD RISK] Verificando posiciones antes del cierre ({current_time.strftime('%H:%M')})...")
    
    for pos in positions:
        try:
            if isinstance(pos, dict):
                ticket = pos.get('ticket', 0)
                symbol = pos.get('symbol', '')
                profit = float(pos.get('profit', 0))
                price_open = float(pos.get('price_open', 0))
                sl = float(pos.get('sl', 0))
                pos_type = int(pos.get('type', 0))
                open_time_ts = float(pos.get('time', 0))
            else:
                ticket = pos.ticket
                symbol = pos.symbol
                profit = pos.profit
                price_open = pos.price_open
                sl = pos.sl
                pos_type = pos.type
                open_time_ts = pos.time
            
            hours_open = (now - datetime.fromtimestamp(open_time_ts)).total_seconds() / 3600
            
            should_close = False
            close_reason = ""
            
            if hours_open > 24 and profit < 0:
                should_close = True
                close_reason = f"EOD RISK: Perdedora >24h (${profit:.2f}, {hours_open:.1f}h)"
                
            if is_friday_afternoon:
                should_close = True
                close_reason = f"WEEKEND RISK: Cierre preventivo viernes (${profit:+.2f})"
            
            if should_close:
                current_positions = mt5.positions_get(ticket=ticket)
                if not current_positions:
                    logger.info(f"[EOD SKIP] Posición {symbol} #{ticket} ya cerrada.")
                    continue
                    
                logger.warning(f"[{close_reason}] Cerrando {symbol} #{ticket}")
                
                result = executor.close_position(ticket=ticket)
                
                # ✅ CORRECCIÓN: Validación única sin logs duplicados
                if result.status == ExecutionStatus.FILLED:
                    logger.info(f"[EOD OK] {symbol} #{ticket} cerrada exitosamente.")
                else:
                    logger.error(f"[EOD FAIL] {symbol} #{ticket}: {result.error_message}")
                
            elif profit > 0:
                pip_offset = 0.0005 if 'JPY' not in symbol else 0.05
                
                tick = mt5.symbol_info_tick(symbol)
                if tick is None:
                    logger.warning(f"[EOD RISK] No se pudo obtener tick para {symbol}")
                    continue

                current_price = tick.bid if pos_type == 0 else tick.ask
                min_distance = 0.00010 
                
                if pos_type == 0:  # BUY
                    new_sl = round(price_open + pip_offset, 5)
                    distance_to_sl = current_price - new_sl
                    
                    if new_sl > sl and distance_to_sl > min_distance:
                        executor.modify_position(ticket, sl=new_sl)
                        logger.info(f"[EOD PROTECT] SL movido a BE+5pips en {symbol} #{ticket}")
                        
                    elif new_sl > sl and distance_to_sl > 0:
                        safe_sl = round(price_open + (pip_offset * 0.4), 5)
                        if (current_price - safe_sl) > 0.00005:
                            executor.modify_position(ticket, sl=safe_sl)
                            logger.info(f"[EOD ADAPT] SL movido a BE+2pips (ajustado) en {symbol} #{ticket}")
                        else:
                            logger.warning(f"[EOD SKIP] Precio demasiado cerca incluso para BE+2. Distancia: {distance_to_sl:.5f}")
                            
                    else:
                        logger.warning(f"[EOD SKIP] SL BE+5pips inválido (precio debajo). Distancia: {distance_to_sl:.5f}")

                elif pos_type == 1:  # SELL
                    new_sl = round(price_open - pip_offset, 5)
                    distance_to_sl = new_sl - current_price
                    
                    if (sl == 0 or new_sl < sl) and distance_to_sl > min_distance:
                        executor.modify_position(ticket, sl=new_sl)
                        logger.info(f"[EOD PROTECT] SL movido a BE+5pips en {symbol} #{ticket}")
                        
                    elif (sl == 0 or new_sl < sl) and distance_to_sl > 0:
                        safe_sl = round(price_open - (pip_offset * 0.4), 5)
                        if (safe_sl - current_price) > 0.00005:
                            executor.modify_position(ticket, sl=safe_sl)
                            logger.info(f"[EOD ADAPT] SL movido a BE+2pips (ajustado) en {symbol} #{ticket}")
                        else:
                            logger.warning(f"[EOD SKIP] Precio demasiado cerca incluso para BE+2. Distancia: {distance_to_sl:.5f}")
                    else:
                        logger.warning(f"[EOD SKIP] SL BE+5pips inválido (precio encima). Distancia: {distance_to_sl:.5f}")
                        
        except Exception as e:
            err_ticket = "N/A"
            if isinstance(pos, dict):
                err_ticket = pos.get('ticket', 'Unknown')
            elif hasattr(pos, 'ticket'):
                err_ticket = pos.ticket
                
            logger.error(f"[ERROR] Gestionando riesgo EOD para ticket {err_ticket}: {e}")
            
def run_trading_cycle():
    """Ejecuta ciclo completo para TODOS los pares activos."""
    
    global last_calendar_refresh_week
    current_week = datetime.now().isocalendar()[1]
    
    if current_week != last_calendar_refresh_week:
        logger.info("[SYSTEM] 🔄 Nueva semana detectada. Actualizando calendario económico...")
        local_news_filter.refresh_calendar()
        last_calendar_refresh_week = current_week

    if not mt5_connector.check_connection():
        logger.error("[ERROR] Sin conexión a MT5. Intentando reconectar...")
        if not mt5_connector.connect():
            return False

    db_manager.update_closed_trades()
    
    account_info = mt5_connector.get_account_info()
    balance = account_info['balance'] if account_info else 10000.0
    
    all_ok = True
    
    for symbol, config in ACTIVE_PAIRS.items():
        try:
            if not local_news_filter.is_safe_to_trade(symbol):
                logger.warning(f"[CYCLE] Saltando {symbol} por noticia local de alto impacto.")
                continue

            # ✅ FILTRO HORARIO + VENTANA DE SILENCIO
            if symbol in TRADING_HOURS:
                current_hour = datetime.now().hour
                current_minute = datetime.now().minute
                hours = TRADING_HOURS[symbol]
                
                if hours["start"] > hours["end"]:
                    is_active = current_hour >= hours["start"] or current_hour < hours["end"]
                else:
                    is_active = hours["start"] <= current_hour < hours["end"]
                    
                if not is_active:
                    logger.info(f"[TIME FILTER] {symbol} fuera de horario ({hours['start']}:00-{hours['end']}:00). Saltando.")
                    continue

                # ✅ BLOQUEO POR CIERRE INMINENTE (Evita bucles de apertura/cierre)
                minutes_to_midnight = (23 * 60 + 59) - (current_hour * 60 + current_minute)
                is_pre_close_block = minutes_to_midnight < PRE_CLOSE_BUFFER_MINUTES
                
                if is_pre_close_block:
                    logger.warning(f"[PRE-CLOSE BLOCK] {symbol} bloqueado: Faltan <{PRE_CLOSE_BUFFER_MINUTES}min para cierre diario. No abrir nuevas posiciones.")
                    continue

            logger.info(f"[CYCLE] Procesando {symbol}...")
            
            existing_positions = mt5.positions_get(symbol=symbol)
            if existing_positions and len(existing_positions) > 0:
                logger.info(f"[INFO] Ya hay posición abierta en {symbol}. Saltando análisis de entrada.")
                continue
            
            fetcher = DataFetcher(mt5_connector)
            df = fetcher.get_historical_data(symbol=symbol, timeframe="H1", bars=200)
            df_h4 = fetcher.get_historical_data(symbol=symbol, timeframe="H4", bars=200)
            
            if df is None or len(df) < 50:
                logger.warning(f"[WARNING] Datos insuficientes para {symbol}")
                continue
            
            if df_h4 is not None and not df_h4.empty:
                db_manager.save_candles(df_h4, symbol, "H4")
                
            df_ind = TechnicalIndicators.apply_all_basic(df)
            
            latest_signal = None
            
            if symbol == "EURUSD":
                all_signals_dict = config["strategy_func"](df_ind, symbol=symbol)
                for strategy_name, signals in all_signals_dict.items():
                    if strategy_name == "EMA_Trend" and signals:
                        latest_signal = signals[-1]
                        break
                        
            elif symbol == "AUDUSD":
                signals = config["strategy_func"](df_ind, symbol=symbol)
                if signals:
                    latest_signal = signals[-1]
                    
            elif symbol == "USDJPY":
                signals = config["strategy_func"](df_ind, symbol=symbol)
                if signals:
                    latest_signal = signals[-1]
                    # Nota: La estrategia aprobada usa TP fijo, no TS. 
                    # Si la señal viene con TP explícito, lo respetamos.
            
            if not latest_signal:
                logger.info(f"[INFO] Sin señales para {symbol}")
                continue
                
            logger.info(f"[INFO] Señal detectada en {symbol}: {latest_signal.signal_type.value} @ {latest_signal.entry_price}")
            
            risk_mgr = RiskCalculator(
                account_balance=balance, 
                daily_loss_current=0.0, 
                open_positions_count=len(mt5_connector.get_positions() or [])
            )
            
            validation, msg = risk_mgr.validate_signal(latest_signal)
            if validation != RiskValidationResult.APPROVED:
                logger.warning(f"[REJECT] {symbol} rechazado: {msg}")
                continue
            
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.error(f"[ERROR] Sin tick para {symbol}")
                continue
                
            current_atr = df_ind.iloc[-1].get('atr_14', 0.001)
            if pd.isna(current_atr) or current_atr <= 0:
                current_atr = 0.001
                
            if latest_signal.signal_type.value == "BUY":
                real_sl = round(tick.ask - (current_atr * 2.0), 5)  # ✅ Ajustado a 2.0 ATR según backtest aprobado
                real_tp = round(tick.ask + (current_atr * 3.0), 5)
                real_entry = tick.ask
            else:
                real_sl = round(tick.bid + (current_atr * 2.0), 5)
                real_tp = round(tick.bid - (current_atr * 3.0), 5)
                real_entry = tick.bid
            
            latest_signal.stop_loss = real_sl
            latest_signal.take_profit = real_tp
            latest_signal.entry_price = real_entry
            
            pos_size = risk_mgr.calculate_position_size(latest_signal)
            execution = None
            
            if pos_size:
                executor = OrderExecutor(mt5_connector)
                execution = executor.execute_market_order(latest_signal, pos_size)
            
            if execution and execution.status.value == "FILLED":
                logger.info(f"[OK] {symbol} ejecutada: Ticket {execution.ticket}")
                
                telegram_notifier.notify_signal({
                    'direction': latest_signal.signal_type.value,
                    'symbol': latest_signal.symbol,
                    'ticket': execution.ticket,
                    'entry_price': real_entry,
                    'stop_loss': real_sl,
                    'take_profit': real_tp,
                    'strategy': latest_signal.strategy_name,
                    'strength': latest_signal.strength,
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                })
            else:
                error_msg = execution.error_message if execution else "Tamaño inválido o nulo"
                logger.error(f"[ERROR] {symbol} fallo: {error_msg}")
                
        except Exception as e:
            logger.error(f"[ERROR] Fallo crítico en {symbol}: {e}")
            all_ok = False
            import traceback; traceback.print_exc()
            
    positions = mt5_connector.get_positions()
    if positions:
        executor_temp = OrderExecutor(mt5_connector)
        local_news_filter.check_open_positions_risk(positions, executor_temp)
    
    manage_trailing_stops()
    check_end_of_day_risk()
            
    return all_ok

if __name__ == "__main__":
    logger.info("[START] Iniciando ForexTrader System v2.0 Multi-Par")
    mt5_connector.connect()
    
    try:
        while True:
            logger.info(f"[CYCLE] Revisando mercado... {datetime.now().strftime('%H:%M:%S')}")
            run_trading_cycle()
            sleep_time.sleep(60) 
            
    except KeyboardInterrupt:
        logger.info("[STOP] Sistema detenido por usuario")
    finally:
        mt5_connector.disconnect()
        logger.info("[DISCONNECT] Conexión MT5 cerrada correctamente")