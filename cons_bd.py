from sqlalchemy import create_engine, text
from config.settings import DATABASE_URL # Importamos la configuración real del bot

print(f"🔍 Conectando a BD real: {DATABASE_URL}")

try:
    engine = create_engine(DATABASE_URL)
    
    with engine.connect() as conn:
        # 1. Listar tablas
        result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table';"))
        tables = [row[0] for row in result.fetchall()]
        print(f"📂 Tablas encontradas: {tables}")
        
        # 2. Verificar trade_log
        if 'trade_log' in tables:
            count = conn.execute(text("SELECT COUNT(*) FROM trade_log")).fetchone()[0]
            print(f"✅ Registros en trade_log: {count}")
            
            if count > 0:
                print("\n📜 Últimas 3 operaciones:")
                rows = conn.execute(text("SELECT * FROM trade_log ORDER BY open_time DESC LIMIT 3")).fetchall()
                for r in rows:
                    print(f"   Ticket: {r[1]} | {r[2]} | Profit: {r[9]}")
        else:
            print("⚠️ La tabla 'trade_log' NO EXISTE en esta BD.")
            
except Exception as e:
    print(f"❌ Error: {e}")