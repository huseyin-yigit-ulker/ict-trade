# Order Flow Araştırması — OPUS breakout barı agresyonu

**Tarih:** 2026-07-14
**Durum:** ARAŞTIRMA TAMAM — SHIP EDİLMEDİ, karar bekliyor
**Scriptler:** `scratchpad/of_fetch.py`, `of_feat.py`, `of_build.py`, `of_oos.py`, `of_buckets.py`, `of_control.py`, `of_generalize.py`, `of_size.py`, `of_lag.py`
**Çıktılar:** `scratchpad/of_oos_report.txt`, `of_gen_report.txt`, `of_oos_results.csv`, `of_sizing.csv`

---

## 0. Veri: tick arşivine gerek yok

Order flow için `aggTrades` indirmek gerektiği sanılır (BTCUSDT tek ay = **692 MB**). Gerekmiyor:
**Binance kline satırı zaten `taker_buy_volume` ve `count` taşıyor.** Agresör tarafı doğrudan mumdan
çıkar:

```
delta       = taker_buy − taker_sell = 2·taker_buy − volume
delta_ratio = delta / volume  ∈ [−1, +1]     ← "dr"
```

30m aylık dosya = **75 KB**. 18 sembol × 3 yıl = 126 MB, dakikalar içinde iner (`of_fetch.py`).
Kaynak: `data.binance.vision/data/futures/um/{monthly,daily}/klines/`.

---

## 1. Bulgu: breakout barının delta oranı (`dr`)

Donchian(55) kanalını kıran 30m barın **kendi agresör dengesizliği**, işlemin sonucunu öngörüyor.
Yön-hizalı (long'da +delta iyi, short'ta −delta iyi).

### OPUS (d30so8f3h7), 18 kripto, 2024-01 → 2026-07

| | işlem | totR | avgR | WR | PF | 2024 | 2025 | 2026 |
|---|---|---|---|---|---|---|---|---|
| BASELINE | 2812 | +386.4 | +0.137 | 54.4% | 1.29 | +45.7 | +201.0 | +139.7 |
| **dr > 0.10** | 1933 | +368.6 | **+0.191** | 55.6% | **1.41** | +62.0 | +177.3 | +129.3 |
| dr > 0.20 | 777 | +193.0 | +0.248 | 56.4% | 1.54 | +17.6 | +116.1 | +59.3 |

- İşlemlerin **%31'ini eler, R'ın %95'ini korur**. avgR **+%39**.
- Rastgele-eleme null'ına karşı **z = +2.62** (99.3. persentil, 300 çekiliş).
- Üç yılın üçü de pozitif.

### Kanıt zinciri (hepsi geçti)

| Test | Sonuç |
|---|---|
| **Nedensellik** | Fill'ler sinyal barından **en erken +31 dk** sonra. Breakout barı hiç para hareket etmeden kapanıyor. Lookahead yapısal olarak imkânsız. |
| **Lag taraması** | Spread −1:+0.221 → 0:+0.160 → +1:+0.086 → +3:+0.081. Düzgün bozunma; tek-nokta artefaktı değil. |
| **Monotonluk** | Quintile avgR: +0.084 / +0.082 / +0.158 / +0.120 / **+0.243**. Eşik sivrilmesi değil, merdiven. |
| **Long ve short** | İki tarafta da çalışıyor (rho +0.50 / +0.90). |
| **Momentum kontrolü** | `corr(akış, ret12) = −0.06`. Fiyat+volatilite akışın varyansının sadece **%12**'sini açıklıyor. Akış momentumun kılık değiştirmiş hâli DEĞİL. |
| **Çifte sıralama** | Her fiyat-momentum quintile'ı **içinde** akış hâlâ ayrıştırıyor (ort. rho +0.70). Tersi doğru değil: her akış quintile'ı içinde fiyat ayrıştırmıyor (ort. rho −0.22). **Akış fiyatı domine ediyor.** |
| **Walk-forward** | Eşik SADECE 2024'te seçildi (dr>0.10 kazandı) → dokunulmadan 2025-26'ya uygulandı: avgR +0.187 → **+0.229 (+%23)**, işlemlerin %73'ü korundu. |
| **Çapraz-strateji** | `d1h_so8c` (1h bar, 4h onayı YOK, farklı exit, farklı sinyaller): avgR +0.068 → **+0.120 (+%76)**, z=+2.47, üç yıl da pozitif. **OPUS'a özgü değil.** |
| **Yanlışlama** | Teori "ıraksak akış kötü olmalı" dedi; ölçüm doğruladı: `cvd_pos<0` → avgR +0.072 (z=−1.40, 9.7. persentil). Tahmin edilen yönde başarısız oluyor. |

