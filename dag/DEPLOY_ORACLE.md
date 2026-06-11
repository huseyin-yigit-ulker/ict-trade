# ICT Bot — Oracle Cloud Always Free VM Deploy

`dag/dag.py`'ı ücretsiz, 7/24 açık, **AB bölgesi** (Binance erişimli) bir Oracle VM'de
saatlik cron ile çalıştırma rehberi. ABD GitHub runner'ları Binance'ten **451** aldığı
için bu yola geçildi.

---

## 1. Oracle hesabı + VM oluştur

1. https://www.oracle.com/cloud/free/ → **Start for free**. Doğrulama için kredi kartı
   ister ama **Always Free** kaynaklar ücretsizdir, çekim yapılmaz.
2. Hesap bölgesi (home region): **Germany Central (Frankfurt)** ya da
   **Netherlands Northwest (Amsterdam)** seç → Binance AB'den erişilebilir.
   (⚠️ Bölge sonradan değiştirilemez; ABD seçme.)
3. Console → **Compute → Instances → Create instance**:
   - **Image:** Canonical Ubuntu 22.04 (veya 24.04)
   - **Shape:** "Always Free eligible" olanı seç:
     - `VM.Standard.A1.Flex` (ARM, 1 OCPU / 6 GB yeter) **veya**
     - `VM.Standard.E2.1.Micro` (AMD x86, 1 GB) — bizim bota 1 GB fazlasıyla yeter.
   - **SSH key:** kendi public key'ini ekle (yoksa Oracle üretir, private key'i indir).
4. **Create**. Public IP'yi not al.

## 2. SSH ile bağlan

```bash
ssh -i /path/to/private_key ubuntu@<PUBLIC_IP>
```

## 3. Gerekli paketler + repoyu çek

```bash
sudo apt update && sudo apt install -y python3-venv python3-pip git
git clone https://github.com/huseyin-yigit-ulker/ict-trade.git
cd ict-trade
```

## 4. .env oluştur (secrets — repoya GİRMEZ)

```bash
nano .env
```
İçine (kendi değerlerinle):
```
DB_CONNECTION_STRING=postgresql://postgres.xxxx:SIFRE@aws-1-eu-central-1.pooler.supabase.com:6543/postgres
TELEGRAM_BOT_TOKEN=123456789:AAH...
TELEGRAM_CHAT_ID=your_telegram_chat_id
# Günlük backtest senkronu (sync/) için — backtest Supabase'inin yazma yetkili postgres bağlantısı:
BACKTESTING_DB_CONNECTION_STRING=postgresql://postgres.yyyy:SIFRE@aws-1-eu-central-1.pooler.supabase.com:6543/postgres
```
> Not: Eski hardcoded DB şifreni ve Telegram token'ını **yenilemen** önerilir (git geçmişinde açıktalar).
> `BACKTESTING_DB_CONNECTION_STRING` sadece `sync/` işleri (canlı→backtest aktarımı) için gerekir; saatlik DAG kullanmaz.

## 5. Kurulum + test

```bash
bash dag/setup_vm.sh
```
Bu: venv kurar, bağımlılıkları yükler ve **Binance erişimini test eder**.
`✅ Binance OK: ... bar` görmen lazım. `❌ ... 451` görürsen bölge yanlış demektir.

## 6. Tek seferlik elle çalıştırma (DB'ye yazar, Telegram atar)

```bash
cd ~/ict-trade && ./.venv/bin/python dag/dag.py
```
17 sembolü tarar; yeni sinyal varsa DB'ye yazıp Telegram atar.

## 7. Saatlik cron kur

