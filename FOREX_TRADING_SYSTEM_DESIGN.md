# DOCUMENTO DE DISEÑO E IMPLEMENTACION
# SISTEMA DE TRADING FOREX AUTOMATIZADO

**Fecha:** Noviembre 2026  
**Version:** 1.0  
**Lenguaje:** Python 3.9+  
**IDE:** Visual Studio Code  

---

## INDICE DE CONTENIDOS

1. RESUMEN EJECUTIVO
2. REQUISITOS DEL SISTEMA
3. ARQUITECTURA TECNICA
4. INSTALACION Y CONFIGURACION
5. MODULOS DEL SISTEMA
6. FLUJO DE DATOS
7. ESPECIFICACIONES TECNICAS DETALLADAS
8. PLAN DE IMPLEMENTACION POR FASES
9. PRUEBAS Y VALIDACION
10. DESPLIEGUE Y OPERACION
11. MANTENIMIENTO Y MEJORAS
12. ANEXOS

---

## 1. RESUMEN EJECUTIVO

### Objetivo
Desarrollar un sistema automatizado de trading para Forex que incluya:
- Analisis tecnico automatizado con indicadores personalizables
- Ejecucion automatica de operaciones mediante conexion a broker (MT5)
- Gestion de riesgo integrada
- Sistema de alertas y notificaciones
- Backtesting de estrategias
- Interfaz de usuario basica para monitoreo

### Alcance
- **Mercado:** Forex (pares principales y cruzados)
- **Broker:** MetaTrader 5 (inicialmente)
- **Timeframes:** M1, M5, M15, M30, H1, H4, D1
- **Operacion:** Semi-automatica inicial, completamente automatica posterior

---

## 2. REQUISITOS DEL SISTEMA

### 2.1 REQUISITOS FUNCIONALES

**RF01 - Conexion a Broker**
- Conectar/desconectar de MT5
- Autenticacion segura
- Verificacion de estado de conexion
- Reconexion automatica en caso de fallo

**RF02 - Obtencion de Datos**
- Datos historicos (OHLCV) en multiples timeframes
- Datos en tiempo real via streaming
- Almacenamiento automatico en base de datos
- Actualizacion periodica de datos historicos

**RF03 - Analisis Tecnico**
- Calculo de indicadores tecnicos estandar:
  - Media Movil Simple (SMA)
  - Media Movil Exponencial (EMA)
  - RSI (Relative Strength Index)
  - MACD (Moving Average Convergence Divergence)
  - Bandas de Bollinger
  - ATR (Average True Range)
  - Estocastico
  - ADX (Average Directional Index)
- Indicadores personalizados configurables
- Deteccion de patrones de velas

**RF04 - Generacion de Senales**
- Evaluacion de condiciones de entrada/salida
- Confirmacion multiple de senales
- Filtrado de senales por fuerza/tendencia
- Registro historico de senales generadas

**RF05 - Gestion de Riesgo**
- Calculo automatico de tamano de lote
- Stop Loss dinamico/estatico
- Take Profit configurable
- Trailing Stop
- Limite maximo de operaciones simultaneas
- Limite de perdida diaria/semanal
- Ratio riesgo/beneficio minimo configurable

**RF06 - Ejecucion de Ordenes**
- Envio de ordenes market
- Ordenes pendientes (limit, stop)
- Modificacion de ordenes existentes
- Cierre parcial/total de posiciones
- Verificacion de ejecucion

**RF07 - Backtesting**
- Simulacion historica de estrategias
- Calculo de metricas de rendimiento
- Optimizacion de parametros
- Generacion de reportes

**RF08 - Sistema de Alertas**
- Notificaciones por Telegram
- Alertas por email
- Logs detallados
- Alertas configurables por evento

**RF09 - Interfaz de Usuario**
- Dashboard de monitoreo en tiempo real
- Visualizacion de graficos
- Estado de posiciones abiertas
- Historial de operaciones
- Metricas de rendimiento
- Configuracion de parametros

