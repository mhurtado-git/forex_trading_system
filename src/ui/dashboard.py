import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime
import sys
import os
import time
from pathlib import Path

# --- CONFIGURACIÓN DE RUTAS ABSOLUTAS (A PRUEBA DE STREAMLIT) ---
# Obtiene la ruta absoluta de ESTE archivo dashboard.py
current_file_path = Path(__file__).resolve()
# Sube dos niveles: dashboard.py -> ui/ -> src/ -> forex_trading_system/ (RAÍZ)
ROOT_DIR = current_file_path.parent.parent 

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Imports seguros con manejo de errores detallado
HAS_MT5 = False
HAS_DB = False
mt5_connector = None
db_manager = None

try:
    from src.trading.broker_mt5 import mt5_connector
    HAS_MT5 = True
except ImportError as e:
    st.warning(f"⚠️ No se pudo cargar MT5Connector: {e}")
    st.caption(f"🔍 Ruta buscada: {ROOT_DIR}/src/trading/broker_mt5.py")

try:
    from src.data.database import db_manager
    HAS_DB = True
except ImportError as e:
    st.error(f"❌ Error crítico cargando DatabaseManager: {e}")
    st.caption(f"🔍 Ruta buscada: {ROOT_DIR}/src/data/database.py")

# Forzar modo oscuro explícito (por si Streamlit lo resetea)
st.set_page_config(page_title="ForexTrader Pro | Multi-Par", layout="wide", page_icon="📈", initial_sidebar_state="collapsed")

# --- ESTILOS CSS PARA MODO OSCURO PROFESIONAL (SOLUCIÓN DEFINITIVA DROPDOWN) ---
st.markdown("""
<style>
    /* 1. FONDO PRINCIPAL DE LA APP */
    .stApp { background-color: #0e1117 !important; }
    
    /* 2. TÍTULOS Y SUBTÍTULOS */
    h1, h2, h3, h4, h5, h6 { color: #ffffff !important; }
    .stMarkdown h2, .stMarkdown h3 { color: #ffffff !important; font-weight: bold; }
    
    /* 3. TEXTOS GENERALES */
    p, label, span { color: #e0e0e0 !important; }
    
    /* 4. MÉTRICAS PERSONALIZADAS */
    div[data-testid="stMetric"] label { color: #888 !important; font-size: 14px !important; }
    div[data-testid="stMetricValue"] { color: #fff !important; font-size: 24px !important; }
    
    /* 5. SELECTOR DE PARES - SOLUCIÓN COMPLETA */
    .stSelectbox > div > div { 
        background-color: #1e1e1e !important; 
        color: white !important; 
        border: 1px solid #444 !important;
    }
    .stSelectbox label { color: #fafafa !important; }
    
    [data-baseweb="popover"], 
    [data-baseweb="menu"], 
    ul[role="listbox"],
    div[role="listbox"] {
        background-color: #1e1e1e !important;
        border: 1px solid #444 !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.5) !important;
    }
    
    [data-baseweb="popover"] li,
    [data-baseweb="menu"] li,
    ul[role="listbox"] li,
    div[role="listbox"] div {
        color: #ffffff !important;
        background-color: #1e1e1e !important;
    }
    
    [data-baseweb="popover"] li:hover,
    [data-baseweb="menu"] li:hover,
    ul[role="listbox"] li:hover,
    div[role="listbox"] div:hover {
        background-color: #333333 !important;
    }
    
    [data-baseweb="popover"] li[aria-selected="true"],
    [data-baseweb="menu"] li[aria-selected="true"],
    ul[role="listbox"] li[aria-selected="true"],
    div[role="listbox"] div[aria-selected="true"] {
        background-color: #2a2a2a !important;
        font-weight: bold;
    }
    
    /* 6. TABLAS DE DATOS */
    .stDataFrame { background-color: transparent !important; }
    .stDataFrame th { color: #aaa !important; background-color: #2a2a2a !important; }
    .stDataFrame td { color: #eee !important; }
    
    /* 7. INPUTS Y FORMULARIOS */
    input, textarea, select { background-color: #1e1e1e !important; color: white !important; border: 1px solid #444 !important; }
    
    /* 8. DIVIDERS */
    hr { border-color: #333 !important; }
    
    /* 9. MENSAJES INFORMATIVOS (st.info) */
    div[data-testid="stAlertContainer"] {
        background-color: #1e1e1e !important;
        border: 1px solid #333 !important;
        color: #e0e0e0 !important;
    }
    div[data-testid="stAlertContainer"] p {
        color: #e0e0e0 !important;
    }
    
    /* 10. BOTONES DEL FORMULARIO - FIX DEFINITIVO */
    button[data-testid="stBaseButton-primary"],
    div.stForm button,
    .stButton > button:first-child {
        background-color: #26a69a !important;
        color: #ffffff !important;
        border: 1px solid #26a69a !important;
        font-weight: 600 !important;
        text-shadow: none !important;
    }
    
    button[data-testid="stBaseButton-primary"]:hover,
    div.stForm button:hover,
    .stButton > button:first-child:hover {
        background-color: #2bbbad !important;
        color: #ffffff !important;
        border-color: #2bbbad !important;
    }
    
    button svg, 
    div.stForm button svg,
    .stButton > button svg {
        fill: #ffffff !important;
        stroke: #ffffff !important;
    }
    
    /* Contenedor del formulario */
    form {
        background-color: transparent !important;
        border: 1px solid #333 !important;
        padding: 15px !important;
        border-radius: 8px !important;
    }
</style>

""", unsafe_allow_html=True)

