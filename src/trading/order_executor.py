from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any

import MetaTrader5 as mt5

from src.trading.broker_mt5 import MT5Connector
from src.risk.calculator import PositionSize
from src.analysis.signals import TradingSignal, SignalType
from src.core.logger import setup_logger
from src.notifications.telegram_bot import telegram_notifier
from src.data.database import db_manager  # Import movido al inicio para mejor práctica

logger = setup_logger("OrderExecutor")


class ExecutionStatus(Enum):
    FILLED = "FILLED"
    REJECTED = "REJECTED"
    ERROR = "ERROR"
    TIMEOUT = "TIMEOUT"


@dataclass
class ExecutionResult:
    """Resultado inmutable de una ejecución de orden."""
    status: ExecutionStatus
    ticket: int = 0
    price_filled: float = 0.0
    volume_filled: float = 0.0
    sl_set: float = 0.0
    tp_set: float = 0.0
    error_code: int = 0
    error_message: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class OrderExecutor:
    """
    Ejecuta órdenes market en MetaTrader 5 con validación post-ejecución.
    Requiere MT5 abierto y logueado (usa MT5Connector existente).
    """

    # Mapeo de tipos de orden MT5
    ORDER_TYPES = {
        SignalType.BUY: mt5.ORDER_TYPE_BUY,
        SignalType.SELL: mt5.ORDER_TYPE_SELL,
    }

    def __init__(self, connector: MT5Connector):
        if not isinstance(connector, MT5Connector):
            raise TypeError("[ERROR] Se requiere instancia válida de MT5Connector")
        self.connector = connector

    def execute_market_order(
        self, 
        signal: TradingSignal, 
        position_size: PositionSize
    ) -> ExecutionResult:
        """Envía orden market a MT5 con detección robusta de filling mode."""
        
        # 1. Validar conexión activa PRIMERO
        if not self.connector.check_connection():
            return ExecutionResult(status=ExecutionStatus.ERROR, error_message="No hay conexión activa con MT5")

        symbol = signal.symbol.upper()
        
        # 2. Obtener precios actuales (tick) ANTES de cualquier otra cosa
        tick = mt5.symbol_info_tick(symbol)
        if tick is None:
            return ExecutionResult(status=ExecutionStatus.ERROR, error_message=f"No se pudo obtener tick para {symbol}")

        # 3. Obtener información del símbolo para filling mode
        symbol_info = mt5.symbol_info(symbol)
        if symbol_info is None:
            return ExecutionResult(status=ExecutionStatus.ERROR, error_message=f"Símbolo {symbol} no encontrado")
        
        # 4. Determinar modo de llenado compatible
        # MetaQuotes-Demo suele requerir FOK (0). IOC (1) causa error 10030.
        filling_type = mt5.ORDER_FILLING_FOK  # Forzado: MetaQuotes-Demo requiere FOK

        # 5. Determinar tipo de orden y precio
        order_type = self.ORDER_TYPES.get(signal.signal_type)
        if order_type is None:
            return ExecutionResult(status=ExecutionStatus.ERROR, error_message=f"Tipo de señal no ejecutable: {signal.signal_type}")

        price = tick.ask if signal.signal_type == SignalType.BUY else tick.bid
        
        # 6. Calcular SL en precio absoluto basado en tick actual
        multiplier = 0.01 if 'JPY' in symbol else 0.0001
        sl_distance_price = position_size.stop_distance_pips * multiplier
        
        if signal.signal_type == SignalType.BUY:
            sl_price = round(price - sl_distance_price, 5)
        else:
            sl_price = round(price + sl_distance_price, 5)

        # 7. Construir request completo
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": position_size.lots,
            "type": order_type,
            "price": price,
            "sl": sl_price,
            "tp": signal.take_profit,
            "deviation": 20,
            "magic": 123456,
            "comment": f"Bot:{signal.strategy_name}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_type,
        }

        logger.info(f"[INFO] Enviando orden {signal.signal_type.value} {symbol} | Lotes: {position_size.lots} | Precio: {price:.5f} | SL: {sl_price:.5f}")

        try:
            result = mt5.order_send(request)
            
            if result is None:
                error = mt5.last_error()
                return ExecutionResult(
                    status=ExecutionStatus.ERROR,
                    error_code=error[0],
                    error_message=f"order_send retornó None. Error MT5: {error}"
                )

            if result.retcode != mt5.TRADE_RETCODE_DONE:
                return ExecutionResult(
                    status=ExecutionStatus.REJECTED,
                    error_code=result.retcode,
                    error_message=f"Broker rechazó orden. Código: {result.retcode} | Comentario: {result.comment}"
                )

            # 8. Confirmar posición abierta
            positions = mt5.positions_get(symbol=symbol)
            if positions and len(positions) > 0:
                last_pos = positions[-1]
                logger.info(f"[OK] Orden ejecutada exitosamente | Ticket: {result.order} | Llenado: {last_pos.volume} @ {last_pos.price_open:.5f}")
                
                # Registrar en historial INMEDIATAMENTE tras ejecución exitosa
                trade_data = {
                    'ticket': result.order,
                    'symbol': symbol,
                    'direction': signal.signal_type.value,
                    'entry_price': last_pos.price_open,
                    'exit_price': None,
                    'volume': last_pos.volume,
                    'sl': last_pos.sl,
                    'tp': last_pos.tp,
                    'profit': 0.0,
                    'strategy': signal.strategy_name,
                    'open_time': datetime.now(),
                    'close_time': None
                }

                # ✅ NUEVO: Guardar Deal ID si está disponible para futura sincronización
                if hasattr(result, 'deal') and result.deal:
                    trade_data['mt5_deal_id'] = result.deal
                    logger.info(f"[DB] Deal ID registrado: {result.deal}")

                db_manager.save_trade(trade_data)
                
                telegram_notifier.notify_execution({
                    'status': 'FILLED',
                     'ticket': result.order,
                     'price_filled': last_pos.price_open,
                     'volume_filled': last_pos.volume
                 })
                
                return ExecutionResult(
                    status=ExecutionStatus.FILLED,
                    ticket=result.order,
                    price_filled=last_pos.price_open,
                    volume_filled=last_pos.volume,
                    sl_set=last_pos.sl,
                    tp_set=last_pos.tp,
                    metadata={
                        'request_price': price,
                        'fill_price': last_pos.price_open,
                        'slippage_points': abs(last_pos.price_open - price) / multiplier,
                        'filling_mode_used': filling_type,
                        'deal_id': trade_data.get('mt5_deal_id') # Incluir en metadata también
                    }
                )
            else:
                return ExecutionResult(
                    status=ExecutionStatus.TIMEOUT,
                    ticket=result.order,
                    error_message="Orden enviada pero posición no encontrada tras ejecución"
                )

        except Exception as e:
            logger.error(f"[ERROR] Excepción ejecutando orden: {e}")
            return ExecutionResult(status=ExecutionStatus.ERROR, error_message=str(e))

    def close_position(self, symbol: str, ticket: Optional[int] = None) -> ExecutionResult:
        """Cierra una posición abierta por símbolo o ticket específico."""
        if not self.connector.check_connection():
            return ExecutionResult(status=ExecutionStatus.ERROR, error_message="Sin conexión MT5")

        positions = mt5.positions_get(symbol=symbol) if ticket is None else mt5.positions_get(ticket=ticket)
        
        if not positions:
            return ExecutionResult(status=ExecutionStatus.ERROR, error_message=f"No hay posición abierta para {symbol}")

        pos = positions[0]
        order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).bid if order_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": pos.volume,
            "type": order_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "Bot:Close",
        }

        result = mt5.order_send(request)
        
        if result and result.retcode == mt5.TRADE_RETCODE_DONE:
            logger.info(f"[OK] Posición {pos.ticket} cerrada @ {price:.5f}")
            return ExecutionResult(status=ExecutionStatus.FILLED, ticket=result.order, price_filled=price)
        else:
            err = mt5.last_error() if result is None else result.comment
            return ExecutionResult(status=ExecutionStatus.REJECTED, error_message=str(err))
    
    def modify_position(self, ticket: int, sl: float = None, tp: float = None):
        """Modifica SL/TP de una posición abierta."""
        import MetaTrader5 as mt5_lib
        
        request = {
            "action": mt5_lib.TRADE_ACTION_SLTP,
            "symbol": "",  # Se obtendrá del ticket
            "position": ticket,
            "sl": sl if sl is not None else 0.0,
            "tp": tp if tp is not None else 0.0,
        }
        
        # Obtener símbolo desde el ticket si no se pasó
        if not request["symbol"]:
            positions = mt5_lib.positions_get(ticket=ticket)
            if positions:
                request["symbol"] = positions[0].symbol
            else:
                logger.error(f"[ERROR] No se encontró posición con ticket {ticket}")
                return False
                
        result = mt5_lib.order_send(request)
        
        if result.retcode == mt5_lib.TRADE_RETCODE_DONE:
            logger.info(f"[OK] Posición #{ticket} modificada: SL={sl}, TP={tp}")
            return True
        else:
            logger.error(f"[ERROR] Fallo al modificar posición #{ticket}: {result.comment} (Código: {result.retcode})")
            return False


