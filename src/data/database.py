import os
from datetime import datetime
from typing import Optional, List, Dict

import pandas as pd
from sqlalchemy import create_engine, text, Column, Integer, String, Float, DateTime, UniqueConstraint
from sqlalchemy.orm import declarative_base, Session

from config.settings import DATABASE_URL, DATA_DIR
from src.core.logger import setup_logger

logger = setup_logger("Database")

Base = declarative_base()


class SymbolModel(Base):
    """Tabla de símbolos/pares de divisas soportados."""
    __tablename__ = 'symbols'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(10), unique=True, nullable=False, index=True)
    description = Column(String(100), default='')
    active = Column(Integer, default=1)  # 1=activo, 0=inactivo
    
    def __repr__(self):
        return f"<Symbol(symbol='{self.symbol}')>"


class CandleModel(Base):
    """Tabla principal de velas OHLCV históricas."""
    __tablename__ = 'candles'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol_id = Column(Integer, nullable=False, index=True)
    timeframe = Column(String(5), nullable=False, index=True)
    timestamp = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Integer, default=0)
    
    # Evitar duplicados: mismo símbolo + timeframe + timestamp
    __table_args__ = (
        UniqueConstraint('symbol_id', 'timeframe', 'timestamp', name='uq_candle'),
    )
    
    def __repr__(self):
        return f"<Candle(symbol_id={self.symbol_id}, tf={self.timeframe}, ts={self.timestamp})>"


