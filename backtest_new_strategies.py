import pandas as pd
from src.data.data_fetcher import DataFetcher
from src.trading.broker_mt5 import mt5_connector
from src.analysis.indicators import TechnicalIndicators
from src.analysis.signals import SignalGenerator
import numpy as np  # 👈 AGREGAR ESTA LÍNEA
import pandas as pd
from src.data.data_fetcher import DataFetcher


def validate_strategy(strategy_func, symbol, bars=2000):
    """Backtesting seguro con normalización de columnas."""
    print(f"\n🔍 Validando {strategy_func.__name__} en {symbol}...")
    
    # 1. Obtener datos crudos
    df = DataFetcher(mt5_connector).get_historical_data(symbol, "H1", bars)
    
    if df is None or df.empty:
        print("❌ No se obtuvieron datos.")
        return
    
    # 2. NORMALIZAR COLUMNAS (Crítico para evitar KeyError)
    # Mapeo flexible: busca variaciones comunes de nombres
    col_map = {}
    for c in df.columns:
        cl = c.lower()
        if 'close' in cl and 'ema' not in cl: col_map[c] = 'close'
        elif 'open' in cl: col_map[c] = 'open'
        elif 'high' in cl: col_map[c] = 'high'
        elif 'low' in cl: col_map[c] = 'low'
        elif 'time' in cl or 'date' in cl: col_map[c] = 'timestamp'
        elif 'vol' in cl: col_map[c] = 'volume'
    
    df = df.rename(columns=col_map)
    
    # Verificar que tenemos lo mínimo necesario
    required = ['open', 'high', 'low', 'close']
    missing = [r for r in required if r not in df.columns]
    if missing:
        print(f"❌ Faltan columnas OHLC tras normalización: {missing}")
        print(f"   Columnas disponibles: {list(df.columns)}")
        return
        
    # 3. Calcular indicadores manualmente (bypass total de apply_all_basic)
    try:
        # EMAs básicas
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        
        # ATR 14
        tr = pd.concat([
            df['high'] - df['low'],
            (df['high'] - df['close'].shift()).abs(),
            (df['low'] - df['close'].shift()).abs()
        ], axis=1).max(axis=1)
        df['atr_14'] = tr.rolling(14).mean()
        
        # ADX 14 (simplificado para backtest rápido)
        plus_dm = df['high'].diff()
        minus_dm = -df['low'].diff()
        plus_dm = plus_dm.where((plus_dm > 0) & (plus_dm > minus_dm), 0)
        minus_dm = minus_dm.where((minus_dm > 0) & (minus_dm > plus_dm), 0)
        atr_smooth = tr.rolling(14).mean()
        plus_di = 100 * (plus_dm.rolling(14).mean() / atr_smooth)
        minus_di = 100 * (minus_dm.rolling(14).mean() / atr_smooth)
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        df['adx_14'] = dx.rolling(14).mean()
        
        # Indicadores específicos por par
        if 'AUD' in symbol:
            if 'timestamp' in df.columns:
                df = df.set_index('timestamp')
                
        elif 'XAU' in symbol:
            # RSI 14
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            df['rsi_14'] = 100 - (100 / (1 + rs))
            
            # Bollinger 25, 2.5 std
            sma25 = df['close'].rolling(25).mean()
            std25 = df['close'].rolling(25).std()
            df['bb_upper_25'] = sma25 + (2.5 * std25)
            df['bb_lower_25'] = sma25 - (2.5 * std25)
            
            # VWAP aproximado
            tp = (df['high'] + df['low'] + df['close']) / 3
            df['vwap_daily'] = tp.cumsum() / np.arange(1, len(df)+1)
            
            # EMA 200 H4
            if 'timestamp' in df.columns:
                df = df.set_index('timestamp')
            df_h4 = df.resample('4h').agg({'close':'last'}).dropna()
            if len(df_h4) >= 200:
                ema_h4 = df_h4['close'].ewm(span=200, adjust=False).mean()
                df = df.join(ema_h4.to_frame('ema_200_h4'), how='left')
                df['ema_200_h4'] = df['ema_200_h4'].ffill()
            else:
                df['ema_200_h4'] = np.nan
                
    except Exception as e:
        print(f"❌ Error calculando indicadores: {e}")
        import traceback; traceback.print_exc()
        return
        
    # 4. Generar señales
    signals = strategy_func(df, symbol)
    
    # 5. Métricas
    if not signals:
        print("❌ Sin señales generadas.")
        return
        
    wins = losses = 0
    total_pnl = 0.0
    for sig in signals:
        pnl = (sig.take_profit - sig.entry_price) if sig.signal_type.value == "BUY" else (sig.entry_price - sig.take_profit)
        multiplier = 100 if 'XAU' in symbol else 10000 
        pnl_usd = pnl * multiplier * 0.1 
        
        if pnl > 0: wins += 1
        else: losses += 1
        total_pnl += pnl_usd
        
    win_rate = wins / (wins + losses) * 100 if (wins+losses) > 0 else 0
    pf = wins / losses if losses > 0 else float('inf')
    
    print(f"✅ Resultados:")
    print(f"   Trades: {len(signals)} | Win Rate: {win_rate:.1f}% | P&L Total: ${total_pnl:,.2f}")
    print(f"   Profit Factor: {pf:.2f} | {'🟢 APROBADO' if pf > 1.3 and win_rate > 45 else '🔴 REQUIERE AJUSTE'}")

if __name__ == "__main__":
    mt5_connector.connect()
    validate_strategy(SignalGenerator.aud_trend_strategy, "AUDUSD")
    validate_strategy(SignalGenerator.xau_breakout_atr, "XAUUSD")
    ##validate_strategy(SignalGenerator.xau_vwap_reversion, "XAUUSD")
    mt5_connector.disconnect()