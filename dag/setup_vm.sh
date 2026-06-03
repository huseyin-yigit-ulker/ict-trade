#!/usr/bin/env bash
# ICT bot — Oracle/Linux VM kurulum scripti (idempotent).
# Repo kökünden çalıştır:  bash dag/setup_vm.sh
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_DIR"
echo "Repo: $REPO_DIR"

# 1. Python venv
if [ ! -d ".venv" ]; then
  echo "venv oluşturuluyor..."
  python3 -m venv .venv
fi
./.venv/bin/python -m pip install --upgrade pip -q
echo "Bağımlılıklar yükleniyor..."
./.venv/bin/python -m pip install -q -r dag/requirements.txt

# 2. .env kontrolü
if [ ! -f ".env" ]; then
  echo "UYARI: .env yok. Aşağıdakileri içeren bir .env oluştur:"
  echo "  DB_CONNECTION_STRING=postgresql://..."
  echo "  TELEGRAM_BOT_TOKEN=123:ABC"
  echo "  TELEGRAM_CHAT_ID=123456"
else
  echo ".env mevcut."
fi

# 3. Hızlı bağlantı testi (DB'ye YAZMADAN: tek sembol son bar)
echo "Binance erişim + motor testi (DB'ye yazmaz)..."
./.venv/bin/python - <<'PY'
import sys, importlib.util, pandas as pd
spec = importlib.util.spec_from_file_location('dagmod', 'dag/dag.py')
m = importlib.util.module_from_spec(spec); sys.modules['dagmod']=m
spec.loader.exec_module(m)
df = m.fetch_klines('BTCUSDT', '1h',
    int((pd.Timestamp.now(tz='UTC')-pd.Timedelta(hours=50)).timestamp()*1000),
    int(pd.Timestamp.now(tz='UTC').timestamp()*1000))
if df.empty:
    print('  ❌ Binance veri ÇEKİLEMEDİ (451/geo-block olabilir). Bölgeyi kontrol et.')
    sys.exit(1)
print(f'  ✅ Binance OK: {len(df)} bar, son {df.index[-1]}')
PY

echo
echo "Kurulum tamam. Crontab eklemek için:"
echo "  crontab -e   →   5 * * * * cd $REPO_DIR && $REPO_DIR/.venv/bin/python dag/dag.py >> $REPO_DIR/ict-bot.log 2>&1"