```bash
crontab -e
```
En alta ekle (HH:01'de, bar kapandıktan ~1 dk sonra):
```
1 * * * * cd /home/ubuntu/ict-trade && /home/ubuntu/ict-trade/.venv/bin/python dag/dag.py >> /home/ubuntu/ict-bot.log 2>&1
```
> VM saati UTC'dir (cron UTC çalışır) — bot zaten UTC bar mantığında, uyumlu.

## 7b. Günlük backtest senkronu (canlı sinyaller → trading_signals)

Her gün, **1 gün geriden** (sinyaller TP/SL ile sonuçlansın diye) canlı sinyalleri sonuçlarıyla
backtest Supabase'indeki `ict_trade.trading_signals`'a aktarır. Son 3 günü her koşuda yeniden
tarar (gecikmeli sonuçlananları yakalar) ve idempotenttir (tekrar çalışmak çift kayıt üretmez).
`.env`'de `BACKTESTING_DB_CONNECTION_STRING` gerektirir (bkz. adım 4). Binance erişimi gerektiği için
bu da VM'de çalışmalı (GitHub runner 451 alır).

Saatlik DAG'ın altına ekle (00:30 UTC, "dün" tamamen kapanmışken):
```
30 0 * * * cd /home/ubuntu/ict-trade && /home/ubuntu/ict-trade/.venv/bin/python sync/sync_daily.py >> /home/ubuntu/ict-sync.log 2>&1
```

İlgili komutlar:
```
./.venv/bin/python sync/sync_daily.py --dry-run        # DB'ye yazmadan önizle
./.venv/bin/python sync/backfill_year.py --year 2026 --dry-run         # 2026 backfill önizleme
./.venv/bin/python sync/backfill_year.py --year 2026 --wipe-scope all  # tek seferlik: sil + 2026'yı doldur
./.venv/bin/python sync/backfill_year.py --year 2025 --wipe-scope year # 2025'i ekle (2026'ya dokunmaz)
# Son 2-3 günü 3 stratejinin HEPSİ için tek komutta backtest (hızlı doğrulama / gap-fill):
./.venv/bin/python sync/backtest_recent.py --dry-run                    # 3 akış (v1/v1-dyn/v1-15m), son 3 gün, önizleme
./.venv/bin/python sync/backtest_recent.py --days 2 --wipe-scope window # gerçek yazım: sadece bu pencereyi tazele
```
> Şema/RPC: `supabase/trading_signals_schema.sql` + `supabase/backtest_analytics.sql` bir kez uygulanır.

## 7c. PULSE 15m canlı (ayrı 15-dakikalık cron)

PULSE = yüksek-frekans **15m, yalnız Strateji C** akışı. Saatlik MAIN taramasından
**tamamen ayrı**: DB'de `mode='pulse'`, Telegram'da `⚡ PULSE 15m` banner (veya ayrı kanal).
Aynı `dag/dag.py`, `pulse` argümanıyla çalışır.

Tek seferlik elle test (DB'ye `mode='pulse'` yazar, Telegram'a ⚡ banner'la atar):
```bash
cd ~/ict-trade && git pull
./.venv/bin/python dag/dag.py pulse
```
25 sembolü son kapanan 15m bar'ında tarar; yeni C sinyali varsa yazıp Telegram atar.

15-dakikalık cron (`crontab -e`, saatlik MAIN cron'unun altına). 15m bar kapanışından
**~15 saniye sonra** çalışır (`sleep 15`); MAIN ise saatlik HH:01'de (+1 dk) kalır:
```
0,15,30,45 * * * * cd /home/ubuntu/ict-bot && sleep 15 && SCAN_MODE=pulse /home/ubuntu/ict-bot/.venv/bin/python dag/dag.py >> /home/ubuntu/ict-pulse.log 2>&1
```
> `dag/dag.py pulse` ya da `SCAN_MODE=pulse` — ikisi de pulse taramasını seçer.
> Günlük `sync_daily.py` (00:30 UTC) artık **üç akışı da** (v1 / v1-dyn / v1-15m) backtest'e aktarır.

Opsiyonel — PULSE'u **ayrı bir Telegram kanalına** göndermek için `.env`'e ekle:
```
TELEGRAM_PULSE_CHAT_ID=<pulse_kanal_id>     # boşsa ana kanala ⚡ banner'la düşer
# PULSE_HEARTBEAT=1                          # her taramada "tarama yapıldı" özeti (varsayılan kapalı)
```
> Dedup mode-duyarlı: 15m pulse ile 1h live sinyali aynı sembol/bar-açılışında **çakışmaz**.

## 8. İzleme

```bash
tail -f ~/ict-bot.log        # canlı log
crontab -l                   # cron kayıtlı mı
```

---

## Notlar / sorun giderme

- **Güncelleme:** kodu yenilemek için `cd ~/ict-trade && git pull`. Bağımlılık değişirse
  `bash dag/setup_vm.sh` tekrar.
- **GitHub Actions:** `ict_signals.yml` ve `live_signals.yml` cron'ları kapalı — tek
  çalışan yer bu VM. (İstersen Actions'ta manuel tetikleyebilirsin ama 451 alır.)
- **Idempotent:** bot `(symbol, signal_time, direction)` kontrolü yapar; aynı saati iki
  kez çalıştırmak çift sinyal/Telegram üretmez.
- **VM kapanırsa** o saatki sinyal kaçar (cron çalışmaz). Always Free VM'ler kalıcıdır;
  Oracle "inactive" derse 7/24 cron zaten aktif tutar.
- **Binance hâlâ 451 verirse** (nadiren bazı Oracle IP blokları): instance'ı sonlandırıp
  yeni public IP ile tekrar oluştur, ya da Amsterdam bölgesini dene.
