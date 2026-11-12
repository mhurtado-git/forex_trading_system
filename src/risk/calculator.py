from dataclasses import dataclass
from enum import Enum
from typing import Optional, Dict, Any
import MetaTrader5 as mt5_lib

from config.settings import TRADING_CONFIG
from src.analysis.signals import TradingSignal, SignalType
from src.core.logger import setup_logger
from src.trading.broker_mt5 import mt5_connector  # Import necesario para riesgo global

logger = setup_logger("RiskManager")


class RiskValidationResult(Enum):
    APPROVED = "APPROVED"
    REJECTED_MAX_POSITIONS = "REJECTED_MAX_POSITIONS"
    REJECTED_DAILY_LOSS = "REJECTED_DAILY_LOSS"
    REJECTED_RR_RATIO = "REJECTED_RR_RATIO"
    REJECTED_INVALID_SL_TP = "REJECTED_INVALID_SL_TP"


@dataclass
class PositionSize:
    """Resultado del cálculo de tamaño de posición."""
    lots: float
    risk_amount: float      # Monto en divisa base arriesgado
    stop_distance_pips: float
    pip_value: float        # Valor monetario de 1 pip para este par
    rr_ratio: float         # Ratio Riesgo/Beneficio real


class RiskCalculator:
    """
    Gestor de riesgo pre-ejecución. Valida señales y calcula lotes óptimos.
    Usa configuración centralizada desde settings.py / .env
    """

    # Valores aproximados de pip por lote estándar (ajustar según broker)
    PIP_VALUES = {
        'EURUSD': 10.0, 'GBPUSD': 10.0, 'AUDUSD': 10.0, 'NZDUSD': 10.0,
        'USDCAD': 7.8, 'USDCHF': 10.2, 'USDJPY': 7.0,
        'EURJPY': 9.3, 'GBPJPY': 9.3, 'EURGBP': 12.5
    }

    def __init__(self, account_balance: float, daily_loss_current: float = 0.0, 
                 open_positions_count: int = 0, max_total_exposure_pct: float = 3.0):
        self.balance = account_balance
        self.daily_loss = daily_loss_current
        self.open_positions = open_positions_count
        self.config = TRADING_CONFIG
        self.max_total_exposure_pct = max_total_exposure_pct 

    def can_open_position(self, symbol: str, signal) -> bool:
        """Verifica riesgo individual Y exposición total de cuenta."""
        
        # 1. Chequeo INDIVIDUAL existente
        validation, msg = self.validate_signal(signal)
        if validation != RiskValidationResult.APPROVED:
            logger.warning(f"[RISK INDIVIDUAL] {symbol} rechazado: {msg}")
            return False
            
        # 2. Chequeo de exposición GLOBAL
        try:
            current_total_risk = self._get_current_total_risk_usd()
            new_trade_risk = self._calculate_trade_risk_usd(signal)
            
            max_allowed_risk = self.balance * (self.max_total_exposure_pct / 100)
            
            if (current_total_risk + new_trade_risk) > max_allowed_risk:
                logger.warning(
                    f"[RISK GLOBAL] Bloqueado en {symbol}. "
                    f"Riesgo actual: ${current_total_risk:.2f} + Nuevo: ${new_trade_risk:.2f} "
                    f"> Límite ({self.max_total_exposure_pct}%): ${max_allowed_risk:.2f}"
                )
                return False
        except Exception as e:
            logger.error(f"[ERROR] Calculando riesgo global: {e}. Permitiendo operación por seguridad.")
            
        return True

    def _get_current_total_risk_usd(self) -> float:
        """Suma el riesgo potencial de TODAS las posiciones abiertas."""
        positions = mt5_connector.get_positions()
        if not positions:
            return 0.0
            
        total_risk = 0.0
        for pos in positions:
            # CORRECCIÓN: Usar abs() para manejar BUY y SELL correctamente
            # Calcular pips reales considerando pares JPY
            multiplier = 0.01 if 'JPY' in pos.symbol else 0.0001
            distance_pips = abs(pos.price_open - pos.sl) / multiplier
            
            # Obtener valor de pip del diccionario o usar default
            pip_val = self.PIP_VALUES.get(pos.symbol.upper(), 10.0)
            
            # Riesgo = Pips * ValorPip * Volumen
            risk_pos = distance_pips * pip_val * pos.volume
            total_risk += risk_pos
            
        return total_risk

    def _calculate_trade_risk_usd(self, signal) -> float:
        """Calcula el riesgo en USD de la nueva señal."""
        symbol = signal.symbol.upper()
        multiplier = 0.01 if 'JPY' in symbol else 0.0001
        
        # Distancia absoluta en precio
        dist_price = abs(signal.entry_price - signal.stop_loss)
        dist_pips = dist_price / multiplier
        
        pip_val = self.PIP_VALUES.get(symbol, 10.0)
        
        # Estimación de lotes basada en config si no está en la señal
        risk_pct = self.config.get('default_risk_percent', 1.0)
        estimated_lots = (self.balance * (risk_pct / 100)) / (dist_pips * pip_val)
        estimated_lots = max(0.01, round(estimated_lots, 2))
        
        return dist_pips * pip_val * estimated_lots

    def validate_signal(self, signal: TradingSignal) -> tuple[RiskValidationResult, str]:
        """
        Valida si una señal cumple con todas las reglas de riesgo.
        Retorna (resultado, mensaje descriptivo).
        """
        cfg = self.config

        # 1. Límite de posiciones abiertas
        if self.open_positions >= cfg['max_open_positions']:
            msg = f"[REJECT] Máx posiciones ({cfg['max_open_positions']}) alcanzado"
            logger.warning(msg)
            return RiskValidationResult.REJECTED_MAX_POSITIONS, msg

        # 2. Límite de pérdida diaria
        max_daily_loss_amt = self.balance * (cfg['max_daily_loss_percent'] / 100)
        if self.daily_loss >= max_daily_loss_amt:
            msg = f"[REJECT] Pérdida diaria máxima (${max_daily_loss_amt:.2f}) alcanzada"
            logger.warning(msg)
            return RiskValidationResult.REJECTED_DAILY_LOSS, msg

        # 3. Validar SL/TP existen y son lógicos
        if signal.stop_loss is None or signal.take_profit is None:
            msg = "[REJECT] Señal sin Stop Loss o Take Profit definido"
            logger.error(msg)
            return RiskValidationResult.REJECTED_INVALID_SL_TP, msg

        if signal.signal_type == SignalType.BUY:
            if signal.stop_loss >= signal.entry_price:
                return RiskValidationResult.REJECTED_INVALID_SL_TP, "[REJECT] SL debe estar debajo del precio de entrada en BUY"
            if signal.take_profit <= signal.entry_price:
                return RiskValidationResult.REJECTED_INVALID_SL_TP, "[REJECT] TP debe estar arriba del precio de entrada en BUY"
            risk_dist = signal.entry_price - signal.stop_loss
            reward_dist = signal.take_profit - signal.entry_price
        else:  # SELL
            if signal.stop_loss <= signal.entry_price:
                return RiskValidationResult.REJECTED_INVALID_SL_TP, "[REJECT] SL debe estar arriba del precio de entrada en SELL"
            if signal.take_profit >= signal.entry_price:
                return RiskValidationResult.REJECTED_INVALID_SL_TP, "[REJECT] TP debe estar abajo del precio de entrada en SELL"
            risk_dist = signal.stop_loss - signal.entry_price
            reward_dist = signal.entry_price - signal.take_profit

        # 4. Ratio Riesgo/Beneficio mínimo
        if risk_dist <= 0:
            return RiskValidationResult.REJECTED_INVALID_SL_TP, "[REJECT] Distancia al SL inválida"
            
        rr_ratio = reward_dist / risk_dist
        min_rr = cfg['min_risk_reward_ratio']
        if rr_ratio < min_rr:
            msg = f"[REJECT] R/R {rr_ratio:.2f} < mínimo {min_rr}"
            logger.warning(msg)
            return RiskValidationResult.REJECTED_RR_RATIO, msg

        logger.info(f"[OK] Señal {signal.signal_type.value} {signal.symbol} aprobada | R/R: {rr_ratio:.2f}")
        return RiskValidationResult.APPROVED, f"Señal aprobada con R/R {rr_ratio:.2f}"

    def calculate_position_size(self, signal: TradingSignal) -> Optional[PositionSize]:
        """
        Calcula el tamaño de lote basado en riesgo porcentual de la cuenta.
        Debe llamarse DESPUÉS de validate_signal().
        """
        symbol = signal.symbol.upper()
        pip_value = self.PIP_VALUES.get(symbol, 10.0)

        risk_pct = self.config['default_risk_percent']
        risk_amount = self.balance * (risk_pct / 100)

        if signal.signal_type == SignalType.BUY:
            stop_distance = signal.entry_price - signal.stop_loss
        else:
            stop_distance = signal.stop_loss - signal.entry_price

        if stop_distance <= 0:
            logger.error(f"[ERROR] Distancia al SL inválida para {symbol}")
            return None

        # Convertir distancia de precio a pips
        multiplier = 0.01 if 'JPY' in symbol else 0.0001
        stop_distance_pips = stop_distance / multiplier

        # Lotes = Riesgo $ / (Pips de SL × Valor por Pip)
        lots = risk_amount / (stop_distance_pips * pip_value)

        # Redondear a 2 decimales (lotes estándar MT5)
        lots = round(max(0.01, lots), 2)

        rr_ratio = abs(signal.take_profit - signal.entry_price) / stop_distance

        pos_size = PositionSize(
            lots=lots,
            risk_amount=round(risk_amount, 2),
            stop_distance_pips=round(stop_distance_pips, 1),
            pip_value=pip_value,
            rr_ratio=round(rr_ratio, 2)
        )

        logger.info(f"[OK] Tamaño calculado: {lots} lots | Riesgo: ${risk_amount:.2f} | SL: {stop_distance_pips:.1f} pips")
        return pos_size

    def update_state(self, daily_loss_add: float = 0.0, position_change: int = 0):
        """Actualiza el estado interno tras ejecutar/rechazar una operación."""
        self.daily_loss += daily_loss_add
        self.open_positions += position_change
        logger.info(f"[INFO] Estado actualizado: DailyLoss=${self.daily_loss:.2f} | Posiciones={self.open_positions}")


