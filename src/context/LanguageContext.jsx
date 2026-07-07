import { createContext, useContext, useState, useCallback, useMemo } from 'react';
import { savePrefs } from '../utils/userPrefs';

// Lightweight i18n (no dependency). Pattern: the Turkish string IS the key.
// t('Kapat') -> 'Kapat' in TR, EN[...] (or the key as fallback) in EN.
// Interpolate with {x}: t('{n} dk önce', { n: 5 }).

const EN = {
  // --- Chart modal controls ---
  'Mum': 'Candles',
  'Çizgi': 'Line',
  'Genişlet': 'Expand',
  'Daralt': 'Collapse',
  'Konfluens': 'Confluence',
  'Kalite': 'Quality',
  // --- Header / nav ---
  "Backtest'e Geç": 'To Backtest',
  "Live'a Geç": 'To Live',
  'Sembol Seçimi': 'Symbols',
  'Sembol ara...': 'Search symbol...',
  'Sonuç yok': 'No results',
  'Uygula': 'Apply',
  'Tümünü Seç': 'Select All',
  'Temizle': 'Clear',
  'Başarı Geçmişi': 'Track Record',
  'Likidite Avı': 'Liquidity Ambush',
  'Sembol': 'Symbols',
  'Mod': 'Mode',
  'Backtest': 'Backtest',
  'Sinyal yok.': 'No signals.',
  'Seçilmedi': 'None',
  'Ayarlar': 'Settings',
  'Tema': 'Theme',
  'Komuta Merkezi': 'Command Center',
  'İstihbarat': 'Intelligence',
  'Hacim Radarı': 'Volume Radar',
  'Hacim anomalisi': 'Volume anomaly',
  'Önceki periyotta anormal hacim artışı gösteren, sabit liste dışı semboller — aynı ICT motoruyla tarandı. Deneysel; backtest ile doğrulanmamış.': 'Symbols outside the fixed list with an abnormal volume spike in the prior period — scanned by the same ICT engine. Experimental; not backtest-validated.',
  'Henüz dinamik sinyal yok.': 'No dynamic signals yet.',

  // --- Intelligence Report card ---
  'Güven Skoru': 'Confidence Score',
  'GÜVEN': 'CONF',
  'LİKİDİTE OLAYI': 'LIQUIDITY EVENT',
  'Killzone': 'Killzone',
  'Yapı Kırılımı': 'Structure Shift',
  'Uygulama Planı': 'Execution Plan',

  // --- Login --- ('Şifre' already defined in the Dashboard/lock block; 'Çıkış'='Exit' kept for the chart — logout uses 'Çıkış Yap')
  'Kullanıcı adı': 'Username',
  'Giriş Yap': 'Sign In',
  'Kullanıcı adı veya şifre hatalı.': 'Invalid username or password.',
  'Piyasaya Gir': 'Enter the Market',
  'Şifreli Oturum': 'Secure Session',
  'Beni Hatırla': 'Remember Me',
  'Şifremi Unuttum': 'Forgot Password',
  'Şifreyi göster': 'Show password',
  'Şifreyi gizle': 'Hide password',
  'Doğrulanıyor…': 'Verifying…',
  'Erişim için sistem yöneticinize başvurun.': 'Contact your system administrator for access.',
  'bağlantı yok': 'no connection',
  'ÇEVRİMDIŞI': 'OFFLINE',
  'Çok fazla hatalı deneme. {s} sn bekleyin.': 'Too many failed attempts. Wait {s}s.',
  'Caps Lock açık': 'Caps Lock is on',
  'Oturum süresi doldu. Lütfen tekrar giriş yapın.': 'Your session has expired. Please sign in again.',
  'Varsayılan giriş bilgileri aktif — .env ile özelleştirin.': 'Default credentials are active — override them via .env.',

  // --- Topbar: killzone clock + refresh ---
  'Sonraki': 'Next',
  'ICT killzone saati (UTC)': 'ICT killzone clock (UTC)',
  'Son güncelleme': 'Last update',
  'Yenile': 'Refresh',

  // --- Dashboard: copy + empty state ---
  'Kopyala': 'Copy',
  'Motor bir likidite tuzağı yakaladığında sinyal burada belirecek.': 'Signals will appear here the moment the engine catches a liquidity trap.',

  // --- Settings ---
  'Görünüm': 'Appearance',
  'Koyu': 'Dark',
  'Açık': 'Light',
  'Dil': 'Language',
  'Veri & Motor': 'Data & Engine',
  'Kapsam': 'Coverage',
  'Veritabanı': 'Database',
  'Bağlantıyı Test Et': 'Test Connection',
  'Semboller': 'Symbols',
  'Hesap': 'Account',
  'Kullanıcı': 'User',
  'Çıkış Yap': 'Sign Out',
  'Hakkında': 'About',
  'Sürüm': 'Version',

  // --- Boot ---
  'sembol': 'symbols',
  'strateji': 'strategies',

  // --- Intro / hub (Genel Bakış) ---
  'Genel Bakış': 'Overview',
  'Stratejiler': 'Strategies',
  'Sekiz işlem akımı, tek bir likidite avı felsefesi — kurumsal süpürmeleri yakala, disiplinli çıkışla yönet.':
    'Eight trading streams, one liquidity-ambush philosophy — catch institutional sweeps, manage them with disciplined exits.',
  '{n} işlem akımı, tek bir likidite avı felsefesi — kurumsal süpürmeleri yakala, disiplinli çıkışla yönet.':
    '{n} trading streams, one liquidity-ambush philosophy — catch institutional sweeps, manage them with disciplined exits.',
  'Tüm sayılar 2026 backtest — örneklem içi. Forward beklenti daha düşüktür.':
    'All figures are 2026 backtest — in-sample. Forward expectancy is lower.',
  'En Yüksek R': 'Top Total R',
  'En İyi Beklenti': 'Best Expectancy',
  'En Yüksek İsabet': 'Top Win Rate',
  'Tam TP': 'Full TP',
  'Adaptif': 'Adaptive',
  'Seans': 'Session',
  'ICT Çekirdek': 'ICT Core',
  'Sembol-bazlı çıkış': 'Per-symbol exit',
  'Sırala': 'Sort',
  'İsabet': 'Win Rate',
  'Akım ara...': 'Search stream...',
  'Akım': 'Streams',
  'Detay': 'Detail',
  'Sonuç verisi yok': 'No result data',
  'Sonuç verisi alınamadı — akım açıklamaları yine de aşağıda.': "Couldn't load results — stream descriptions still below.",
  'örneklem içi': 'in-sample',
  'Operatör Girişi': 'Operator Login',

  // --- common / trade fields ---
  'Kapat': 'Close',
  'KAPAT': 'CLOSE',
  'Giriş': 'Entry',
  'Hedef': 'Target',
  'Risk': 'Risk',
  'Stop': 'Stop',
  'Çıkış': 'Exit',
  'İz Süren Stop': 'Trailing Stop',
  'İşlem Seansları (UTC)': 'Trading Sessions (UTC)',
  'Londra açılış-öncesi (07-13 UTC) atlanır · Cuma 16:00 ET düz · hafta sonu pozisyon yok':
    'London pre-NY (07-13 UTC) skipped · flat Fri 16:00 ET · no weekend positions',
  'işlem': 'trades',
  'alınmaz': 'not taken',
  'Binance · GERÇEK': 'Binance · REAL',
  // Scale-out (d30_4h_so) chart panel
  'Runner Cap (+{cap}R)': 'Runner Cap (+{cap}R)',
  'Runner Cap +{cap}R': 'Runner Cap +{cap}R',
  '+{cap}R cap · breakeven · {hor}g': '+{cap}R cap · breakeven · {hor}d',
  'Pozisyon Durumu': 'Position state',
  'SL · tüm pozisyon (+1R görülmedi)': 'SL · full position (+1R not reached)',
  'Ters sinyal · erken kapanış (+1R yok)': 'Reverse signal · early close (no +1R)',
  '%{book} +1R alındı · %{run} runner BE (0R)': '{book}% +1R booked · {run}% runner BE (0R)',
  '%{book} +1R alındı · %{run} runner +{cap}R cap': '{book}% +1R booked · {run}% runner +{cap}R cap',
  '%{book} +1R alındı · %{run} runner aktif (≤+{cap}R / {hor}g)': '{book}% +1R booked · {run}% runner active (≤+{cap}R / {hor}d)',
  '%{book} +1R alındı · %{run} runner mark ({hor}g)': '{book}% +1R booked · {run}% runner mark ({hor}d)',
  '%{book} +1R alındı · %{run} runner mark (veri sonu, <{hor}g)': '{book}% +1R booked · {run}% runner mark (data end, <{hor}d)',
  'Runner +{cap}R': 'Runner +{cap}R',
  'Mark': 'Mark',
  'Durum': 'Status',
  'İşlem': 'Trades',
  'Strateji': 'Strategy',
  'Piyasa': 'Market',
  'Kripto': 'Crypto',
  'Metal': 'Metal',
  'ABD Hisse': 'US Stocks',
  'En İyi': 'Top',
  'En Kötü': 'Worst',
  'Gizle': 'Hide',
  'Göster': 'Show',
  // --- Regime / Trend map ---
  'Rejim Haritası': 'Regime Map',
  'Her sembolün 4 saatlik fiyatından Efficiency Ratio hesaplanır ve anlık rejim sınıflanır (trend mi, yatay mı). Salt fiyat verisi — sinyal/backtest değil.':
    "Each symbol's regime is classified from its 4h price via the Efficiency Ratio (trending vs ranging). Pure price data — no signals/backtest.",
  'Güçlü Trend': 'Strong Trend',
  'Orta Trend': 'Mid Trend',
  'Hafif Trend': 'Light Trend',
  'Choppy': 'Choppy',
  'Son 10 günün rejim dağılımı': "Last 10 days' regime mix",
  'Hacim': 'Volume',
  'Hacim-ağırlıklı': 'Volume-weighted',
  'Güncel': 'Current',
  'Rejim karışımı': 'Regime mix',
  'Son ER skorları': 'Recent ER scores',
  'Fiyat & Rejim': 'Price & Regime',
  'eşik': 'thresholds',
  'Arka plan rengi o 4h barın rejimidir — kırmızı choppy, yeşil güçlü trend. Alt panel ER skoru.':
    "The background colour is each 4h bar's regime — red choppy, green strong trend. Lower pane is the ER score.",
  // --- Regime detectors / sub-modules (trend vs range ensemble) ---
  'Geçiş': 'Transition',
  'Range': 'Range',
  'Konsensüs': 'Consensus',
  'Rejim Submodülleri': 'Regime Sub-modules',
  'Teknik Göstergeler': 'Technical Indicators',
  'İstatistiksel': 'Statistical',
  'Efficiency Ratio detayı': 'Efficiency Ratio detail',
  'Hurst Üsteli': 'Hurst Exponent',
  'Varyans Oranı': 'Variance Ratio',
  'Otokorelasyon (lag-1)': 'Autocorrelation (lag-1)',
  'Net hareket / toplam yol — 1’e yakın temiz trend, 0’a yakın gürültü/range.':
    'Net move / total path — near 1 a clean trend, near 0 noise/range.',
  'Wilder yönsel hareket endeksi. ≥25 trend, <20 yatay/range.':
    'Wilder directional movement index. ≥25 trend, <20 sideways/range.',
  'Choppiness Index. ≥61.8 yatay/range, ≤38.2 trend.':
    'Choppiness Index. ≥61.8 sideways/range, ≤38.2 trend.',
  'R/S analizi (getiriler). H>0.5 kalıcı/trend, H<0.5 ortalamaya dönüş, ≈0.5 rastgele.':
    'R/S analysis (returns). H>0.5 persistent/trend, H<0.5 mean-reverting, ≈0.5 random.',
  'Lo–MacKinlay VR(4). >1 momentum/trend, <1 ortalamaya dönüş, =1 rastgele yürüyüş.':
    'Lo–MacKinlay VR(4). >1 momentum/trend, <1 mean-reversion, =1 random walk.',
  'Getiri lag-1 otokorelasyonu. Pozitif → momentum/trend, negatif → ortalamaya dönüş/range.':
    'Lag-1 autocorrelation of returns. Positive → momentum/trend, negative → mean-reversion/range.',
  'Her sembolün “trend mi range mi” sorusu altı bağımsız yöntemle ölçülür — üç teknik (Efficiency Ratio, ADX, Choppiness) + üç istatistiksel (Hurst, Varyans Oranı, otokorelasyon) — ve TREND ↔ RANGE ekseninde tek bir konsensüse indirgenir. Salt fiyat verisi — sinyal/backtest değil.':
    'Each symbol\'s "trend vs range" question is measured by six independent methods — three technical (Efficiency Ratio, ADX, Choppiness) + three statistical (Hurst, Variance Ratio, autocorrelation) — and reduced to one consensus on the TREND ↔ RANGE axis. Pure price data — no signals/backtest.',
  'Her submodül trend(+1) ↔ range(−1) ekseninde bağımsız ölçer; ortalamaları konsensüsü verir. Rejim ölçek-bağımlıdır ve gerçek-zamanlı okuma gecikmelidir.':
    'Each sub-module measures the trend(+1) ↔ range(−1) axis independently; their average is the consensus. Regime is scale-dependent and the real-time read lags.',
  'Arka plan = bar bazında rolling rejim · alt pane = konsensüs skoru (−1..+1).':
    'Background = per-bar rolling regime · lower pane = consensus score (−1..+1).',
  'Yukarıdaki ER karışımı ve doğruluk denetimi yalnız Efficiency Ratio submodülüne aittir; ana grafik 6-yöntemli konsensüsü gösterir.':
    'The ER mix and accuracy audit above are for the Efficiency Ratio sub-module only; the main chart shows the 6-method consensus.',
  // --- Regime accuracy (predictive audit) ---
  'Rejim Doğruluğu': 'Regime Accuracy',
  'Süreklilik': 'Continuation',
  'İleriye dönük uyum': 'Forward agreement',
  'Doğruluk': 'Accuracy',
  'Temel oran': 'Baseline',
  'Beceri': 'Skill',
  'Örnek': 'Sample',
  'bar': 'bars',
  'Yetersiz veri': 'Insufficient data',
  'ER rejim etiketi geçmiş pencereyi birebir tanımlar; ancak bir sonraki pencereyi öngörmede beceri göstermez. “Trend” dediğinde fiyat yönünü ~yarı yarıya (yazı-tura) sürdürür ve ileriye dönük uyum, hep çoğunluğu söyleme (temel oran) doğruluğunun altında kalır. Yani “şu an trend” bir tahmin değil, geçmişin betimlemesidir.':
    'The ER regime label describes the trailing window exactly, but shows no skill at predicting the next one. When it calls "trend," price keeps its direction roughly half the time (a coin-flip), and forward agreement stays below the always-guess-majority baseline. "Trend now" is a description of the past, not a forecast.',
  'Yöntem: her barın geriye-dönük ER etiketi (trend ER≥0.25) bir sonraki 10-bar penceredeki gerçekleşmeyle karşılaştırılır; pencereler ayrıktır. Temel oran = hep çoğunluğu söylemenin doğruluğu, Beceri = doğruluk − temel oran.':
    "Method: each bar's trailing ER label (trend if ER≥0.25) is compared with what actually happens over the next 10-bar window; the windows are disjoint. Baseline = accuracy of always guessing the majority class, Skill = accuracy − baseline.",
  'trend yönü korunur': 'trend keeps its direction',
  'sonraki pencere rejimi tutar': 'next window matches the label',
  'Sadece bu piyasayı seç': 'Select only this market',
  'Backtest R’ye göre en iyi 5 sembol': 'Top 5 symbols by backtest R',
  'Backtest R’ye göre en kötü 5 sembol': 'Worst 5 symbols by backtest R',
  'Tarih': 'Date',
  'Yön': 'Direction',
  'Tümü': 'All',
  'PnL': 'PnL',
  'P/L': 'P/L',
  'TP/SL': 'TP/SL',
  'Toplam R': 'Total R',
  'Toplam PnL': 'Total PnL',
  'Beklenti': 'Expectancy',

  // --- Dashboard: KPI / cards ---
  'R Dağılımı': 'R Distribution',
  'Risk {risk}% · Ödül {reward}%': 'Risk {risk}% · Reward {reward}%',
  'kapanan': 'closed',
  'sinyal': 'signals',
  'canlı': 'live',
  'TP1 Gelen': 'TP1 reached',
  'Canlı K/Z': 'Live P/L',
  'Canlı R': 'Live R',
  'kilitli': 'locked',
  'alındı': 'booked',
  'al': 'book',
  'sağlıklı': 'healthy',
  'pozitif': 'positive',
  'negatif': 'negative',
  'işlem başına': 'per trade',

  // --- Dashboard: drill + lock ---
  'Yıllar': 'Years',
  'Aylar': 'Months',
  'Günler': 'Days',
  'Aylara Dön': 'Back to Months',
  'Yıllara Dön': 'Back to Years',
  'Backtest Kilidi': 'Backtest Lock',
  'Şifre': 'Password',
  'Şifre hatalı.': 'Wrong password.',
  'Backtest Aç': 'Open Backtest',

  // --- status labels (display only) ---
  'BEKLEMEDE': 'PENDING',
  'BEKLİYOR': 'WAITING',
  'AKTİF': 'ACTIVE',
  'İPTAL': 'CANCEL',
  'TP+SL': 'TP+SL',

  // --- time-ago / duration ---
  'şimdi': 'now',
  'az önce': 'just now',
  '{n} dk önce': '{n} min ago',
  '{h} sa {m} dk': '{h}h {m}m',
  '{d} gün {h} sa': '{d}d {h}h',
  '{m} dk': '{m} min',
  ' dk': ' min',

  // --- Chart ---
  'Süre': 'Duration',
  'Süre (canlı)': 'Duration (live)',
  'Anlık Fiyat': 'Last Price',
  "Entry'ye Uzaklık": 'Distance to Entry',
  'Canlı Durum': 'Live Status',
  'Veri alınamadı.': 'Failed to load data.',
  'Veriler yükleniyor...': 'Loading data...',
  'Hesaplanıyor...': 'Calculating...',
  'Sinyal': 'Signal',
  'Manipülasyon Fazı': 'Manipulation Phase',

  // --- Summary ---
  'Başarı Paneli': 'Performance Panel',
  'Günlük, haftalık, aylık ve yıllık performans analizi.': 'Daily, weekly, monthly and yearly performance analysis.',
  'Genel Özet': 'Overview',
  'Toplam İşlem': 'Total Trades',
  'Başarı': 'Success',
  'TP / SL': 'TP / SL',
  'Aktif / İptal': 'Active / Cancelled',
  'Ortalama PnL': 'Average PnL',
  'En İyi Semboller': 'Top Symbols',
  'Kayıt yok': 'No records',
  'Günlük': 'Daily',
  'Haftalık': 'Weekly',
  'Aylık': 'Monthly',
  'Yıllık': 'Yearly',
  'Asimetri': 'Asymmetry',
  'DÜŞÜK İSABET · YÜKSEK GETİRİ': 'LOW HIT-RATE · HIGH PAYOFF',
  "En iyi 5 işlem toplam brüt kârın %{share}'ini taşıyor — az kazanır, büyük kazanır; sistem böyle tasarlandı.":
    'The top 5 trades carry {share}% of total gross profit — wins rarely, wins big; the system is designed this way.',
  'En Büyük Kazançlar': 'Biggest Wins',
  'SQL Analiz Özeti': 'SQL Summary',
  'Ortalama Süre': 'Avg Duration',
  'SQL Sembol Analizi': 'SQL Symbol Analysis',
  'SQL Zaman Analizi': 'SQL Time Analysis',

  // --- Stats / ticker ---
  'PORTFÖY KARNESİ': 'PORTFOLIO SCORECARD',
  'Canlı fiyatlar bağlanıyor…': 'Connecting to live prices…',
  'CANLI': 'LIVE',

  // --- sidebar mode + sidebar toggle ---
  'Menüyü Göster': 'Show menu',
  'Menüyü Gizle': 'Hide menu',
  'Operatör': 'Operator',
  'İptal': 'Cancelled',
  'Aktif': 'Active',

  // --- Equity panel ---
  'Sermaye Eğrisi (R)': 'Equity Curve (R)',
  'Tepe': 'Peak',
  'en büyük {n} kazanç': 'top {n} wins',

  // --- Intelligence: strategy comparison surface ---
  'Strateji Karşılaştırma': 'Strategy Comparison',
  'Backtest’teki stratejilerin çok boyutlu karşılaştırması — {a} ve {b}.': 'A multi-dimensional comparison of the backtested strategies — {a} vs {b}.',
  'Ortak Pencere (2026)': 'Common Window (2026)',
  'Tüm Geçmiş': 'Full History',
  '“Tüm Geçmiş”: {a} 2024’ten beri, {b} yalnızca 2026’dan beri var — toplam R’ler farklı pencereleri kapsar. Adil A/B için “Ortak Pencere”yi kullanın.':
    '"Full History": {a} runs from 2024, {b} only from 2026 — the totals cover different windows. Use "Common Window" for a fair A/B.',
  'İstihbarat Değerlendirmesi': 'Intelligence Verdict',
  'Aynı mantık, iki zaman dilimi — hangisi nerede önde?': 'Same logic, two timeframes — which leads where?',
  'Toplam R lideri': 'Total-R leader',
  'İşlem başına verim': 'Per-trade efficiency',
  'Risk verimi (Recovery)': 'Risk efficiency (Recovery)',
  'Günlük R korelasyonu': 'Daily-R correlation',
  'ikisi birden daha sağlam': 'running both is sturdier',
  'büyük ölçüde örtüşüyor': 'largely overlapping',
  'Birebir Metrikler': 'Head-to-Head Metrics',
  '▲ = o metrikte önde olan akım': '▲ = the stream leading that metric',
  'İşlem (kapanan)': 'Trades (closed)',
  'Ort. Kazanç / Kayıp': 'Avg Win / Loss',
  'Maks. Düşüş': 'Max Drawdown',
  'Recovery Factor': 'Recovery Factor',
  'Toplam R / Maks. Düşüş': 'Total R / Max Drawdown',
  'Tutarlılık (R/σ)': 'Consistency (R/σ)',
  'İşlem başına R / standart sapma': 'Per-trade R / standard deviation',
  'En uzun kayıp serisi': 'Longest losing streak',
  'En kötü tek işlem': 'Worst single trade',
  'Kayma/gap kaynaklı en derin tek kayıp': 'Deepest single loss from slippage/gaps',
  'İlk 5 kazanç payı': 'Top-5 win share',
  'Brüt kârın ne kadarı 5 işlemde — düşük = sağlam': 'How much gross profit sits in 5 trades — lower = sturdier',
  'Ort. tutma süresi': 'Avg hold time',
  'Aylık işlem temposu': 'Monthly trade tempo',
  'Ayda kapanan işlem sayısı': 'Closed trades per month',
  'No-fill (iptal) oranı': 'No-fill (cancel) rate',
  'Sermaye Eğrisi — üst üste': 'Equity Curve — overlaid',
  'Her iki akım ortak zaman ekseninde; eğrinin ŞEKLİ edge’i anlatır.': 'Both streams on a shared time axis; the SHAPE of the curve tells the edge.',
  'Sualtı (Drawdown) Eğrisi': 'Underwater (Drawdown) Curve',
  'Tepe altında geçen R — derinlik ve süre = acı eşiği.': 'R spent below the peak — depth and duration = the pain threshold.',
  'g': 'd',
  'sa': 'h',
  'Asimetri — az kazan, büyük kazan': 'Asymmetry — win small, win big',
  'RR=4 tam-TP → çıktı iki kutuplu: −1R (SL) ya da +4R (TP).': 'RR=4 full-TP → outcome is bimodal: −1R (SL) or +4R (TP).',
  'Ort. kazanç': 'Avg win',
  'Ort. kayıp': 'Avg loss',
  'Kazanç süresi': 'Win hold',
  'Kayıp süresi': 'Loss hold',
  'Kazananlar kaybedenlerden ~2× daha uzun tutuluyor — “kayıpları kes, kazananları koştur” imzası.':
    'Winners are held ~2× longer than losers — the "cut losses, run winners" signature.',
  'Sembol Bazında Birebir': 'Per-Symbol Head-to-Head',
  'Her sembolde hangi zaman dilimi daha çok R üretti (R’ye göre sıralı).': 'Which timeframe produced more R on each symbol (sorted by R).',
  'Piyasa Sınıfı': 'Asset Class',
  'Kripto / metal / ABD hisse — trend edge’i nerede?': 'Crypto / metal / US stock — where is the trend edge?',
  'Yön — Long / Short': 'Direction — Long / Short',
  'İşlem yönü bazında R ve isabet.': 'R and hit-rate by trade direction.',
  'Long ↗': 'Long ↗',
  'Short ↘': 'Short ↘',
  'Aylık Getiri': 'Monthly Return',
  'Ortak penceredeki her ayın net R’si — tutarlılık ve eş-zamanlılık.': 'Net R for each month in the common window — consistency and concurrency.',
  'Haftanın Günü': 'Day of Week',
  'Sinyal gününe göre R (UTC).': 'R by signal day (UTC).',
  'Günün Saati (UTC)': 'Hour of Day (UTC)',
  'İşlem saatine göre R — seans etkisi.': 'R by trade hour — session effect.',
  'Çeşitlendirme — ikisini birden çalıştırmak': 'Diversification — running both',
  'İki zaman dilimi ikame mi, tamamlayıcı mı? Düşük korelasyon + daha iyi Recovery = tamamlayıcı.':
    'Are the two timeframes substitutes or complements? Low correlation + better Recovery = complements.',
  'İkisi birden': 'Both',
  'İkisi birden Toplam R': 'Both — Total R',
  'İkisi birden Maks. Düşüş': 'Both — Max Drawdown',
  'İkisi birden Recovery': 'Both — Recovery',
  'Aynı gün ikisi de işlemde': 'Both trading same day',
  '(en iyi tek: {x})': '(best single: {x})',
  'İkisini birlikte çalıştırmak, en iyi tek akımdan daha yüksek risk verimi (Recovery) veriyor — zaman dilimleri birbirini tamamlıyor.':
    'Running both together delivers higher risk efficiency (Recovery) than the best single stream — the timeframes complement each other.',
  'Eğriler büyük ölçüde örtüşüyor — birini seçmek, ikisini birden çalıştırmaya yakın sonuç verir.':
    'The curves largely overlap — picking one is close to running both.',
  'Yıllara Göre (Örneklem-dışı)': 'By Year (Out-of-Sample)',
  '{a} üç yıl, {b} yalnızca 2026 — parametreler 2026-overfit değil.': '{a} spans three years, {b} only 2026 — the parameters are not 2026-overfit.',
  'Yıl bazında karşılaştırma daima tüm geçmişi kullanır (pencere filtresinden bağımsız).': 'The by-year comparison always uses full history (independent of the window filter).',
  'R / piyasada-gün': 'R / day-in-market',
  'Sermaye verimi: Toplam R / piyasada geçen gün': 'Capital efficiency: Total R / days in market',
  'Pozitif ay oranı': 'Positive-month rate',
  'Akımın işlem yaptığı ayların yüzde kaçı pozitif': "Share of the stream's active months that are positive",
  'Seçili penceredeki her ayın net R’si — tutarlılık ve eş-zamanlılık.': 'Net R for each month in the selected window — consistency and concurrency.',
  'Maliyet Duyarlılığı': 'Cost Sensitivity',
  'Backtest %0.1 round-trip’i zaten içerir; aşağısı EK kaymadır (bps/yön). Düşük WR + yüksek frekans bu stratejileri kaymaya çok duyarlı yapar.':
    'The backtest already includes 0.1% round-trip; the rows below are ADDITIONAL slippage (bps/side). Low WR + high frequency make these strategies very cost-sensitive.',
  'Ek kayma': 'Extra slippage',
  'Backtest (gömülü maliyet)': 'Backtest (embedded cost)',
  'yön': 'side',
  'Başabaş ek kayma': 'Break-even extra slippage',
  'Net R’yi sıfıra indiren ek kayma (yüksek = dayanıklı)': 'Extra slippage that drives net R to zero (higher = sturdier)',
  '30m hem ~2× daha sık işlem hem daha kısa risk mesafesi yüzünden kaymaya çok daha kırılgan: başabaş {a} ≈ {x}, {b} ≈ {y}.':
    '30m is far more fragile to slippage — ~2× more trades and a shorter risk distance: break-even {a} ≈ {x}, {b} ≈ {y}.',
  // --- Intelligence: dynamic stream selection ---
  'vs': 'vs',
  'Ortak Pencere ({y})': 'Common Window ({y})',
  '“Tüm Geçmiş”: akımlar farklı tarihlerde başlar ({a}: {ya}, {b}: {yb}) — toplam R’ler farklı pencereleri kapsar. Adil A/B için “Ortak Pencere”yi kullanın.':
    '"Full History": the streams start on different dates ({a}: {ya}, {b}: {yb}) — the totals cover different windows. Use "Common Window" for a fair A/B.',
  'Aynı aile, farklı varyant — hangisi nerede önde?': 'Same family, different variant — which leads where?',
  'Her sembolde hangi akım daha çok R üretti (R’ye göre sıralı).': 'Which stream produced more R on each symbol (sorted by R).',
  'İki akım ikame mi, tamamlayıcı mı? Düşük korelasyon + daha iyi Recovery = tamamlayıcı.':
    'Are the two streams substitutes or complements? Low correlation + better Recovery = complements.',
  'İkisini birlikte çalıştırmak, en iyi tek akımdan daha yüksek risk verimi (Recovery) veriyor — akımlar birbirini tamamlıyor.':
    'Running both together delivers higher risk efficiency (Recovery) than the best single stream — the streams complement each other.',
  'Akımlar farklı sayıda yıl kapsar — çok-yıla yayılan akım tek bir yıla overfit değildir.':
    'The streams span different numbers of years — a multi-year stream is not overfit to a single year.',
  '{f} kaymaya daha kırılgan (daha sık işlem ve/veya daha kısa risk mesafesi) — başabaş {a} ≈ {x}, {b} ≈ {y}.':
    '{f} is more fragile to slippage (more trades and/or a shorter risk distance) — break-even {a} ≈ {x}, {b} ≈ {y}.',
  'Başabaş ek kayma: {a} ≈ {x}, {b} ≈ {y}.': 'Break-even extra slippage: {a} ≈ {x}, {b} ≈ {y}.',

  // --- Multi-user auth: login/signup tabs + approval gate ---
  'E-posta': 'Email',
  'Kayıt Ol': 'Sign Up',
  'Yeni Hesap': 'New Account',
  'Hesap Oluştur': 'Create Account',
  'Şifre (en az 10 karakter)': 'Password (min 10 characters)',
  'Şifre (tekrar)': 'Password (repeat)',
  'Şifreler eşleşmiyor.': 'Passwords do not match.',
  'Şifre en az 10 karakter olmalı.': 'Password must be at least 10 characters.',
  'E-posta veya şifre hatalı.': 'Invalid email or password.',
  'Kayıt başarısız. Tekrar deneyin.': 'Signup failed. Please try again.',
  'Hesap oluşturuldu. E-postanızı doğrulayıp giriş yapın.': 'Account created. Verify your email, then sign in.',
  'Kayıt sonrası hesabınız yönetici onayına düşer; onaylanana kadar canlı işlem özellikleri kapalıdır.':
    'After signup your account awaits admin approval; live trading features stay locked until approved.',
  'Onay bekleniyor': 'Approval pending',
  'Hesap devre dışı': 'Account disabled',
  'Hesabınız oluşturuldu ve yönetici onayı bekliyor. Onaylandığında canlı işlem özellikleri açılacak.':
    'Your account has been created and is awaiting admin approval. Live trading features will unlock once approved.',
  'Hesabınız yönetici tarafından devre dışı bırakıldı. Erişim için sistem yöneticinize başvurun.':
    'Your account was disabled by an administrator. Contact your system administrator for access.',
  'Hesap durumu kontrol ediliyor…': 'Checking account status…',

  // --- Nav: live module / trading hub / admin ---
  'Genel': 'Home',
  'Canlı': 'Live',
  'CANLI MODÜL': 'LIVE MODULE',
  'Binance Pozisyonlar': 'Binance Positions',
  'Kendi API anahtarınızı ekleyin': 'Add your own API key',
  'Hesabınız hazırlanıyor': 'Your account is being set up',
  'API Anahtarı Ekle': 'Add API Key',
  'testnet': 'testnet',
  'Canlı işlem verilerinizi görmek için önce {net} için kendi Binance API anahtarınızı eklemelisiniz. Başkasının hesap verisi burada gösterilmez.': 'To see your live trading data you must first add your own Binance API key for {net}. No one else\'s account data is shown here.',
  '{net} anahtarınız doğrulanıyor — birkaç dakika içinde hesabınız açılır. Burada yalnızca KENDİ verileriniz gösterilir, başka hesabın verisi asla.': 'Your {net} key is being verified — your account opens within a few minutes. Only YOUR data is shown here, never another account\'s.',
  'CANLI İŞLEMLER': 'LIVE TRADING',
  'Binance Mainnet': 'Binance Mainnet',
  'Paper': 'Paper',
  'GERÇEK': 'REAL',
  'Altın': 'Gold',
  'İşlem Merkezi': 'Trading Hub',
  'Yönetim': 'Admin',
  'Menü': 'Menu',

  // --- Stream anonymization (multi-user privacy) ---
  'Otonom işlem akışı · detaylar gizli': 'Autonomous trading stream · details private',
  'Bu akışın kuralları tescillidir ve görüntülenmez. Performansı Live/Backtest sekmelerinden izleyebilirsiniz.':
    "This stream's rules are proprietary and not displayed. You can follow its performance in the Live/Backtest tabs.",
  '{name} artık mainnet (gerçek para) destekliyor — küçük sabit riskle başlayın; paper (testnet) modu deneme için açık.':
    '{name} now supports mainnet (real money) — start with a small fixed risk; paper (testnet) mode stays open for trials.',
  '{name} altın akışı — Binance testnet (paper, gerçek para DEĞİL).':
    '{name} gold stream — Binance testnet (paper, NOT real money).',
  '{name} altın akışı — Binance MAINNET (gerçek para). İşlem başına sabit risk; çıkış iz-süren stopla borsa tarafında korunur.':
    '{name} gold stream — Binance MAINNET (real money). Fixed risk per trade; the exit is protected exchange-side by a trailing stop.',

  // --- İşlem Merkezi: intro + API keys ---
  'Sinyaller merkezî olarak üretilir; emirler kendi Binance hesabınızda, kendi anahtarınızla çalışır.':
    'Signals are generated centrally; orders run on your own Binance account with your own key.',
  'API Anahtarı': 'API Key',
  'Anahtar': 'Key',
  'Anahtar yok': 'No key',
  'Bakiye': 'Balance',
  'Doğrulandı': 'Verified',
  'Geçerli': 'Valid',
  'Geçersiz': 'Invalid',
  'Anahtar Ekle/Yenile': 'Add/Rotate Key',
  'Gönder': 'Submit',
  'Anahtar alındı — doğrulama başladı (≤1 dk).': 'Key received — verification started (≤1 min).',
  'Şifreleme anahtarı yapılandırılmamış — anahtar gönderilemez (VITE_EXEC_PUBKEY_B64).':
    'Encryption key not configured — keys cannot be submitted (VITE_EXEC_PUBKEY_B64).',
  'Bu anahtarın ÇEKİM yetkisi var — reddedildi. Çekim yetkisiz yeni anahtar oluşturun.':
    'This key has WITHDRAWAL permission — rejected. Create a new key without withdrawal access.',
  'Binance hesabınız hedge modda; one-way moda geçin.':
    'Your Binance account is in hedge mode; switch to one-way mode.',
  'Anahtar yalnız şifreli saklanır (RSA) — sunucu düz metni hiç görmez.':
    'Keys are stored encrypted only (RSA) — the server never sees the plaintext.',
  'Sadece Futures trade yetkisi verin.': 'Grant Futures trading permission only.',
  'Çekim (withdraw) yetkisi vermeyin.': 'Never grant withdrawal permission.',
  'IP kısıtı önerilir': 'IP restriction recommended',

  // --- İşlem Merkezi: stream activation ---
  'Akış Aktivasyonu': 'Stream Activation',
  'GERÇEK PARA': 'REAL MONEY',
  'Akış etkin.': 'Stream enabled.',
  'Akış kapatıldı — açık pozisyon varsa drain modunda yönetilip kapanır; yeni giriş açılmaz.':
    'Stream disabled — open positions keep being managed in drain mode until closed; no new entries.',
  'Önce sembol seçin — "Sembol Seçimi" kartından bu akış için en az bir sembol kaydedin.':
    'Pick symbols first — save at least one symbol for this stream from the "Symbols" card.',
  'GERÇEK PARA modunu açıyorsunuz. Onaylamak için kutuya "GERÇEK PARA" yazın.':
    'You are enabling REAL MONEY mode. Type "GERÇEK PARA" into the box to confirm.',
  'Onayla': 'Confirm',
  'Vazgeç': 'Cancel',
  '{name}: TÜM pozisyonlar piyasa emriyle kapatılacak ve akış devre dışı kalacak. Emin misiniz?':
    '{name}: ALL positions will be closed at market and the stream will be disabled. Are you sure?',
  '≤2 dk içinde tüm pozisyonlar kapatılacak ve akış devre dışı kalacak.':
    'All positions will be closed and the stream disabled within ≤2 minutes.',

  // --- İşlem Merkezi: risk limits ---
  'Risk Ayarları': 'Risk Settings',
  'İşlem başına risk (USD)': 'Risk per trade (USD)',
  'Maks. eşzamanlı pozisyon': 'Max concurrent positions',
  'Maks. toplam risk (USD)': 'Max total risk (USD)',
  'Günlük zarar limiti (USD)': 'Daily loss cap (USD)',
  'kapalı': 'off',
  "Balansın %{pct}'i riske giriyor (risk × eşzamanlı).": '{pct}% of your balance is at risk (risk × concurrent).',
  '%25 üzeri sunucu tarafından engellenir.': 'Above 25% is blocked server-side.',
  'Kaydedildi.': 'Saved.',
  'Kaydet': 'Save',
  'Sistem Durumu': 'System Status',
  'GLOBAL KILL': 'GLOBAL KILL',
  'aktif': 'active',
  'bekleyen': 'pending',
  'devre dışı': 'disabled',
  'Açık Pozisyon': 'Open Positions',
  'aktif akış': 'active streams',
  'Son Sinyal': 'Last Signal',
  'Anahtar Doğrulama': 'Key Verification',
  'geçersiz': 'invalid',
  'Bekleyen Bildirim': 'Queued Notifications',
  'Son Giriş': 'Last Sign-in',
  'Açık Poz.': 'Open Pos.',
  'Bugün': 'Today',
  'E-postayı Onayla': 'Confirm Email',
  'E-posta onaylanmamış — giriş yapamaz': 'Email unconfirmed — cannot sign in',
  '{email} e-postası onaylandı — artık giriş yapabilir.': '{email} email confirmed — they can sign in now.',
  'GLOBAL ACİL DURDURMA: TÜM kullanıcıların TÜM pozisyonları kapatılacak ve akışları devre dışı kalacak. Emin misiniz?': 'GLOBAL EMERGENCY STOP: ALL positions of ALL users will be closed and their streams disabled. Are you sure?',
  'Son onay: global kill gönderilsin mi?': 'Final confirmation: send the global kill?',
  '{n} akışa kill gönderildi — ≤2 dk içinde uygulanır.': 'Kill sent to {n} stream(s) — applied within ≤2 min.',
  'Duyuru {n} kullanıcıya kuyruklandı (≤1 dk içinde gider).': 'Announcement queued for {n} user(s) (delivered within ≤1 min).',
  'Duyuru Gönder': 'Send Announcement',
  'Tüm aktif kullanıcılar': 'All active users',
  'Başlık': 'Title',
  'Mesaj (opsiyonel)': 'Message (optional)',
  'Push bildirimi olarak gider (aboneliği açık cihazlara, ≤1 dk). Strateji adları içeren metin yazma — kullanıcılar kod adlarını görür.': 'Delivered as a push notification (to subscribed devices, ≤1 min). Avoid strategy names in the text — users see codenames.',
  '{m} dk önce': '{m} min ago',
  'Şifre Değiştir': 'Change Password',
  'Şifre güncellendi.': 'Password updated.',
  'Şifre güncellenemedi': 'Password update failed',

  // --- İşlem Merkezi: symbol picker + backtest ranking ---
  'Backtest Sıralaması': 'Backtest Ranking',
  'Sıralama sadece bilgi amaçlı — seçim sizin.': 'The ranking is informational only — the choice is yours.',
  'Sıralama alınamadı.': 'Could not load the ranking.',
  'Semboller kaydedildi.': 'Symbols saved.',
  'Bu akış için sembol listesi boş.': 'The symbol universe for this stream is empty.',
  'Bu akışın sembol listesinde değil.': "Not in this stream's symbol universe.",
  'seçili': 'selected',
  'Yükleniyor…': 'Loading…',

  // --- Admin console ---
  'Kullanıcılar': 'Users',
  'İsim': 'Name',
  'Rol': 'Role',
  'Kayıt Tarihi': 'Created At',
  'İşlemler': 'Actions',
  'Devre Dışı': 'Disable',
  'Devre dışı': 'Disabled',
  'Yeniden Aktifle': 'Re-activate',
  'API Anahtarları': 'API Keys',
  'Ağ': 'Network',
  'Son 4': 'Last 4',
  'Denetim Kaydı (son 50)': 'Audit Log (last 50)',
  'Zaman': 'Time',
  'Aktör': 'Actor',
  'Eylem': 'Action',
  "{email}: kullanıcının TÜM akışlarında pozisyonlar kapatılacak (kill). Emin misiniz?":
    "{email}: positions on ALL of this user's streams will be closed (kill). Are you sure?",
  'Kill istendi — ≤2 dk içinde uygulanır.': 'Kill requested — applied within ≤2 minutes.',

  // --- Settings: web-push labels (previously untranslated) ---
  'Bildirimler': 'Notifications',
  'Telefon Bildirimi': 'Phone Notifications',
  'Bildirimleri Aç': 'Enable Notifications',
  'Bildirimleri Kapat': 'Disable Notifications',
  'Kapalı': 'Off',
  'Bildirim izni reddedildi.': 'Notification permission denied.',
  'Bildirim ayarlanamadı.': 'Could not set up notifications.',
  'Bu cihaz/kurulum desteklemiyor. iOS’ta önce uygulamayı Ana Ekrana ekleyin.':
    'This device/install does not support it. On iOS, add the app to the Home Screen first.',

  // --- Admin: user add/delete/role + access chips (2026-07-05) ---
  'Kullanıcı Ekle': 'Add User',
  'Geçici şifre (≥10)': 'Temporary password (≥10)',
  'İsim (opsiyonel)': 'Name (optional)',
  'Aktif olarak başlat': 'Start as active',
  'Hesap admin tarafından açılır; geçici şifreyi kullanıcıya güvenli bir kanaldan iletin. Kullanıcı girişten sonra şifresini değiştirebilir.':
    'Accounts are created by the admin; share the temporary password over a secure channel. The user can change it after signing in.',
  'E-posta girin; şifre en az 10 karakter olmalı.': 'Enter an email; the password must be at least 10 characters.',
  '{email} oluşturuldu ve aktive edildi. Geçici şifreyi kullanıcıya iletin.':
    '{email} created and activated. Share the temporary password with the user.',
  '{email} oluşturuldu (onay bekliyor). Geçici şifreyi kullanıcıya iletin.':
    '{email} created (pending approval). Share the temporary password with the user.',
  '{email}: hesap KALICI olarak silinecek (profil, anahtarlar, ayarlar, abonelikler). Emin misiniz?':
    '{email}: the account will be PERMANENTLY deleted (profile, keys, settings, subscriptions). Are you sure?',
  'Son onay: {email} silinsin mi?': 'Final confirmation: delete {email}?',
  '{email} silindi.': '{email} deleted.',
  'Erişim': 'Access',
  'Adminliği Al': 'Revoke Admin',
  'Admin Yap': 'Make Admin',
  'Sil': 'Delete',

  // --- Settings: user prefs + notification prefs (2026-07-05) ---
  'Açılış Sayfası': 'Start Page',
  'Tema, dil ve açılış sayfası hesabınıza kaydedilir — tüm cihazlarınızda geçerlidir.':
    'Theme, language and start page are saved to your account — they apply on all your devices.',
  'Hangi olaylar bildirilsin?': 'Which events should notify you?',
  'Pozisyon girişleri': 'Position entries',
  'Pozisyon kapanışları': 'Position closes',
  'Ara hedef / iz süren stop': 'Interim target / trailing stop',
  'Sinyal yayınları': 'Signal broadcasts',
  'Sistem uyarıları': 'System alerts',

  // --- Chart legend (plain-language) ---
  'Giriş fiyatı': 'Entry price',
  'İz süren stop — kâr kilitlenir': 'Trailing stop — locks in profit',
  'Hedef (kâr al)': 'Target (take profit)',
  'Stop (zararı kes)': 'Stop (cut loss)',
  'Giriş/Çıkış anları': 'Entry/Exit markers',

  // --- weekday names returned by the SQL RPC (Turkish) ---
  'Pazartesi': 'Monday', 'Sali': 'Tuesday', 'Carsamba': 'Wednesday',
  'Persembe': 'Thursday', 'Cuma': 'Friday', 'Cumartesi': 'Saturday', 'Pazar': 'Sunday',

  // --- TR-labelled keys that need a REAL English rendering (the TR map above only
  // polishes the Turkish side; these must not fall back to the Turkish key) ---
  'Kazanç (Win Rate)': 'Win Rate',
  'CANLI · FUTURES': 'LIVE · FUTURES',
  'AKTIF': 'ACTIVE',
  'IPTAL': 'CANCELLED',
  'Durum Filtre': 'Status Filter',
  'Sembol Filtre': 'Symbol Filter',
};

