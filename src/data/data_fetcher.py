import MetaTrader5 as mt5
import pandas as pd
from typing import Optional, Dict

from src.trading.broker_mt5 import MT5Connector
from src.core.logger import setup_logger

logger = setup_logger("DataFetcher")


class DataFetcher:
    """Módulo responsable de obtener y procesar datos históricos OHLCV desde MetaTrader 5."""

    def __init__(self, connector: MT5Connector):
        if not isinstance(connector, MT5Connector):
            raise TypeError("[ERROR] Se requiere una instancia válida de MT5Connector")
        
        self.connector = connector
        self._timeframe_map: Dict[str, int] = {
            'M1': mt5.TIMEFRAME_M1,
            'M5': mt5.TIMEFRAME_M5,
            'M15': mt5.TIMEFRAME_M15,
            'M30': mt5.TIMEFRAME_M30,
            'H1': mt5.TIMEFRAME_H1,
            'H4': mt5.TIMEFRAME_H4,
            'D1': mt5.TIMEFRAME_D1,
        }

    def get_historical_data(
        self, 
        symbol: str, 
        timeframe: str, 
        bars: int = 1000
    ) -> Optional[pd.DataFrame]:
        """
        Descarga velas históricas OHLCV desde MT5.

        Args:
            symbol: Par de divisas (ej. 'EURUSD')
            timeframe: Temporalidad en formato string ('M1', 'H1', 'D1', etc.)
            bars: Cantidad de velas a descargar (máx 5000 por llamada)

        Returns:
            DataFrame con columnas [timestamp, open, high, low, close, volume]
            o None si ocurre un error.
        """
        # Validar conexión activa
        if not self.connector.check_connection():
            logger.error("[ERROR] No hay conexión activa con MT5. Conecte antes de solicitar datos.")
            return None

        # Mapear timeframe string a constante MT5
        tf_constant = self._timeframe_map.get(timeframe.upper())
        if tf_constant is None:
            available = ', '.join(self._timeframe_map.keys())
            logger.error(f"[ERROR] Timeframe '{timeframe}' no válido. Disponibles: {available}")
            return None

        # Validar y habilitar símbolo en Market Watch
        if not mt5.symbol_select(symbol, True):
            logger.error(f"[ERROR] Símbolo '{symbol}' no disponible en Market Watch o inválido.")
            return None

        try:
            rates = mt5.copy_rates_from_pos(symbol, tf_constant, 0, bars)
            
            if rates is None or len(rates) == 0:
                last_error = mt5.last_error()
                logger.error(f"[ERROR] No se obtuvieron datos para {symbol} {timeframe}. Error MT5: {last_error}")
                return None

            # Convertir tuple de namedtuples a DataFrame estandarizado
            df = pd.DataFrame(rates)
            
            # CORRECCIÓN 1: Manejo seguro de nombres de columnas (MT5 varía según versión)
            # Normalizar nombres de columnas a minúsculas para evitar errores de case-sensitive
            df.columns = [col.lower() for col in df.columns]
            
            # Verificar que tengamos las columnas necesarias
            required_cols = ['time', 'open', 'high', 'low', 'close']
            missing_cols = [c for c in required_cols if c not in df.columns]
            if missing_cols:
                logger.error(f"[ERROR] Columnas faltantes en respuesta MT5: {missing_cols}")
                logger.error(f"[DEBUG] Columnas recibidas: {list(df.columns)}")
                return None
            
            # Convertir timestamp a datetime64[ns] sin zona horaria
            df['time'] = pd.to_datetime(df['time'], unit='s', utc=True).dt.tz_localize(None)
            
            # Renombrar 'time' a 'timestamp' (CORRECCIÓN 2: Sin inplace deprecated)
            df = df.rename(columns={'time': 'timestamp'})
            
            # Seleccionar y ordenar columnas estándar
            output_columns = ['timestamp', 'open', 'high', 'low', 'close']
            
            # Agregar 'volume' solo si existe (algunos brokers no lo envían en forex)
            if 'volume' in df.columns:
                output_columns.append('volume')
                df['volume'] = df['volume'].astype('int64')
            else:
                logger.warning("[WARNING] MT5 no proporcionó columna 'volume'. Se omitirá.")
            
            df = df[output_columns]
            
            # Asegurar tipos de datos explícitos
            df['timestamp'] = df['timestamp'].astype('datetime64[ns]')
            for col in ['open', 'high', 'low', 'close']:
                df[col] = df[col].astype('float64')

            # Ordenar cronológicamente ascendente (CORRECCIÓN 3: Sin inplace)
            df = df.sort_values('timestamp', ascending=True).reset_index(drop=True)

            date_range = f"{df['timestamp'].iloc[0]} a {df['timestamp'].iloc[-1]}"
            logger.info(f"[OK] Descargadas {len(df)} velas {timeframe} de {symbol} | Rango: {date_range}")
            
            return df

        except Exception as e:
            logger.error(f"[ERROR] Excepción al descargar datos de {symbol} {timeframe}: {e}")
            import traceback
            logger.debug(traceback.format_exc())
            return None


if __name__ == "__main__":
    from src.trading.broker_mt5 import mt5_connector
    from config.settings import DATA_DIR

    # Inicializar conexión
    if not mt5_connector.connect():
        print("[ERROR] No se pudo conectar a MT5. Verifique que la terminal esté abierta y logueada.")
        exit(1)

    try:
        # Instanciar DataFetcher con inyección de dependencias
        fetcher = DataFetcher(mt5_connector)

        # Descargar 500 velas H1 de EURUSD
        print("\n[INFO] Descargando 500 velas H1 de EURUSD...")
        df = fetcher.get_historical_data(symbol="EURUSD", timeframe="H1", bars=500)

        if df is not None:
            # Mostrar primeras 5 filas
            print("\n[OK] Primeras 5 velas descargadas:")
            print(df.head().to_string(index=False))
            
            # Guardar CSV temporal para verificación visual
            output_path = DATA_DIR / "eurusd_h1_sample.csv"
            df.to_csv(output_path, index=False)
            print(f"\n[OK] Datos guardados en: {output_path}")
        else:
            print("\n[ERROR] La descarga retornó None. Revise los logs anteriores.")

    finally:
        mt5_connector.disconnect()
        print("\n[DISCONNECT] Prueba finalizada. Conexión cerrada.")