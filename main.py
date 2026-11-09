import time
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime, time as TimeClass  # 👈 Alias explícito
import time as sleep_time                          # 👈 Módulo time renombrado

from src.trading.broker_mt5 import mt5_connector
from src.data.data_fetcher import DataFetcher
from src.analysis.indicators import TechnicalIndicators
from src.analysis.signals import SignalGenerator
from src.risk.calculator import RiskCalculator, RiskValidationResult
from src.trading.order_executor import OrderExecutor
from src.notifications.telegram_bot import telegram_notifier
from src.core.logger import setup_logger
from src.data.database import db_manager 

logger = setup_logger("MainTrader")

# Inicializar tabla de trades al arrancar
db_manager.create_trade_log_table()

# CONFIGURACIÓN MULTI-PAR
ACTIVE_PAIRS = {
    "EURUSD": {"strategy_func": SignalGenerator.generate_all_signals},
    "AUDUSD": {"strategy_func": SignalGenerator.aud_trend_strategy}
}

def check_end_of_day_risk():
    """Gestiona riesgos de fin de día: swaps, gaps y protección de capital."""
    now = datetime.now()
    current_time = now.time()
    current_day = now.weekday()  # 0=Lunes, 4=Viernes
    
    # ZONA DE PELIGRO: 3:45 PM - 4:00 PM Colombia
    is_eod_window = TimeClass(15, 45) <= current_time <= TimeClass(16, 0)
    
    # VIERNES DESDE LAS 2:00 PM
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
            hours_open = (now - datetime.fromtimestamp(pos.time)).total_seconds() / 3600
            
            # REGLA 1: Cerrar perdedoras > 24h
            if hours_open > 24 and pos.profit < 0:
                logger.warning(f"[EOD RISK] Cerrando {pos.symbol} #{pos.ticket} en loss (${pos.profit:.2f}) tras {hours_open:.1f}h.")
                executor.close_position(pos.ticket)
                
            # REGLA 2: Viernes tarde -> Cerrar TODO
            elif is_friday_afternoon:
                logger.warning(f"[WEEKEND RISK] Cerrando {pos.symbol} #{pos.ticket} (${pos.profit:+.2f}) antes del cierre semanal.")
                executor.close_position(pos.ticket)
                
            # REGLA 3: Ganadoras -> Mover SL a Breakeven + 5 pips
            elif pos.profit > 0:
                pip_offset = 0.0005 if 'JPY' not in pos.symbol else 0.05
                
                if pos.type == 0:  # BUY
                    new_sl = round(pos.price_open + pip_offset, 5)
                    if new_sl > pos.sl:
                        executor.modify_position(pos.ticket, sl=new_sl)
                        logger.info(f"[EOD PROTECT] SL movido a BE+5pips en {pos.symbol} #{pos.ticket}")
                        
                elif pos.type == 1:  # SELL
                    new_sl = round(pos.price_open - pip_offset, 5)
                    if (pos.sl == 0 or new_sl < pos.sl):
                        executor.modify_position(pos.ticket, sl=new_sl)
                        logger.info(f"[EOD PROTECT] SL movido a BE+5pips en {pos.symbol} #{pos.ticket}")
                        
        except Exception as e:
            logger.error(f"[ERROR] Gestionando riesgo EOD para ticket {pos.ticket}: {e}")

