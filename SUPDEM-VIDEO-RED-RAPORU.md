# Supply/Demand "Gold $1k/day" Video Stratejisi — İnceleme & RED Raporu

**Tarih:** 2026-06-28 · **Durum:** ❌ REDDEDİLDİ (canlı kurallarımız altında edge yok) · **DB'ye yazılmadı, UI'a bağlanmadı**

Kaynak video: YouTube `AY7fWmE1CBk` — *"This Gold Trading Strategy Makes $1,000 a Day"* (supply & demand / arz-talep).

---

## 1. Strateji mantığı (mekanikleştirilmiş hali)

Tez: kurumsal para agresif alım/satım yaptığında grafikte hızlı tek-yönlü bir mum serisi (displacement) bırakır; bu hareketin **başladığı bölge** doldurulmamış emirlerin durduğu yerdir. Fiyat oraya dönünce tepki verir, biz kurumla **aynı yöne** gireriz.

1. **Bölge (zone):** ≥3 ardışık aynı renk 1h mum + net hareket ≥1.0·ATR(14) olan bir impuls'ün **köken mumu**. Demand = yükseliş impulsünün tabanı, Supply = düşüş impulsünün tabanı. Kutu = köken mumunun [low, high]'ı.
2. **Retest:** fiyat 15m'de bölgeye geri girer. (1h kapanış bölgenin distal kenarını kırarsa bölge iptal.)
3. **Tetik (15m):** 8-EMA çapraz geçişi (fiyat işlem yönüne geçer) **+** engulfing mum.
4. **SL:** bölge distal'inin ötesi (−0.1·ATR tampon). **TP:** soldaki "key level" = önceki swing ekstremi, RR [1.5, 6]'ya kırpılır (varsayılan 2.5).

Kod: `sync/supdem_backfill.py` (self-contained detektör + portföy walk + DB-write iskeleti). Keşif/sweep: `scratchpad/supdem_video_bt.py`, `scratchpad/supdem_sweep.py`.

---

## 2. Sonuçlar — KRİTİK: giriş modeli her şeyi belirliyor

Aynı sinyaller, iki farklı giriş modeliyle çözüldü (4 sembol: BTC/ETH/XAU/XAG, 2026):

| Giriş modeli | Toplam R | WR | PF | Not |
|---|---|---|---|---|
| **entry@close** (mum kapanışında giriş) | **+201R** | 50% | 2.09 | Videonun kendi girişi |
| **+0.5R live confirm** (BİZİM canlı kuralımız) | **−3.2R** | 42% | 0.98 | Edge yok |

entry@close ile 3 yıl OOS-dayanıklı görünüyordu (2026 ~+185R / 2025 +175R / 2024 +152R, PF 1.7–2.0). **Ama bu bizim canlı kuralımız değil.**

---

## 3. Hata: pozitif sonuçlar bir ölçüm artefaktıydı

İlk testlerde "live +0.5R confirm" açtığımı sandım ama **yanlış env değişkeni** set edilmiş:

- Set edilen: `ENTRY_AT_CONFIRM`
- `ict.config`'in OKUDUĞU: **`DCH_ENTRY_AT_CONFIRM`** (`config.py`: `ENTRY_AT_CONFIRM = os.environ.get("DCH_ENTRY_AT_CONFIRM","0")=="1"`)

Dolayısıyla +0.5R kaydırma **hiç devrede değildi** → tüm sweep/backtest aslında **entry@close** koşmuş. Üretim backfill'i `sync/live_exec/_bootenv.py`'yi import ettiği için doğru `DCH_ENTRY_AT_CONFIRM=1`'i set etti ve gerçek sonucu (−3.2R) ortaya çıkardı.

**Neden +0.5R bu stratejiyi öldürüyor:** +0.5R teyit, donchian gibi **uzak hedefli** (RR 4–8) trend kırılımları için ucuzdur. Bu ise **dar hedefli bir fade** (RR~2.5): +0.5R beklemek hareketin ~%20'sini veriyor, riski 1.5×'e şişiriyor ve fade'in para kazandığı "bölgeden temiz dönüş" işlemlerini atlıyor. Üçü birleşince edge sıfırlanıyor.

---

## 4. Yan bulgular (entry@close modeli altında, artık geçersiz canlı-iddia ama metodolojik olarak doğru)

- **Bu bir "gold" stratejisi değil:** XAU 2026'da tek negatif sembol; gerçek edge BTC/ETH'te.
- **fee-tabanı (MIN_RISK_PCT=0.20%)** gerçek bir iyileştirme: stop fiyatın <%0.1–0.2'si olduğunda komisyon R'yi şişiriyordu (−6R aykırıları); taban bunları siliyor (maxLoss −6→−1.5). Ama bu, entry@close edge'i için geçerli — canlı kuralla edge zaten yok.
- 8-EMA (EMA9/21'den iyi), RR_MAX 6 (4/8'den iyi), impulse_N 3 & imp_ATR 1.0 optimumda — yani overfit yok; sorun parametre değil, **giriş modeli uyumsuzluğu**.

---

## 5. Karar & açık soru

**Standart canlı kurallarımız (+0.5R confirm) altında REDDEDİLDİ.** Hiçbir şey ship edilmedi: DB yazımı yok, UI bağlama yok, commit edilen canlı stream yok.

Strateji yine de entry@close'da gerçek bir edge taşıyor (+201R, OOS-dayanıklı). İki yol:
1. **Reddet** — standart live kuralımızdan geçmiyor (temiz seçim).
2. **Ayrı bir live yol** — sinyal mumu kapanışında, +0.5R teyit olmadan giren ayrı bir executor modu. O zaman +201R gerçek; ama teyitsiz giriş daha riskli ve ayrı altyapı gerektirir.

Bu rapor + `sync/supdem_backfill.py` + scratchpad scriptleri history olarak saklanıyor. İleride yeniden değerlendirilebilir.
