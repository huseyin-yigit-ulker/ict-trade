import requests
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta, timezone

# --- AYARLAR ---
SYMBOLS = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT", 
    "DOGEUSDT", "ADAUSDT", "AVAXUSDT", "SHIBUSDT", "TRXUSDT", 
    "DOTUSDT", "LINKUSDT", "TONUSDT", "MATICUSDT", "LTCUSDT", 
    "BCHUSDT", "UNIUSDT", "NEARUSDT", "APTUSDT", "XLMUSDT", 
    "ICPUSDT", "ATOMUSDT", "IMXUSDT", "ARBUSDT", "OPUSDT", 
    "INJUSDT", "STXUSDT", "FILUSDT", "KASUSDT", "VETUSDT", 
    "ETCUSDT", "RNDRUSDT", "GRTUSDT", "ALGOUSDT", "THETAUSDT", 
    "FIMUSDT", "SUIUSDT", "TIAUSDT", "SEIUSDT", "ORDIUSDT", 
    "AAVEUSDT", "MKRUSDT", "QNTUSDT", "EGLDUSDT", "AXSUSDT", 
    "SANDUSDT", "MANAUSDT", "EOSUSDT", "FETUSDT", "GALAUSDT"
]
INTERVAL = "15m"
DISPLACEMENT_FACTOR = 2.0 
ATR_PERIOD = 14
RR_RATIO = 2.0 

# Dosyanın kaydedileceği KLASÖR yolu (Sonuna / koymayı unutmayın)
OUTPUT_FOLDER = "./src/assets/data/" 