### Fiyat momentumu TERS çalışıyor (yan bulgu)

Breakout öncesi fiyat ne kadar uzadıysa sonuç o kadar **kötü**: `ret48` quintile'ları
+0.218 → −0.076 (rho −0.90). Yani "zaten koşmuş" breakout'lar kötü, "agresyonla kırılan" breakout'lar iyi.
Bu ikisi bağımsız ve zıt eksenler.

---

## 2. YANLIŞ İZ: trailing CVD eğimi (agg12/agg24)

**Bu çalışmanın en önemli negatif sonucu.** Son 6-12 saatin net agresyonu (`agg12` = son 12 barın
delta toplamı / hacim toplamı) OPUS'ta **kusursuz bir merdiven** verdi:

```
agg12 quintile avgR:  +0.029  +0.035  +0.165  +0.200  +0.258     rho = +1.00, p = 0.000
```

Çalışmadaki en güzel tablo buydu. **Ve genellemedi.** Aynı kapı 1h kardeş stratejide:

```
agg12>0   z = −0.65     agg24>0   z = −0.23     cvd_pos>0   z = −0.06
```

Yani rastgele elemeden **daha kötü**. Monotonluk tablosunda dursaydım yanlış şeyi ship edecektim.
Trailing CVD eğimi OPUS'un kendi geçmişine uydurulmuş bir örüntü; breakout barının kendi delta'sı ise
piyasa özelliği.

