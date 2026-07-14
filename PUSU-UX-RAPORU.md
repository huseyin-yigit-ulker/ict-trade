# PUSU — UX / Grafik / Bildirim Kapsamlı İyileştirme Çalışması

**Tarih:** 2026-07-14 · **Kapsam:** web + mobil (PWA), admin + user rolleri, grafikler, bildirimler
**Yöntem:** 3 paralel kod-keşif taraması (frontend/UI, grafik/dataviz, bildirim altyapısı) + 3 bağımsız tasarım perspektifi; benchmark olarak Binance, Bybit, TradingView, 3Commas ve Cornix desenleri. Rapordaki **her dosya/satır referansı fiilen okunan koddan** gelir; P0 iddiaları ikinci kez elle doğrulandı.

> Bu rapor bir **öneri kataloğudur** — bu turda hiçbir kod değişikliği yapılmadı. Toplam ~60 öneri, P0 (kritik) → P3 (cila) önceliğiyle; her öneri problem → benchmark → dosya-düzeyi uygulama taslağı → efor (S ≤1 gün / M 2-4 gün / L 1 hafta+) → risk formatında.

---

## 0. Yönetici özeti

PUSU'nun temeli sağlam: rol ayrımlı iki kabuk (admin legacy + kullanıcıya Binance-tarzı 4 sekme), gerçek PWA (service worker + web push + safe-area + 44px dokunma hedefleri), tema/i18n altyapısı, lightweight-charts v5 üzerinde zengin bir işlem görselleştirmesi (ChartModal) ve iki kanallı bildirim (Telegram + Web Push). Bu bir "eksik ürün" değil; sorunlar **son katmanda tutarlılık ve görünürlük** sorunları.

En büyük fırsatlar beş kümede toplanıyor:

1. **Bugün fiilen kırık olan şeyler (§1)** — altın sinyal-izleme push'u hiç çalışmıyor; executor push'ları strateji anonimleştirmesini deliyor; push teslimatı hata durumunda sessizce kayboluyor; light temada büyük grafikler siyah kalıyor. Bunlar öneri değil, **onarım**.
2. **Görünürlük boşluğu** — uygulama içinde bildirim merkezi/toast/unread yok; kullanıcı botun kritik durumunu (geçersiz API key, kill) ancak doğru sekmeye girerse görüyor; kullanıcının kendi parasının PnL geçmişi grafiği hiç yok (backtest'in var!).
3. **Grafiklerde tekilleştirme** — kline fetch 4 kopya, outcome-scan 3 kopya (JS×2 + Python), tema renkleri 2 ayrı dünya. Önce ortak util'ler, sonra özellikler (timeframe, volume, WebSocket).
4. **Bildirimde kontrol ve hijyen** — sessiz saat, dedup, severity routing, Urgency/TTL, test butonu, sağlık paneli yok. Çoğu S/M eforlu, birikince "spam hissi"ni "güvenilir sistem hissi"ne çevirir.
5. **Mobil cila** — pull-to-refresh, haptik, PWA shortcuts/badge, iOS push onboarding'i. Küçük ama kullanıcının her gün dokunduğu yüzeyler.

Önerilen ilk dalga (hepsi S/M): **C-1 signal-watch onarımı → C-2 drain maskeleme → C-8/Aşama-1 Telegram kanal ayrımı (.env, kod yok) → B-2 chartTheme → A-2 toast → A-3 AlertStrip**.

---

## 1. Kritik bulgular (öneriden bağımsız — bugün kırık)

### 1.1 Altın sinyal-izleme push'u hiçbir koşulda çalışamaz 🔴
Üç katman aynı anda kırık (hepsi kodda doğrulandı):
- `supabase/migrations/011_user_signal_watch.sql:18` — CHECK yalnız `('d30so8f3h7','d30so8f3vg','midas')` kabul ediyor; canlı akışlar ise `d30so8f3h7` + `talos_ichi` (`src/utils/streamMask.js` LIVE_STREAM_KEYS). MENKAR (altın) için kaydet → **CHECK ihlali, upsert patlar**.
- `sync/push_notify.py:120-125` `_MODE_TO_STREAM` — `talos_ichi` eşlemesi yok; emit `push_signal_watchers` çağırsa bile satır eşleşemez.
- `src/components/trading/SignalWatchCard.jsx:19` `UNI_BUCKET` — `talos_ichi` bucket'ı yok; kullanıcı sembol bile seçemiyor.
- Bonus: izinli 3 stratejiden 2'si ölü (`midas` backtest-only 2026-07-13'ten beri, `d30so8f3vg`/FABLE emekli 2026-07-07).

"Seçilebilen ama asla tetiklenmeyen alarm" sessiz-başarısızlık sınıfıdır — kullanıcı güvenini en çok kıran hata. Fix: bkz. **C-1** (efor S).

