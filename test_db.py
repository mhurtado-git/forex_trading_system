import pandas as pd  # <--- ¡ESTA LÍNEA FALTABA!
from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL
from datetime import datetime, timezone
import MetaTrader5 as mt5_lib

print("🔧 ACTUALIZACIÓN MANUAL POR DEAL ID CONOCIDO")
print("=" * 60)

# Mapeo manual basado en el diagnóstico anterior
# ⚠️ VERIFICA ESTOS IDs EN TU MT5 ANTES DE EJECUTAR
MANUAL_MATCHES = {
    59250644880: 59252157687,  # Ajusta si es necesario
    59266147714: 59270330757,  # Ajusta si es necesario  
    59275459293: None          # Operación actual, dejar pendiente
}

engine = create_engine(DATABASE_URL)

if not mt5_lib.initialize():
    print("❌ Error conectando a MT5")
    exit(1)

now_utc = datetime.now(timezone.utc)
history = mt5_lib.history_deals_get(now_utc - pd.Timedelta(days=30), now_utc)
mt5_lib.shutdown()

# Crear diccionario rápido de deals por ID
deals_by_id = {deal.order: deal for deal in history if deal.entry == 1 and deal.profit != 0}

updated_count = 0
with engine.connect() as conn:
    for ticket_bd, deal_id in MANUAL_MATCHES.items():
        if deal_id is None:
            print(f"   ⏭️  Saltando Ticket {ticket_bd} (operación actual)")
            continue
            
        deal = deals_by_id.get(deal_id)
        if not deal:
            print(f"   ❌ Deal {deal_id} no encontrado en historial MT5")
            continue
        
        # Obtener info del trade en BD
        trade = conn.execute(text("""
            SELECT id, symbol FROM trade_log WHERE ticket = :t AND exit_price IS NULL
        """), {"t": ticket_bd}).fetchone()
        
        if not trade:
            print(f"   ⚠️ Ticket {ticket_bd} no encontrado o ya actualizado")
            continue
            
        db_id, symbol = trade
        
        print(f"   ✅ MATCH MANUAL: Ticket {ticket_bd} -> Deal {deal_id}")
        print(f"      Símbolo: {symbol} | Profit: {deal.profit:+.2f}")
        
        conn.execute(text("""
            UPDATE trade_log 
            SET exit_price = :price, 
                close_time = :time, 
                profit = :profit 
            WHERE id = :id
        """), {
            "price": deal.price,
            "time": datetime.fromtimestamp(deal.time, tz=timezone.utc),
            "profit": deal.profit,
            "id": db_id
        })
        updated_count += 1
    
    conn.commit()

print(f"\n🎉 {updated_count} operaciones actualizadas manualmente.")
print("💡 Recarga Streamlit (F5) para ver resultados finales.")