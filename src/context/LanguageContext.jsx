import { createContext, useContext, useState, useCallback, useMemo } from 'react';

// Lightweight i18n (no dependency). Pattern: the Turkish string IS the key.
// t('Kapat') -> 'Kapat' in TR, EN[...] (or the key as fallback) in EN.
// Interpolate with {x}: t('{n} dk önce', { n: 5 }).

const EN = {
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

const TRANSLATIONS = { tr: {}, en: EN };

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
