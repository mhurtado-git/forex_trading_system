import pandas as pd
import numpy as np
from typing import Optional, Dict, List, Union

from src.core.logger import setup_logger

logger = setup_logger("Indicators")


class TechnicalIndicators:
    """
    Biblioteca de indicadores técnicos estándar para análisis de series temporales financieras.
    Todos los métodos aceptan y retornan DataFrames de Pandas compatibles con DatabaseManager.
    """

    @staticmethod
    def calculate_sma(data: pd.DataFrame, period: int = 20, column: str = 'close') -> pd.Series:
        """Media Móvil Simple (Simple Moving Average)"""
        if len(data) < period:
            logger.warning(f"[WARNING] Datos insuficientes para SMA({period}). Se requieren {period} velas.")
            return pd.Series(dtype=float)
        return data[column].rolling(window=period).mean()

    @staticmethod
    def calculate_ema(data: pd.DataFrame, period: int = 20, column: str = 'close') -> pd.Series:
        """Media Móvil Exponencial (Exponential Moving Average)"""
        if len(data) < period:
            logger.warning(f"[WARNING] Datos insuficientes para EMA({period}).")
            return pd.Series(dtype=float)
        return data[column].ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(data: pd.DataFrame, period: int = 14, column: str = 'close') -> pd.Series:
        """Índice de Fuerza Relativa (Relative Strength Index)"""
        if len(data) < period + 1:
            logger.warning(f"[WARNING] Datos insuficientes para RSI({period}).")
            return pd.Series(dtype=float)
        
        delta = data[column].diff()
        gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean()
        
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_macd(
        data: pd.DataFrame, 
        fast: int = 12, 
        slow: int = 26, 
        signal: int = 9, 
        column: str = 'close'
    ) -> Dict[str, pd.Series]:
        """
        MACD (Moving Average Convergence Divergence)
        Retorna diccionario con 'macd_line', 'signal_line' y 'histogram'.
        """
        if len(data) < slow:
            logger.warning(f"[WARNING] Datos insuficientes para MACD({fast},{slow},{signal}).")
            return {'macd_line': pd.Series(dtype=float), 'signal_line': pd.Series(dtype=float), 'histogram': pd.Series(dtype=float)}
        
        ema_fast = data[column].ewm(span=fast, adjust=False).mean()
        ema_slow = data[column].ewm(span=slow, adjust=False).mean()
        
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return {
            'macd_line': macd_line,
            'signal_line': signal_line,
            'histogram': histogram
        }

    @staticmethod
    def calculate_bollinger_bands(
        data: pd.DataFrame, 
        period: int = 20, 
        std_dev: float = 2.0, 
        column: str = 'close'
    ) -> Dict[str, pd.Series]:
        """
        Bandas de Bollinger
        Retorna diccionario con 'upper', 'middle' (SMA) y 'lower'.
        """
        if len(data) < period:
            logger.warning(f"[WARNING] Datos insuficientes para BB({period}, {std_dev}).")
            return {'upper': pd.Series(dtype=float), 'middle': pd.Series(dtype=float), 'lower': pd.Series(dtype=float)}
        
        middle = data[column].rolling(window=period).mean()
        std = data[column].rolling(window=period).std()
        
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        
        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }

    @staticmethod
    def calculate_atr(data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range (Rango Verdadero Promedio)"""
        if len(data) < period + 1:
            logger.warning(f"[WARNING] Datos insuficientes para ATR({period}).")
            return pd.Series(dtype=float)
        
        high_low = data['high'] - data['low']
        high_close = (data['high'] - data['close'].shift()).abs()
        low_close = (data['low'] - data['close'].shift()).abs()
        
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()
        return atr

    @staticmethod
    def calculate_adx(data: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average Directional Index (ADX) - Mide fuerza de tendencia."""
        if len(data) < period * 2 + 1:
            logger.warning(f"[WARNING] Datos insuficientes para ADX({period})")
            return pd.Series(dtype=float)
        
        high_diff = data['high'].diff()
        low_diff = -data['low'].diff()
        
        plus_dm = high_diff.where((high_diff > low_diff) & (high_diff > 0), 0.0)
        minus_dm = low_diff.where((low_diff > high_diff) & (low_diff > 0), 0.0)
        
        tr = pd.concat([
            data['high'] - data['low'],
            (data['high'] - data['close'].shift()).abs(),
            (data['low'] - data['close'].shift()).abs()
        ], axis=1).max(axis=1)
        
        atr = tr.rolling(window=period).mean()
        plus_di = 100 * (plus_dm.rolling(window=period).mean() / atr)
        minus_di = 100 * (minus_dm.rolling(window=period).mean() / atr)
        
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()
        
        return adx
    
    @classmethod
    def apply_all_basic(cls, data: pd.DataFrame) -> pd.DataFrame:
        """
        Aplica todos los indicadores básicos en un solo paso.
        Ideal para preparación rápida de datos antes de generar señales.
        """
        df = data.copy()
        
        # Medias móviles
        df['sma_20'] = cls.calculate_sma(df, period=20)
        df['sma_50'] = cls.calculate_sma(df, period=50)
        df['ema_12'] = cls.calculate_ema(df, period=12)
        df['ema_26'] = cls.calculate_ema(df, period=26)
        
        # Osciladores
        df['rsi_14'] = cls.calculate_rsi(df, period=14)
        
        # MACD
        macd_data = cls.calculate_macd(df)
        df['macd_line'] = macd_data['macd_line']
        df['macd_signal'] = macd_data['signal_line']
        df['macd_hist'] = macd_data['histogram']
        
        # Volatilidad
        bb_data = cls.calculate_bollinger_bands(df)
        df['bb_upper'] = bb_data['upper']
        df['bb_middle'] = bb_data['middle']
        df['bb_lower'] = bb_data['lower']
        
        df['atr_14'] = cls.calculate_atr(df)
    
        df['adx_14'] = cls.calculate_adx(df)    
    
        logger.info(f"[OK] Indicadores aplicados exitosamente a {len(df)} velas")
        
                # Agregar ADX y asegurar EMAs estén presentes
        df['adx_14'] = cls.calculate_adx(df)
        
        # Asegurar que EMA9 y EMA21 existan (si no estaban en apply_all_basic original)
        if 'ema_9' not in df.columns:
            df['ema_9'] = cls.calculate_ema(df, period=9)
        if 'ema_21' not in df.columns:
            df['ema_21'] = cls.calculate_ema(df, period=21)
            
        return df


if __name__ == "__main__":
    from src.data.database import db_manager
    
    print("\n[INFO] === PRUEBA DE INDICADORES TÉCNICOS ===\n")
    
    # Cargar datos desde BD local
    df = db_manager.load_candles(symbol="EURUSD", timeframe="H1", limit=200)
    
    if df is not None:
        print(f"[OK] Datos cargados: {len(df)} velas de EURUSD H1")
        
        # Aplicar todos los indicadores
        df_with_indicators = TechnicalIndicators.apply_all_basic(df)
        
        # Mostrar últimas 5 filas con indicadores calculados
        print("\n[OK] Últimas 5 velas con indicadores:")
        display_cols = ['timestamp', 'close', 'sma_20', 'rsi_14', 'macd_line', 'macd_signal', 'bb_upper', 'bb_lower', 'atr_14']
        available_cols = [c for c in display_cols if c in df_with_indicators.columns]
        print(df_with_indicators.tail()[available_cols].to_string(index=False))
        
        # Estadísticas rápidas de RSI
        rsi_valid = df_with_indicators['rsi_14'].dropna()
        if not rsi_valid.empty:
            print(f"\n[INFO] RSI Stats -> Min: {rsi_valid.min():.2f} | Max: {rsi_valid.max():.2f} | Mean: {rsi_valid.mean():.2f}")
            
            overbought = (rsi_valid > 70).sum()
            oversold = (rsi_valid < 30).sum()
            print(f"[INFO] Velas sobrecompradas (>70): {overbought} | Sobrevendidas (<30): {oversold}")
    else:
        print("[ERROR] No hay datos en BD. Ejecute primero 'python -m src.data.database' para poblar la BD.")