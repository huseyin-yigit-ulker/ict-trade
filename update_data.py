import requests
import pandas as pd
import numpy as np
import json
import os
from datetime import datetime, timedelta, timezone

# --- AYARLAR ---
SYMBOL = "BTCUSDT"
INTERVAL = "15m"
DISPLACEMENT_FACTOR = 2.0 
ATR_PERIOD = 14
RR_RATIO = 2.0 
FILENAME = "./src/assets/data/btc.json" # Kaydedilecek dosya adı

def get_binance_data(symbol, interval, start_str, end_str=None):
    url = "https://api.binance.com/api/v3/klines"
    dt_obj = datetime.strptime(start_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    start_ts = int(dt_obj.timestamp() * 1000)
    
    params = {
        "symbol": symbol,
        "interval": interval,
        "startTime": start_ts,
        "limit": 1000 
    }
    
    if end_str:
        dt_end = datetime.strptime(end_str, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        params["endTime"] = int(dt_end.timestamp() * 1000)

    try:
        response = requests.get(url, params=params)
        data = response.json()
        
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
        print(f"Veri çekme hatası: {e}")
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

def generate_ict_signals():
    now = datetime.now(timezone.utc)
    yesterday = now - timedelta(days=1)
    yesterday_start = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_end = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
    
    print(f"Analiz edilen tarih aralığı: {yesterday_start} - {yesterday_end}")

    df = get_binance_data(
        SYMBOL, 
        INTERVAL, 
        yesterday_start.strftime("%Y-%m-%d %H:%M:%S")
    )
    
    if df.empty:
        return {"ict_signal": []}

    df['body_size'] = abs(df['close'] - df['open'])
    df['body_avg'] = df['body_size'].rolling(window=20).mean()
    
    df['tr'] = np.maximum((df['high'] - df['low']), 
                          np.maximum(abs(df['high'] - df['close'].shift(1)), 
                                     abs(df['low'] - df['close'].shift(1))))
    df['atr'] = df['tr'].rolling(window=ATR_PERIOD).mean()

    signals_list = []
    mask = (df['open_time'] >= yesterday_start) & (df['open_time'] <= yesterday_end)
    target_indices = df.index[mask].tolist()

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
                "symbol": SYMBOL,
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
            signals_list.append(signal_obj)

    return {"ict_signal": signals_list}

def save_to_json_file(data):
    """
    Veriyi .json dosyasına kaydeder.
    Eğer dosya varsa üzerine yazar (overwrite).
    """
    try:
        with open(FILENAME, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        print(f"✅ Dosya başarıyla kaydedildi: {FILENAME}")
    except Exception as e:
        print(f"❌ Dosya kaydetme hatası: {e}")

if __name__ == "__main__":
    # Sinyalleri üret
    result_data = generate_ict_signals()
    
    # Dosyaya kaydet
    save_to_json_file(result_data)