if __name__ == "__main__":
    from src.data.database import db_manager
    from src.analysis.indicators import TechnicalIndicators
    from src.analysis.signals import SignalGenerator, SignalType

    print("\n[INFO] === PRUEBA DE RISK MANAGER ===\n")

    # Cargar datos e indicadores
    df = db_manager.load_candles(symbol="EURUSD", timeframe="H1", limit=200)
    if df is None:
        print("[ERROR] No hay datos en BD")
        exit(1)

    df_ind = TechnicalIndicators.apply_all_basic(df)
    all_signals_dict = SignalGenerator.generate_all_signals(df_ind, symbol="EURUSD")

    # Aplanar todas las señales
    all_signals = []
    for strategy_name, signals in all_signals_dict.items():
        for s in signals:
            s.metadata['strategy'] = strategy_name
            all_signals.append(s)

    print(f"[OK] Total señales a evaluar: {len(all_signals)}")

    # Simular Risk Manager con balance demo
    risk_mgr = RiskCalculator(account_balance=10000.0, daily_loss_current=0.0, open_positions_count=0)

    approved = 0
    rejected = 0
    rejection_reasons = {}

    print("\n" + "=" * 70)
    print("EVALUACIÓN DE SEÑALES POR RISK MANAGER")
    print("=" * 70)

    for i, signal in enumerate(all_signals[:20]):  # Evaluar primeras 20 para legibilidad
        validation, msg = risk_mgr.validate_signal(signal)

        if validation == RiskValidationResult.APPROVED:
            pos_size = risk_mgr.calculate_position_size(signal)
            approved += 1
            print(f"\n✅ #{i+1} [{signal.metadata.get('strategy','')}] {signal.signal_type.value} @ {signal.entry_price:.5f}")
            print(f"   Lotes: {pos_size.lots} | Riesgo: ${pos_size.risk_amount:.2f} | SL: {pos_size.stop_distance_pips:.1f} pips | R/R: {pos_size.rr_ratio:.2f}")
            # Simular que se ejecuta y actualizar estado
            risk_mgr.update_state(position_change=1)
        else:
            rejected += 1
            reason = validation.value
            rejection_reasons[reason] = rejection_reasons.get(reason, 0) + 1
            print(f"\n❌ #{i+1} [{signal.metadata.get('strategy','')}] {signal.signal_type.value} @ {signal.entry_price:.5f}")
            print(f"   Motivo: {msg}")

    # Resumen final
    print("\n" + "=" * 70)
    print("RESUMEN DE VALIDACIÓN")
    print("=" * 70)
    print(f"Aprobadas: {approved} | Rechazadas: {rejected}")
    if rejection_reasons:
        print("\nMotivos de rechazo:")
        for reason, count in rejection_reasons.items():
            print(f"  - {reason}: {count}")
    print("=" * 70)