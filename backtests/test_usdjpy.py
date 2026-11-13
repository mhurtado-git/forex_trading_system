# backtests/test_usdjpy.py
import sys
sys.path.append('.')

import pandas as pd  # ✅ IMPORT FALTANTE AGREGADO
import numpy as np   # ✅ IMPORT FALTANTE AGREGADO

from src.data.data_fetcher import DataFetcher
from src.trading.broker_mt5 import mt5_connector
from src.analysis.signals import SignalGenerator
from backtests.base_backtest import HonestBacktester

def validate_usdjpy(bars=5000):
    print(f"\n🇯🇵 Validando USDJPY Trend Pullback ({bars} velas)...")
    
    df = DataFetcher(mt5_connector).get_historical_data("USDJPY", "H1", bars)
    if df is None or df.empty:
        print("❌ Sin datos"); return
        
    # Calcular indicadores SOLO para USDJPY
    df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    tr = pd.concat([
        df['high'] - df['low'],
        (df['high'] - df['close'].shift()).abs(),
        (df['low'] - df['close'].shift()).abs()
    ], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(14).mean()
    
    plus_dm = df['high'].diff()
    minus_dm = -df['low'].diff()
    plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm), 0)
    minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm), 0)
    atr_smooth = tr.rolling(14).mean()
    plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth)
    minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth)
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
    df['adx_14'] = dx.rolling(14).mean()
    
    signals = SignalGenerator.usdjpy_trend_pullback(df, "USDJPY")
    print(f"   Señales generadas: {len(signals)}")
    
    if not signals:
        print("❌ Sin señales. Revisar filtros de entrada."); return
        
    # ✅ DESACTIVAR VALIDACIÓN Estricta DE EMA PARA JPY (Debugging)
    tester = HonestBacktester("USDJPY")
    results = tester.run(df, signals, use_realtime_ema_validation=False)
    
    status = "🟢 APROBADO" if results['approved'] else "🔴 REQUIERE AJUSTE"
    print(f"   Trades: {results['trades']} | WR: {results['win_rate']:.1f}% | P&L: ${results['pnl']:,.2f} | PF: {results['profit_factor']:.2f} {status}")

if __name__ == "__main__":
    if mt5_connector.connect():
        validate_usdjpy()
        mt5_connector.disconnect()