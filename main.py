import time
import pandas as pd
import MetaTrader5 as mt5
from datetime import datetime

from src.trading.broker_mt5 import mt5_connector
from src.data.data_fetcher import DataFetcher
from src.analysis.indicators import TechnicalIndicators
from src.analysis.signals import SignalGenerator
from src.risk.calculator import RiskCalculator, RiskValidationResult
from src.trading.order_executor import OrderExecutor
from src.notifications.telegram_bot import telegram_notifier
from src.core.logger import setup_logger
# AGREGAR ESTO:
from src.data.database import db_manager 

logger = setup_logger("MainTrader")

db_manager.create_trade_log_table()

def run_trading_cycle():
    """Ejecuta un ciclo completo de trading: Datos -> Señales -> Riesgo -> Ejecución"""
    
    # 1. Verificar conexión
    if not mt5_connector.check_connection():
        logger.error("[ERROR] Sin conexión a MT5. Intentando reconectar...")
        if not mt5_connector.connect():
            return False

    # NUEVO: Verificar si ya hay posición abierta en EURUSD
    existing_positions = mt5.positions_get(symbol="EURUSD")
    if existing_positions and len(existing_positions) > 0:
        logger.info(f"[INFO] Ya hay {len(existing_positions)} posición(es) abierta(s) en EURUSD. Saltando ciclo.")
        return True
    
    # 2. Obtener datos frescos (últimas 100 velas H1)
    fetcher = DataFetcher(mt5_connector)
    df = fetcher.get_historical_data(symbol="EURUSD", timeframe="H1", bars=100)
    
    if df is None or len(df) < 50:
        logger.warning("[WARNING] Datos insuficientes para analizar")
        return False

    db_manager.update_closed_trades() 
 
    # 3. Calcular indicadores
    df_ind = TechnicalIndicators.apply_all_basic(df)
    
    # ACTUALIZAR TRADES CERRADOS ANTES DE BUSCAR NUEVAS SEÑALES
    db_manager.update_closed_trades()

    # 4. Generar señales (Solo EMA_Trend como validamos)
    all_signals_dict = SignalGenerator.generate_all_signals(df_ind, symbol="EURUSD")
    
    # Filtrar solo la última señal generada (la más reciente)
    latest_signal = None
    for strategy_name, signals in all_signals_dict.items():
        if strategy_name == "EMA_Trend" and signals:
            latest_signal = signals[-1]
            break

    if not latest_signal:
        logger.info("[INFO] No hay nuevas señales EMA_Trend en esta vela")
        return True

    logger.info(f"[INFO] Nueva señal detectada: {latest_signal.signal_type.value} @ {latest_signal.entry_price}")

    # 5. Validar Riesgo
    account_info = mt5_connector.get_account_info()
    balance = account_info['balance'] if account_info else 10000.0
    
    risk_mgr = RiskCalculator(
        account_balance=balance, 
        daily_loss_current=0.0, 
        open_positions_count=0
    )
    
    validation, msg = risk_mgr.validate_signal(latest_signal)
    
    if validation != RiskValidationResult.APPROVED:
        logger.warning(f"[REJECT] Señal rechazada por riesgo: {msg}")
        return True

    # ---------------------------------------------------------
    # NOTIFICAR SEÑAL A TELEGRAM (Antes de ajustar precios)
    # Usamos los datos originales de la señal histórica
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # CORRECCIÓN CRÍTICA: Recalcular SL/TP basado en precio ACTUAL
    # Esto evita el error 10016 (Invalid Stops)
    # ---------------------------------------------------------
    tick = mt5.symbol_info_tick(latest_signal.symbol)
    
    if tick is None:
        logger.error("[ERROR] No se pudo obtener tick actual para ajustar SL/TP")
        return True

    # Obtener ATR actual para mantener proporción de riesgo dinámica
    current_atr = df_ind.iloc[-1].get('atr_14', 0.001)
    if pd.isna(current_atr) or current_atr <= 0:
        current_atr = 0.001

    # Determinar multiplicador según par (JPY vs otros)
    multiplier = 0.01 if 'JPY' in latest_signal.symbol else 0.0001
    
    # Recalcular niveles basados en precio REAL de mercado
    if latest_signal.signal_type.value == "BUY":
        real_sl = round(tick.ask - (current_atr * 1.5), 5)
        real_tp = round(tick.ask + (current_atr * 3.0), 5)
        real_entry = tick.ask
    else:  # SELL
        real_sl = round(tick.bid + (current_atr * 1.5), 5)
        real_tp = round(tick.bid - (current_atr * 3.0), 5)
        real_entry = tick.bid

    # Actualizar objeto señal con precios reales ANTES de calcular lotes
    latest_signal.stop_loss = real_sl
    latest_signal.take_profit = real_tp
    latest_signal.entry_price = real_entry

    # 6. Calcular tamaño y Ejecutar con precios corregidos
    pos_size = risk_mgr.calculate_position_size(latest_signal)
    
    if pos_size:
        executor = OrderExecutor(mt5_connector)
        execution = executor.execute_market_order(latest_signal, pos_size)
        
        if execution.status.value == "FILLED":
            logger.info(f"[OK] Orden ejecutada exitosamente: Ticket {execution.ticket}")
        else:
            logger.error(f"[ERROR] Fallo ejecución: {execution.error_message}")
    else:
        logger.error("[ERROR] No se pudo calcular tamaño de posición válido")

    return True


if __name__ == "__main__":
    logger.info("[START] Iniciando ForexTrader System v1.0")
    mt5_connector.connect()
    
    try:
        while True:
            logger.info(f"[CYCLE] Revisando mercado... {datetime.now().strftime('%H:%M:%S')}")
            run_trading_cycle()
            
            # Esperar 60 segundos antes del siguiente ciclo
            time.sleep(60) 
            
    except KeyboardInterrupt:
        logger.info("[STOP] Sistema detenido por usuario")
    finally:
        mt5_connector.disconnect()
        logger.info("[DISCONNECT] Conexión MT5 cerrada correctamente")