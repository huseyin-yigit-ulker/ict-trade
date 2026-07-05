import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import { getJSON } from '../utils/supa';

// Canlı işlem panolarının (Binance Mainnet / Paper) önündeki KAPI.
//
// RLS Faz-6'ya (007) kadar canlı tabloları kullanıcı-bazlı ayırmıyor ve executor
// tek-hesap modunda (EXEC_MULTI_USER=false) yalnız owner'ın (is_canonical) hesabını
// yazıyor. Bu yüzden anahtarsız / owner-olmayan bir kullanıcıya operatörün Binance
// verisi SIZMAMALI — bunun yerine kendi API anahtarını eklemeye yönlendirilir.
//
//   • owner (is_canonical)            → legacy tek-hesap panosunu görür (kendi verisi).
//   • owner-değil + geçerli anahtar    → "hesabınız hazırlanıyor" (kendi verisi Faz-5 sonrası).
//   • owner-değil + anahtar yok        → "API anahtarı ekle" → /trading.
//
// Kapı çocukları (pano) yalnız 'ok' durumunda MOUNT edilir; aksi halde pano hiç
// yüklenmez, dolayısıyla başkasının verisini çeken hiçbir sorgu atılmaz.
export default function ExecGate({ network, children }) {
  const { isCanonical } = useAuth();
  const { t } = useLang();
  const [state, setState] = useState(isCanonical ? 'ok' : 'loading');

  useEffect(() => {
    if (isCanonical) { setState('ok'); return undefined; }
    let alive = true;
    setState('loading');
    getJSON('user_api_keys_public?select=network,status')
      .then((rows) => {
        if (!alive) return;
        const mine = (rows || []).filter((r) => r.network === network);
        setState(mine.some((r) => r.status === 'valid' || r.status === 'pending_verify') ? 'pending' : 'nokey');
      })
      .catch(() => { if (alive) setState('nokey'); });
    return () => { alive = false; };
  }, [isCanonical, network]);

  if (state === 'ok') return children;
  if (state === 'loading') {
    return <div className="pending-gate"><div className="overview-card pending-gate__card">
      <div className="summary-kicker">PUSU</div><p>{t('Yükleniyor…')}</p>
    </div></div>;
  }

  const netLabel = network === 'mainnet' ? t('Binance Mainnet') : `${t('Paper')} (${t('testnet')})`;
  return (
    <div className="pending-gate">
      <div className="overview-card pending-gate__card">
        <div className="summary-kicker">PUSU</div>
        <h2>{state === 'pending' ? t('Hesabınız hazırlanıyor') : t('Kendi API anahtarınızı ekleyin')}</h2>
        <p>
          {state === 'pending'
            ? t('{net} anahtarınız kaydedildi. Canlı işlem hesabınız aktivasyon tamamlanınca açılacak — burada yalnızca KENDİ verileriniz gösterilir, başka hesabın verisi asla.', { net: netLabel })
            : t('Canlı işlem verilerinizi görmek için önce {net} için kendi Binance API anahtarınızı eklemelisiniz. Başkasının hesap verisi burada gösterilmez.', { net: netLabel })}
        </p>
        <Link className="primary-btn" to="/trading" style={{ marginTop: 6 }}>{t('API Anahtarı Ekle')} →</Link>
      </div>
    </div>
  );
}
