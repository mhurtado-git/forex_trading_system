import pandas as pd
import numpy as np
from src.data.data_fetcher import DataFetcher
from src.trading.broker_mt5 import mt5_connector
from src.analysis.signals import SignalGenerator

# CONFIGURACIÓN DE COSTOS REALISTAS PARA JPY
SPREAD_PIPS = 0.3      # Spread típico en cuenta demo/real estándar
SLIPPAGE_PIPS = 0.2    # Deslizamiento promedio en ejecución
MAX_BARS_HOLD = 200    # Límite máximo de velas (~8 días en H1)

def validate_strategy(strategy_func, symbol, bars=5000):
    """
    Backtesting robusto con simulación barra-por-barra, costos reales y límite temporal.
    Soporta TP Fijos y Trailing Stop Dinámico (EMA 21).
    """
    print(f"\n🔍 Validando {strategy_func.__name__} en {symbol} ({bars} velas)...")
    
    # 1. Obtener datos
    df = DataFetcher(mt5_connector).get_historical_data(symbol, "H1", bars)
    if df is None or df.empty:
        print("❌ No se obtuvieron datos.")
        return
    
    # 2. Normalizar columnas
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
    required = ['open', 'high', 'low', 'close']
    missing = [r for r in required if r not in df.columns]
    if missing:
        print(f"❌ Faltan columnas OHLC: {missing}")
        return
        
    # 3. Calcular indicadores base
    try:
        df['ema_9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['ema_21'] = df['close'].ewm(span=21, adjust=False).mean()
        
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
        
        # Indicadores específicos
        if 'XAU' in symbol:
            delta = df['close'].diff()
            gain = delta.where(delta > 0, 0).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            rs = gain / loss
            df['rsi_14'] = 100 - (100 / (1 + rs))
            
        if 'JPY' in symbol:
             df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
            
    except Exception as e:
        print(f"❌ Error calculando indicadores: {e}")
        return
        
    # 4. Generar señales
    signals = strategy_func(df, symbol)
    if not signals:
        print("❌ Sin señales generadas.")
        return
        
    # 5. SIMULACIÓN BARRA POR BARRA CON COSTOS REALES Y PRIORIDAD CORRECTA
    wins = losses = draws = timeouts = 0
    total_pnl = 0.0
    gross_profit = 0.0
    gross_loss = 0.0
    
    for sig in signals:
        # Encontrar índice de la vela de señal
        entry_idx = None
        if hasattr(sig, 'timestamp') and sig.timestamp in df.index:
            entry_idx = df.index.get_loc(sig.timestamp)
        else:
            matches = df[df['close'] == sig.entry_price].index
            if len(matches) > 0:
                entry_idx = matches[0]
                
        if entry_idx is None or entry_idx >= len(df) - 1:
            continue
            
        # ENTRAR EN LA SIGUIENTE VELA (Evitar Look-ahead bias)
        next_candle = df.iloc[entry_idx + 1]
        real_entry = next_candle['open']
        
        # APLICAR SPREAD Y SLIPPAGE A LA ENTRADA
        if sig.signal_type.value == "BUY":
            real_entry += (SPREAD_PIPS + SLIPPAGE_PIPS) * 0.01
        else:
            real_entry -= (SPREAD_PIPS + SLIPPAGE_PIPS) * 0.01
        
        # Determinar si usa TP Fijo o Trailing Stop
        use_trailing_stop = (sig.take_profit is None or sig.take_profit == -1)
        
        # Calcular SL Real (basado en distancia original)
        if sig.signal_type.value == "BUY":
            sl_dist = sig.entry_price - sig.stop_loss
            actual_sl = real_entry - sl_dist
            actual_tp = real_entry + (sig.take_profit - sig.entry_price) if not use_trailing_stop else None
        else:
            sl_dist = sig.stop_loss - sig.entry_price
            actual_sl = real_entry + sl_dist
            actual_tp = real_entry - (sig.entry_price - sig.take_profit) if not use_trailing_stop else None
            
        # Buscar salida en velas futuras CON LÍMITE DE DURACIÓN
        hit_tp = False
        hit_sl = False
        hit_trailing = False
        hit_timeout = False
        exit_price = 0
        
        start_search = entry_idx + 2
        end_search = min(start_search + MAX_BARS_HOLD, len(df))
        
        for j in range(start_search, end_search):
            future_row = df.iloc[j]
            
            if sig.signal_type.value == "BUY":
                # PRIORIDAD 1: SL Catastrófico (SIEMPE PRIMERO)
                if future_row['low'] <= actual_sl:
                    hit_sl = True
                    exit_price = actual_sl
                    break
                    
                # PRIORIDAD 2: TP Fijo
                elif not use_trailing_stop and actual_tp is not None and future_row['high'] >= actual_tp:
                    hit_tp = True
                    exit_price = actual_tp
                    break
                
                # PRIORIDAD 3: Trailing Stop (EMA 21)
                elif use_trailing_stop and future_row['close'] < future_row['ema_21']:
                    hit_trailing = True
                    exit_price = future_row['close']
                    break
                    
            else:  # SELL
                # PRIORIDAD 1: SL Catastrófico (SIEMPRE PRIMERO)
                if future_row['high'] >= actual_sl:
                    hit_sl = True
                    exit_price = actual_sl
                    break
                    
                # PRIORIDAD 2: TP Fijo
                elif not use_trailing_stop and actual_tp is not None and future_row['low'] <= actual_tp:
                    hit_tp = True
                    exit_price = actual_tp
                    break
                
                # PRIORIDAD 3: Trailing Stop (EMA 21)
                elif use_trailing_stop and future_row['close'] > future_row['ema_21']:
                    hit_trailing = True
                    exit_price = future_row['close']
                    break
        
        # Aplicar SLIPPAGE A TODAS LAS SALIDAS
        if hit_tp or hit_trailing:
            if sig.signal_type.value == "BUY":
                exit_price -= SLIPPAGE_PIPS * 0.01
            else:
                exit_price += SLIPPAGE_PIPS * 0.01
        elif hit_sl:
            # En SL, el slippage suele ser peor (en contra)
            if sig.signal_type.value == "BUY":
                exit_price -= SLIPPAGE_PIPS * 0.01 * 2  # Doble slippage en stops
            else:
                exit_price += SLIPPAGE_PIPS * 0.01 * 2
        
        # Si salió del bucle por tiempo límite, cerrar al market
        if not (hit_tp or hit_sl or hit_trailing):
            hit_timeout = True
            exit_price = df.iloc[end_search - 1]['close']
            if sig.signal_type.value == "BUY":
                exit_price -= SLIPPAGE_PIPS * 0.01
            else:
                exit_price += SLIPPAGE_PIPS * 0.01
        
        # Calcular P&L REAL
        pnl_price = 0.0
        if hit_tp or hit_trailing:
            pnl_price = abs(exit_price - real_entry)
            wins += 1
            gross_profit += pnl_price
        elif hit_sl:
            pnl_price = -abs(actual_sl - real_entry)
            losses += 1
            gross_loss += abs(pnl_price)
        elif hit_timeout:
            # Cierre por tiempo: puede ser ganancia o pérdida pequeña
            pnl_price = exit_price - real_entry if sig.signal_type.value == "BUY" else real_entry - exit_price
            if pnl_price > 0:
                wins += 1
                gross_profit += pnl_price
            else:
                losses += 1
                gross_loss += abs(pnl_price)
        else:
            draws += 1
            continue
            
        # Convertir a USD aproximado
        if 'JPY' in symbol:
            pnl_usd = pnl_price * 1000 * 0.01 * 0.1 
        elif 'XAU' in symbol:
            pnl_usd = pnl_price * 100 * 0.1
        else:
            pnl_usd = pnl_price * 10000 * 0.1
            
        total_pnl += pnl_usd
        
    # 6. Métricas Finales
    total_trades = wins + losses
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
    pf = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
    
    print(f"✅ Resultados Reales (Spread {SPREAD_PIPS}pip + Slippage {SLIPPAGE_PIPS}pip):")
    print(f"   Trades Cerrados: {total_trades} | Timeouts: {timeouts} | Draws: {draws}")
    print(f"   Win Rate: {win_rate:.1f}% | P&L Total: ${total_pnl:,.2f}")
    print(f"   Profit Factor: {pf:.2f} | {'🟢 APROBADO' if pf > 1.3 and win_rate > 45 else '🔴 REQUIERE AJUSTE'}")

if __name__ == "__main__":
    if not mt5_connector.connect():
        print("[ERROR] No se pudo conectar a MT5")
        exit(1)
        
    validate_strategy(SignalGenerator.aud_trend_strategy, "AUDUSD", bars=5000)
    validate_strategy(SignalGenerator.xau_breakout_atr, "XAUUSD", bars=5000)
    validate_strategy(SignalGenerator.usdjpy_trend_pullback, "USDJPY", bars=5000)
    
    mt5_connector.disconnect()