**RF10 - Gestion de Configuracion**
- Archivo de configuracion centralizado
- Perfiles de estrategia
- Parametros ajustables sin reinicio
- Backup automatico de configuracion

### 2.2 REQUISITOS NO FUNCIONALES

**RNF01 - Rendimiento**
- Latencia maxima de 500ms para ejecucion de ordenes
- Actualizacion de datos en tiempo real < 1 segundo
- Capacidad de procesar 10+ pares simultaneamente

**RNF02 - Confiabilidad**
- Disponibilidad 24/5 (horas de mercado Forex)
- Tolerancia a fallos de conexion
- Recuperacion automatica despues de interrupciones
- Logging completo de todas las operaciones

**RNF03 - Seguridad**
- Credenciales almacenadas de forma segura
- Sin exposicion de datos sensibles en logs
- Validacion de entradas
- Proteccion contra ordenes erroneas

**RNF04 - Escalabilidad**
- Arquitectura modular para agregar nuevos brokers
- Facil incorporacion de nuevas estrategias
- Soporte para multiples cuentas

**RNF05 - Mantenibilidad**
- Codigo documentado
- Estructura clara y organizada
- Separacion de responsabilidades
- Tests unitarios

### 2.3 REQUISITOS TECNICOS

- Python 3.9 o superior
- MetaTrader 5 terminal instalado
- Base de datos PostgreSQL o SQLite
- Conexion a Internet estable
- RAM minima: 4GB (recomendado 8GB)
- Espacio en disco: 10GB minimo

---

## 3. ARQUITECTURA TECNICA

### 3.1 PATRON ARQUITECTONICO

Arquitectura en capas:

- CAPA DE PRESENTACION (UI Dashboard + Notificaciones)
- CAPA DE LOGICA DE NEGOCIO (Estrategias, Senales, Risk Manager)
- CAPA DE SERVICIOS (Broker Connector, Data Fetcher)
- CAPA DE DATOS (Database, Cache, Historical Data)

### 3.2 COMPONENTES PRINCIPALES

**A. Core Engine** - Orquestador principal del sistema

**B. Data Layer**
- DataFetcher: Obtiene datos historicos y en vivo
- DatabaseManager: Gestiona almacenamiento
- DataCache: Cache en memoria para acceso rapido

**C. Analysis Layer**
- IndicatorCalculator: Calcula indicadores tecnicos
- SignalGenerator: Genera senales de trading
- PatternRecognizer: Detecta patrones de velas

**D. Trading Layer**
- BrokerConnector: Interface con MT5
- OrderManager: Gestiona envio/modificacion de ordenes
- PositionManager: Monitorea posiciones abiertas

**E. Risk Management Layer**
- RiskCalculator: Calcula tamanos de posicion
- RiskMonitor: Monitorea exposicion al riesgo
- StopLossManager: Gestiona stops dinamicos

**F. Notification Layer**
- AlertSystem: Sistema central de alertas
- TelegramNotifier: Envia mensajes a Telegram
- EmailNotifier: Envia emails
- Logger: Sistema de logging

**G. UI Layer**
- Dashboard: Interfaz web/desktop
- ChartViewer: Visualizador de graficos
- ConfigPanel: Panel de configuracion

**H. Backtesting Layer**
- BacktestEngine: Motor de simulacion
- PerformanceAnalyzer: Analisis de resultados
- ParameterOptimizer: Optimizacion de parametros

---

## 4. INSTALACION Y CONFIGURACION

### 4.1 ESTRUCTURA DE DIRECTORIOS

forex_trading_system/
- config/ (settings.py, credentials_template.py, strategies.py)
- src/
  - core/ (engine.py, scheduler.py)
  - data/ (data_fetcher.py, database.py, cache.py)
  - analysis/ (indicators.py, signals.py, patterns.py)
  - trading/ (broker_mt5.py, order_manager.py, position_manager.py)
  - risk/ (calculator.py, monitor.py, stop_loss.py)
  - notifications/ (alert_system.py, telegram_bot.py, email_notifier.py)
  - ui/ (dashboard.py, charts.py, config_panel.py)
  - backtesting/ (engine.py, metrics.py, optimizer.py)
