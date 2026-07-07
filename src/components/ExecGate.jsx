import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useLang } from '../context/LanguageContext';
import { getJSON } from '../utils/supa';

// Canlı işlem panolarının (Binance Mainnet / Paper) önündeki KAPI.
//
// Faz-5/6 cutover (2026-07-05) sonrası: executor çok-kullanıcı modunda (her kullanıcı
// KENDİ anahtarıyla işlem görür) ve canlı tablolar RLS ile kullanıcıya kilitli (007) —
// yani bir kullanıcının JWT'siyle çekilen satırlar YALNIZ kendi hesabınındır.
//
// 2026-07-07 (kullanıcı isteği): kapı artık İKİ şart arar — o ağda (1) GEÇERLİ anahtar
// VE (2) ENABLED bir akış satırı (sembol seçili). İkisi de yoksa pano BOŞ (CTA kartı):
//
//   • anahtar + aktif akış (veya owner)      → KENDİ panosu (RLS satırları kilitler).
//   • anahtar doğrulanıyor (pending_verify)  → "hesabınız hazırlanıyor".
//   • anahtar var, akış/sembol aktif değil   → "akış + sembol aktifleştir" → /trading.
//   • anahtar yok                            → "API anahtarı ekle" → /trading.
//
// network="any": ağlardan HERHANGİ biri aktifse geçer (ağ-dinamik detay sayfaları için,
// ör. /binance-altin). Kapı çocukları yalnız 'ok' durumunda MOUNT edilir.
export default function ExecGate({ network, children }) {
  const { isCanonical, user } = useAuth();
  const { t } = useLang();
  const [state, setState] = useState(isCanonical ? 'ok' : 'loading');

  useEffect(() => {
    if (isCanonical) { setState('ok'); return undefined; }   // owner: is_admin RLS → kendi satırları
    let alive = true;
    setState('loading');
    // user_id filtresi: bu iki kaynak admin'e tüm satırları açar (own OR is_admin) —
    // kapının konusu her zaman GİREN kullanıcının KENDİ aktivasyonudur.
    const q = user?.id ? `&user_id=eq.${user.id}` : '';
    Promise.all([
      getJSON(`user_api_keys_public?select=network,status${q}`).catch(() => []),
      getJSON(`user_stream_settings?select=network,enabled,symbols${q}`).catch(() => []),
    ])
      .then(([keys, sets]) => {
        if (!alive) return;
        const nets = network === 'any' ? ['mainnet', 'testnet'] : [network];
        const valid = (n) => (keys || []).some((k) => k.network === n && k.status === 'valid');
        const pending = (n) => (keys || []).some((k) => k.network === n && k.status === 'pending_verify');
        const enabled = (n) => (sets || []).some((s) => s.network === n && s.enabled && (s.symbols || []).length > 0);
        if (nets.some((n) => valid(n) && enabled(n))) setState('ok');
        else if (nets.some(pending)) setState('pending');
        else if (nets.some(valid)) setState('noact');        // anahtar tamam, akış/sembol kapalı
        else setState('nokey');
      })
      .catch(() => { if (alive) setState('nokey'); });
    return () => { alive = false; };
  }, [isCanonical, user?.id, network]);

  if (state === 'ok') return children;
  if (state === 'loading') {
    return <div className="pending-gate"><div className="overview-card pending-gate__card">
      <div className="summary-kicker">PUSU</div><p>{t('Yükleniyor…')}</p>
    </div></div>;
  }

  const netLabel = network === 'mainnet' ? t('Binance Canlı')
    : network === 'testnet' ? `${t('Paper')} (${t('testnet')})` : t('Canlı işlem');
  const head = state === 'pending' ? t('Hesabınız hazırlanıyor')
    : state === 'noact' ? t('Akış ve sembol aktifleştirin')
    : t('Kendi API anahtarınızı ekleyin');
  const body = state === 'pending'
    ? t('{net} anahtarınız doğrulanıyor — birkaç dakika içinde hesabınız açılır. Burada yalnızca KENDİ verileriniz gösterilir, başka hesabın verisi asla.', { net: netLabel })
    : state === 'noact'
      ? t('Anahtarınız hazır ama {net} için henüz aktif bir akış/sembol seçiminiz yok. İşlem Merkezi’nden bir akışı açıp sembollerinizi seçince panonuz burada belirir.', { net: netLabel })
      : t('Canlı işlem verilerinizi görmek için önce {net} için kendi Binance API anahtarınızı eklemelisiniz. Başkasının hesap verisi burada gösterilmez.', { net: netLabel });

  return (
    <div className="pending-gate">
      <div className="overview-card pending-gate__card">
        <div className="summary-kicker">PUSU</div>
        <h2>{head}</h2>
        <p>{body}</p>
        <Link className="primary-btn" to="/trading" style={{ marginTop: 6 }}>
          {state === 'noact' ? `${t('İşlem Merkezi')} →` : `${t('API Anahtarı Ekle')} →`}
        </Link>
      </div>
    </div>
  );
}
