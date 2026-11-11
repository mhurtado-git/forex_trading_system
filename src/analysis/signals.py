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
  
    @staticmethod
    def aud_trend_strategy(df: pd.DataFrame, symbol: str = "AUDUSD") -> List[TradingSignal]:
        """Estrategia EMA Trend adaptada para AUDUSD con filtro de sesión (Colombia UTC-5)."""
        signals = []
        
        # Seguridad: Asegurar que el índice sea datetime
        if not isinstance(df.index, pd.DatetimeIndex):
            if 'timestamp' in df.columns:
                df = df.set_index('timestamp')
            else:
                logger.warning(f"[WARNING] No se puede aplicar filtro horario en {symbol}: falta índice temporal")
                return [] # Retornar vacío en lugar de fallar
            
        # Filtro de horario: Solo operar entre 03:00 y 11:00 AM hora Colombia
        # En datos H1, verificamos la hora de la vela
        df['hour_col'] = df.index.hour 
        
        for i in range(1, len(df)):
            current = df.iloc[i]
            prev = df.iloc[i-1]
            
            # Validar horario permitido (3 AM - 11 AM COL)
            if not (3 <= current['hour_col'] < 11):
                continue
                
            # Lógica EMA Trend idéntica a EURUSD pero aplicada a AUD
            if (prev['ema_9'] <= prev['ema_21'] and current['ema_9'] > current['ema_21'] 
                and current['adx_14'] > 25):
                signals.append(TradingSignal(
                    timestamp=current.name, symbol=symbol, signal_type=SignalType.BUY,
                    entry_price=current['close'], strategy_name="AUD_Trend",
                    stop_loss=current['low'] - (current['atr_14'] * 1.5),
                    take_profit=current['close'] + (current['atr_14'] * 3.0),
                    strength=current['adx_14'] / 100
                ))
                
            elif (prev['ema_9'] >= prev['ema_21'] and current['ema_9'] < current['ema_21'] 
                  and current['adx_14'] > 25):
                signals.append(TradingSignal(
                    timestamp=current.name, symbol=symbol, signal_type=SignalType.SELL,
                    entry_price=current['close'], strategy_name="AUD_Trend",
                    stop_loss=current['high'] + (current['atr_14'] * 1.5),
                    take_profit=current['close'] - (current['atr_14'] * 3.0),
                    strength=current['adx_14'] / 100
                ))
                
        return signals

    @staticmethod
    def xau_breakout_atr(df: pd.DataFrame, symbol: str = "XAUUSD") -> List[TradingSignal]:
        """Breakout Donchian ajustado para XAUUSD."""
        signals = []
        
        required = ['high', 'low', 'close', 'atr_14', 'adx_14']
        if not all(col in df.columns for col in required):
            logger.warning(f"[WARNING] Faltan indicadores base para {symbol} Breakout")
            return signals
            
        # Convertir índice si es necesario
        if not isinstance(df.index, pd.DatetimeIndex) and 'timestamp' in df.columns:
            df = df.set_index('timestamp')
            
        # Calcular Donchian más sensible (15 periodos en lugar de 20)
        df['donchian_high_15'] = df['high'].rolling(15).max()
        df['donchian_low_15'] = df['low'].rolling(15).min()
            
        for i in range(15, len(df)):
            current = df.iloc[i]
            
            # RELAJAR HORARIO: 6AM - 12PM COL (Incluye apertura Londres y NY completa)
            hour_col = current.name.hour
            if not (6 <= hour_col < 12):
                continue
                
            # RELAJAR ADX: > 25 (Igual que EURUSD/AUD, no exigir 30)
            if current['adx_14'] < 25:
                continue
                
            atr = current['atr_14']
            
            # SEÑAL COMPRA
            if current['close'] > current['donchian_high_15']:
                signals.append(TradingSignal(
                    timestamp=current.name, 
                    symbol=symbol, 
                    signal_type=SignalType.BUY,
                    entry_price=current['close'], 
                    strategy_name="XAU_Breakout_ATR",
                    stop_loss=current['low'] - (atr * 2.0),  # SL ligeramente más ajustado
                    take_profit=current['close'] + (atr * 4.0),  # R/R 1:2
                    strength=min(current['adx_14'] / 40, 1.0)
                ))
                
            # SEÑAL VENTA
            elif current['close'] < current['donchian_low_15']:
                signals.append(TradingSignal(
                    timestamp=current.name, 
                    symbol=symbol, 
                    signal_type=SignalType.SELL,
                    entry_price=current['close'], 
                    strategy_name="XAU_Breakout_ATR",
                    stop_loss=current['high'] + (atr * 2.0),
                    take_profit=current['close'] - (atr * 4.0),
                    strength=min(current['adx_14'] / 40, 1.0)
                ))
                
        return signals
    
    @staticmethod
    def usdjpy_trend_pullback(df: pd.DataFrame, symbol: str) -> List[TradingSignal]:
        """
        Estrategia de seguimiento de tendencia con entrada en pullback para USDJPY.
        Usa EMA 200 como filtro direccional y EMA 9/21 como gatillo.
        """
        signals = []
        
        # Verificar columnas necesarias
        required = ['close', 'ema_9', 'ema_21', 'adx_14', 'atr_14']
        if not all(col in df.columns for col in required):
            print(f"[WARN] Faltan indicadores para {symbol}. Se requiere EMA200 adicional.")
            return signals

        # Calcular EMA 200 si no existe (necesaria para filtro macro)
        if 'ema_200' not in df.columns:
            df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()

        # Iterar desde la vela 201 para tener EMA200 válida
        for i in range(201, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i-1]
            
            price = row['close']
            ema9, ema21, ema200 = row['ema_9'], row['ema_21'], row['ema_200']
            adx = row['adx_14']
            atr = row['atr_14']
            
            # --- LÓGICA DE COMPRA ---
            buy_condition = (
                price > ema200 and          # Tendencia alcista macro
                adx > 20 and                # Tendencia activa
                prev['ema_9'] <= prev['ema_21'] and  # Cruce previo
                ema9 > ema21                # Cruce actual confirmado
            )
            
            if buy_condition:
                sl = price - (1.5 * atr)
                tp = -1.0, #price + (35 * 0.01)    # 30 pips fijos para JPY
                
                signals.append(TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.BUY,
                    entry_price=price,
                    stop_loss=round(sl, 3),
                    take_profit=-1.0, #round(tp, 3),
                    strategy_name="USDJPY_TrendPullback",
                    timestamp=row.name if hasattr(row, 'name') else None
                ))
                continue  # Evitar señal doble en misma vela

            # --- LÓGICA DE VENTA ---
            sell_condition = (
                price < ema200 and          # Tendencia bajista macro
                adx > 20 and                
                prev['ema_9'] >= prev['ema_21'] and
                ema9 < ema21                
            )
            
            if sell_condition:
                sl = price + (1.5 * atr)
                tp = -1.0, #price - (35 * 0.01)    
                
                signals.append(TradingSignal(
                    symbol=symbol,
                    signal_type=SignalType.SELL,
                    entry_price=price,
                    stop_loss=round(sl, 3),
                    take_profit=-1.0, #round(tp, 3),
                    strategy_name="USDJPY_TrendPullback",
                    timestamp=row.name if hasattr(row, 'name') else None
                ))
                
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