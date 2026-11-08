import MetaTrader5 as mt5
from config.settings import MT5_CONFIG
from src.core.logger import setup_logger

logger = setup_logger("MT5Connector")

class MT5Connector:
    def __init__(self):
        self.config = MT5_CONFIG
        self.connected = False
    
    def connect(self) -> bool:
        """Conecta a MT5 (debe estar abierto previamente)"""
        try:
            # Inicializar SIN path: se conecta al MT5 que ya está corriendo
            if not mt5.initialize():
                error = mt5.last_error()
                logger.error(f"[ERROR] No se pudo inicializar MT5. ¿Está abierto? Detalle: {error}")
                return False
            
            # Verificar si ya hay sesión activa
            account_info = mt5.account_info()
            
            # Si no hay sesión, intentar login automático
            if not account_info:
                logger.info("[INFO] Iniciando sesión automática...")
                authorized = mt5.login(
                    login=self.config['login'],
                    password=self.config['password'],
                    server=self.config['server']
                )
                
                if not authorized:
                    error = mt5.last_error()
                    logger.error(f"[ERROR] Login fallido: {error}")
                    return False
                
                account_info = mt5.account_info()

            if account_info:
                logger.info("[OK] Conectado exitosamente a MT5")
                logger.info(f"   Cuenta: {account_info.login} | Servidor: {account_info.server}")
                logger.info(f"   Balance: ${account_info.balance:.2f} | Equity: ${account_info.equity:.2f}")
                logger.info(f"   Apalancamiento: 1:{account_info.leverage}")
            
            self.connected = True
            return True
            
        except Exception as e:
            logger.critical(f"[CRITICAL] Error crítico en conexión: {e}")
            return False
    
    def disconnect(self):
        """Cierra conexión con MT5"""
        if self.connected:
            mt5.shutdown()
            self.connected = False
            logger.info("[DISCONNECT] Conexión cerrada correctamente")
    
    def get_account_info(self):
        """Obtiene información de la cuenta"""
        if not self.connected:
            return None
        info = mt5.account_info()
        if info:
            return {
                'login': info.login,
                'balance': info.balance,
                'equity': info.equity,
                'margin_free': info.margin_free,
                'profit': info.profit,
                'leverage': info.leverage
            }
        return None

    def check_connection(self) -> bool:
        """Verifica si la conexión con MT5 sigue activa y funcional"""
        if not self.connected:
            return False
        
        try:
            # Intentar obtener info de cuenta como prueba de vida
            account_info = mt5.account_info()
            is_active = account_info is not None
            
            if not is_active:
                logger.warning("[WARNING] La conexión con MT5 se ha perdido")
                self.connected = False
                
            return is_active
        except Exception as e:
            logger.error(f"[ERROR] Error verificando conexión MT5: {e}")
            self.connected = False
            return False
        
    def get_account_info(self) -> dict | None:
        """Obtiene información de la cuenta MT5 conectada."""
        try:
            import MetaTrader5 as mt5
            info = mt5.account_info()
            if info is None:
                return None
            return {
                'balance': info.balance,
                'equity': info.equity,
                'margin': info.margin,
                'free_margin': info.margin_free,
                'profit': info.profit,
                'leverage': info.leverage,
                'server': info.server,
                'currency': info.currency
            }
        except Exception:
            return None

    def get_positions(self, symbol: str | None = None) -> list | None:
        """Obtiene posiciones abiertas. Si se pasa symbol, filtra por ese par."""
        try:
            import MetaTrader5 as mt5
            if symbol:
                positions = mt5.positions_get(symbol=symbol)
            else:
                positions = mt5.positions_get()
            
            if positions is None:
                return []
                
            result = []
            for pos in positions:
                result.append({
                    'ticket': pos.ticket,
                    'symbol': pos.symbol,
                    'type': pos.type,  # 0=BUY, 1=SELL
                    'volume': pos.volume,
                    'price_open': pos.price_open,
                    'sl': pos.sl,
                    'tp': pos.tp,
                    'profit': pos.profit,
                    'time': pos.time
                })
            return result
        except Exception:
            return None

# Instancia global
mt5_connector = MT5Connector()