- tests/
- logs/
- data/
- docs/
- requirements.txt
- main.py
- .env
- .gitignore
- README.md

### 4.2 REQUIREMENTS.TXT

numpy>=1.21.0
pandas>=1.3.0
scipy>=1.7.0
ta-lib>=0.4.24
pandas-ta>=0.3.14b0
talib-binary>=0.4.24
MetaTrader5>=5.0.45
SQLAlchemy>=1.4.0
psycopg2-binary>=2.9.0
alembic>=1.7.0
websocket-client>=1.2.0
websockets>=10.0
APScheduler>=3.8.0
schedule>=1.1.0
python-telegram-bot>=13.7
requests>=2.26.0
streamlit>=1.10.0
plotly>=5.3.0
dash>=2.0.0
backtrader>=1.9.76
vectorbt>=0.23.0
python-dotenv>=0.19.0
colorlog>=6.6.0
pydantic>=1.8.0
pytest>=6.2.0
pytest-cov>=3.0.0
black>=21.7b0
flake8>=3.9.0
mypy>=0.930

**Nota importante:** ta-lib requiere instalacion previa del sistema:
- **Windows:** Descargar desde https://www.lfd.uci.edu/~gohlke/pythonlibs/
- **Linux:** sudo apt-get install libta-lib0-dev
- **Mac:** brew install ta-lib

### 4.3 CONFIGURACION .ENV

MT5_LOGIN=12345678
MT5_PASSWORD=tu_password
MT5_SERVER=tu_servidor
MT5_PATH=C:/Program Files/MetaTrader 5

DB_TYPE=sqlite
DB_HOST=localhost
DB_PORT=5432
DB_NAME=forex_trading
DB_USER=usuario
DB_PASSWORD=password

TELEGRAM_BOT_TOKEN=tu_token_aqui
TELEGRAM_CHAT_ID=tu_chat_id

EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_USER=tu_email@gmail.com
EMAIL_PASSWORD=tu_app_password

DEFAULT_RISK_PERCENT=1.0
MAX_DAILY_LOSS_PERCENT=3.0
MAX_OPEN_POSITIONS=5
MIN_RISK_REWARD_RATIO=1.5

LOG_LEVEL=INFO
LOG_FILE=logs/trading.log

---

## 5. MODULOS DEL SISTEMA - ESPECIFICACIONES

### 5.1 MODULO: DATA FETCHER

**Responsabilidad:** Obtener y gestionar datos de mercado

**Clases principales:**
- DataFetcher: Clase base para obtencion de datos
- MT5DataFetcher: Implementacion especifica para MT5
- HistoricalDataManager: Gestion de datos historicos

**Base de datos - Tablas necesarias:**

CREATE TABLE symbols (
    id SERIAL PRIMARY KEY,
    symbol VARCHAR(10) UNIQUE NOT NULL,
    description VARCHAR(100),
    active BOOLEAN DEFAULT TRUE
);

CREATE TABLE candles (
    id SERIAL PRIMARY KEY,
    symbol_id INTEGER REFERENCES symbols(id),
    timeframe VARCHAR(5) NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    open DECIMAL(10, 5),
    high DECIMAL(10, 5),
    low DECIMAL(10, 5),
    close DECIMAL(10, 5),
    volume INTEGER,
    UNIQUE(symbol_id, timeframe, timestamp)
);

### 5.2 MODULO: INDICATORS

**Indicadores a implementar:**
1. Media Movil Simple (SMA)
2. Media Movil Exponencial (EMA)
3. RSI (14 periodos por defecto)
4. MACD (12, 26, 9)
5. Bandas de Bollinger (20, 2)
6. ATR (14 periodos)
7. Estocastico (14, 3, 3)
8. ADX (14 periodos)

