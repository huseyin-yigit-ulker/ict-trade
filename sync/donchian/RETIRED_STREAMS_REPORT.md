# Strateji Emeklilik Raporu — donchian dışındaki tüm stream'ler

*Tarih: 2026-06-16 · Karar: yalnızca `donchian` stream'i kalsın; aşağıdakiler UI + DB + live'dan kaldırılsın.*
*Bu rapor, silme ÖNCESİ kalıcı kayıttır — her stream'in sonuçları + yorumum.*

---

## 0. Özet karar

| Stream | Net R (full) | 2025 OOS | Karar | Gerekçe |
|---|---|---|---|---|
| **donchian** | +288.1 (2026) | **+662 / +179 (24)** | **KALIYOR** | Tek hem büyük-örneklem pozitif hem çok-yıl OOS-onaylı |
| v1 (MAIN) | **−223.0** | −260.1 | KALDIR | OOS felaketi; orijinal ICT seti net zarar |
| opus | +39.1 | **−117.6** | KALDIR | 2026-overfit; OOS negatif |
| opus_half | −14.6 | −108.3 | KALDIR | Aynı overfit, daha kötü; ½TP zarar |
| range | +73.7 | +14.0 | KALDIR | Gerçekten pozitif ama odak için kaldırılıyor (kullanıcı kararı) |

**Tek cümle:** donchian, sistemdeki **tek** stream ki hem geniş örneklemde net pozitif hem de bağımsız yıllarda (2025 +662R, 2024 +179R kısmi) doğrulanmış. Diğerleri ya net zarar (v1), ya yalnızca in-sample (opus), ya da daha küçük/odak-dışı (range).

---

## 1. Envanter (silme öncesi)

### Backtest DB (`ict_trade.trading_signals`)
| version | satır | net R | WR | sembol | aralık |
|---|---|---|---|---|---|
| v1 | 6813 | −223.0 | %16 | 40 | 2025-01 → 2026-06 |
| donchian | 2409 | +288.1 | %23 | 40 | 2026-01 → 2026-06 |
| opus | 1872 | +39.1 | %17 | 18 | 2025-01 → 2026-06 |
| opus_half | 1872 | −14.6 | %27 | 18 | 2025-01 → 2026-06 |
| range | 432 | +73.7 | %32 | 28 | 2025-01 → 2026-06 |

### Live DB (`ict_trade.signals`)
| mode | satır | sembol | aralık | not |
|---|---|---|---|---|
| (null) | 739 | 12 | 2026-02 | eski/etiketsiz |
| Weekday | 622 | 12 | 2026-02→05 | eski deneysel |
| Weekend | 506 | 12 | 2026-02→05 | eski deneysel |
| live | 494 | 39 | 2026-05→06 | MAIN tarayıcı (aktif) |
| impulse | 78 | 31 | 2026-06 | IMPULSE tarayıcı (aktif) |
| *donchian* | 0 | — | — | henüz emit etmedi (cron :01) |

---

## 2. Stream stream — sonuçlar + yorum

### 2.1 v1 (MAIN) — orijinal ICT seti (B/C/D/E) → **KALDIR**
| yıl | işlem | net R | WR |
|---|---|---|---|
| 2025 | 1304 | **−260.1** | %14 |
| 2026 | 825 | +37.0 | %18 |
| **Toplam** | 2129 | **−223.0** | %16 |

**Yorum:** Bu, projenin orijinal ICT stratejisi — ve veriler acımasız. 2025'te **−260R** (out-of-sample felaket), 2026'da yalnızca +37R (zar zor pozitif, kısmen in-sample). WR %16 — likidite-süpürme/FVG/OB confluence setinin geniş, düşük-edge'li bir ortalaması. Memory'deki "v1 OOS-negatif, period-fit" tespitini birebir doğruluyor. **Net −223R taşıyan bir stream UI'da tutulmamalı.** donchian'ın varlık sebebi zaten buydu: MAIN bir RANGE sistemiydi ve trendde batıyordu.