### 1.2 Anonimleştirme sızıntısı: executor kişisel push'ları maskesiz 🔴
- `sync/live_exec/executor.py:50` — `_TAG = "OPUS · d30so8f3h7"` (EXEC_NAME + gerçek version key); `_alert` (satır 55-66) bu metni HTML-strip edip **olduğu gibi** `push_user`'a veriyor.
- `sync/users/store.py:190` `push_user` ve `sync/push_notify.py:264` `drain_outbox` **hiç maskeleme yapmaz** (drain docstring'i bunu açıkça söylüyor). Aynı örüntü 4 executor'da da var.
- `009_admin_tools.sql` `admin_notify` RPC payload'ı verbatim yazar — duyuruda "OPUS" geçerse tüm kullanıcılara aynen gider.

Sonuç: non-admin bir kullanıcıya kendi executor'ünün push'unda **"OPUS · d30so8f3h7"** görünür — kod adı sözleşmesinin (ATLAS/MENKAR/VELA) tam ihlali. Broadcast sinyal yolu (`send_push`) doğru maskeliyor; kişisel yol delik. Fix: bkz. **C-2** (efor S). Not: `_MASK_MAP`'e VELA ekleyen working-tree diff'i (`sync/push_notify.py`) hâlâ commit edilmemiş.

### 1.3 Push teslimatı: "hata da olsa gönderildi sayılır" 🟠
`drain_outbox` (`sync/push_notify.py:305-330`) her satırı sonuç ne olursa olsun `sent_at=now()` işaretler; 404/410 dışındaki hatalar (5xx, timeout, **429**) yalnız print edilir, retry yok. Chrome 2026 başından beri Push API'ye hız limiti uyguluyor (aşımda HTTP 429) — meşgul bir günde push'lar sessizce kaybolur. Ayrıca tüm push'lar default TTL (4 hafta!) ve default urgency ile gidiyor: 3 gün önceki sinyal push'u telefon açılınca teslim edilebilir. Fix: **C-3** + **C-11**.

### 1.4 Light temada büyük grafikler bozuk 🟠
SVG mikro-grafikler (Sparkline, EquityCurvePanel, IntelViz) CSS token okuyup temayla dönerken, tüm lightweight-charts örnekleri koyu hex'leri hardcode ediyor: `src/components/ChartModal.jsx` (~269, 1088, 1443), `src/components/MidasLiveChart.jsx` (261, 391), `src/components/user/TradeChart.jsx:23`, `src/pages/TrendDetail.jsx` (92-95). Light temada beyaz sayfa ortasında siyah blok. Fix: **B-2**.

### 1.5 Outcome-scan mantığı 3 kopya 🟠
"Mumlardan işlemin akıbetini çöz" taraması üç yerde bağımsız yaşıyor: `ChartModal.jsx` (~462-540), `SharedTradePage.jsx` `scanOutcome` (55-97, kendi yorumu "sadeleştirilmiş ikiz"), `sync/live_exec/trade_report.py` (Python). Ayrıştıkları gün aynı işlem üç yüzeyde farklı sonuç gösterir — güven ürünü için en tehlikeli bug sınıfı. Fix: **B-3** (ortak util + JS/Python paylaşımlı test vektörleri).

### 1.6 İstemcide bildirimler birbirini eziyor 🟡
`executor.py:66` tüm executor push'larını sabit `tag="exec"` ile gönderiyor → tarayıcıda aynı tag'li bildirim bir öncekini **değiştirir**; hızlı ardışık olaylarda (GİRİŞ → TP1) kullanıcı yalnız sonuncuyu görür. Fix: **C-9** içinde tag'i `exec:{sym}:{pos_id}` yapmak (tek satır).

---

## 2. Mevcut durum haritası

### 2.1 UI/UX

| Katman | Durum |
|---|---|
| Stack | React 19 + React Router 7 + Vite 7, düz JS/JSX; global CSS + design token (`style.css` 3274 satır, `user.css` 702) |
| Roller | `AppRoutes.jsx` çatalı: admin → AppShell (Sidebar/Topbar, 13 rota), user → UserShell (4 sekme + profil/yardım, 560px) |
| Mobil | 768px kırılım; drawer, bottom tabbar (iki kabukta), tablolar→kart (`data-label`), fullscreen modallar, `useSwipeDownClose`, safe-area, ≥44px hedefler, 11× `prefers-reduced-motion` |
| PWA | vite-plugin-pwa manifest (standalone, maskable ikon), `sw.js` yalnız app-shell cache (veri asla — bilinçli), push + notificationclick deep-link, deploy'da otomatik reload |
| Tema/i18n | dark default + light (`[data-theme]` token swap, localStorage + user_prefs senkron); TR anahtar = TR metin, ~797 EN girdisi (≈%23 açık); sunucu metinleri yalnız TR |
| A11y | aria-label/role yaygın, `role="dialog/alert/progressbar"` var; **yok:** skip-link, `:focus-visible` standardı (user.css'te 0 focus kuralı), renk-körü desteği (win/loss yalnız renk) |
| Eksik desenler | in-app bildirim merkezi, toast, unread badge, pull-to-refresh, offline göstergesi, işlem geçmişi sayfalama (limit=60), PnL geçmişi grafiği |
| Monolitler | ChartModal 1458 · TradeContext 1257 · Dashboard 1174 · LanguageContext 1033 · style.css 3274 — tümü tek bundle (code splitting yok) |

### 2.2 Grafikler

| Katman | Durum |
|---|---|
| Kütüphane | Yalnız lightweight-charts v5 (7 dosya); mikro-viz el yapımı SVG; 1 canvas share kartı; Telegram'da matplotlib (`trade_report.py`) |
| Veri | App-owned OHLC API **yok** — tarayıcı doğrudan Binance REST (fapi→spot fallback); WebSocket yok; canlı ChartModal 3 sn'de bir TAM refetch |
| ChartModal | Mum/çizgi toggle, bar-dimming, 3 zone dolgusu, 6+ price line, trailing-stop path, ICT geometrisi (FVG/OB/SWEEP/BOS), marker'lar, OHLC legend, sürüklenebilir panel, TV iframe fallback, admin paylaşım (1 saatlik /p/:token). **Yok:** timeframe seçimi, hacim, indikatör; tema-uyumu yok |
| Backtest | Dashboard KPI hero + R-histogram + drill (Yıl→Ay→Gün, sparkline'lı); SummaryModal (equity + underwater bant + asimetri + dönem kartları + SQL tabloları); IntelligencePage A/B tearsheet |
| Kullanıcı | PositionCard/ClosedCard yalnız sayı; PnL/equity grafiği YOK (backtest'te var, gerçek parada yok) |
| SVG mikro-viz | Tooltip/etkileşim yok, `aria-hidden`; ama tema-uyumlu (CSS var) |
| Bilinen kırılganlık | strict-ascending-time istisnası (taze 30m sinyal), marker çakışması, `minHeight:520px` sabit |

### 2.3 Bildirimler

| Katman | Durum |
|---|---|
| Kanallar | Telegram (tek chat — `TELEGRAM_EXEC_CHAT_ID` env yazılı ama **unset**; sinyal+executor+close-card+digest+heartbeat+ops hepsi karışık) · Web Push (VAPID + pywebpush) |
| Push yolları | `send_push` broadcast (maskeli ✅) · `push_signal_watchers` hedefli (maskeli ✅ ama §1.1 nedeniyle altın için ölü) · `push_user` kişisel (maskesiz 🔴) → `push_outbox` → dakikalık `--drain` (maskesiz 🔴, retry'sız 🟠) |
| Tercihler | `user_prefs`: notify_entry/exit/milestone/signals/system (yalnız push ayağını süzer; Telegram hep tam akış) + `user_signal_watch` sembol listesi |
| Eksikler | sessiz saat, dedup/rate-limit, digest (yerleşik kullanıcıya), teslimat telemetrisi, test butonu, in-app merkez, severity routing, i18n, flair opt-out |
| Sağlam desenler | best-effort sözleşmesi (bildirim kodu asla raise etmez), 404/410 abonelik temizliği, broadcast/watchlist çifte-bildirim önleme, `push_flair` mizah katmanı (global env toggle) |

---

## 3. Benzer uygulamalarla karşılaştırma

| Desen | Binance/Bybit | TradingView | 3Commas/Cornix | PUSU bugün | Öneri |
|---|---|---|---|---|---|
| Bildirim merkezi + unread | ✅ standart | ✅ | ✅ timeline | ❌ | A-1/C-5 |
| İşlem sonucu toast'u | ✅ | ✅ (undo'lu) | ✅ | ❌ inline banner | A-2 |
| Bot hata banner'ı (her ekranda) | ✅ API-key uyarısı | — | ✅ kırmızı şerit | ❌ sekmeye gömülü | A-3 |
| PnL Analysis (günlük bar + kümülatif + takvim) | ✅ amiral gemisi | — | ✅ bot karnesi | ❌ (yalnız backtest) | B-7, B-12, A-5 |
| Grafik teması app temasını izler | ✅ | ✅ | — | ❌ | B-2 |
| Timeframe seçimi | ✅ | ✅ temel kontrol | — | ❌ otomatik | B-6 |
| Hacim pane | ✅ default | ✅ | — | ❌ (veri atılıyor) | B-8 |
| WebSocket canlı bar | ✅ istisnasız | ✅ | — | ❌ 3sn REST | B-5 |
| Sembol/strateji-bazlı bildirim susturma | ✅ fiyat alarmı | ✅ alert'ler | ✅ bot-başına | yarım (yalnız sinyal watchlist) | C-7 |
| Sessiz saat / DND | ✅ mute | — | ✅ | ❌ | C-6 |
| Kanal ayrımı (sinyal/işlem/ops) | — | — | ✅ ayrı kanallar | ❌ tek chat | C-8 |
| Test bildirimi | ✅ | — | ✅ | ❌ | C-4 |
| Push'ta işlem özeti digest'i | ✅ günlük | — | ✅ | yalnız yeni kullanıcıya | C-12 |
| PnL paylaşım kartı | ✅ poster | ✅ screenshot | — | ✅ var (keşfedilebilirliği düşük) | A-22, B-15 |
| Pull-to-refresh | ✅ | ✅ | ✅ | ❌ | A-14 |
| App shortcuts / badge | ✅ | — | — | ❌ | A-9, B-21 |

Sonuç: PUSU'nun eksikleri "egzotik" özellikler değil — bu kategorinin **beklenen** desenleri. Kullanıcı Binance mobil alışkanlıklarıyla geliyor; boşluklar doğrudan kıyasla hissediliyor.

---

## 4. Katalog A — UX (admin + user, web + mobil) · 22 öneri

### P0

**A-1. Uygulama-içi Bildirim Merkezi (push_outbox tabanlı)** — Bildirim geçmişi hiçbir yerde yok; push izni vermeyen (veya iOS'ta A2HS yapmamış) kullanıcı giriş/TP/SL olaylarını ve admin duyurularını **hiç görmüyor**. Benchmark: Binance/Bybit zil ikonu + unread rozeti; 3Commas olay timeline'ı. Uygulama: `push_outbox`'a select-own RLS + `authenticated` grant (yeni migration; **ÖNKOŞUL: C-2 enqueue-mask** — payload DB'de düz strateji adıyla durduğu sürece client SELECT açılamaz); `read_at` kolonu; `UserHeader.jsx` + `Topbar.jsx`'e zil + sayaç; yeni `NotificationSheet.jsx` (gün-gruplu liste, SignalsPage deseni); satır tıklaması payload `url`'ine deep-link + mark-read. Efor: **M** (C-2 ile birlikte L). C-5 ile aynı iş.

**A-2. Global toast/snackbar sistemi** — Geri bildirim sayfaya gömülü `setOk/setErr` banner'larında (`AdminPage.jsx:292`, trading kartları, Settings); uzun sayfada sonuç kaçıyor. Uygulama: `ToastContext.jsx` + `Toast.jsx` (`aria-live="polite"`, mobilde tabbar üstü safe-area konum, reduced-motion uyumlu); ilk dalga geçiş: AdminPage, StreamActivationCard, ApiKeysCard, SettingsPage. Form-doğrulama hataları inline kalır. Efor: **S/M**. Birçok öneri buna rapor verir — **ilk yapılacak iş**.

**A-3. Kalıcı kritik-durum uyarı şeridi (AlertStrip)** — API anahtarı `invalid` olursa / akış `kill_requested/drain`'e düşerse / günlük zarar tavanı vurursa kullanıcı ancak Bot sekmesinde görüyor. Gerçek parada bu sessizlik "bot çalışıyor sanıp günlerce sinyal kaçırma" senaryosu üretir. Benchmark: 3Commas/Cornix kırmızı kalıcı şerit; Binance API-key uyarısı. Uygulama: `AlertStrip.jsx`, `UserShell.jsx`'te header altına; veri zaten çekiliyor (`user_api_keys_public.status`, `user_stream_settings.kill_requested/drain` — BotPage:39 sorgusunu paylaşılan hook'a çıkar); tık → `/bot`. Efor: **S**.

**A-4. Grafiklerde light-theme uyumu** — §1.4'ün UX ayağı; uygulama detayı **B-2**'de. Efor: **S/M**.

### P1

**A-5. Portföyde PnL geçmişi kartı** — "Bu ay nasıl gitti?" cevapsız; kapalı işlem verisi RLS'li zaten iniyor. Benchmark: Binance PnL Analysis (günlük bar + kümülatif + 7/30/90g segment). Uygulama: `PnlHistoryCard.jsx` — `useLiveExec` closed listesinden günlük toplam + kümülatif; çizim mevcut `Sparkline`/`EquityCurvePanel` ile; `useLiveExec.js:138` limit=60 yetmez → kart mount'unda tek `state=eq.CLOSED&limit=500` fetch. `pusu.hideBalance` maskesine uyar. Efor: **M**. (Tam sayfa versiyonu: B-7.)

**A-6. İşlem geçmişi: sayfalama + tarih/sembol filtresi + admin CSV** — Kullanıcı en fazla son 60 işlem görebiliyor (`useLiveExec.js:138-142`); arşive erişim yok; admin export yok. Uygulama: `useLiveExec`'e `loadMore(beforeTs)` (`updated_at=lt.{ts}` cursor); TradesPage'e "Daha fazla" + sembol filtre + ay çipi; LivePositionsPage'e `exportCsv` (Blob, bağımlılıksız). Efor: **M**.

**A-7. Onboarding: iOS push adımı kaybolmasın + kurulum yönlendirmesi** — `OnboardingCard.jsx:93` push adımını `pushSupported=false` ise tamamen gizliyor: iOS Safari kullanıcısı bildirim özelliğinin varlığını hiç öğrenmiyor (Help 7. madde çözümü anlatıyor ama köprü yok); Android'de `beforeinstallprompt` hiç yakalanmıyor. Uygulama: iOS UA'da adımı "Bildirim için Ana Ekrana Ekleyin" olarak göster + `/yardim` anchor'ına link; yeni `InstallPrompt.jsx` (beforeinstallprompt + dismissed kalıcılığı) Portföy'de tek seferlik kart. Efor: **S/M**.

**A-8. Admin konsolu: arama/filtre + kullanıcı detay çekmecesi + toplu onay** — `AdminPage.jsx` (606) tablosu 10 kolon × satır başı 5-6 buton; kullanıcının keys+streams+audit'i üç ayrı tabloda. Benchmark: Stripe/Supabase Studio deseni (arama + durum filtresi + satır→drawer + bulk). Uygulama: `admin/UserTable.jsx` (e-posta arama, status çipleri, "bekleyen (n)" sekmesi), `admin/UserDrawer.jsx` (tek kullanıcının her şeyi), çoklu-seçim + "Seçilenleri Onayla" (`admin_set_user` döngüsü). Efor: **M/L**.

**A-9. PWA parlatma: manifest shortcuts + Badging + bildirim aksiyonları** — `vite.config.js:80-98` manifest'te `shortcuts` yok; ikon rozeti yok; `sw.js` bildirimleri aksiyonsuz. Uygulama: manifest'e Portföy/Sinyaller/Bot kısayolları; `navigator.setAppBadge` bildirim-merkezi sayacına bağlı (A-1); sw.js aksiyonları C-10'da. Efor: **S**.

**A-10. i18n: sunucu-üretimi metinler kullanıcı diline göre** — UI iki dilli ama push/Telegram metinleri sabit TR (`executor.py:831,846` "Acil durdurma", "Günlük zarar limiti"); EN kullanıcı en kritik anda anlamadığı dilde bildirim alıyor; TR→EN sözlükte ~%23 açık. Uygulama: `profiles.lang` kolonu (migration) + Settings toggle'ının profili de yazması; `push_notify.py`'ye {tr,en} şablon sözlüğü; dev-mode eksik-anahtar uyarısı. Efor: **M** (tam kapsam C-14'te L). 

**A-11. Erişilebilirlik paketi** — `user.css`'te 0 focus kuralı; skip-link yok; win/loss yalnız renk (kırmızı-yeşil körlüğünde PositionCard okunamaz). Benchmark: TradingView renk-körü paleti; Binance renk+işaret+ok üçlü kodlama. Uygulama: global `:focus-visible` kuralı; `App.jsx`/`UserShell.jsx` skip-link; kart değerlerine ▲/▼ glifi; `ThemeContext`'e opsiyonel `colorblind` tercihi (`[data-cb="1"]` → `--pos:#2E7CF6; --neg:#F0850A`; grafikler B-2'nin chartTheme'i üzerinden aynı token'ları okur). Efor: **M**. (Grafik ayağı: B-11.)

### P2

**A-12. Route-level code splitting** — `AppRoutes.jsx` her şeyi statik import ediyor; normal kullanıcı hiç göremeyeceği Dashboard(1174)/Intelligence/AdminPage'i indiriyor — mobil ilk açılış gereksiz yavaş. Uygulama: `React.lazy` + `Suspense fallback={<BootSplash/>}` (BootSplash mevcut): AdminPage, IntelligencePage, Dashboard/CommandCenter, SharedTradePage, MarketCap, TrendPage; ChartModal iki kabukta lazy. Efor: **M**. Bağımsız hızlı kazanım.

**A-13. Boş/yükleme/hata standardizasyonu + offline göstergesi** — SignalsPage'de güzel skeleton var; Portfolio/TradesPage düz "Yükleniyor…"; `useLiveExec` hataları yutuyor (`catch(()=>[])`) — "işlem yok" ile "veri gelmedi" ayırt edilemiyor. Uygulama: `useLiveExec`'e `error` state; skeleton'ları kopyala; `OfflineBar.jsx` (`navigator.onLine` + event) iki kabuğa; hata durumunda "Tekrar dene". Efor: **S/M**.

**A-14. Pull-to-refresh (kullanıcı kabuğu)** — 30sn poll + visibilitychange var ama mobil refleks çek-yenile; tek manuel tetik 44px altı `⟳`. Uygulama: `usePullToRefresh.js` (useSwipeDownClose touch deseni; scrollTop===0 + sürükleme → `refresh()`); `overscroll-behavior-y: contain`. Efor: **S**.

**A-15. Sinyal akış çiplerine 7g R mini-karnesi + sembol filtresi** — Çipler yalnız kod adı; kullanıcı ATLAS/VELA arasında neye göre seçeceğini bilmiyor; 18 sembollü akışta sembol filtresi yok. Benchmark: 3Commas bot kartında 7g/30g kâr rozeti. Uygulama: çip başına 7g R rozeti (hesap sayfada zaten var — `week.r`; seçili olmayan akışlar için hafif özet fetch, yalnız kod adı+R); uniq sembollerle ikinci çip satırı. Efor: **S/M**.

**A-16. Sayı biçimlendirme tek elden** — Para formatı dağınık (`useLiveExec.fmtUsd` vs `AdminPage.jsx:276` `toFixed(2)$`); binlik ayracı yok; kolon zıplaması. Uygulama: `src/utils/format.js` (`Intl.NumberFormat`: fmtMoney/fmtPct/fmtR); `.mono`'ya `font-variant-numeric: tabular-nums`. Efor: **S**.

**A-17. Admin Topbar'da sistem-sağlığı pili** — Heartbeat/invalid-key/outbox durumu yalnız /admin'de; admin Dashboard'da gezinirken arıza fark edilmiyor. Uygulama: Topbar'a `admin_overview` RPC'sini 60sn poll eden yeşil/kırmızı pil; bayat heartbeat'te toast; tık → /admin. Efor: **S/M**. (Bildirim-sağlığı kartı: C-4.)

**A-18. Haptik geri bildirim** — Kodda hiç `navigator.vibrate` yok; KILL onayı gibi yüksek riskli aksiyonlar dokunsal geri bildirimsiz. Uygulama: `haptics.js` (destek + reduced-motion kontrolü): StreamActivationCard KILL onayı, tabbar geçişi (10ms), bildirim-merkezi yeni öğe; bakiye değişiminde CSS flaş. Efor: **S**.

### P3

**A-19. "Bot neden işlem açmadı?" tanılama sihirbazı + aranabilir SSS** — En sık destek sorusuna tanı yolu yok; cevap verisi istemcide mevcut. Uygulama: `BotDiagnostics.jsx` — sırayla ① key valid? ② akış enabled? ③ sembol seçili? ④ son 48s sinyal var mı? ⑤ push açık mı? — ilk kırmızıyı vurgula + ilgili sekmeye link; HelpPage'e arama. Efor: **M**.

**A-20. ChartModal/Dashboard dosya ayrıştırması** — bkz. **B-10** (aynı iş, oradaki plan esas).

**A-21. Açılış sekmesi tercihi + filtre kalıcılığı** — User kabuğu hep /portfoy'a açılıyor; TradesPage filtresi unutuluyor. Uygulama: `userPrefs.js`'e `homeTab`/`tradesFilter`; Settings'e seçici; `AppRoutes.jsx` index redirect tercihten. Efor: **S**.

**A-22. ClosedCard'dan tek-dokunuş paylaşım** — `shareCard.js` (canvas + `navigator.share({files})`) hazır ama yalnız modal içinde; kapalı işlem kartında paylaşım ipucu yok — kazanan işlem paylaşımı organik büyüme kanalı, kod adı maskesi zaten uygulanıyor. Uygulama: ClosedCard'a paylaş ikonu → doğrudan shareCard akışı → toast. Efor: **S**.

---

## 5. Katalog B — Grafikler / Dataviz · 22 öneri

> lightweight-charts **v5 API adları typings'ten doğrulandı**: `autoSize`, `takeScreenshot(addTopLayer?, includeCrosshair?)`, `addSeries(def, opts, paneIndex)`, `panes()/setHeight/moveToPane`, `attachPrimitive` (ISeriesPrimitive), `addCustomSeries`, `createTextWatermark/createImageWatermark`, `createSeriesMarkers`, `series.update(bar)`, `subscribeCrosshairMove`, `subscribeVisibleLogicalRangeChange`.

### P0 — doğruluk ve temel

**B-1. Ortak kline pipeline'ı (`src/utils/klines.js`)** — Binance kline fetch'i 4 kopya: ChartModal (fapi→spot fallback + LRU), user/TradeChart, SharedTradePage, LivePositionModal. Hiçbirinde sort/dedupe güvencesi yok; taze 30m sinyallerde lightweight-charts'ın strict-ascending-time istisnası grafiği düşürüyor (§1.5 komşusu). Uygulama: `fetchKlines({symbol, interval, start, end, cacheable})` — fallback, doğrulama, `sort + dedupe`, LRU'nun taşınması, **`volume: +d[5]` parse** (B-8 hazırlığı); 4 dosya buna geçer. İleride app-owned proxy'ye geçiş için tek dokunuş noktası. Efor: **M**. Risk: düşük (davranış değişmez).

**B-2. Tema-duyarlı grafik renkleri (`src/utils/chartTheme.js`)** — §1.4. Uygulama: `readChartTheme()` — `getComputedStyle`'dan `--bg/--text/--win/--loss/--accent` okuyup lightweight-charts opsiyonlarına çevirir; `data-theme` değişiminde `chart.applyOptions` + `series.applyOptions`; zone dolguları için mevcut `--win-soft/--loss-soft` (style.css 1574-1575). Efor: **M**. Risk: light'ta opaklık kalibrasyonu — ekran görüntüsü karşılaştırmalı QA şart.

**B-3. Ortak outcome-scan util'i (`src/utils/outcomeScan.js`)** — §1.5'in çözümü. `scanOutcome(candles, {entry, sl, tp, partialLevel, dir, entryTs, flags})` → `{entryFillSec, partialBarSec, closeBarSec, result}`; ChartModal + SharedTradePage buna geçer. Python birleşemez → **paylaşımlı JSON test vektörleri** (aynı mum seti + beklenen çıktı) hem Vitest hem pytest'te koşar; parite sözleşmesi kilitlenir. Efor: **M**. Risk: scale-out/½TP dalları incelikli — test vektörleri işin parçası.

**B-4. `autoSize: true` + sabit yüksekliklerin kaldırılması** — ChartModal `minHeight:520px`; TradeChart kendi el yapımı ResizeObserver'ını taşıyor. v5 `createChart(el, {autoSize:true})` dahili RO kullanır. Uygulama: TradeChart RO'su silinir; ChartModal konteyneri responsive CSS'e (`min(70vh,…)`). Efor: **S**. Risk: konteyner ölçüsüz ise 0×0 — modal animasyonunda ilk ölçüm için rAF.

### P1 — yüksek etkili

**B-5. Canlı modda WebSocket kline stream** — `ChartModal.jsx:941`: 3 sn'de bir TÜM pencere refetch + tam rerender; bant genişliği, Binance IP rate-limit riski, GC baskısı. Benchmark: TradingView/Binance istisnasız WS ile bar günceller. Uygulama: `src/utils/klineStream.js` — `wss://fstream.binance.com/ws/<sym>@kline_<int>` (spot fallback); mesajın `k`'sı → `series.update()`; `k.x===true` yeni bar; ilk yükleme REST, `onclose`'da backoff + gap backfill; işlem kapanınca socket kapanır. Aynı combined-stream LiveTicker/PositionCard için paylaşılabilir. Efor: **M/L**. Risk: reconnect/gap doğruluğu, arka plan sekme throttling, 24h bağlantı ömrü.

**B-6. Kullanıcı seçimli timeframe (ChartModal)** — Interval otomatik (`pickInterval` 377-384); 4 saatlik işlemi 1m'de inceleme imkânı yok — "TV iframe'ine kaçış"ın ana sebebi. Uygulama: başlığa `1m 5m 15m 1h 4h 1d` segmenti (`pusu.chartTf` persist); 1450-bar guard'ı korunur (kırpılınca rozet göster); sola kaydırınca `subscribeVisibleLogicalRangeChange` + `barsBefore<50` → REST backfill (v5 resmi lazy-load deseni). **Kritik:** outcome-scan (B-3) her zaman kanonik interval'de koşar; timeframe yalnız render'ı etkiler. Efor: **M**. Bağımlılık: B-3.

**B-7. Kullanıcı "Portföy Analizi" sayfası** — Kullanıcı tarafında tek bir analitik grafik yok; backtest'in sermaye eğrisi kullanıcının gerçek parası için yok — **ürünün en büyük görsel boşluğu**. Benchmark: Binance Futures PnL Analysis (günlük PnL bar + kümülatif + win-rate kutuları + sembol kırılımı). Uygulama: `src/pages/user/PortfolioStatsPage.jsx`: stat şeridi (net USD, WR, seri, işlem sayısı); tek lightweight-charts örneğinde günlük PnL `HistogramSeries` + kümülatif `LineSeries` (`addSeries(def,opts,paneIndex)`, tema B-2'den); sembol kırılımı `Sparkline variant='bars'`. Veri: kullanıcının RLS'li kayıtları; strateji mekaniği kayıtta zaten yok. Efor: **L**. A-5 kartının tam sayfa hali; A-5 önce, bu sonra.

**B-8. Volume histogram pane (toggle)** — Kline'daki hacim (`d[5]`) hiçbir grafikte kullanılmıyor; sweep/BOS anlatan bir üründe hacim teyidi eksik. Uygulama: `chart.addSeries(HistogramSeries, {priceFormat:{type:'volume'}, priceScaleId:''}, 1)` — paneIndex=1 (TrendDetail'de desen mevcut); `panes()[1].setHeight(%18)`; bar rengi `--win-soft/--loss-soft`; legend'a toggle (`pusu.chartVol`, mobilde default kapalı). Efor: **S**. Bağımlılık: B-1 (volume parse).

**B-9. SVG mikro-grafiklere tooltip/crosshair** — Sparkline/EquityCurvePanel/MiniCurve/MarketCap LineChart'ta hover yok; "şu düşüş hangi tarihte?" cevapsız. **lightweight-charts'a migrasyon REDDEDİLDİ** (30+ kartta instance maliyeti; SVG'nin tema uyumu zaten daha iyi). Uygulama: `viz/useSparkTooltip.js` — `onPointerMove`'da en yakın nokta + portal tooltip + dikey kılavuz; öncelik EquityCurvePanel (işlem no + kümülatif R + tarih) ve MarketCap; 64×18 KPI spark'larına eklenmez (bilinçli sade). Efor: **M**. Risk: dokunmatikte scroll çakışması — pointerdown sonrası aktif.

**B-10. ChartModal decomposition (1458 → ~300 satır)** — Fetch, interval, scan, zone/marker kurulumu, panel drag, TV iframe, share tek dosyada; her değişiklik yüksek regresyon riski. Hedef yapı: `hooks/useKlines.js` (B-1 sarmalı + live tick) · `utils/outcomeScan.js` (B-3) · `chart/TradeChartCanvas.jsx` (chart + geometri render) · `chart/TradeInfoPanel.jsx` (sürüklenebilir panel) · ChartModal yalnız orkestrasyon. Sıra: B-3 → B-1 → decomposition → B-5/6/8 bu iskelete gelir. Efor: **M/L**. Risk: davranış birebir korunmalı; B-3 test vektörleri güvenlik ağı.

**B-11. Grafik erişilebilirliği** — Win/loss yalnız yeşil/kırmızı; SVG'ler `aria-hidden`, alternatif metin yok (WCAG 1.4.1). Uygulama: sayısal rozetlerde +/− denetimi; `Sparkline variant='bars'`a kayıp barlar için `<pattern>` çapraz tarama opsiyonu; EquityCurve/MiniCurve'e `role="img"` + `aria-label="Sermaye eğrisi: toplam +XR, tepe +YR, maks düşüş −ZR"` (veri modelde hazır); TP/SL price line'ları renk + `lineStyle` (solid/dashed) ile ayrışır. Efor: **S/M**. A-11 ile birlikte.

### P2 — değerli genişletmeler

**B-12. Aylık PnL takvim heatmap'i** — Drill kartları var ama "ayın hangi günleri kazandırdı" tek bakışta görünmüyor; kullanıcı tarafında hiç yok. Benchmark: Binance PnL takvimi; TraderSync/Tradervue günlük heatmap. Uygulama: `viz/PnlCalendar.jsx` — saf CSS grid (7 sütun), hücre alpha'sı günlük R/USD'ye göre, gün numarası + işlem sayısı noktası, tap→gün detayı; SummaryModal (backtest R) + B-7 sayfası (gerçek USD). Kütüphane gerekmez. Efor: **M**. Risk: renk skalası körlük-dostu (alpha + işaret birlikte).

**B-13. Underwater drawdown şeridi** — EquityCurvePanel DD'yi eğri-tepe bandı olarak veriyor; derinlik/süre okunmuyor. Benchmark: quantstats/pyfolio underwater plot. Uygulama: aynı `model`'den `peak−cum` serisi, ikinci mini SVG şeridi (1000×50, `--loss-soft`, en derin nokta etiketli) — mevcut bileşene ~30 satır; SummaryModal'da otomatik, B-7'de USD ile yeniden kullanılır. Efor: **S**.

**B-14. Intelligence'a BTC al-tut benchmark overlay** — A/B karşılaştırma var ama "pasif BTC'ye karşı" bağlamı yok; edge alfa mı beta mı görünmüyor. Uygulama: `MiniCurve`'e üçüncü kesikli `--muted` seri: aralık için 1d BTC kapanışları (B-1 util'i), başlangıca-göre-% normalize, legend'a "BTC al-tut". Sayfa admin-only — gizlilik sorunu yok. Efor: **M**. Risk: R-ekseni ile % ekseni karıştırılmamalı (ikisi de normalize %).

**B-15. Grafik screenshot/paylaşım butonu** — Kullanıcılar telefon screenshot'ıyla paylaşıyor (markasız, kırpık). Uygulama: v5 `chart.takeScreenshot()` → canvas → `shareCard.js` pipeline'ına (PUSU çerçevesi) → `sharePng()`; ayrıca `createTextWatermark(panes()[0], …)` düşük opaklıkta marka. Efor: **S**. Gizlilik: non-admin görünümde legend/panel zaten nötr; admin-only alanların canvas DIŞINDA (HTML panelde) kaldığı doğrulanmalı.

**B-16. Zone/FVG render'ının series primitive'lere taşınması** — Zone'lar 3 BaselineSeries hilesi; FVG/OB yalnız çizgi — kutu (zaman×fiyat dikdörtgeni) çizilemiyor. Uygulama: `chart/primitives/RectanglePrimitive.js` (ISeriesPrimitive; `timeToCoordinate` + `priceToCoordinate` ile canvas); BaselineSeries'ler ve FVG/OB çizgileri değişir; live'da zone re-setData biter. Efor: **M/L**. Risk: zoom/pan uçlarında koordinat testi; B-10'dan sonra.

**B-17. Marker çakışma yönetimi** — Sinyal/Giriş/TP1/Çıkış aynı bara düşünce etiketler üst üste. Uygulama: marker builder'da aynı `time`'ı birleştir ("Giriş + TP1"), above/below sırala, dar zoom'da `size` düşür. Efor: **S**.

**B-18. Sembol-bazlı yatay performans barları** — StatsModal per-symbol veriyi yalnız tablo veriyor. **Treemap REDDEDİLDİ** (10-30 sembolde alan algısı değer katmaz, etiket sığmaz). Uygulama: tablo üstüne toplam R sıralı div-bar listesi (`+X.XR · N işlem`) — Dashboard CSS-bar deseninin kardeşi. Efor: **S**.

### P3 — cila

**B-19. PositionCard PnL mini-sparkline** — Pozisyonun "yolculuğu" modala girmeden görünmüyor. Uygulama: `useLiveExec`'te sembol başına son ~40 mark-price rolling buffer (mevcut poll'dan, **ekstra Binance isteği YOK**) → `Sparkline variant='line'` + giriş referans çizgisi; buffer yoksa gizle. Efor: **M**. B-5'in paylaşılan WS'i gelirse doğal ikinci adım.

**B-20. Telegram kartına ay-içi net PnL inset'i** — Kart tek işlemlik bağlam veriyor; "bu kapanışla ay nasıl gidiyor" yok. **mplfinance REDDEDİLDİ** (el yapımı candle render markaya özgü; bağımlılık değmez). Uygulama: `render_card`'a köşe inset'i — Binance income history'den ayın günlük net serisi, 8-10 barlık mini spark (`_sparkline` deseninin kardeşi). Efor: **M**. Risk: income çağrısı hata verirse kart yine gitmeli (dosyanın "her şeyi yut" felsefesi korunur).

**B-21. PWA badge — dürüst kapsam** — "İkonda canlı PnL" **kısmen REDDEDİLDİ**: `setAppBadge` yalnız sayı/nokta gösterir. Yapılabilir: açık pozisyon SAYISI (`setAppBadge(open.length)`), sekme başlığına `(+$123) PUSU`, dinamik favicon. Efor: **S**. Progressive enhancement (iOS kısıtlı).

**B-22. Rejim sayfalarında crosshair okuma satırı** — TrendDetail'de hover'da "o gün skor kaçtı" yok. Uygulama: `subscribeCrosshairMove` ile başlık altına tarih · fiyat · skor · rejim satırı; MarketCap SVG'leri B-9 tooltip'ini alır. Efor: **S**.

---

## 6. Katalog C — Bildirimler · 16 öneri

### P0 — bug ve sözleşme ihlalleri (önerinin ötesinde: onarım)

**C-1. Sinyal izleme listesi onarımı** — §1.1'in çözümü. Uygulama: yeni migration `020_signal_watch_fix.sql`: CHECK'i genişlet `('d30so8f3h7','talos_ichi','midas','talos')` **veya** tamamen kaldırıp uygulama katmanında doğrula (yeni akış her defasında migration istemesin — önerilen bu); ölü `d30so8f3vg` satırlarını temizle. `push_notify.py` `_MODE_TO_STREAM`'e `"talos_ichi": "talos_ichi"`. `SignalWatchCard.jsx` `UNI_BUCKET`'a talos_ichi (akış XAUUSDT-only → `['XAUUSDT']` fallback yeterli; stream_universe seed'i doğrulanmalı). Efor: **S**. Risk: düşük — tablo yalnız push yönlendirir, emir yönetimine dokunmaz.

**C-2. Merkezi maskeleme: drain + enqueue çift katman** — §1.2'nin çözümü. Uygulama (tek dokunuşla en geniş kapsama): `drain_outbox()` içinde `_admin_user_ids` setini çek (desen dosyada mevcut); `user_id` admin değilse payload title/body'sine `_mask_text` uygula (url/tag'e değil) → `push_user`, `admin_notify` ve gelecekteki tüm enqueue'lar tek noktadan korunur (çifte maske zararsız — replace idempotent). Ek savunma: `_MASK_MAP`'i `sync/users/mask.py` paylaşılan modüle taşı ve `push_user` enqueue anında da maskele (**A-1/C-5 bildirim merkezinin ÖNKOŞULU** — DB'de düz metin kaldıkça client SELECT açılamaz); eski maskesiz satırlara tek seferlik mask-update. Working-tree'deki VELA `_MASK_MAP` diff'i commit edilmeli. Efor: **S** (drain) + **S/M** (enqueue+geçmiş temizliği). Risk: maskeleme best-effort try/except içinde kalmalı; admin'in kendi push'ları maskelenmez.

**C-3. Teslim telemetrisi + transient retry (Chrome 429)** — §1.3'ün çözümü. Uygulama: migration `021_push_outbox_delivery.sql`: `push_outbox`'a `attempts int default 0`, `last_error text`, `next_attempt_at timestamptz`; `push_subscriptions`'a `fail_count`, `last_success_at`. `drain_outbox`: başarı→sent_at; 404/410→prune (mevcut); 429/5xx/timeout→`attempts+1`, `next_attempt_at = now() + 2^attempts dk`, satır açık kalır; `attempts>=5`→sent_at+last_error (poison-pill tavanı — kuyruk sınırsız büyümez, mevcut tasarım hedefi korunur); SELECT'e `next_attempt_at` şartı. Efor: **M**. Risk: tüm yeni mantık mevcut dev try/except + "migration yoksa sessiz no-op" deseninde kalır; emir yönetimi hiçbir koşulda etkilenmez.

### P1 — yüksek değer

**C-4. Test bildirimi butonu + admin bildirim-sağlığı kartı** — VAPID yoksa push sessiz no-op (`push_notify.py:154`); kullanıcı açar, gelmez, neden anlaşılmaz. Benchmark: tüm push SDK'larında "send test notification". Uygulama: Settings Bildirimler kartına "Test Bildirimi Gönder" → yeni RPC `user_test_notify()` (auth.uid()'e sabit nötr payload insert; dakikalık drain ≤60sn'de teslim; RPC içinde 1dk rate-limit); AdminPage'e Bildirim Sağlığı kartı (bekleyen outbox, 24h sent/fail — C-3 kolonlarından, abone sayısı, VAPID configured). Efor: **S** (buton) + **M** (kart).

**C-5. In-app Bildirim Merkezi** — A-1 ile aynı iş; bildirim tarafı gereksinimleri: migration'da `read_at` + `grant select, update(read_at)` + RLS `user_id=auth.uid()` (update yalnız read_at kolonu — payload kullanıcı tarafından değiştirilemez); **ÖNKOŞUL C-2 enqueue-mask**. iOS push'suz kullanıcının bildirim deneyimini sıfırdan kurtarır; push "best effort", merkez "source of truth" olur. Efor: **L** (toplam).

**C-6. Sessiz saatler (TZ-aware, kritik-override)** — Gece 03:00 TP1 push'u; hiçbir zamanlama kontrolü yok. Benchmark: Binance mute; kritik istisna (margin-call kategorisi asla susmaz) endüstri normu. Uygulama: migration: `user_prefs.quiet_start/quiet_end smallint` (dakika-of-day) + `quiet_tz text default 'Europe/Istanbul'`; Settings'e aralık seçici. Uygulama noktası **drain**: penceredeyse `next_attempt_at = pencere_bitişi` (C-3 altyapısını yeniden kullanır); `kind='system'` deler; broadcast sinyalde erteleme yerine **düşür** (sinyal 15dk'da bayatlar). Efor: **M**. Risk: TZ `zoneinfo`; hata → "gönder" default'u.

**C-7. Executor olayları için strateji+sembol susturma** — 4 `kind` toggle'ı ya hep ya hiç; "ATLAS BTC'yi bildir, DOGE'u sustur" yok. Benchmark: 3Commas bot-başına bildirim. Uygulama: migration: `user_exec_mute(user_id, stream, symbols[])` — `user_signal_watch`'un ikizi (aynı semantik → kullanıcı modeli tutarlı); `_alert`→`push_user`'a `stream/symbol` parametreleri; `push_allowed` mute'a da bakar; UI: SignalWatchCard kopyası `ExecMuteCard.jsx`. Efor: **M**. Risk: `push_allowed` hata→TRUE deseni korunur; Telegram/owner ayağı değişmez.

**C-8. Telegram severity routing** — Her şey tek chat'te; kritik ops uyarısı gürültüde kayboluyor. Altyapı yarı hazır: `TELEGRAM_EXEC_CHAT_ID` fallback'i 4 executor config'inde + digest + trade_report'ta kodlu ama env **unset**. Uygulama — Aşama 1 (**S, kod değişikliği YOK**): `.env`'e `TELEGRAM_EXEC_CHAT_ID` set et → executor yaşam döngüsü + close-card + digest ayrı chat'e. Aşama 2 (S): `TELEGRAM_OPS_CHAT_ID` + safety_sweep/heartbeat tercihi. Aşama 3 (M, ops.): supergroup topics (`message_thread_id`). Efor: **S→M**. Risk: yanlış chat_id sessiz kayıp — her kanalda heartbeat doğrulaması.

**C-9. Dedup / rate-limit + tag düzeltmesi** — §1.6 + hiçbir bastırma penceresi yok; Chrome 429 sunucu tarafı throttle'ı ayrıca zorunlu kılıyor. Uygulama: (1) `tag="exec"` sabitini `exec:{sym}:{pos_id}` yap (tek satır, istemcide ezilme biter); (2) drain'de kullanıcı-başına dedup — aynı `(user_id, tag, body)` son 30sn'de gittiyse `last_error='dedup'`; (3) kullanıcı-başına dakika tavanı (10/dk, fazlası `next_attempt_at`'e); (4) `webpush(..., headers={'Topic': tag[:32]})`. Efor: **M**. Risk: anahtar body+tag ikilisi olmalı (yalnız tag değil — TP1 + hemen exit farklı body, yutulmamalı).

### P2 — deneyim

**C-10. sw.js zengin bildirimler** — Yalnız title/body/tag/url işleniyor. Uygulama: payload şeması `{…, kind?, silent?, renotify?, badge_count?}`; `options.actions=[{action:'open_chart', title:'Grafiği Aç'}]`; `notificationclick`'te `event.action` dallanması; milestone'da `silent:true`; `setAppBadge(badge_count)` (destek yoksa yut). Eski SW yeni alanları yok sayar — geriye uyumlu. Efor: **S/M**. Risk: iOS `actions` desteklemez — feature-detect.

**C-11. Urgency/TTL header'ları** — Her push default TTL (4 hafta) + default urgency. Uygulama: `webpush(..., ttl=…, headers={'Urgency':…})`; kind haritası: entry/exit/system=high/1800 · signal=high/900 · milestone=normal/3600 · digest=low/86400. Efor: **S**. Risk: yok denecek kadar az.

**C-12. Günlük/haftalık performans digest'i (opt-in)** — `newuser_digest.py` yalnız ≤7 günlük kullanıcıya; yerleşik kullanıcının "bugün nasıl geçti" özeti yok. Benchmark: Binance günlük özet; düşük frekanslı yüksek değerli push = en iyi retention aracı. Uygulama: newuser_digest'i genelleştir (`perf_digest.py`); hedef `user_prefs.notify_digest='daily'|'weekly'|null` (**default null = kapalı**, opt-in); cron mevcut 18:05 hattının yanına; `kind='digest'` → C-11'de low. Format zaten nötr ("Bugün: 2 işlem, +$3.40"). Efor: **M**.

**C-13. Kritik ops eskalasyonu (ack'e kadar tekrar)** — "Executor X dk çalışmıyor, N pozisyon korumasız!" (`safety_sweep.py:142-144`) tek atımlık; gece kaçarsa pozisyonlar saatlerce korumasız. Benchmark: PagerDuty tarzı ack-until-repeat; borsa risk bildirimleri susturulamaz. Uygulama: durum `app_flags`'e (`ops_alert_stale_exec` + first_seen); koşul sürdükçe 5→10→15dk backoff ile Telegram (ops kanalı, C-8) + owner push tekrar; AdminPage sağlık kartına "Onayla/Sustur" (mevcut `admin_set_flag` deseni); düzelince "düzeldi ✅". Efor: **M**. Risk: sweep'in kendi try/except'inde; alarm fırtınasına karşı backoff şart.

### P3 — cila

**C-14. Sunucu string i18n** — A-10'un tam kapsamı: `sync/users/notif_i18n.py` `{key: {tr, en}}` şablonları; `push_user` lang'ı `user_prefs`'ten okur (push_allowed sorgusuyla birleşik tek SELECT); kapsam yalnız push şablonları — Telegram owner kanalı TR kalır; kademeli (önce en sık 8-10 executor mesajı). Efor: **L**. Risk: çeviri maskeli kod adlarıyla çalışmalı; format hatası push'u düşürmemeli (fallback TR).

**C-15. Flair (espri) opt-out** — `push_flair.py` kind≠system push'larına rastgele espri ekliyor; kapatma yalnız global env. Ciddi para yöneten kullanıcı "Kasa gülümsüyor 😎" istemeyebilir (Robinhood konfeti dersi). Uygulama: `user_prefs.notify_flair boolean default true`; `push_user` spice öncesi kontrol (lang SELECT'iyle aynı sorgu); Settings NOTIF_ROWS'a satır; broadcast ayağında flair'i tamamen kaldır (kullanıcı-başına olamıyor). Efor: **S**.

**C-16. Owner çift-bildirim azaltma** — Canonical hesapta her olay hem Telegram hem push (tasarım gereği) — gürültü ×2. Uygulama: önce **sıfır-kod** çözüm: owner'ın legacy (user_id NULL) subscription'larını silmesi; yetmezse `user_prefs.notify_push_mirror` tercihi (`kind='system'` mirror kapalıyken bile geçer). Efor: **S**.

---

## 7. Yol haritası (bağımlılık sıralı)

| Dalga | İçerik | Tema |
|---|---|---|
| **0 — Onarım** (hepsi S) | C-1 signal-watch · C-2 drain maskeleme · C-8/Aşama-1 (.env, kod yok) · C-9/tag düzeltmesi (tek satır) | Bugün kırık olanlar |
| **1 — Görünürlük** | A-2 toast → A-3 AlertStrip → C-3 telemetri → C-4 test butonu+sağlık · A-17 topbar pili | "Sistem bana söylüyor" hissi |
| **2 — Merkez** | C-2/enqueue-mask → A-1/C-5 Bildirim Merkezi → A-9 PWA badge/shortcuts → C-10 zengin sw.js → C-11 TTL/Urgency | Bildirim çekirdeği |
| **3 — Grafik temeli** | B-1 klines → B-3 outcomeScan → B-4 autoSize → B-2 chartTheme → A-11/B-11 a11y | Tekilleştirme + tema |
| **4 — Grafik amiral gemisi** | B-10 decomposition → B-6 timeframe → B-8 volume → B-17 marker | ChartModal |
| **5 — Canlılık** | B-5 WebSocket → B-19 kart spark → B-21 badge | Gerçek-zaman |
| **6 — Analitik** | A-5 PnL kartı → B-7 Portföy Analizi → B-12 takvim → B-13 DD → B-18 sembol barları → B-14 benchmark | Kullanıcı analitiği |
| **7 — Kontrol** | C-6 sessiz saat → C-7 exec mute → C-12 digest → C-13 eskalasyon | Bildirim kontrolü |
| **Sürekli** | A-12 lazy-loading (erken alınabilir) · A-13/14/16/18 · A-6/7/8 · geri kalan P3'ler | Cila |

## 8. Değişmezler (her PR'da kontrol)

1. **Anonimleştirme sözleşmesi:** non-admin hiçbir yüzeyde gerçek strateji adı / version key / mekanik terim (ATRX, Keltner, Ichimoku, Donchian, konfluens, kalite skoru) görmez. Referans desen: `sd.isAdmin` çatalları (`ChartModal.jsx:766,1286,1387`), `streamMask.js`, R-ekonomisinin "Hedef"e nötrlenmesi. Yeni yüzeyler (bildirim merkezi, digest, Portföy Analizi, paylaşım) yalnız kullanıcının kendi kayıtlarındaki nötr alanlardan beslenir. En sağlam yol: maskelemeyi **enqueue + drain çift katmana** almak (C-2).
2. **Best-effort sözleşmesi:** bildirim/rapor kodu ASLA raise etmez, emir yönetimini etkileyemez (`trade_report.py` ve `push_notify.py`'deki mevcut desen); migration uygulanmamışsa sessiz no-op ("pre-migration" örüntüsü) korunur.
3. **Veri tazeliği:** SW trading verisi cache'lemez (bilinçli karar — korunur); offline UX bunu gösterge ile telafi eder (A-13), cache ile değil.
4. **Tek-pozisyon motoru PRE/POST filtre tuzağı** ve backtest/live parite kuralları bu rapor kapsamı dışında ama grafik outcome-scan'i (B-3) parite test vektörleriyle kilitlenir.

## 9. Değerlendirilip REDDEDİLEN fikirler (gerekçeli)

| Fikir | Neden red |
|---|---|
| SVG mikro-grafikleri lightweight-charts'a taşımak | 30+ kartta instance maliyeti (canvas+RO+event); SVG'nin CSS-var tema uyumu zaten üstün. Tooltip ihtiyacı B-9 ile çözülür. |
| Sembol performansı treemap'i | 10-30 sembolde alan algısı katma değer vermez, etiketler sığmaz → sıralı yatay bar (B-18). |
| Telegram kartında mplfinance | El yapımı candle render markaya özgü ve yeterli; bağımlılık eklemeye değmez → inset iyileştirmesi (B-20). |
| İkon rozetinde canlı PnL değeri | `setAppBadge` yalnız sayı/nokta gösterir; PnL işareti/değeri teknik olarak imkânsız → açık pozisyon sayısı (B-21). |
| Win-rate ring/gauge | Zaten bilinçli reddedilmiş (`Dashboard.jsx:603` yorumu: %17.9 arc +428R kitabında yanlış okunur) — korunur. |
| Firebase/OneSignal migrasyonu | VAPID + Telegram rayları yeterli; dış servis bağımlılığı eklemez (C setinin tamamı mevcut raylar üstünde). |
| Tailwind/TypeScript migrasyonu | UX işi değil; mevcut token'lı düz CSS düzeni çalışıyor. |
| Broadcast sinyalde sessiz-saat ertelemesi | Sinyal 15 dk'da bayatlar → ertelemek yerine düşürmek doğru (C-6). |

## 10. Kaynaklar

- MDN — Web Push API Best Practices; web-push kütüphanesi README (TTL/Urgency/Topic header'ları)
- Chrome 2026 push rate-limit (HTTP 429) duyurusu
- Binance — App Settings & Notifications yardım sayfaları; Binance.US fiyat alarmı/mute dokümanı
- lightweight-charts v5 typings (`node_modules/lightweight-charts/dist/typings.d.ts`) — API adları buradan doğrulandı
- Keşif: bu repo (tüm dosya/satır referansları 2026-07-14 working tree)

