import { createContext, useContext, useState, useCallback, useMemo } from 'react';

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
  'Live': 'Live',
  'Backtest': 'Backtest',
  'Default': 'Default',
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
  'Entry': 'Entry',
  'Hedef': 'Target',
  'Risk': 'Risk',
  'Stop': 'Stop',
  'Çıkış': 'Exit',
  // Scale-out (d30_4h_so) chart panel
  'Runner Cap (+{cap}R)': 'Runner Cap (+{cap}R)',
  'Runner Cap +{cap}R': 'Runner Cap +{cap}R',
  '+{cap}R cap · breakeven · {hor}g': '+{cap}R cap · breakeven · {hor}d',
  'CANLI': 'LIVE',
  'Pozisyon Durumu': 'Position state',
  'SL · tüm pozisyon (+1R görülmedi)': 'SL · full position (+1R not reached)',
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
  'Timeframe': 'Timeframe',
  'Tarih': 'Date',
  'Yön': 'Direction',
  'Tümü': 'All',
  'PnL': 'PnL',
  'P/L': 'P/L',
  'TP/SL': 'TP/SL',
  'Win Rate': 'Win Rate',
  'Toplam R': 'Total R',
  'Toplam PnL': 'Total PnL',
  'Beklenti': 'Expectancy',
  'Profit Factor': 'Profit Factor',

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
  'işlem': 'trades',
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
  'AKTIF': 'ACTIVE',
  'İPTAL': 'CANCEL',
  'IPTAL': 'CANCELLED',
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
  'Risk-Reward': 'Risk-Reward',
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
  'Sembol Filtre': 'Symbol Filter',
  'Durum Filtre': 'Status Filter',
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
  'Kazanç (Win Rate)': 'Win Rate',
  "En iyi 5 işlem toplam brüt kârın %{share}'ini taşıyor — az kazanır, büyük kazanır; sistem böyle tasarlandı.":
    'The top 5 trades carry {share}% of total gross profit — wins rarely, wins big; the system is designed this way.',
  'En Büyük Kazançlar': 'Biggest Wins',
  'SQL Analiz Özeti': 'SQL Summary',
  'Expectancy': 'Expectancy',
  'Ortalama Süre': 'Avg Duration',
  'TP / SL / Cancel': 'TP / SL / Cancel',
  'SQL Sembol Analizi': 'SQL Symbol Analysis',
  'SQL Zaman Analizi': 'SQL Time Analysis',

  // --- Stats / ticker ---
  'PORTFÖY KARNESİ': 'PORTFOLIO SCORECARD',
  'Canlı fiyatlar bağlanıyor…': 'Connecting to live prices…',
  'CANLI · FUTURES': 'LIVE · FUTURES',
  'CANLI': 'LIVE',
  'FUTURES': 'FUTURES',

  // --- sidebar mode + sidebar toggle ---
  'Menüyü Göster': 'Show menu',
  'Menüyü Gizle': 'Hide menu',
  'Operatör': 'Operator',
  'İptal': 'Cancelled',
  'Aktif': 'Active',

  // --- Equity panel ---
  'Sermaye Eğrisi (R)': 'Equity Curve (R)',
  'Tepe': 'Peak',
  'Max DD': 'Max DD',
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
  'Kırılım yönü bazında R ve isabet.': 'R and hit-rate by breakout direction.',
  'Long ↗': 'Long ↗',
  'Short ↘': 'Short ↘',
  'Aylık Getiri': 'Monthly Return',
  'Ortak penceredeki her ayın net R’si — tutarlılık ve eş-zamanlılık.': 'Net R for each month in the common window — consistency and concurrency.',
  'Haftanın Günü': 'Day of Week',
  'Sinyal gününe göre R (UTC).': 'R by signal day (UTC).',
  'Günün Saati (UTC)': 'Hour of Day (UTC)',
  'Kırılımın saatine göre R — seans etkisi.': 'R by breakout hour — session effect.',
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

  // --- weekday names returned by the SQL RPC (Turkish) ---
  'Pazartesi': 'Monday', 'Sali': 'Tuesday', 'Carsamba': 'Wednesday',
  'Persembe': 'Thursday', 'Cuma': 'Friday', 'Cumartesi': 'Saturday', 'Pazar': 'Sunday',
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

  const setLang = useCallback((l) => {
    setLangState(l);
    try { localStorage.setItem(LS_KEY, l); } catch { /* ignore */ }
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