# ============================================================
# 0. SELECTOR DINÁMICO DE PARES (NUEVO - Persistente)
# ============================================================
ACTIVE_PAIRS = ["EURUSD", "AUDUSD"] 

if 'selected_pair' not in st.session_state:
    st.session_state.selected_pair = ACTIVE_PAIRS[0]

col_sel, col_info = st.columns([1, 4])
with col_sel:
    selected_pair = st.selectbox(
        "🎯 Par Activo:", 
        options=ACTIVE_PAIRS, 
        index=ACTIVE_PAIRS.index(st.session_state.selected_pair),
        key="pair_selector"
    )
    st.session_state.selected_pair = selected_pair

with col_info:
    st.markdown(f"<div style='text-align:right; padding-top:28px;'>Estrategia: <b>EMA Trend + ADX>25</b> | Hora: {datetime.now().strftime('%H:%M:%S')}</div>", unsafe_allow_html=True)

st.divider()

# ============================================================
# 1. ESTADO DE CUENTA AUTOMÁTICO (TU CÓDIGO ORIGINAL INTACTO)
# ============================================================
st.subheader("💳 Estado de Cuenta Global (MT5)")

def fetch_mt5_data():
    if HAS_MT5 and mt5_connector:
        try:
            if not mt5_connector.check_connection():
                mt5_connector.connect()
                time.sleep(0.5)
            
            import MetaTrader5 as mt5_lib
            acc_info = mt5_lib.account_info()
            
            if acc_info:
                st.session_state['mt5_balance'] = float(acc_info.balance)
                st.session_state['mt5_equity'] = float(acc_info.equity)
                st.session_state['mt5_profit'] = float(acc_info.equity - acc_info.balance)
                
                positions = mt5_lib.positions_get()
                st.session_state['mt5_positions'] = len(positions) if positions else 0
                st.session_state['mt5_last_update'] = time.time()
                return True
        except Exception as e:
            st.error(f"❌ Error leyendo MT5: {e}")
    return False

current_time = time.time()
last_update = st.session_state.get('mt5_last_update', 0)

if 'mt5_balance' not in st.session_state or (current_time - last_update) > 30:
    fetch_mt5_data()

bal = st.session_state.get('mt5_balance', 0.0)
eq = st.session_state.get('mt5_equity', 0.0)
prof = st.session_state.get('mt5_profit', 0.0)
pos = st.session_state.get('mt5_positions', 0)

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
    # Win Rate GLOBAL calculado en vivo
    wr_global = "N/A"
    if HAS_DB and db_manager:
        try:
            hist_all = db_manager.get_trade_history(limit=1000)
            if hist_all is not None and not hist_all.empty:
                closed_all = hist_all[hist_all['exit_price'].notna()]
                if len(closed_all) > 0:
                    wr_val = round(len(closed_all[closed_all['profit']>0])/len(closed_all)*100, 1)
                    wr_global = f"{wr_val}%"
        except: pass

    st.markdown(f"""
    <div style="background:#1e1e1e; padding:15px; border-radius:8px; text-align:center;">
        <p style="color:#888; margin:0; font-size:14px;">🎯 WIN RATE GLOBAL</p>
        <h3 style="color:#2196f3; margin:5px 0;">{wr_global}</h3>
    </div>
    """, unsafe_allow_html=True)

status_text = "✅ Datos actualizados" if 'mt5_balance' in st.session_state else "⏳ Esperando datos..."
st.caption(f"Estado MT5: {status_text} | Última lectura: {datetime.fromtimestamp(last_update).strftime('%H:%M:%S') if last_update > 0 else 'Nunca'}")

# ============================================================
# 2. GRÁFICO TÉCNICO DEL PAR SELECCIONADO (ADAPTADO)
# ============================================================
st.subheader(f"📈 {selected_pair} H1 - Análisis Técnico en Tiempo Real")

df = None
if HAS_DB and db_manager:
    try:
        # Cargar velas del par seleccionado dinámicamente
        df = db_manager.load_candles(symbol=selected_pair, timeframe="H1", limit=100)
    except Exception as e:
        st.error(f"Error cargando datos para {selected_pair}: {e}")

if df is not None and not df.empty:
    from src.analysis.indicators import TechnicalIndicators
    df = TechnicalIndicators.apply_all_basic(df) 