def get_binance_futures_data(symbol, interval, start_str, end_str=None):
    url = "https://fapi.binance.com/fapi/v1/klines"
    
    dt_obj = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    start_ts = int(dt_obj.timestamp() * 1000)
    
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ts,
        "limit": 1500
    }
    
    if end_str:
        dt_end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        params["endTime"] = int(dt_end.timestamp() * 1000)

    try:
        response = requests.get(url, params=params)
        data = response.json()
        
        if isinstance(data, dict) and "code" in data:
            print(f"API Hatası ({symbol}): {data.get('msg')}")
            return pd.DataFrame()

        if not isinstance(data, list):
            return pd.DataFrame()
            
        df = pd.DataFrame(data, columns=[
            "open_time", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
        ])
        
        df["open_time"] = pd.to_datetime(df["open_time"], unit='ms', utc=True)
        df["close_time"] = pd.to_datetime(df["close_time"], unit='ms', utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = df[col].astype(float)
            
        return df
    except Exception as e:
        print(f"Veri çekme hatası ({symbol}): {e}")
        return pd.DataFrame()

def check_trade_outcome(df, signal_index, entry_price, tp_price, sl_price, trade_type):
    status = "OPEN" 
    real_entry_time = None
    exit_time = None
    is_filled = False

    future_candles = df.iloc[signal_index + 1:]

    for idx, row in future_candles.iterrows():
        if not is_filled:
            if trade_type == "BUY":
                if row['low'] <= entry_price:
                    is_filled = True
                    real_entry_time = row['open_time'] 
            else: 
                if row['high'] >= entry_price:
                    is_filled = True
                    real_entry_time = row['open_time']
        
        if is_filled:
            if trade_type == "BUY":
                if row['low'] <= sl_price:
                    status = "STOP LOSS"
                    exit_time = row['open_time'] 
                    break
                if row['high'] >= tp_price:
                    status = "TAKE PROFIT"
                    exit_time = row['open_time']
                    break
            else: 
                if row['high'] >= sl_price:
                    status = "STOP LOSS"
                    exit_time = row['open_time']
                    break
                if row['low'] <= tp_price:
                    status = "TAKE PROFIT"
                    exit_time = row['open_time']
                    break
    
    if not is_filled:
        status = "NO FILL"
        
    if is_filled and status == "OPEN":
        status = "OPEN (RUNNING)"

    return status, real_entry_time, exit_time

def analyze_symbol(symbol, start_str, end_str):
    """Tek bir sembol için analizi yapar ve sinyalleri döner"""
    df = get_binance_futures_data(symbol, INTERVAL, start_str, end_str)
    
    if df.empty:
        return []

    df['body_size'] = abs(df['close'] - df['open'])
    df['body_avg'] = df['body_size'].rolling(window=20).mean()
    
    df['tr'] = np.maximum((df['high'] - df['low']), 
                          np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                     abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(window=ATR_PERIOD).mean()

    # Tarih Filtreleme (Sadece analiz edilen gün)
    dt_start = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    dt_end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)

    mask = (df['open_time'] >= dt_start) & (df['open_time'] <= dt_end)
    target_indices = df.index[mask].tolist()

    symbol_signals = []

    for i in target_indices:
        if i < 2: continue 

        row = df.iloc[i]
        pre_prev_row = df.iloc[i-2]

        if row['body_size'] <= (row['body_avg'] * DISPLACEMENT_FACTOR):
            continue

        trade_type = None
        entry = 0.0
        sl = 0.0
        tp = 0.0

        if row['close'] > row['open']: 
            if row['low'] > pre_prev_row['high']:
                gap = row['low'] - pre_prev_row['high']
                if gap > (row['atr'] * 0.1): 
                    trade_type = "BUY"
                    entry = row['low'] 
                    sl = row['low'] - row['atr'] 
                    tp = entry + (entry - sl) * RR_RATIO

        elif row['close'] < row['open']: 
            if row['high'] < pre_prev_row['low']:
                gap = pre_prev_row['low'] - row['high']
                if gap > (row['atr'] * 0.1):
                    trade_type = "SELL"
                    entry = row['high'] 
                    sl = row['high'] + row['atr']
                    tp = entry - (sl - entry) * RR_RATIO

        if trade_type:
            status, real_entry, exit_ts = check_trade_outcome(df, i, entry, tp, sl, trade_type)

            signal_obj = {
                "symbol": symbol,
                "trade_type": trade_type,
                "signal_time": row['open_time'].isoformat().replace("+00:00", "Z"),
                "signal_time_confirmed": row['close_time'].isoformat().replace("+00:00", "Z"),
                "signal_price": float(f"{row['close']:.8f}"),
                "entry_price": float(f"{entry:.8f}"),
                "sl_price": float(f"{sl:.8f}"),
                "tp_price": float(f"{tp:.8f}"),
                "status": status,
                "real_entry_time": real_entry.isoformat().replace("+00:00", "Z") if real_entry else None,
                "exit_time": exit_ts.isoformat().replace("+00:00", "Z") if exit_ts else None,
                "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
            }
            symbol_signals.append(signal_obj)
            
    return symbol_signals

def generate_ict_signals():
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    
    # Analiz edilen günün başlangıcı ve bitişi
    yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    # Dosya ismi için tarih stringi (Örn: 2026-02-07)
    date_str = yesterday.strftime("%Y-%m-%d")
    
    print(f"Analiz Tarihi: {date_str}")
    
    all_signals = []

    start_str = yesterday_start.strftime("%Y-%m-%d %H:%M:%S")
    # Bitiş zamanını vermiyoruz ki trade sonucunu kontrol etmek için bugünün verisini de çekebilsin
    # Ancak analiz fonksiyonunda (analyze_symbol) sadece dün filtreleniyor.
    
    # check_trade_outcome için "bugün"ün verisine de ihtiyaç olduğundan API çağrısında end_time vermiyoruz.
    # Ancak analiz fonksiyonuna tarih aralığını paslıyoruz.
    
    end_str_for_filter = yesterday_end.strftime("%Y-%m-%d %H:%M:%S")

    for symbol in SYMBOLS:
        print(f"Taranıyor: {symbol}...")
        try:
            signals = analyze_symbol(symbol, start_str, end_str_for_filter)
            all_signals.extend(signals)
        except Exception as e:
            print(f"Hata oluştu ({symbol}): {e}")

    return {"ict_signal": all_signals}, date_str

def save_to_json_file(data, date_str):
    """
    Veriyi YYYY-MM-DD.json ismiyle kaydeder.
    """
    # Klasör yoksa oluştur
    if OUTPUT_FOLDER and not os.path.exists(OUTPUT_FOLDER):
        os.makedirs(OUTPUT_FOLDER)
    
    # Dosya ismini tarih yap: ./src/assets/data/2026-02-07.json
    filename = f"{OUTPUT_FOLDER}{date_str}.json"

    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"✅ Dosya başarıyla kaydedildi: {filename}")
    except Exception as e:
        print(f"❌ Dosya kaydetme hatası: {e}")

if __name__ == "__main__":
    result_data, date_filename = generate_ict_signals()
    save_to_json_file(result_data, date_filename)