// TR overrides — the key is already the Turkish string, so this map only fixes
// what the keys get wrong: English jargon left untranslated (Win Rate, Live...),
// ASCII-mangled weekday names from the SQL RPC (Sali -> Salı) and a few awkward
// phrasings. Trade jargon with no settled Turkish (PnL, TP/SL, Backtest) stays.
const TR = {
  // --- English leftovers shown in the TR UI ---
  'Live': 'Canlı',
  'Default': 'Varsayılan',
  'Entry': 'Giriş',
  'Timeframe': 'Zaman Dilimi',
  'Win Rate': 'Kazanma Oranı',
  'Kazanç (Win Rate)': 'Kazanma Oranı',
  'Profit Factor': 'Kâr Faktörü',
  'Expectancy': 'Beklenti',
  'Max DD': 'Maks. Düşüş',
  'TP / SL / Cancel': 'TP / SL / İptal',
  'Risk-Reward': 'Risk/Ödül',
  'FUTURES': 'VADELİ',
  'CANLI · FUTURES': 'CANLI · VADELİ',

  // --- ASCII -> proper Turkish (status labels + SQL weekday names) ---
  'AKTIF': 'AKTİF',
  'IPTAL': 'İPTAL',
  'Sali': 'Salı',
  'Carsamba': 'Çarşamba',
  'Persembe': 'Perşembe',

  // --- phrasing polish ---
  'Durum Filtre': 'Durum Filtresi',
  'Sembol Filtre': 'Sembol Filtresi',
};