if __name__ == "__main__":
    from src.trading.broker_mt5 import mt5_connector
    from src.analysis.indicators import TechnicalIndicators
    from src.analysis.signals import SignalGenerator, SignalType
    from src.risk.calculator import RiskCalculator, RiskValidationResult

    print("\n[INFO] === PRUEBA DE ORDER EXECUTOR (DEMO) ===\n")
    
    # Conectar a MT5
    if not mt5_connector.connect():
        print("[ERROR] No se pudo conectar a MT5")
        exit(1)

    try:
        # Cargar datos y generar señales
        df = db_manager.load_candles(symbol="EURUSD", timeframe="H1", limit=200)
        if df is None:
            print("[ERROR] No hay datos en BD")
            exit(1)

        df_ind = TechnicalIndicators.apply_all_basic(df)
        all_signals_dict = SignalGenerator.generate_all_signals(df_ind, symbol="EURUSD")
        
        # Tomar la primera señal BUY válida
        first_buy_signal = None
        for signals in all_signals_dict.values():
            for s in signals:
                if s.signal_type == SignalType.BUY:
                    first_buy_signal = s
                    break
            if first_buy_signal:
                break

        if not first_buy_signal:
            print("[WARNING] No hay señales BUY disponibles para prueba. Usando SELL.")
            for signals in all_signals_dict.values():
                for s in signals:
                    if s.signal_type == SignalType.SELL:
                        first_buy_signal = s
                        break
                if first_buy_signal:
                    break

        if not first_buy_signal:
            print("[ERROR] No hay señales disponibles")
            exit(1)

        print(f"[OK] Señal seleccionada: {first_buy_signal.signal_type.value} EURUSD @ {first_buy_signal.entry_price:.5f}")

        # Validar con Risk Manager
        account_info = mt5_connector.get_account_info()
        balance = account_info['balance'] if account_info else 10000.0
        
        risk_mgr = RiskCalculator(account_balance=balance, daily_loss_current=0.0, open_positions_count=0)
        validation, msg = risk_mgr.validate_signal(first_buy_signal)
        
        if validation != RiskValidationResult.APPROVED:
            print(f"[REJECT] Señal rechazada: {msg}")
            exit(1)

        pos_size = risk_mgr.calculate_position_size(first_buy_signal)
        print(f"[OK] Tamaño aprobado: {pos_size.lots} lots | Riesgo: ${pos_size.risk_amount:.2f}")

        # EJECUTAR ORDEN REAL EN DEMO
        executor = OrderExecutor(mt5_connector)
        print(f"\n[INFO] Enviando orden real a cuenta demo...")
        
        execution = executor.execute_market_order(first_buy_signal, pos_size)
        
        print(f"\n{'='*60}")
        print("RESULTADO DE EJECUCIÓN")
        print(f"{'='*60}")
        print(f"Estado: {execution.status.value}")
        print(f"Ticket: {execution.ticket}")
        print(f"Precio llenado: {execution.price_filled:.5f}")
        print(f"Volumen: {execution.volume_filled}")
        print(f"SL establecido: {execution.sl_set:.5f}")
        print(f"TP establecido: {execution.tp_set:.5f}")
        if execution.metadata:
            print(f"Slippage: {execution.metadata.get('slippage_points', 0):.1f} pips")
            print(f"Deal ID: {execution.metadata.get('deal_id', 'N/A')}")
        if execution.error_message:
            print(f"Error: {execution.error_message}")
        print(f"{'='*60}")

        # OPCIONAL: Cerrar la posición inmediatamente después de confirmar
        input("\nPresiona ENTER para cerrar la posición de prueba...")
        close_result = executor.close_position("EURUSD")
        print(f"\nCierre: {close_result.status.value} @ {close_result.price_filled:.5f}")

    finally:
        mt5_connector.disconnect()
        print("\n[DISCONNECT] Prueba de ejecución finalizada")