def run_trading_cycle():
    """Ejecuta ciclo completo para TODOS los pares activos conservando lógica original."""
    
    # 0. GESTIÓN DE RIESGO FIN DE DÍA (Se ejecuta en cada ciclo cerca de las 4PM)
    check_end_of_day_risk()
    
    # 1. Verificar conexión MT5
    if not mt5_connector.check_connection():
        logger.error("[ERROR] Sin conexión a MT5. Intentando reconectar...")
        if not mt5_connector.connect():
            return False

    # Actualizar trades cerrados UNA sola vez por ciclo (global)
    db_manager.update_closed_trades()
    
    # Obtener info de cuenta UNA sola vez
    account_info = mt5_connector.get_account_info()
    balance = account_info['balance'] if account_info else 10000.0
    
    all_ok = True
    
    for symbol, config in ACTIVE_PAIRS.items():
        try:
            logger.info(f"[CYCLE] Procesando {symbol}...")
            
            # VERIFICAR POSICIÓN ABIERTA ESPECÍFICA DEL PAR
            existing_positions = mt5.positions_get(symbol=symbol)
            if existing_positions and len(existing_positions) > 0:
                logger.info(f"[INFO] Ya hay posición abierta en {symbol}. Saltando análisis de entrada.")
                continue
            
            # OBTENER DATOS DEL PAR
            fetcher = DataFetcher(mt5_connector)
            df = fetcher.get_historical_data(symbol=symbol, timeframe="H1", bars=200)
            
            if df is None or len(df) < 50:
                logger.warning(f"[WARNING] Datos insuficientes para {symbol}")
                continue
                
            # CALCULAR INDICADORES
            df_ind = TechnicalIndicators.apply_all_basic(df)
            
            # GENERAR SEÑALES SEGÚN ESTRATEGIA ASIGNADA
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
            
            if not latest_signal:
                logger.info(f"[INFO] Sin señales para {symbol}")
                continue
                
            logger.info(f"[INFO] Señal detectada en {symbol}: {latest_signal.signal_type.value} @ {latest_signal.entry_price}")
            
            # VALIDAR RIESGO
            risk_mgr = RiskCalculator(
                account_balance=balance, 
                daily_loss_current=0.0, 
                open_positions_count=len(mt5_connector.get_positions() or [])
            )
            
            validation, msg = risk_mgr.validate_signal(latest_signal)
            if validation != RiskValidationResult.APPROVED:
                logger.warning(f"[REJECT] {symbol} rechazado: {msg}")
                continue
            
            # NOTIFICAR TELEGRAM ANTES DE AJUSTAR PRECIOS
            telegram_notifier.notify_signal({
                'direction': latest_signal.signal_type.value,
                'symbol': latest_signal.symbol,
                'entry_price': latest_signal.entry_price,
                'stop_loss': latest_signal.stop_loss,
                'take_profit': latest_signal.take_profit,
                'strategy': latest_signal.strategy_name,
                'strength': latest_signal.strength,
                'timestamp': latest_signal.timestamp.strftime('%Y-%m-%d %H:%M')
            })
            
            # RECÁLCULO CRÍTICO DE SL/TP EN TIEMPO REAL (Protección error 10016)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                logger.error(f"[ERROR] Sin tick para {symbol}")
                continue
                
            current_atr = df_ind.iloc[-1].get('atr_14', 0.001)
            if pd.isna(current_atr) or current_atr <= 0:
                current_atr = 0.001
                
            if latest_signal.signal_type.value == "BUY":
                real_sl = round(tick.ask - (current_atr * 1.5), 5)
                real_tp = round(tick.ask + (current_atr * 3.0), 5)
                real_entry = tick.ask
            else:
                real_sl = round(tick.bid + (current_atr * 1.5), 5)
                real_tp = round(tick.bid - (current_atr * 3.0), 5)
                real_entry = tick.bid
                
            latest_signal.stop_loss = real_sl
            latest_signal.take_profit = real_tp
            latest_signal.entry_price = real_entry
            
            # EJECUTAR ORDEN
            pos_size = risk_mgr.calculate_position_size(latest_signal)
            if pos_size:
                executor = OrderExecutor(mt5_connector)
                execution = executor.execute_market_order(latest_signal, pos_size)
                
                if execution.status.value == "FILLED":
                    logger.info(f"[OK] {symbol} ejecutada: Ticket {execution.ticket}")
                else:
                    logger.error(f"[ERROR] {symbol} fallo: {execution.error_message}")
            else:
                logger.error(f"[ERROR] Tamaño inválido para {symbol}")
                
        except Exception as e:
            logger.error(f"[ERROR] Fallo crítico en {symbol}: {e}")
            all_ok = False
            import traceback; traceback.print_exc()
            
    return all_ok


if __name__ == "__main__":
    logger.info("[START] Iniciando ForexTrader System v2.0 Multi-Par")
    mt5_connector.connect()
    
    try:
        while True:
            logger.info(f"[CYCLE] Revisando mercado... {datetime.now().strftime('%H:%M:%S')}")
            run_trading_cycle()
            
            # Esperar 60 segundos antes del siguiente ciclo
            sleep_time.sleep(60) 
            
    except KeyboardInterrupt:
        logger.info("[STOP] Sistema detenido por usuario")
    finally:
        mt5_connector.disconnect()
        logger.info("[DISCONNECT] Conexión MT5 cerrada correctamente")