class DatabaseManager:
    """Gestor de base de datos SQLite para datos históricos de trading."""

    def __init__(self, db_url: Optional[str] = None):
        self.db_url = db_url or DATABASE_URL
        self.engine = create_engine(
            self.db_url,
            echo=False,           # Cambiar a True para debug SQL
            pool_pre_ping=True    # Verificar conexiones antes de usar
        )
        self._initialize_db()

    def _initialize_db(self):
        """Crear tablas si no existen."""
        try:
            Base.metadata.create_all(self.engine)
            logger.info("[OK] Base de datos inicializada correctamente")
        except Exception as e:
            logger.error(f"[ERROR] Fallo al inicializar BD: {e}")
            raise

    def get_session(self) -> Session:
        """Retorna una nueva sesión de SQLAlchemy."""
        return Session(self.engine)

    def ensure_symbol(self, symbol: str, description: str = "") -> int:
        """
        Garantiza que el símbolo existe en la BD.
        Retorna el ID del símbolo.
        """
        with self.get_session() as session:
            existing = session.query(SymbolModel).filter_by(symbol=symbol.upper()).first()
            if existing:
                return existing.id
            
            new_symbol = SymbolModel(
                symbol=symbol.upper(),
                description=description
            )
            session.add(new_symbol)
            session.commit()
            logger.info(f"[OK] Nuevo símbolo registrado: {symbol.upper()}")
            return new_symbol.id

    def save_candles(
        self, 
        df: pd.DataFrame, 
        symbol: str, 
        timeframe: str
    ) -> int:
        """
        Guarda un DataFrame de velas en la base de datos.
        Usa INSERT OR IGNORE para evitar duplicados.
        """
        if df.empty:
            logger.warning("[WARNING] DataFrame vacío. Nada que guardar.")
            return 0

        # Asegurar que el símbolo exista
        symbol_id = self.ensure_symbol(symbol)
        
        # CORRECCIÓN: Convertir Timestamps de Pandas a datetime nativo de Python
        # y asegurar que volume sea siempre int
        records = []
        for _, row in df.iterrows():
            records.append({
                'symbol_id': symbol_id,
                'timeframe': timeframe.upper(),
                # Convertir pandas.Timestamp -> datetime.datetime
                'timestamp': row['timestamp'].to_pydatetime() if hasattr(row['timestamp'], 'to_pydatetime') else row['timestamp'],
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
                # Asegurar que volume sea int (manejar NaN o None)
                'volume': int(row.get('volume', 0)) if pd.notna(row.get('volume')) else 0
            })

        try:
            with self.get_session() as session:
                conn = session.connection()
                result = conn.execute(
                    text("""
                        INSERT OR IGNORE INTO candles 
                        (symbol_id, timeframe, timestamp, open, high, low, close, volume)
                        VALUES 
                        (:symbol_id, :timeframe, :timestamp, :open, :high, :low, :close, :volume)
                    """),
                    records
                )
                session.commit()
                
                inserted = result.rowcount
                logger.info(f"[OK] Guardadas {inserted} velas {timeframe} de {symbol} en BD")
                return inserted
                
        except Exception as e:
            logger.error(f"[ERROR] Error guardando velas en BD: {e}")
            return 0
        
    def load_candles(
        self, 
        symbol: str, 
        timeframe: str, 
        limit: Optional[int] = None
    ) -> Optional[pd.DataFrame]:
        """
        Carga velas históricas desde la BD.
        
        Args:
            symbol: Par de divisas
            timeframe: Temporalidad
            limit: Máximo número de velas (None = todas)
            
        Returns:
            DataFrame ordenado cronológicamente o None si no hay datos
        """
        query = """
            SELECT c.timestamp, c.open, c.high, c.low, c.close, c.volume
            FROM candles c
            JOIN symbols s ON c.symbol_id = s.id
            WHERE s.symbol = :symbol AND c.timeframe = :timeframe
            ORDER BY c.timestamp ASC
        """
        
        params = {'symbol': symbol.upper(), 'timeframe': timeframe.upper()}
        if limit:
            query += " LIMIT :limit"
            params['limit'] = limit

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query), params)
                rows = result.fetchall()
                
                if not rows:
                    logger.warning(f"[WARNING] No hay datos en BD para {symbol} {timeframe}")
                    return None
                
                df = pd.DataFrame(rows, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                
                logger.info(f"[OK] Cargadas {len(df)} velas {timeframe} de {symbol} desde BD")
                return df
                
        except Exception as e:
            logger.error(f"[ERROR] Error cargando velas desde BD: {e}")
            return None

    def get_stored_symbols(self) -> List[Dict]:
        """Lista todos los símbolos almacenados en la BD."""
        with self.get_session() as session:
            symbols = session.query(SymbolModel).all()
            return [{'id': s.id, 'symbol': s.symbol, 'active': bool(s.active)} for s in symbols]

    def create_trade_log_table(self):
        """Crea la tabla de historial si no existe."""
        from sqlalchemy import text
        
        query = text("""
        CREATE TABLE IF NOT EXISTS trade_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket INTEGER UNIQUE,
            symbol TEXT NOT NULL,
            direction TEXT NOT NULL,
            entry_price REAL NOT NULL,
            exit_price REAL,
            volume REAL NOT NULL,
            sl REAL,
            tp REAL,
            profit REAL DEFAULT 0.0,
            strategy TEXT,
            open_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            close_time TIMESTAMP
        )
        """)
        
        # Usar el engine de SQLAlchemy directamente
        with self.engine.connect() as conn:
            conn.execute(query)
            conn.commit()
            
        logger.info("[OK] Tabla trade_log verificada/creada")

    def update_closed_trades(self):
        """Actualiza P&L, exit_price y close_time para trades ya cerrados en MT5."""
        try:
            import MetaTrader5 as mt5_lib
            from sqlalchemy import text
            
            # Obtener historial de operaciones cerradas en MT5 (últimas 24h)
            from datetime import timedelta
            now = datetime.now()
            history = mt5_lib.history_deals_get(now - timedelta(days=1), now)
            
            if not history:
                return
                
            updated_count = 0
            with self.engine.connect() as conn:
                for deal in history:
                    # Solo procesar deals de salida/cierre (tipo 1 o 2 según broker)
                    if deal.entry == 1:  # DEAL_ENTRY_OUT
                        ticket = deal.order
                        
                        # Verificar si existe en nuestra BD
                        check_query = text("SELECT id FROM trade_log WHERE ticket = :ticket AND exit_price IS NULL")
                        result = conn.execute(check_query, {"ticket": ticket}).fetchone()
                        
                        if result:
                            update_query = text("""
                                UPDATE trade_log 
                                SET exit_price = :price, 
                                    close_time = :time, 
                                    profit = :profit 
                                WHERE ticket = :ticket
                            """)
                            
                            params = {
                                "ticket": ticket,
                                "price": deal.price,
                                "time": datetime.fromtimestamp(deal.time),
                                "profit": deal.profit
                            }
                            
                            conn.execute(update_query, params)
                            updated_count += 1
                            
                conn.commit()
                
            if updated_count > 0:
                logger.info(f"[OK] {updated_count} trades actualizados con P&L real")
                
        except Exception as e:
            logger.error(f"[ERROR] Actualizando trades cerrados: {e}")

    def save_trade(self, trade_data: dict):
        """Registra una operación ejecutada."""
        from sqlalchemy import text
        
        query = text("""
        INSERT OR REPLACE INTO trade_log 
        (ticket, symbol, direction, entry_price, exit_price, volume, sl, tp, profit, strategy, open_time, close_time)
        VALUES (:ticket, :symbol, :direction, :entry_price, :exit_price, :volume, :sl, :tp, :profit, :strategy, :open_time, :close_time)
        """)
        
        params = {
            'ticket': trade_data.get('ticket'),
            'symbol': trade_data.get('symbol'),
            'direction': trade_data.get('direction'),
            'entry_price': trade_data.get('entry_price'),
            'exit_price': trade_data.get('exit_price'),
            'volume': trade_data.get('volume'),
            'sl': trade_data.get('sl'),
            'tp': trade_data.get('tp'),
            'profit': trade_data.get('profit', 0.0),
            'strategy': trade_data.get('strategy', 'EMA_Trend'),
            'open_time': trade_data.get('open_time', datetime.now()),
            'close_time': trade_data.get('close_time')
        }
        
        with self.engine.connect() as conn:
            conn.execute(query, params)
            conn.commit()
            
        logger.info(f"[OK] Trade #{trade_data.get('ticket')} registrado en historial")

    def get_trade_history(self, limit: int = 50) -> pd.DataFrame:
        """Obtiene las últimas operaciones."""
        from sqlalchemy import text
        
        query = text("SELECT * FROM trade_log ORDER BY open_time DESC LIMIT :limit")
        
        with self.engine.connect() as conn:
            df = pd.read_sql(query, conn, params={'limit': limit})

    def update_closed_trades(self):
        """Actualiza P&L, exit_price y close_time para trades cerrados en MT5."""
        try:
            import MetaTrader5 as mt5_lib
            from sqlalchemy import text
            from datetime import timedelta
            
            # Obtener historial de operaciones cerradas en MT5 (últimas 24h)
            now = datetime.now()
            history = mt5_lib.history_deals_get(now - timedelta(days=1), now)
            
            if not history:
                return
                
            updated_count = 0
            with self.engine.connect() as conn:
                for deal in history:
                    # DEAL_ENTRY_OUT = 1 significa que es una operación de cierre/salida
                    if deal.entry == 1:  
                        ticket = deal.order
                        
                        # Verificar si existe en BD y aún no tiene precio de salida
                        check_query = text("SELECT id FROM trade_log WHERE ticket = :ticket AND exit_price IS NULL")
                        result = conn.execute(check_query, {"ticket": ticket}).fetchone()
                        
                        if result:
                            update_query = text("""
                                UPDATE trade_log 
                                SET exit_price = :price, 
                                    close_time = :time, 
                                    profit = :profit 
                                WHERE ticket = :ticket
                            """)
                            
                            params = {
                                "ticket": ticket,
                                "price": deal.price,
                                "time": datetime.fromtimestamp(deal.time),
                                "profit": deal.profit
                            }
                            
                            conn.execute(update_query, params)
                            updated_count += 1
                            
                conn.commit()
                
            if updated_count > 0:
                logger.info(f"[OK] {updated_count} trades actualizados con P&L real")
                
        except Exception as e:
            logger.error(f"[ERROR] Actualizando trades cerrados: {e}")
                        
        #return df
 
    
# Instancia singleton para uso global
db_manager = DatabaseManager()


if __name__ == "__main__":
    from src.data.data_fetcher import DataFetcher
    from src.trading.broker_mt5 import mt5_connector

    print("\n[INFO] === PRUEBA DE BASE DE DATOS ===\n")
    
    # Conectar a MT5
    if not mt5_connector.connect():
        print("[ERROR] No se pudo conectar a MT5")
        exit(1)

    try:
        fetcher = DataFetcher(mt5_connector)
        
        # 1. Descargar datos frescos
        print("[INFO] Descargando 200 velas H1 de EURUSD...")
        df = fetcher.get_historical_data(symbol="EURUSD", timeframe="H1", bars=200)
        
        if df is not None:
            # 2. Guardar en BD
            saved = db_manager.save_candles(df, symbol="EURUSD", timeframe="H1")
            print(f"[OK] Filas guardadas: {saved}")
            
            # 3. Leer desde BD (simulando que MT5 está cerrado)
            print("\n[INFO] Leyendo datos desde BD...")
            df_from_db = db_manager.load_candles(symbol="EURUSD", timeframe="H1", limit=5)
            
            if df_from_db is not None:
                print("\n[OK] Primeras 5 velas desde BD:")
                print(df_from_db.to_string(index=False))
            
            # 4. Listar símbolos almacenados
            symbols = db_manager.get_stored_symbols()
            print(f"\n[OK] Símbolos en BD: {[s['symbol'] for s in symbols]}")
        else:
            print("[ERROR] No se pudieron descargar datos para probar la BD")
            
    finally:
        mt5_connector.disconnect()
        print("\n[DISCONNECT] Prueba de BD finalizada")