const TRANSLATIONS = { tr: TR, en: EN };

const LanguageContext = createContext();
export const useLang = () => useContext(LanguageContext);

const LS_KEY = 'pusu.lang';

export const LanguageProvider = ({ children }) => {
  const [lang, setLangState] = useState(() => {
    try { return localStorage.getItem(LS_KEY) || 'tr'; } catch { return 'tr'; }
  });

  // Persist: localStorage (instant) + ict_trade.user_prefs (cross-device, logged-in
  // only). setLang(l, {persist:false}) is the server-apply path — no DB echo.
  const setLang = useCallback((l, opts) => {
    setLangState(l);
    try { localStorage.setItem(LS_KEY, l); } catch { /* ignore */ }
    if (opts?.persist !== false) savePrefs({ lang: l });
  }, []);

  const t = useCallback((key, vars) => {
    let out = (TRANSLATIONS[lang] && TRANSLATIONS[lang][key] != null) ? TRANSLATIONS[lang][key] : key;
    if (vars) for (const k in vars) out = String(out).split(`{${k}}`).join(vars[k]);
    return out;
  }, [lang]);

  const value = useMemo(() => ({
    lang,
    setLang,
    t,
    locale: lang === 'en' ? 'en-US' : 'tr-TR',
  }), [lang, setLang, t]);

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
};
