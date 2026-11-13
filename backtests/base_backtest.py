# backtests/base_backtest.py
import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional

class HonestBacktester:
    """Motor de backtesting brutalmente honesto reutilizable."""
    
    def __init__(self, symbol: str, spread_pips: float = 0.3, max_bars_hold: int = 200):
        self.symbol = symbol
        self.spread_pips = spread_pips
        self.max_bars_hold = max_bars_hold
        
        # Configuración específica por par
        self.configs = {
            'XAUUSD': {'ts_slippage': 10.0, 'pnl_mult': 100 * 0.1},
            'USDJPY': {'ts_slippage': 0.15, 'pnl_mult': 1000 * 0.01},
            'AUDUSD': {'ts_slippage': 0.00015, 'pnl_mult': 10000 * 0.0001}
        }
        
        cfg = self.configs.get(symbol, {'ts_slippage': 0.15, 'pnl_mult': 10000 * 0.0001})
        self.ts_slippage = cfg['ts_slippage']
        self.pnl_mult = cfg['pnl_mult']

    def run(self, df: pd.DataFrame, signals: List[Any], 
            use_realtime_ema_validation: bool = True) -> Dict[str, Any]:
        """Ejecuta simulación barra-por-barra con honestidad total."""
        wins = losses = draws = timeouts = 0
        total_pnl = gross_profit = gross_loss = 0.0
        
        for sig in signals:
            entry_idx = None
            if hasattr(sig, 'timestamp') and sig.timestamp in df.index:
                entry_idx = df.index.get_loc(sig.timestamp)
            else:
                matches = df[df['close'] == sig.entry_price].index
                if len(matches) > 0:
                    entry_idx = matches[0]
                    
            if entry_idx is None or entry_idx >= len(df) - 1:
                continue
                
            # ✅ REVALIDACIÓN DE ENTRADA CON EMA REAL-TIME (Opcional)
            if use_realtime_ema_validation and entry_idx >= 21:
                window_entry = df['close'].iloc[max(0, entry_idx-20):entry_idx+1]
                real_ema_21_at_signal = window_entry.ewm(span=21, adjust=False).mean().iloc[-1]
                
                if sig.signal_type.value == "BUY":
                    if not (df.iloc[entry_idx]['close'] > df.iloc[entry_idx]['ema_200'] and 
                            real_ema_21_at_signal > df.iloc[entry_idx]['ema_200']):
                        continue
                elif sig.signal_type.value == "SELL":
                    if not (df.iloc[entry_idx]['close'] < df.iloc[entry_idx]['ema_200'] and 
                            real_ema_21_at_signal < df.iloc[entry_idx]['ema_200']):
                        continue
            
            next_candle = df.iloc[entry_idx + 1]
            real_entry = next_candle['open']
            
            if sig.signal_type.value == "BUY":
                real_entry += self.spread_pips * 0.01
            else:
                real_entry -= self.spread_pips * 0.01
            
            use_trailing_stop = (sig.take_profit is None or sig.take_profit == -1)
            
            if sig.signal_type.value == "BUY":
                sl_dist = sig.entry_price - sig.stop_loss
                actual_sl = real_entry - sl_dist
                actual_tp = real_entry + (sig.take_profit - sig.entry_price) if not use_trailing_stop else None
            else:
                sl_dist = sig.stop_loss - sig.entry_price
                actual_sl = real_entry + sl_dist
                actual_tp = real_entry - (sig.entry_price - sig.take_profit) if not use_trailing_stop else None
                
            hit_tp = hit_sl = hit_trailing = hit_timeout = False
            exit_price = 0
            
            start_search = entry_idx + 2
            end_search = min(start_search + self.max_bars_hold, len(df))
            
            for j in range(start_search, end_search):
                future_row = df.iloc[j]
                
                # ✅ EMA 21 EN TIEMPO REAL PARA SALIDAS
                if j >= 21:
                    window = df['close'].iloc[max(0, j-20):j+1]
                    current_ema_21 = window.ewm(span=21, adjust=False).mean().iloc[-1]
                else:
                    current_ema_21 = np.nan
                    
                if pd.isna(current_ema_21):
                    continue
                
                if sig.signal_type.value == "BUY":
                    if future_row['low'] <= actual_sl:
                        hit_sl = True; exit_price = actual_sl; break
                    elif not use_trailing_stop and actual_tp and future_row['high'] >= actual_tp:
                        hit_tp = True; exit_price = actual_tp; break
                    elif use_trailing_stop and future_row['low'] <= current_ema_21:
                        hit_trailing = True; exit_price = current_ema_21 - self.ts_slippage; break
                else:
                    if future_row['high'] >= actual_sl:
                        hit_sl = True; exit_price = actual_sl; break
                    elif not use_trailing_stop and actual_tp and future_row['low'] <= actual_tp:
                        hit_tp = True; exit_price = actual_tp; break
                    elif use_trailing_stop and future_row['high'] >= current_ema_21:
                        hit_trailing = True; exit_price = current_ema_21 + self.ts_slippage; break
            
            # Slippage en salidas no-TS
            if hit_tp:
                exit_price -= (self.spread_pips * 0.01) if sig.signal_type.value == "BUY" else -(self.spread_pips * 0.01)
            elif hit_sl:
                exit_price -= (self.spread_pips * 0.01 * 2) if sig.signal_type.value == "BUY" else -(self.spread_pips * 0.01 * 2)
            elif hit_timeout:
                hit_timeout = True
                exit_price = df.iloc[end_search - 1]['close']
                exit_price -= (self.spread_pips * 0.01) if sig.signal_type.value == "BUY" else -(self.spread_pips * 0.01)
            
            # ✅ P&L DIRECCIONAL (SIN ABS CIEGO)
            pnl_price = (exit_price - real_entry) if sig.signal_type.value == "BUY" else (real_entry - exit_price)
            
            if hit_tp or hit_trailing:
                if pnl_price > 0: wins += 1; gross_profit += pnl_price
                else: losses += 1; gross_loss += abs(pnl_price)
            elif hit_sl:
                losses += 1; gross_loss += abs(pnl_price)
            elif hit_timeout:
                if pnl_price > 0: wins += 1; gross_profit += pnl_price
                else: losses += 1; gross_loss += abs(pnl_price)
            else:
                draws += 1; continue
                
            total_pnl += pnl_price * self.pnl_mult
            
        total_trades = wins + losses
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        pf = (gross_profit / gross_loss) if gross_loss > 0 else float('inf')
        
        return {
            'symbol': self.symbol,
            'trades': total_trades,
            'win_rate': win_rate,
            'pnl': total_pnl,
            'profit_factor': pf,
            'approved': pf > 1.3 and win_rate > 45
        }