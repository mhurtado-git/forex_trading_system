from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional

import pandas as pd
import numpy as np

from src.analysis.signals import TradingSignal, SignalType
from src.risk.calculator import RiskCalculator
from src.core.logger import setup_logger

logger = setup_logger("Backtester")


@dataclass
class TradeResult:
    entry_time: datetime
    exit_time: datetime
    direction: str
    entry_price: float
    exit_price: float
    lots: float
    profit_usd: float
    profit_pips: float
    duration_hours: float
    strategy: str
    r_r_ratio: float


@dataclass
class BacktestReport:
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    total_profit: float
    max_drawdown: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    sharpe_ratio: float
    trades: List[TradeResult] = field(default_factory=list)


class BacktestEngine:
    """Motor de backtesting basado en eventos con matching tolerante de timestamps."""

    def __init__(self, initial_balance: float = 10000.0):
        self.initial_balance = initial_balance

    def run(
        self,
        df: pd.DataFrame,
        signals: List[TradingSignal],
        risk_pct: float = 1.0,
        symbol: str = "EURUSD"
    ) -> BacktestReport:
        logger.info(f"[INFO] Iniciando backtest: {len(df)} velas, {len(signals)} señales")

        balance = self.initial_balance
        equity_curve = [balance]
        trades: List[TradeResult] = []
        open_position: Optional[Dict] = None
        pip_value = 10.0 if 'JPY' not in symbol else 9.3

        # Crear índice de señales por timestamp para búsqueda O(1)
        signal_map: Dict[pd.Timestamp, TradingSignal] = {}
        for sig in signals:
            ts = pd.Timestamp(sig.timestamp).normalize() if hasattr(sig.timestamp, 'hour') else pd.Timestamp(sig.timestamp)
            signal_map[ts] = sig

        for i in range(len(df)):
            bar = df.iloc[i]
            bar_ts = pd.Timestamp(bar['timestamp']).normalize() if hasattr(bar['timestamp'], 'hour') else pd.Timestamp(bar['timestamp'])

            # 1. Abrir posición si hay señal coincidente y no hay posición abierta
            if open_position is None and bar_ts in signal_map:
                sig = signal_map[bar_ts]
                risk_mgr = RiskCalculator(account_balance=balance, daily_loss_current=0.0, open_positions_count=0)
                validation, _ = risk_mgr.validate_signal(sig)

                if validation.value == "APPROVED":
                    pos_size = risk_mgr.calculate_position_size(sig)
                    if pos_size:
                        open_position = {
                            'entry_time': bar['timestamp'],
                            'entry_price': bar['close'],
                            'direction': sig.signal_type.value,
                            'lots': pos_size.lots,
                            'sl': sig.stop_loss,
                            'tp': sig.take_profit,
                            'strategy': sig.strategy_name,
                            'rr_ratio': pos_size.rr_ratio
                        }
                        logger.debug(f"[DEBUG] Entrada {sig.signal_type.value} @ {bar['close']:.5f}")

            # 2. Gestionar posición abierta
            if open_position is not None:
                pos = open_position
                high, low, close = bar['high'], bar['low'], bar['close']
                exited = False
                exit_price = 0.0
                exit_reason = ""

                if pos['direction'] == 'BUY':
                    if low <= pos['sl']:
                        exit_price, exit_reason = pos['sl'], "SL"
                        exited = True
                    elif high >= pos['tp']:
                        exit_price, exit_reason = pos['tp'], "TP"
                        exited = True
                else:  # SELL
                    if high >= pos['sl']:
                        exit_price, exit_reason = pos['sl'], "SL"
                        exited = True
                    elif low <= pos['tp']:
                        exit_price, exit_reason = pos['tp'], "TP"
                        exited = True

                # Cierre forzado al final del dataset
                if not exited and i == len(df) - 1:
                    exit_price, exit_reason = close, "END_OF_DATA"
                    exited = True

                if exited:
                    mult = 0.0001 if 'JPY' not in symbol else 0.01
                    profit_pips = (exit_price - pos['entry_price']) / mult if pos['direction'] == 'BUY' else (pos['entry_price'] - exit_price) / mult
                    profit_usd = profit_pips * pos['lots'] * pip_value
                    balance += profit_usd
                    duration = (bar['timestamp'] - pos['entry_time']).total_seconds() / 3600

                    trades.append(TradeResult(
                        entry_time=pos['entry_time'], exit_time=bar['timestamp'],
                        direction=pos['direction'], entry_price=pos['entry_price'],
                        exit_price=exit_price, lots=pos['lots'],
                        profit_usd=round(profit_usd, 2), profit_pips=round(profit_pips, 1),
                        duration_hours=round(duration, 2), strategy=pos['strategy'],
                        r_r_ratio=pos['rr_ratio']
                    ))
                    equity_curve.append(balance)
                    open_position = None
                    logger.debug(f"[DEBUG] Salida {exit_reason} @ {exit_price:.5f} | P&L: ${profit_usd:.2f}")

        return self._generate_report(symbol, trades, equity_curve)

    def _generate_report(self, symbol: str, trades: List[TradeResult], equity_curve: List[float]) -> BacktestReport:
        if not trades:
            logger.warning("[WARNING] Cero operaciones ejecutadas. Revisa matching de timestamps.")
            return BacktestReport(0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        profits = [t.profit_usd for t in trades]
        wins = [p for p in profits if p > 0]
        losses = [p for p in profits if p < 0]

        peak = self.initial_balance
        max_dd = 0.0
        for eq in equity_curve:
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            max_dd = max(max_dd, dd)

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 1
        pf = gross_profit / gross_loss

        returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
        sharpe = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0

        report = BacktestReport(
            total_trades=len(trades), winning_trades=len(wins), losing_trades=len(losses),
            win_rate=round(len(wins) / len(trades) * 100, 2),
            total_profit=round(sum(profits), 2), max_drawdown=round(max_dd, 2),
            avg_win=round(np.mean(wins), 2) if wins else 0,
            avg_loss=round(np.mean(losses), 2) if losses else 0,
            profit_factor=round(pf, 2), sharpe_ratio=round(sharpe, 2), trades=trades
        )
        logger.info(f"[OK] Backtest completado: {report.total_trades} trades")
        return report


if __name__ == "__main__":
    from src.data.database import db_manager
    from src.analysis.indicators import TechnicalIndicators
    from src.analysis.signals import SignalGenerator

    print("\n[INFO] === BACKTEST ENGINE v2 ===\n")

    df = db_manager.load_candles(symbol="EURUSD", timeframe="H1", limit=2000)
    if df is None or len(df) < 500:
        print("[ERROR] Datos insuficientes")
        exit(1)

    print(f"[OK] {len(df)} velas cargadas")
    df_ind = TechnicalIndicators.apply_all_basic(df)

    all_signals_dict = SignalGenerator.generate_all_signals(df_ind, symbol="EURUSD")
    all_signals = []
    for sigs in all_signals_dict.values():
        all_signals.extend(sigs)
    all_signals.sort(key=lambda s: s.timestamp)
    print(f"[OK] {len(all_signals)} señales generadas")

    engine = BacktestEngine(initial_balance=10000.0)
    report = engine.run(df_ind, all_signals, risk_pct=1.0, symbol="EURUSD")

    print("\n" + "=" * 60)
    print("REPORTE DE BACKTEST - EURUSD H1")
    print("=" * 60)
    print(f"Operaciones totales: {report.total_trades}")
    print(f"Ganadoras: {report.winning_trades} | Perdedoras: {report.losing_trades}")
    print(f"Win Rate: {report.win_rate}%")
    print(f"Beneficio Neto: ${report.total_profit:.2f}")
    print(f"Profit Factor: {report.profit_factor}")
    print(f"Max Drawdown: {report.max_drawdown}%")
    print(f"Sharpe Ratio: {report.sharpe_ratio}")
    print(f"Avg Win: ${report.avg_win:.2f} | Avg Loss: ${report.avg_loss:.2f}")
    print("=" * 60)

    if report.trades:
        print("\nÚLTIMAS 5 OPERACIONES:")
        for t in report.trades[-5:]:
            print(f"  {t.direction} | Entry: {t.entry_price:.5f} | Exit: {t.exit_price:.5f} | P&L: ${t.profit_usd:.2f} | {t.strategy}")