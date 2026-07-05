import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import { getJSON } from '../utils/supa';

// Canlı işlem panolarının (Binance Mainnet / Paper) önündeki KAPI.
//
// Faz-5/6 cutover (2026-07-05) sonrası: executor çok-kullanıcı modunda (her kullanıcı
// KENDİ anahtarıyla işlem görür) ve canlı tablolar RLS ile kullanıcıya kilitli (007) —
// yani bir kullanıcının JWT'siyle çekilen satırlar YALNIZ kendi hesabınındır. Kapı bu
// yüzden kullanıcının o ağ için KENDİ GEÇERLİ anahtarı olup olmadığına bakar:
//
//   • geçerli anahtar (veya owner/is_admin)  → KENDİ panosu (RLS satırları kilitler).
//   • anahtar doğrulanıyor (pending_verify)  → "hesabınız hazırlanıyor".
//   • anahtar yok                            → "API anahtarı ekle" → /trading.
//
// Kapı çocukları (pano) yalnız 'ok' durumunda MOUNT edilir; aksi halde pano hiç
// yüklenmez, dolayısıyla hiçbir sorgu atılmaz.
export default function ExecGate({ network, children }) {
  const { isCanonical } = useAuth();
  const { t } = useLang();
  const [state, setState] = useState(isCanonical ? 'ok' : 'loading');

  useEffect(() => {
    if (isCanonical) { setState('ok'); return undefined; }   // owner: is_admin RLS → kendi satırları
    let alive = true;
    setState('loading');
    getJSON('user_api_keys_public?select=network,status')
      .then((rows) => {
        if (!alive) return;
        const mine = (rows || []).filter((r) => r.network === network);
        if (mine.some((r) => r.status === 'valid')) setState('ok');          // kendi geçerli anahtarı → kendi panosu
        else if (mine.some((r) => r.status === 'pending_verify')) setState('pending');
        else setState('nokey');
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
            ? t('{net} anahtarınız doğrulanıyor — birkaç dakika içinde hesabınız açılır. Burada yalnızca KENDİ verileriniz gösterilir, başka hesabın verisi asla.', { net: netLabel })
            : t('Canlı işlem verilerinizi görmek için önce {net} için kendi Binance API anahtarınızı eklemelisiniz. Başkasının hesap verisi burada gösterilmez.', { net: netLabel })}
        </p>
        <Link className="primary-btn" to="/trading" style={{ marginTop: 6 }}>{t('API Anahtarı Ekle')} →</Link>
      </div>
    </div>
  );
}