**Ejemplo de implementacion:**

class TechnicalIndicators:
    @staticmethod
    def calculate_sma(data, period=20):
        return data['close'].rolling(window=period).mean()
    
    @staticmethod
    def calculate_rsi(data, period=14):
        delta = data['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi
    
    @staticmethod
    def calculate_macd(data, fast=12, slow=26, signal=9):
        ema_fast = data['close'].ewm(span=fast).mean()
        ema_slow = data['close'].ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

### 5.3 MODULO: SIGNAL GENERATOR

**Estructura de senal:**

from dataclasses import dataclass
from datetime import datetime

@dataclass
class TradingSignal:
    symbol: str
    signal_type: str  # BUY, SELL, HOLD, CLOSE
    strength: float  # 0-1
    entry_price: float
    stop_loss: float
    take_profit: float
    timestamp: datetime
    strategy_name: str
    confidence: float  # 0-100%

### 5.4 MODULO: RISK MANAGEMENT

**Implementacion:**

class RiskManager:
    def calculate_position_size(self, entry_price, stop_loss, pair):
        risk_amount = self.account_balance * (self.max_risk_percent / 100)
        stop_distance = abs(entry_price - stop_loss)
        pip_value = self.get_pip_value(pair)
        lot_size = risk_amount / (stop_distance * pip_value)
        return round(lot_size, 2)
		
### 5.5 MODULO: BROKER CONNECTOR (MT5)

**Implementacion:**

import MetaTrader5 as mt5

class MT5Connector:
    def connect(self):
        if not mt5.initialize():
            raise Exception("Error inicializando MT5")
        
        authorized = mt5.login(
            login=self.login,
            password=self.password,
            server=self.server
        )
        
        if not authorized:
            raise Exception("Error de autorizacion")
        
        self.connected = True
        return True
    
    def send_market_order(self, symbol, order_type, volume, sl=None, tp=None):
        if order_type == 'BUY':
            action = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(symbol).ask
        else:
            action = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(symbol).bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": action,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        if sl:
            request["sl"] = sl
        if tp:
            request["tp"] = tp
        
        result = mt5.order_send(request)
        return result

### 5.6 MODULO: NOTIFICATIONS

**Implementacion Telegram:**

class TelegramNotifier:
    def send_trade_alert(self, signal):
        message = "Nueva Senal de Trading\n\n"
        message += "Par: " + signal.symbol + "\n"
        message += "Tipo: " + signal.signal_type + "\n"
        message += "Precio Entrada: " + str(signal.entry_price) + "\n"
        message += "Stop Loss: " + str(signal.stop_loss) + "\n"
        message += "Take Profit: " + str(signal.take_profit)
        return self.send_message(message)

### 5.7 MODULO: UI DASHBOARD

**Tecnologia:** Streamlit

import streamlit as st

def create_dashboard():
    st.set_page_config(page_title="Forex Trading System", layout="wide")
    st.title("Forex Trading Dashboard")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Balance", "$10,000.00", "+$250.00")
    with col2:
        st.metric("Posiciones Abiertas", "3")
    with col3:
        st.metric("P&L Hoy", "+$125.50")

### 5.8 MODULO: BACKTESTING

**Framework:** Backtrader

import backtrader as bt

class MAStrategy(bt.Strategy):
    params = (('fast_period', 10), ('slow_period', 30))
    
    def __init__(self):
        self.sma_fast = bt.indicators.SMA(self.data.close, period=self.params.fast_period)
        self.sma_slow = bt.indicators.SMA(self.data.close, period=self.params.slow_period)
    
    def next(self):
        if not self.position:
            if self.sma_fast[0] > self.sma_slow[0]:
                self.buy()
            elif self.sma_fast[0] < self.sma_slow[0]:
                self.sell()
        else:
            if self.position.size > 0 and self.sma_fast[0] < self.sma_slow[0]:
                self.close()

---

## 6. FLUJO DE DATOS

### 6.1 FLUJO PRINCIPAL

1. Obtener datos actuales
2. Calcular indicadores
3. Evaluar senales
4. Verificar gestion de riesgo
5. Ejecutar ordenes si corresponde
6. Actualizar posiciones
7. Enviar notificaciones
8. Esperar intervalo
9. Repetir

### 6.2 FLUJO DE EJECUCION DE ORDEN

1. Signal Generator crea senal
2. Risk Manager valida operacion
3. Si aprobado -> Order Manager envia orden
4. Broker Connector ejecuta en MT5
5. Confirma ejecucion
6. Actualiza base de datos
7. Envia notificacion
8. Registra en log

---

## 7. ESPECIFICACIONES TECNICAS DETALLADAS

### 7.1 MODELO DE DATOS

**Entidades principales:**
- Symbol (Par de divisas)
- Candle (Vela OHLCV)
- TradingSignal
- Order
- Position
- TradeLog

### 7.2 MANEJO DE ERRORES

**Niveles:**
1. CRITICAL: Detiene el sistema
2. ERROR: Operacion fallida, sistema continua
3. WARNING: Situacion anormal recuperable
4. INFO: Informacion operativa normal

---

## 8. PLAN DE IMPLEMENTACION POR FASES

### FASE 1: FUNDAMENTOS (Semana 1-2)
- Configurar entorno de desarrollo
- Instalar dependencias
- Crear estructura de directorios
- Configurar base de datos
- Implementar conexion basica a MT5
- Modulo de obtencion de datos historicos
- Sistema de logging basico

### FASE 2: ANALISIS TECNICO (Semana 3-4)
- Implementar indicadores tecnicos basicos
- Crear framework de estrategias
- Implementar estrategia de ejemplo
- Generador de senales basico
- Pruebas unitarias

### FASE 3: GESTION DE RIESGO (Semana 5)
- Calculadora de tamano de posicion
- Sistema de limites de riesgo
- Validacion de ratio riesgo/beneficio
- Control de drawdown

### FASE 4: EJECUCION DE ORDENES (Semana 6)
- Envio de ordenes market
- Ordenes pending
- Gestion de posiciones abiertas
- Cierre de posiciones
- Pruebas en cuenta DEMO

### FASE 5: NOTIFICACIONES Y UI (Semana 7)
- Configurar bot de Telegram
- Notificaciones de operaciones
- Dashboard basico con Streamlit
- Visualizacion de posiciones
- Reportes diarios automaticos

### FASE 6: BACKTESTING (Semana 8)
- Integrar Backtrader
- Adaptar estrategias para backtesting
- Metricas de rendimiento
- Reportes de backtest

### FASE 7: INTEGRACION Y PRUEBAS (Semana 9-10)
- Integrar todos los modulos
- Pruebas end-to-end en cuenta demo
- Optimizacion de rendimiento
- Documentacion completa

### FASE 8: DESPLIEGUE Y MONITOREO (Semana 11-12)
- Configuracion de servidor/VPS
- Scripts de inicio automatico
- Sistema de monitoreo
- Procedimientos de mantenimiento

---

## 9. PRUEBAS Y VALIDACION

### 9.1 ESTRATEGIA DE PRUEBAS

- Pruebas Unitarias: Cada indicador, calculos de riesgo
- Pruebas de Integracion: Conexion MT5, Base de datos
- Pruebas End-to-End: Flujo completo
- Pruebas de Stress: Multiples pares, alta frecuencia

### 9.2 CRITERIOS DE ACEPTACION

Para pasar a produccion:
- 100+ operaciones exitosas en demo sin errores criticos
- Drawdown maximo dentro de limites establecidos
- Todas las notificaciones funcionando
- Recovery automatico probado
- Documentacion completa

### 9.3 METRICAS DE VALIDACION

**Backtesting:**
- Sharpe Ratio > 1.0
- Win Rate > 50%
- Profit Factor > 1.5
- Max Drawdown < 20%

**Live Trading (Demo):**
- Latencia de ejecucion < 500ms
- Uptime > 99%
- Zero ordenes erroneas

---

## 10. DESPLIEGUE Y OPERACION

### 10.1 REQUISITOS DE SERVIDOR

**VPS Windows (Recomendado):**
- Windows Server 2019+
- 4 GB RAM minimo
- 2 CPU cores
- 50 GB SSD
- Conexion estable < 50ms al broker

### 10.2 PROCEDIMIENTO DE DESPLIEGUE

1. Preparar servidor
2. Instalar Python y dependencias
3. Instalar MT5 terminal
4. Configurar cuenta demo/real
5. Clonar repositorio
6. Configurar variables de entorno
7. Ejecutar migraciones de BD
8. Probar conexion
9. Iniciar en modo demo
10. Monitorear 1 semana
11. Si todo OK, activar modo produccion

### 10.3 MONITOREO

**Metricas a monitorear:**
- Estado de conexion a MT5
- Ultima actualizacion de datos
- Numero de posiciones abiertas
- P&L del dia
- Espacio en disco
- Uso de memoria

---

## 11. MANTENIMIENTO Y MEJORAS

### 11.1 MANTENIMIENTO REGULAR

**Diario:**
- Revisar logs de errores
- Verificar P&L
- Confirmar notificaciones funcionando

**Semanal:**
- Backup de base de datos
- Actualizar datos historicos
- Revisar rendimiento de estrategias

**Mensual:**
- Actualizar dependencias
- Revisar y optimizar estrategias
- Auditoria de seguridad

### 11.2 MEJORAS FUTURAS

**Fase 2.0:**
- Machine Learning para prediccion
- Multiples brokers simultaneos
- Copy trading
- API REST externa

**Fase 3.0:**
- Inteligencia Artificial avanzada
- Analisis de sentimiento de noticias
- Correlacion entre pares

---

## 12. ANEXOS

### ANEXO A: GLOSARIO DE TERMINOS

- **Pip:** Unidad minima de movimiento de precio
- **Spread:** Diferencia entre bid y ask
- **Lot:** Unidad de volumen (1 lot = 100,000 unidades)
- **Leverage:** Apalancamiento
- **Margin:** Margen requerido
- **Drawdown:** Perdida maxima desde pico
- **Slippage:** Diferencia entre precio esperado y ejecutado

### ANEXO B: RECURSOS RECOMENDADOS

**Documentacion:**
- MetaTrader 5 Python API: https://www.mql5.com/en/docs/integration/python_metatrader5
- TA-Lib: https://ta-lib.org/
- Backtrader: https://www.backtrader.com/
- Streamlit: https://docs.streamlit.io/

**Libros:**
- Algorithmic Trading by Ernest Chan
- Building Winning Algorithmic Trading Systems by Kevin Davey

**Comunidades:**
- Reddit: r/algotrading
- Forex Factory forums
- GitHub repositorios de trading

### ANEXO C: CHECKLIST DE SEGURIDAD

- [ ] Credenciales nunca hardcodeadas
- [ ] Uso de variables de entorno
- [ ] .gitignore configurado correctamente
- [ ] Contrasenas fuertes en cuenta de trading
- [ ] 2FA activado en broker si disponible
- [ ] Acceso restringido al servidor
- [ ] Backups regulares y encriptados
- [ ] Logs sin informacion sensible
- [ ] Actualizaciones de seguridad aplicadas

---

## NOTAS FINALES

**Advertencias importantes:**

- Este documento es una guia viva y debe actualizarse conforme evolucione el proyecto
- Todas las decisiones tecnicas deben documentarse
- Mantener comunicacion constante sobre cambios arquitectonicos
- **Priorizar seguridad y gestion de riesgo sobre ganancias**
- **NUNCA operar con dinero real sin extenso testing en demo**

---

**Documento creado:** Noviembre 2026  
**Version:** 1.0  
**Autor:** Sistema de Trading Forex Automatizado  
**Licencia:** Uso interno
		