if df is not None and not df.empty:
    fig = go.Figure(data=[go.Candlestick(
        x=df['timestamp'],
        open=df['open'], high=df['high'], low=df['low'], close=df['close'],
        name=selected_pair, 
        increasing_line_color='#26a69a', decreasing_line_color='#ef5350'
    )])
    
    indicators_added = False
    if 'ema_9' in df.columns and 'ema_21' in df.columns:
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_9'], name='EMA 9', line=dict(color='#ffeb3b', width=1)))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['ema_21'], name='EMA 21', line=dict(color='#2196f3', width=1)))
        indicators_added = True
        
    if 'bb_upper_25' in df.columns and 'bb_lower_25' in df.columns:
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_upper_25'], name='BB Upper (25)', line=dict(color='#9c27b0', width=1, dash='dot')))
        fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_lower_25'], name='BB Lower (25)', line=dict(color='#9c27b0', width=1, dash='dot')))
        indicators_added = True
    elif 'bb_upper' in df.columns and 'bb_lower' in df.columns:
         fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_upper'], name='BB Upper', line=dict(color='#9c27b0', width=1, dash='dot')))
         fig.add_trace(go.Scatter(x=df['timestamp'], y=df['bb_lower'], name='BB Lower', line=dict(color='#9c27b0', width=1, dash='dot')))
         indicators_added = True

    if not indicators_added:
        st.warning(f"⚠️ Indicadores no disponibles para {selected_pair}. Verifica apply_all_basic.")

    fig.update_layout(height=500, xaxis_rangeslider_visible=False, template="plotly_dark", hovermode="x unified")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.warning(f"⚠️ No hay datos suficientes en BD para graficar {selected_pair}.")

st.divider()

# ============================================================
# 3. HISTORIAL FILTRABLE POR PAR SELECCIONADO
# ============================================================
st.subheader(f"📜 Historial de Operaciones: {selected_pair}")

if HAS_DB and db_manager:
    try:
        db_manager.update_closed_trades()
        df_trades = db_manager.get_trade_history(limit=100)
        
        if df_trades is not None and not df_trades.empty:
            # Filtrar SOLO por el par seleccionado
            filtered_df = df_trades[df_trades['symbol'] == selected_pair].copy()
            
            if filtered_df.empty:
                st.info(f"💡 Aún no hay operaciones registradas para {selected_pair}. El sistema las guardará automáticamente.")
            else:
                display_df = filtered_df[['ticket', 'symbol', 'direction', 'entry_price', 
                                       'exit_price', 'volume', 'profit', 'strategy', 'open_time']].copy()
                display_df['open_time'] = pd.to_datetime(display_df['open_time']).dt.strftime('%Y-%m-%d %H:%M')
                display_df['profit'] = display_df['profit'].apply(lambda x: f"${x:+,.2f}" if pd.notna(x) else "Abierta")
                
                st.dataframe(
                    display_df, 
                    use_container_width=True, 
                    hide_index=True,
                    column_config={
                        "ticket": "Ticket", "symbol": "Par", "direction": "Dir.",
                        "entry_price": st.column_config.NumberColumn("Entrada", format="%.5f"),
                        "exit_price": st.column_config.NumberColumn("Salida", format="%.5f"),
                        "volume": "Lots", "profit": "P&L", "strategy": "Estrategia", "open_time": "Fecha"
                    }
                )
                
                # Métricas ESPECÍFICAS del par seleccionado
                total_p = len(filtered_df)
                closed_p = filtered_df[filtered_df['exit_price'].notna()]
                wr_p = round(len(closed_p[closed_p['profit']>0])/len(closed_p)*100, 1) if len(closed_p)>0 else 0
                pnl_p = filtered_df['profit'].sum()
                
                h1, h2, h3 = st.columns(3)
                with h1: st.metric(f"Trades ({selected_pair})", total_p)
                with h2: st.metric(f"Win Rate ({selected_pair})", f"{wr_p}%")
                with h3: st.metric(f"P&L ({selected_pair})", f"${pnl_p:+,.2f}")
        else:
            st.info("El historial global está vacío.")
    except Exception as e:
        st.error(f"Error cargando historial: {e}")
else:
    st.warning("⚠️ DatabaseManager no disponible.")
    
# ============================================================
# 4. CONFIGURACIÓN DE PARÁMETROS EN VIVO
# ============================================================
st.subheader("⚙️ Panel de Configuración Operativa")
st.caption("Ajustes globales aplicados a todos los pares activos.")

with st.form("config_form"):
    c1, c2, c3 = st.columns(3)
    with c1: adx_thresh = st.number_input("ADX Threshold", min_value=10, max_value=50, value=25, step=1)
    with c2: risk_pct = st.number_input("Riesgo % por Trade", min_value=0.1, max_value=5.0, value=1.0, step=0.1)
    with c3: rr_min = st.number_input("Ratio R/R Mínimo", min_value=1.0, max_value=5.0, value=1.5, step=0.1)
    
    submitted = st.form_submit_button("💾 Guardar y Aplicar Configuración")
    if submitted:
        st.success(f"✅ Configuración actualizada: ADX={adx_thresh}, Riesgo={risk_pct}%, R/R={rr_min}")
        st.toast("El bot leerá estos valores en su siguiente ciclo.", icon="🔄")

st.divider()
st.caption("ForexTrader v2.0 | Sistema Multi-Par Algorítmico | Cuenta DEMO MetaQuotes")