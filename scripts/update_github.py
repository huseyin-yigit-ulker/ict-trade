import json
import os
from github import Github
from datetime import datetime

# BU KISMI AIRFLOW VARIABLE VEYA ENV'DEN ALMALISIN (GÜVENLİK İÇİN)
GITHUB_TOKEN = os.getenv("MY_GITHUB_TOKEN") 
REPO_NAME = "kullanici_adin/trade-bot-dashboard"
FILE_PATH = "public/signals.json"

def send_signal(signal_data):
    g = Github(GITHUB_TOKEN)
    repo = g.get_repo(REPO_NAME)

    try:
        contents = repo.get_contents(FILE_PATH)
        data = json.loads(contents.decoded_content.decode())
        
        # Yeni veriyi ekle
        data.insert(0, signal_data)
        data = data[:50] # Son 50 veri

        repo.update_file(
            path=contents.path,
            message=f"Bot Signal: {signal_data.get('symbol')}",
            content=json.dumps(data, indent=4),
            sha=contents.sha
        )
        print("GitHub Guncellendi!")
    except Exception as e:
        print(f"Hata: {e}")

# Test Sinyali (Airflow bu fonksiyonu çağıracak)
if __name__ == "__main__":
    test_signal = {
        "id": int(datetime.now().timestamp()),
        "symbol": "BTCUSDT",
        "dir": "LONG",
        "entry": 45000,
        "sl": 44000,
        "tp": 46000,
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    # Token varsa çalıştır (Test amaçlı)
    if GITHUB_TOKEN:
        send_signal(test_signal)
    else:
        print("Lutfen GITHUB_TOKEN environment variable'ini ayarlayin.")