### 2.2 opus — MAIN, sembol-başı NY seansına filtreli → **KALDIR**
| yıl | işlem | net R | WR |
|---|---|---|---|
| 2025 | 348 | **−117.6** | %12 |
| 2026 | 216 | +156.7 | %25 |
| **Toplam** | 564 | +39.1 | %17 |

**Yorum:** +39R net "pozitif" görünüyor ama bu bir **yanılsama**. Tüm kazanç 2026'dan (+156.7R) — ve opus'un sembol×seans seçimi tam da 2026 verisi üzerinde yapıldı (in-sample, ders kitabı overfit). 2025 OOS'ta **−117.6R**. Yani opus, donchian_ict deneyinde gördüğümüz tuzağın canlı örneği: in-sample parlak, OOS çöküyor. **Güvenilmez, kaldırılmalı.**

### 2.3 opus_half — opus + ½TP çıkış → **KALDIR**
| yıl | işlem | net R | WR |
|---|---|---|---|
| 2025 | 348 | −108.3 | %23 |
| 2026 | 216 | +93.7 | %33 |
| **Toplam** | 564 | **−14.6** | %27 |

**Yorum:** opus'un ½TP varyantı. Aynı 2026-overfit / 2025-OOS-çöküş paterni, üstüne ½TP toplam R'yi daha da düşürüyor (net negatif). Memory'deki "½TP genelde net-negatif" tespitiyle tutarlı. Kaldır.

### 2.4 range — Burak RANGE_DEV sapma-fade → **KALDIR (ama gerçekten pozitif)**
| yıl | işlem | net R | WR |
|---|---|---|---|
| 2025 | 215 | +14.0 | %29 |
| 2026 | 193 | +59.7 | %35 |
| **Toplam** | 408 | **+73.7** | %32 |

**Yorum:** Dürüst olmak gerekirse, **range gerçek bir edge taşıyor** — iki yılda da pozitif (+14 / +60), WR %32 (en yüksek). Bu bir mean-reversion kaynağı (donchian'ın tam tersi rejim). Net zarar eden v1/opus'tan farklı olarak range silmeye "mecbur" değil. Kullanıcı **odak** için (tek-strateji sadeleştirme) kaldırılmasını istedi — teknik gerekçeyle değil. **Not:** range backtest-only ve `backfill_range.py` ile yeniden üretilebilir; istenirse ileride geri getirilebilir.

---

## 3. donchian neden kalıyor (karşılaştırma)

| | v1 | opus | range | **donchian** |
|---|---|---|---|---|
| Net R | −223 | +39 | +74 | **+288 (2026)** |
| 2025 OOS | −260 | −118 | +14 | **+662** |
| 2024 OOS | — | — | — | **+179 (kısmi)** |
| Çok-yıl tutarlı? | ✗ | ✗ | ~ | **✓ (3 yıl pozitif)** |
| Örneklem | büyük | orta | küçük | büyük |

donchian, **tek** stream ki hem büyük örneklem, hem net pozitif, hem de bağımsız iki+ yılda OOS-onaylı. Diğerleri bu çubuğu geçemiyor.

---

## 4. Kaldırma planı (bu rapordan sonra uygulanacak)

**Backtest DB:** `DELETE WHERE version IN ('v1','opus','opus_half','range')` → 10,989 satır. *(Hepsi script'lerle yeniden üretilebilir: sync_daily / backtest_opus / backfill_range.)*

**Live DB:** `DELETE WHERE mode IN ('live','impulse','Weekday','Weekend')` + null mode → 2,439 satır. **⚠️ DİKKAT: live sinyaller gerçek-zamanlı geçmiş emisyonlardır — script'le yeniden üretilemez, kalıcı silinir.**

**UI:** `STRATEGY_VERSION` / `STRATEGY_LIVE_MODE` / Sidebar `GROUPS` / `streamStats.STREAMS` / `strategyInfo` → yalnızca donchian kalır.

**Live (crontab):** main(:01) + impulse(:02) + halftp(*/5) tarayıcıları kaldırılır; **donchian emit(:01) + sync_daily(00:30) kalır.**

**2024 bitince:** donchian'ın 2024 + 2025 sonuçları backtest DB'ye yazılır (`backtest.py --apply`), böylece UI'da üç-yıllık geçmiş görünür.