**Diğer elenenler:**
- `ats_z` (ortalama işlem büyüklüğü = "büyük oyuncu" proxy'si): null'a karşı z=+2.47 çıkardı **ama
  monotonluğu yok** (rho −0.10, hörgüç şeklinde). Tam olarak null-geçen-artefakt profili. Yüksek z tek
  başına yeterli değil — bunun canlı kanıtı.
- `dr_z` (delta'nın z-skoru): sinyal yok (rho +0.10). Seviyeyi normalize etmek bilgiyi yok ediyor —
  **agresyonun mutlak seviyesi** önemli, son 2 güne göre sapması değil.
- `volx` (breakout barının bağıl hacmi): OPUS'ta güçlü NEGATİF (rho −0.90, yüksek hacim = kötü, klasik
  "climax/likidite süpürmesi") ama 1h'te ters işaret (rho +0.70). **Replike olmadı, güvenilmez.**

---

## 3. Dürüst maliyet: filtre para KAZANDIRMIYOR

Bunu net söylemek gerekiyor:

> **Saf filtre olarak dr>0.10 toplam R'ı DÜŞÜRÜYOR: +386.4 → +368.6 (−%4.6).**

Sabit $-risk/işlem ile çalıştığınız için toplam kâr toplam R ile orantılı. Yani filtre bir *kâr*
iyileştirmesi değil, bir *verimlilik* iyileştirmesi:

| | totR | işlem | maxDD | getiri/DD | işlem-başı Sharpe |
|---|---|---|---|---|---|
| baseline | +386.4 | 2812 | 61.6R | 6.28 | +0.090 |
| filtre dr>0.10 | +284.7¹ | 1668 | **44.5R** | 6.40 | **+0.109** |

¹ *post-hoc ledger üzerinden; slot mekaniğiyle yeniden yürütülen gerçek sayı +368.6 / 1933 işlem.
Fark tam olarak PRE/POST tuzağı: elenen sinyal sembol slotunu boşaltır, sonraki sinyal girer.*

### Daha iyi kullanım: KANAAT BAZLI BOYUTLANDIRMA

Filtrelemek yerine **her işlemi al, akışa göre boyutlandır**. Boyutlandırma işlem *kümesini*
değiştirmediği için PRE/POST tuzağı ve slot mekaniği riski **sıfır** — baseline ledger doğrudan
yeniden ağırlıklandırılabilir.

| şema | totR | risk-birimi | R/birim |
|---|---|---|---|
| baseline (hepsi ×1.0) | +386.4 | 2812 | +0.137 |
| **dr>0.10 ise ×1.25, değilse ×0.5** | **+406.7** | **2657** | **+0.153** |
| dr>0.10 ise ×1.5, değilse ×0.5 | +477.9 | 3074 | +0.155 |

**×1.25/×0.5 şeması her iki eksende de baseline'ı domine ediyor: daha çok R (+%5), daha az sermaye
(−%5.5).** Her yıl pozitif (2024 +52.5 / 2025 +205.1 / 2026 +149.2).

⚠️ Ağırlıklar (1.25/0.5) post-hoc seçildi. Sağlam olan kısım **sıralama** (yüksek-akış > düşük-akış);
oranın tam değeri değil. Ayrıca hafızadaki [[regime-sizing-oos-fail]] uyarısı geçerli — o çalışmada
6-dedektörlü ensemble sizing OOS'ta çökmüştü. Fark: oradaki sinyal walk-forward ve çapraz-strateji
testlerinden geçmemişti, buradaki geçti.

---

## 4. Uygulama notu

Canlı veri yolu `taker_buy_volume`'ü **düşürüyor**: `backtest/ict/data.py:17 fetch_klines()` sadece
`["open","high","low","close","volume"]` döndürüyor. Binance REST kline yanıtının **9. alanı**
taker-buy base volume — sadece parse edilip taşınması gerekiyor. Backfill için ek API çağrısı yok.

---

## 5. Karar

| Seçenek | Ne olur |
|---|---|
| **A — hiçbir şey** | Bulgu doğru ama filtre toplam kârı düşürüyor. Meşru seçim. |
| **B — sizing (×1.25/×0.5)** | Daha çok R, daha az sermaye, işlem kümesi değişmez. En cazip. Sizing'in OOS'ta çöktüğü bir geçmiş var. |
| **C — filtre (dr>0.10)** | %31 daha az işlem, %28 daha az maxDD, %39 daha iyi avgR, %4.6 daha az toplam R. Slot/marj kısıtlıysa mantıklı. |

Önerim: **B**, ama önce backtest-only bir stream olarak (yeni version tag) canlıya paralel koşturup
gerçek emirlerle karşılaştırmak — MIDAS/TALOS'ta izlenen yolun aynısı.

---

---

# BÖLÜM 2 — TALOS-ICHI / XAUUSDT 2026

**Sonuç: SHIP EDİLEBİLİR BİR ŞEY YOK.** Ama iki değerli çıktı var, biri OPUS bulgusunun canlı altın
akışına taşınmasını engelliyor.

**Scriptler:** `scratchpad/ofg_fetch.py`, `ofg_talos.py`, `ofg_xau.py`, `ofg_split.py`, `ofg_buckets.py`

## Kurulum

Canlı gerçek-para stream'i `talos_ichi` (exec tag `tichix`), XAUUSDT, tek pozisyon. Sinyal **1m** barda
(Keltner 15m'den ffill), giriş **bir sonraki 1m barın açılışında** — yani sinyal barı para hareket
etmeden kapanıyor, nedensellik temiz. Baseline (PRE, canlı semantik): **238 işlem / +107.8R /
avgR +0.453 / PF 1.93** — RUNBOOK'taki rakamlarla örtüşüyor.

⚠️ PRE/POST tuzağı burada **zaten bir kez ısırmış**: talos_ichi POST rakamlarıyla ship edilmiş
(PAXG +107.2R) ama üretim PRE koşuyor (+55.2R) — 227 "doğan" işlem, −53.7R. Ben baştan PRE koştum.

## Hipotez: OPUS'un TERSİ

Bir **pullback** girişinde iki zıt okuma var:
- **H1 ONAY:** dönüş barında alıcılar zaten agresif olmalı (delta > 0 iyi). ← OPUS'un breakout mantığı
- **H2 EMİLİM:** satıcılar hâlâ agresif vuruyor ama fiyat kırılmıyor → biri limitle yutuyor (delta < 0 iyi).

## Sonuçlar (XAU 2026, fit Oca-Nis / test May-Tem)

| sınıf | in-sample ort. ΔavgR | **OOS ort. ΔavgR** | OOS'ta pozitif |
|---|---|---|---|
| **H1 onay** | −0.054 | **−0.096** | **0 / 3** |
| **H2 emilim** | +0.182 | **−0.105** | 2 / 8 |

### 1. KESİN NEGATİF: OPUS bulgusu TALOS'a TAŞINMAMALI

H1 (akış-onayı) hem in-sample hem OOS'ta **negatif**, 3 kapının 3'ü de. Yani OPUS'ta çalışan
"delta breakout yönünü onaylasın" kuralı altına naif şekilde port edilseydi **canlı altın akışına
zarar verecekti**. Bu, çalışmanın en operasyonel çıktısı.

### 2. Emilim doğru yön, ama ship-grade DEĞİL

In-sample çok güçlü görünüyor (`dr5<-0.05`: POST avgR **+0.766** vs baseline +0.453, PF 2.29,
null'a karşı z=+2.02) ve baseline kitabı üzerinde **düzgün monoton**: `dr15` quintile'ları
+0.695 / +0.659 / +0.252 / +0.206, **rho = −1.00, p = 0.000** — pullback bacağına ne kadar agresif
satış geldiyse sonuç o kadar iyi. Teori tam olarak bunu öngörüyordu.

**Ama zaman bölmesinde çöküyor.** 8 emilim kapısından OOS'ta sadece 2'si pozitif (şansla beklenen
4'ün altında). Tek ciddi hayatta kalan `dr5<-0.05` (OOS ΔavgR +0.102) — 8 kapı denendiği için bu tek
başına bir şey ifade etmiyor.

### 3. Neden düzeltilemez: veri yok

**Binance XAUUSDT vadeli işlem verisi 2025-12-11'de başlıyor.** Toplam 238 işlem, OOS kısmı 82 işlem.
Daha fazla XAU verisi *yok*. Bu örneklemde ne yaparsak yapalım ~80 işleme fit ediyoruz. OPUS'ta
elimizde 2812 işlem ve 3 yıl vardı; burada yok. Fark tam olarak bu.

(Yan not: PAXG ve XAG'de de baktım — XAG'de TALOS-ICHI tamamen çöküyor, 208 işlem **−164.7R**. Üretimde
XAG yok, ama strateji altına özgü, gümüşe genellemiyor.)

## Karar

**HİÇBİR ŞEY SHIP ETME.** Emilim ilginç ve teoriyle uyumlu ama 238 işlemde kanıtlanamaz. Tekrar
bakmaya değer koşul: XAU verisi ~2 yıla ulaşınca (2027 sonu) veya PAXG'yi vekil kabul edip çok-yıl
koşarak.

---

## Changelog

- **2026-07-14** — Araştırma tamamlandı. Bulgu: breakout barı delta oranı (`dr`) yön-hizalı olarak
  öngörücü; walk-forward + çapraz-strateji + momentum-kontrolü + nedensellik testlerinin hepsini geçti.
  Trailing CVD eğimi (agg12/agg24) OPUS'ta kusursuz merdiven verdi ama 1h'te genellemedi — ELENDİ.
  Ship edilmedi, karar bekliyor.
- **2026-07-14 (Bölüm 2)** — TALOS-ICHI / XAU 2026 incelendi. SHIP YOK. H1 (akış-onayı, OPUS'un kuralı)
  in-sample ve OOS'ta negatif → **OPUS bulgusu altına port EDİLMEMELİ**. H2 (emilim) doğru yön ve
  in-sample güçlü (POST avgR +0.766, dr15 rho=−1.00) ama zaman bölmesinde çöküyor (8 kapıdan 2'si).
  Kök sebep: XAU vadeli verisi 2025-12'de başlıyor → 238 işlem, 82 OOS. Yeterli örneklem yok.
