import os
import json
from datetime import datetime, timedelta, timezone
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()

# --- AYARLAR ---
# Supabase (PostgreSQL) Bağlantı Adresi
# Format: postgresql://USER:PASSWORD@HOST:PORT/DBNAME
# Önceki kodunuzdaki bağlantı stringini buraya ekleyin:
DB_CONNECTION_STRING = os.getenv("DB_CONNECTION_STRING")
# Tablo adı (Şema varsa şema.tablo şeklinde yazın, örn: ict_trade.signals)
DB_TABLE = os.getenv("DB_TABLE")
print(DB_CONNECTION_STRING)
# Dosyanın kaydedileceği KLASÖR yolu
OUTPUT_FOLDER = "./src/assets/data/"

def get_db_engine():
    return create_engine(DB_CONNECTION_STRING)

def fetch_yesterday_data():
    """
    SQLAlchemy kullanarak veritabanından dünün verilerini çeker 
    ve frontend uyumlu JSON formatına getirir.
    """
    engine = get_db_engine()
    
    # Zaman Ayarları (UTC)
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    
    # Dünün başlangıç ve bitiş zamanı (UTC)
    start_of_day = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    date_str = yesterday.strftime("%Y-%m-%d") # Dosya adı: 2026-02-07
    
    print(f"📅 Hedef Tarih: {date_str}")
    print(f"🔍 Sorgu Aralığı: {start_of_day} - {end_of_day}")

    formatted_signals = []

    try:
        with engine.connect() as conn:
            # SQL Sorgusu
            query = text(f"""
                SELECT * FROM {DB_TABLE}
                WHERE signal_time >= :start_time AND signal_time <= :end_time
                ORDER BY signal_time DESC
            """)
            
            result = conn.execute(query, {
                "start_time": start_of_day,
                "end_time": end_of_day
            })
            
            # Sonuçları satır satır işle
            rows = result.mappings().all() # Sütun isimleriyle erişmek için mappings() kullanılır

            for row in rows:
                # DB'deki LONG/SHORT verisini frontend için BUY/SELL formatına çevir
                # row nesnesi dictionary gibi davranır
                direction = row.get("direction")
                trade_type = "BUY" if direction == "LONG" else "SELL"
                
                # Frontend'in beklediği JSON yapısı
                signal_obj = {
                    "id": row.get("id"),
                    "symbol": row.get("symbol"),
                    "trade_type": trade_type,
                    # Tarih nesnesini stringe çevir (ISO format)
                    "signal_time": row.get("signal_time").isoformat() if row.get("signal_time") else None,
                    "entry_price": float(row.get("entry", 0)),
                    "sl_price": float(row.get("sl", 0)),
                    "tp_price": float(row.get("tp", 0)),
                    "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
                    # Varsayılan değerler
                    "status": "OPEN", 
                    "signal_price": float(row.get("entry", 0))
                }
                formatted_signals.append(signal_obj)

        print(f"✅ Toplam {len(formatted_signals)} adet sinyal çekildi.")
        return {"ict_signal": formatted_signals}, date_str

    except Exception as e:
        print(f"❌ Veritabanı hatası: {e}")
        return {"ict_signal": []}, date_str

def save_to_json_file(data, date_str):
    """
    Veriyi YYYY-MM-DD.json ismiyle kaydeder.
    """
    if OUTPUT_FOLDER and not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    
    filename = f"{OUTPUT_FOLDER}{date_str}.json"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"💾 Dosya başarıyla kaydedildi: {filename}")
    except Exception as e:
        print(f"❌ Dosya kaydetme hatası: {e}")

if __name__ == "__main__":
    result_data, date_filename = fetch_yesterday_data()
    
    if result_data["ict_signal"]:
        save_to_json_file(result_data, date_filename)
    else:
        print("⚠️ Kaydedilecek veri bulunamadı.")