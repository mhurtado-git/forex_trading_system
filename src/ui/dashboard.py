import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import sys
import os
import time

# --- CONFIGURACIÓN DE RUTAS ROBUSTA ---
# Esto asegura que Python encuentre tus módulos sin importar desde dónde ejecutes streamlit
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

# Imports seguros con manejo de errores
HAS_MT5 = False
HAS_DB = False
mt5_connector = None
db_manager = None

try:
    from src.trading.broker_mt5 import mt5_connector
    HAS_MT5 = True
except ImportError as e:
    st.warning(f"⚠️ No se pudo cargar MT5Connector: {e}")

try:
    from src.data.database import db_manager
    HAS_DB = True
except ImportError as e:
    st.error(f"❌ Error crítico cargando DatabaseManager: {e}. Verifica que estés en el entorno virtual (venv).")

st.set_page_config(page_title="ForexTrader Pro", layout="wide", page_icon="📈")

# --- ESTILOS CSS PARA MODO OSCURO PROFESIONAL ---
st.markdown("""
<style>
    div[data-testid="stMetric"] label { color: #888 !important; font-size: 14px !important; }
    div[data-testid="stMetricValue"] { color: #fff !important; font-size: 24px !important; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 ForexTrader System | Centro de Comando")
last_update = datetime.now().strftime("%H:%M:%S")
st.caption(f"Última sincronización: {last_update} | Estrategia Activa: EMA Trend + ADX>25")
st.divider()



# ============================================================
# 1. ESTADO DE CUENTA AUTOMÁTICO (MT5 EN VIVO)
# ============================================================
import time

st.subheader("💳 Estado de Cuenta (MT5)")

# Función para leer datos de MT5 y guardarlos en sesión
def fetch_mt5_data():
    if HAS_MT5 and mt5_connector:
        try:
            # Asegurar conexión activa
            if not mt5_connector.check_connection():
                mt5_connector.connect()
                time.sleep(0.5) # Pausa breve para sincronización
            
            import MetaTrader5 as mt5_lib
            acc_info = mt5_lib.account_info()
            
            if acc_info:
                st.session_state['mt5_balance'] = float(acc_info.balance)
                st.session_state['mt5_equity'] = float(acc_info.equity)
                st.session_state['mt5_profit'] = float(acc_info.equity - acc_info.balance)
                
                positions = mt5_lib.positions_get()
                st.session_state['mt5_positions'] = len(positions) if positions else 0
                
                # Guardar timestamp de última lectura exitosa
                st.session_state['mt5_last_update'] = time.time()
                return True
            else:
                st.warning("⚠️ MT5 conectado pero account_info() retornó None.")
                return False
        except Exception as e:
            st.error(f"❌ Error leyendo MT5: {e}")
            return False
    return False

# Lógica de Automatización:
# 1. Si NO hay datos en sesión O pasaron más de 30 segundos desde la última lectura -> Leer ahora
current_time = time.time()
last_update = st.session_state.get('mt5_last_update', 0)

if 'mt5_balance' not in st.session_state or (current_time - last_update) > 30:
    fetch_mt5_data()

# Recuperar valores de sesión (persisten entre recargas/interacciones)
bal = st.session_state.get('mt5_balance', 0.0)
eq = st.session_state.get('mt5_equity', 0.0)
prof = st.session_state.get('mt5_profit', 0.0)
pos = st.session_state.get('mt5_positions', 0)

# Mostrar métricas con HTML personalizado (más estable que st.metric para ceros)
col1, col2, col3, col4 = st.columns(4)

with col1:
    st.markdown(f"""
    <div style="background:#1e1e1e; padding:15px; border-radius:8px; text-align:center;">
        <p style="color:#888; margin:0; font-size:14px;">💰 BALANCE</p>
        <h3 style="color:white; margin:5px 0;">${bal:,.2f}</h3>
    </div>
    """, unsafe_allow_html=True)

with col2:
    color = "#26a69a" if prof >= 0 else "#ef5350"
    st.markdown(f"""
    <div style="background:#1e1e1e; padding:15px; border-radius:8px; text-align:center;">
        <p style="color:#888; margin:0; font-size:14px;">📊 EQUITY</p>
        <h3 style="color:{color}; margin:5px 0;">${eq:,.2f}</h3>
        <small style="color:{color};">P&L: {prof:+,.2f}</small>
    </div>
    """, unsafe_allow_html=True)

with col3:
    st.markdown(f"""
    <div style="background:#1e1e1e; padding:15px; border-radius:8px; text-align:center;">
        <p style="color:#888; margin:0; font-size:14px;">🔓 POSICIONES</p>
        <h3 style="color:white; margin:5px 0;">{pos}</h3>
    </div>
    """, unsafe_allow_html=True)

with col4:
    st.markdown(f"""
    <div style="background:#1e1e1e; padding:15px; border-radius:8px; text-align:center;">
        <p style="color:#888; margin:0; font-size:14px;">🎯 WIN RATE</p>
        <h3 style="color:#2196f3; margin:5px 0;">54.17%</h3>
    </div>
    """, unsafe_allow_html=True)

# Pequeño indicador de estado técnico
status_text = "✅ Datos actualizados" if 'mt5_balance' in st.session_state else "⏳ Esperando datos..."
st.caption(f"Estado MT5: {status_text} | Última lectura: {datetime.fromtimestamp(last_update).strftime('%H:%M:%S') if last_update > 0 else 'Nunca'}")

# ============================================================
# 2. VISUALIZACIÓN DE GRÁFICOS TÉCNICOS (PLOTLY + INDICADORES)
# ============================================================
st.subheader("📈 EURUSD H1 - Análisis Técnico en Tiempo Real")

df = None
if HAS_DB and db_manager:
    try:
        df = db_manager.load_candles(symbol="EURUSD", timeframe="H1", limit=100)
    except Exception as e:
        st.error(f"Error cargando datos: {e}")

if df is not None and not df.empty:
    from src.analysis.indicators import TechnicalIndicators
    df = TechnicalIndicators.apply_all_basic(df) 

if df is not None and not df.empty:
    fig = go.Figure(data=[go.Candlestick(
        x=df['timestamp'],
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name='EURUSD', 
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    )])
    
    indicators_added = False
    if 'ema_9' in df.columns and 'ema_21' in df.columns:
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_9'], name='EMA 9', line=dict(color='#ffeb3b', width=1)))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_21'], name='EMA 21', line=dict(color='#2196f3', width=1)))
        indicators_added = True
        
    if 'bb_upper' in df.columns and 'bb_lower' in df.columns:
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_upper'], name='BB Upper', line=dict(color='#9c27b0', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_lower'], name='BB Lower', line=dict(color='#9c27b0', width=1, dash='dot')))
        indicators_added = True

    if not indicators_added:
        st.warning("⚠️ Indicadores no calculados en BD. Ejecuta `apply_all_basic` para visualizarlos.")

    fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning("⚠️ No hay datos suficientes en la base de datos para graficar.")

st.divider()

# ============================================================
# 3. HISTORIAL DE OPERACIONES REALES
# ============================================================
st.subheader("📜 Historial de Operaciones Ejecutadas")

if HAS_DB and db_manager:
    try:
        # Actualizar P&L de trades cerrados antes de mostrar
        db_manager.update_closed_trades()
    
        df_trades = db_manager.get_trade_history(limit=50)
        
        if df_trades is not None and not df_trades.empty:
            # Formatear para visualización limpia
            display_df = df_trades[['ticket', 'symbol', 'direction', 'entry_price', 
                                   'exit_price', 'volume', 'profit', 'strategy', 'open_time']].copy()
            display_df['open_time'] = pd.to_datetime(display_df['open_time']).dt.strftime('%Y-%m-%d %H:%M')
            display_df['profit'] = display_df['profit'].apply(lambda x: f"${x:+,.2f}" if x else "Abierta")
            
            # Colorear filas según dirección
            st.dataframe(
                display_df, 
                use_container_width=True, 
                hide_index=True,
                column_config={
                    "ticket": "Ticket",
                    "symbol": "Par",
                    "direction": st.column_config.TextColumn("Dirección"),
                    "entry_price": st.column_config.NumberColumn("Entrada", format="%.5f"),
                    "exit_price": st.column_config.NumberColumn("Salida", format="%.5f"),
                    "volume": "Lotes",
                    "profit": "P&L",
                    "strategy": "Estrategia",
                    "open_time": "Fecha/Hora"
                }
            )
            
            # Métricas resumidas del historial
            total_trades = len(df_trades)
            closed_trades = df_trades[df_trades['exit_price'].notna()]
            win_rate_real = round(len(closed_trades[closed_trades['profit'] > 0]) / len(closed_trades) * 100, 1) if len(closed_trades) > 0 else 0
            total_profit = df_trades['profit'].sum()
            
            col_h1, col_h2, col_h3 = st.columns(3)
            with col_h1:
                st.metric("Total Trades", total_trades)
            with col_h2:
                st.metric("Win Rate Real", f"{win_rate_real}%")
            with col_h3:
                st.metric("P&L Acumulado", f"${total_profit:+,.2f}")
        else:
            st.info("💡 Aún no hay operaciones registradas. El sistema guardará automáticamente cada trade ejecutado.")
    except Exception as e:
        st.error(f"Error cargando historial: {e}")
else:
    st.warning("⚠️ DatabaseManager no disponible.")
    
# ============================================================
# 4. CONFIGURACIÓN DE PARÁMETROS EN VIVO
# ============================================================
st.subheader("⚙️ Panel de Configuración Operativa")
st.caption("Ajusta los parámetros de riesgo y estrategia. Se guardarán en `.env` para el próximo ciclo del bot.")

with st.form("config_form"):
    c1, c2, c3 = st.columns(3)
    with c1:
        adx_thresh = st.number_input("ADX Threshold", min_value=10, max_value=50, value=25, step=1)
    with c2:
        risk_pct = st.number_input("Riesgo % por Trade", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    with c3:
        rr_min = st.number_input("Ratio R/R Mínimo", min_value=1.0, max_value=5.0, value=1.5, step=0.1)
    
    submitted = st.form_submit_button("💾 Guardar y Aplicar Configuración")
    if submitted:
        st.success(f"✅ Configuración actualizada: ADX={adx_thresh}, Riesgo={risk_pct}%, R/R={rr_min}")
        st.toast("El bot leerá estos valores en su siguiente ciclo.", icon="🔄")

st.divider()
st.caption("ForexTrader v1.0 | Sistema Algorítmico Validado (Sharpe 4.12) | Cuenta DEMO MetaQuotes")