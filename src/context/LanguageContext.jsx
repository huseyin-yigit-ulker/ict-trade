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
