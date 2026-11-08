from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict, Any

import pandas as pd
import numpy as np

from src.core.logger import setup_logger

logger = setup_logger("SignalGenerator")


class SignalType(Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"
    CLOSE_BUY = "CLOSE_BUY"
    CLOSE_SELL = "CLOSE_SELL"


@dataclass
class TradingSignal:
    symbol: str
    signal_type: SignalType
    timestamp: datetime
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    strength: float = 0.0
    confidence: float = 0.0
    strategy_name: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not 0 <= self.strength <= 1:
            raise ValueError(f"[ERROR] Strength debe estar entre 0 y 1, recibido: {self.strength}")
        if not 0 <= self.confidence <= 100:
            raise ValueError(f"[ERROR] Confidence debe estar entre 0 y 100, recibido: {self.confidence}")


class SignalGenerator:
    
    @staticmethod
    def rsi_reversal_strategy(
        df: pd.DataFrame,
        symbol: str,
        rsi_period: int = 14,
        oversold: float = 25,      # OPTIMIZADO: de 30 a 25
        overbought: float = 75,     # OPTIMIZADO: de 70 a 75
        min_strength: float = 0.6
    ) -> List[TradingSignal]:
        """
        Estrategia RSI Reversal Optimizada:
        - Umbrales más extremos (25/75) para filtrar señales débiles
        - Filtro de tendencia: NO operar contra SMA50 vs SMA200
        """
        signals = []
        rsi_col = f'rsi_{rsi_period}'
        
        # Verificar columnas necesarias para filtro de tendencia
        has_trend_filter = 'sma_50' in df.columns and 'sma_200' in df.columns
        
        if rsi_col not in df.columns:
            logger.error(f"[ERROR] Columna '{rsi_col}' no encontrada")
            return signals

        for i in range(1, len(df)):
            prev_rsi = df.iloc[i-1][rsi_col]
            curr_rsi = df.iloc[i][rsi_col]
            
            if pd.isna(prev_rsi) or pd.isna(curr_rsi):
                continue

            # FILTRO DE TENDENCIA (NUEVO)
            trend_aligned = True
            if has_trend_filter:
                sma50 = df.iloc[i]['sma_50']
                sma200 = df.iloc[i]['sma_200']
                if not pd.isna(sma50) and not pd.isna(sma200):
                    # Solo BUY si precio > SMA50 > SMA200 (tendencia alcista)
                    # Solo SELL si precio < SMA50 < SMA200 (tendencia bajista)
                    close = df.iloc[i]['close']
                    if curr_rsi < oversold and not (close > sma50 > sma200):
                        trend_aligned = False
                    elif curr_rsi > overbought and not (close < sma50 < sma200):
                        trend_aligned = False

            if not trend_aligned:
                continue

            # Señal COMPRA: cruce alcista desde zona sobrevendida extrema
            if prev_rsi < oversold and curr_rsi >= oversold:
                distance = (curr_rsi - oversold) / (50 - oversold)
                strength = min(1.0, min_strength + distance * 0.4)
                
                sig = TradingSignal(
                    symbol=symbol, signal_type=SignalType.BUY,
                    timestamp=df.iloc[i]['timestamp'],
                    entry_price=df.iloc[i]['close'],
                    stop_loss=df.iloc[i]['low'] * 0.998,
                    take_profit=df.iloc[i]['close'] * 1.015,
                    strength=round(strength, 3),
                    confidence=round(min(95, 50 + strength * 45), 1),
                    strategy_name="RSI_Reversal_v2",
                    metadata={'rsi_prev': round(prev_rsi, 2), 'rsi_curr': round(curr_rsi, 2)}
                )
                signals.append(sig)

            # Señal VENTA: cruce bajista desde zona sobrecomprada extrema
            elif prev_rsi > overbought and curr_rsi <= overbought:
                distance = (overbought - curr_rsi) / (overbought - 50)
                strength = min(1.0, min_strength + distance * 0.4)
                
                sig = TradingSignal(
                    symbol=symbol, signal_type=SignalType.SELL,
                    timestamp=df.iloc[i]['timestamp'],
                    entry_price=df.iloc[i]['close'],
                    stop_loss=df.iloc[i]['high'] * 1.002,
                    take_profit=df.iloc[i]['close'] * 0.985,
                    strength=round(strength, 3),
                    confidence=round(min(95, 50 + strength * 45), 1),
                    strategy_name="RSI_Reversal_v2",
                    metadata={'rsi_prev': round(prev_rsi, 2), 'rsi_curr': round(curr_rsi, 2)}
                )
                signals.append(sig)

        logger.info(f"[OK] RSI_Reversal_v2 generó {len(signals)} señales para {symbol}")
        return signals

    @staticmethod
    def bb_mean_reversion_strategy(
        df: pd.DataFrame,
        symbol: str,
        bb_period: int = 20,
        bb_std: float = 2.5,          # OPTIMIZADO: de 2.0 a 2.5
        min_strength: float = 0.5
    ) -> List[TradingSignal]:
        """
        Bollinger Mean Reversion Optimizada:
        - Bandas más anchas (2.5 std dev) para reducir falsos positivos
        - Confirmación de cierre dentro de banda
        """
        signals = []
        
        # Detectar nombres de columnas dinámicamente
        upper_col = next((c for c in ['bb_upper', 'upper'] if c in df.columns), None)
        lower_col = next((c for c in ['bb_lower', 'lower'] if c in df.columns), None)
        middle_col = next((c for c in ['bb_middle', 'middle'] if c in df.columns), None)

        if not upper_col or not lower_col:
            logger.error("[ERROR] Columnas de Bollinger Bands no encontradas")
            return signals

        for i in range(len(df)):
            row = df.iloc[i]
            close = row['close']
            upper = row[upper_col]
            lower = row[lower_col]
            
            if pd.isna(close) or pd.isna(upper) or pd.isna(lower):
                continue

            band_width = upper - lower
            if band_width <= 0:
                continue

            # BUY: precio toca/cruza banda inferior Y cierra dentro
            if close <= lower:
                penetration = (lower - close) / band_width
                strength = min(1.0, min_strength + penetration * 0.5)
                
                tp = row[middle_col] if middle_col and not pd.isna(row[middle_col]) else close * 1.01
                
                sig = TradingSignal(
                    symbol=symbol, signal_type=SignalType.BUY,
                    timestamp=row['timestamp'], entry_price=close,
                    stop_loss=lower * 0.997, take_profit=tp,
                    strength=round(strength, 3),
                    confidence=round(min(90, 45 + strength * 45), 1),
                    strategy_name="BB_MeanRev_v2",
                    metadata={'penetration_pct': round(penetration * 100, 2)}
                )
                signals.append(sig)

            # SELL: precio toca/cruza banda superior Y cierra dentro
            elif close >= upper:
                penetration = (close - upper) / band_width
                strength = min(1.0, min_strength + penetration * 0.5)
                
                tp = row[middle_col] if middle_col and not pd.isna(row[middle_col]) else close * 0.99
                
                sig = TradingSignal(
                    symbol=symbol, signal_type=SignalType.SELL,
                    timestamp=row['timestamp'], entry_price=close,
                    stop_loss=upper * 1.003, take_profit=tp,
                    strength=round(strength, 3),
                    confidence=round(min(90, 45 + strength * 45), 1),
                    strategy_name="BB_MeanRev_v2",
                    metadata={'penetration_pct': round(penetration * 100, 2)}
                )
                signals.append(sig)

        logger.info(f"[OK] BB_MeanRev_v2 generó {len(signals)} señales para {symbol}")
        return signals

    @staticmethod
    def ema_trend_strategy(
        df: pd.DataFrame,
        symbol: str,
        fast_ema: int = 9,
        slow_ema: int = 21,
        adx_threshold: float = 25.0,
        min_strength: float = 0.6
    ) -> List[TradingSignal]:
        """
        Estrategia de Seguimiento de Tendencia:
        - BUY: EMA9 cruza arriba EMA21 + ADX > umbral
        - SELL: EMA9 cruza abajo EMA21 + ADX > umbral
        - SL basado en ATR, TP dinámico según volatilidad reciente
        """
        signals = []
        fast_col = f'ema_{fast_ema}'
        slow_col = f'ema_{slow_ema}'
        adx_col = 'adx_14'
        
        if not all(c in df.columns for c in [fast_col, slow_col, adx_col]):
            logger.error("[ERROR] Columnas EMA/ADX faltantes. Ejecuta apply_all_basic primero.")
            return signals

        for i in range(1, len(df)):
            prev_fast = df.iloc[i-1][fast_col]
            curr_fast = df.iloc[i][fast_col]
            prev_slow = df.iloc[i-1][slow_col]
            curr_slow = df.iloc[i][slow_col]
            adx_val = df.iloc[i][adx_col]
            
            if any(pd.isna(v) for v in [prev_fast, curr_fast, prev_slow, curr_slow, adx_val]):
                continue

            # Filtrar tendencias débiles
            if adx_val < adx_threshold:
                continue

            close = df.iloc[i]['close']
            atr_val = df.iloc[i].get('atr_14', 0.001)
            if pd.isna(atr_val) or atr_val <= 0:
                atr_val = 0.001

            # Señal COMPRA: cruce alcista confirmado
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                sl_dist = atr_val * 1.5
                tp_dist = atr_val * 3.0
                
                sig = TradingSignal(
                    symbol=symbol, signal_type=SignalType.BUY,
                    timestamp=df.iloc[i]['timestamp'], entry_price=close,
                    stop_loss=round(close - sl_dist, 5),
                    take_profit=round(close + tp_dist, 5),
                    strength=min(1.0, min_strength + (adx_val - adx_threshold) / 50),
                    confidence=min(95, 50 + adx_val),
                    strategy_name="EMA_Trend",
                    metadata={'adx': round(adx_val, 2), 'atr': round(atr_val, 5)}
                )
                signals.append(sig)

            # Señal VENTA: cruce bajista confirmado
            elif prev_fast >= prev_slow and curr_fast < curr_slow:
                sl_dist = atr_val * 1.5
                tp_dist = atr_val * 3.0
                
                sig = TradingSignal(
                    symbol=symbol, signal_type=SignalType.SELL,
                    timestamp=df.iloc[i]['timestamp'], entry_price=close,
                    stop_loss=round(close + sl_dist, 5),
                    take_profit=round(close - tp_dist, 5),
                    strength=min(1.0, min_strength + (adx_val - adx_threshold) / 50),
                    confidence=min(95, 50 + adx_val),
                    strategy_name="EMA_Trend",
                    metadata={'adx': round(adx_val, 2), 'atr': round(atr_val, 5)}
                )
                signals.append(sig)

        logger.info(f"[OK] EMA_Trend generó {len(signals)} señales para {symbol}")
        return signals
    
    @classmethod
    def generate_all_signals(cls, df: pd.DataFrame, symbol: str) -> Dict[str, List[TradingSignal]]:
        results = {}
        strategies = [
            #("RSI_Reversal_v2", cls.rsi_reversal_strategy),
            #("BB_MeanRev_v2", cls.bb_mean_reversion_strategy),
            ("EMA_Trend", cls.ema_trend_strategy),  # NUEVA
        ]
        
        for name, strategy_fn in strategies:
            try:
                signals = strategy_fn(df, symbol)
                results[name] = signals
            except Exception as e:
                logger.error(f"[ERROR] Estrategia {name} falló: {e}")
                results[name] = []
        
        total = sum(len(s) for s in results.values())
        logger.info(f"[OK] Total señales v2: {total} para {symbol}")
        return results


if __name__ == "__main__":
    from src.data.database import db_manager
    from src.analysis.indicators import TechnicalIndicators
    
    print("\n[INFO] === PRUEBA SEÑALES V2 ===\n")
    
    df = db_manager.load_candles(symbol="EURUSD", timeframe="H1", limit=2000)
    if df is None:
        print("[ERROR] No hay datos en BD")
        exit(1)
    
    print(f"[OK] Datos: {len(df)} velas")
    df_ind = TechnicalIndicators.apply_all_basic(df)
    
    all_signals = SignalGenerator.generate_all_signals(df_ind, symbol="EURUSD")
    
    print("\n" + "=" * 60)
    for strat, sigs in all_signals.items():
        buys = sum(1 for s in sigs if s.signal_type == SignalType.BUY)
        sells = sum(1 for s in sigs if s.signal_type == SignalType.SELL)
        print(f"{strat}: {len(sigs)} total | BUY: {buys} | SELL: {sells}")
    print("=" * 60)