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
```
> Not: Eski hardcoded DB şifreni ve Telegram token'ını **yenilemen** önerilir (git geçmişinde açıktalar).

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
En alta ekle (HH:05'te, bar kapandıktan sonra):
```
5 * * * * cd /home/ubuntu/ict-trade && /home/ubuntu/ict-trade/.venv/bin/python dag/dag.py >> /home/ubuntu/ict-bot.log 2>&1
```
> VM saati UTC'dir (cron UTC çalışır) — bot zaten UTC bar mantığında, uyumlu.

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
