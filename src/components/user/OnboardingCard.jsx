import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../context/AuthContext';
import { useLang } from '../../context/LanguageContext';
import { getJSON } from '../../utils/supa';
import { SETTINGS_EVT } from '../trading/streams';
import { pushState, enablePush } from '../../utils/push';

// Kurulum Adımları — YENİ kullanıcının Portföy'de gördüğü canlı ilerleme kartı
// (Binance'in "görevler" kartı gibi). 4 adım kendi satırlarından otomatik işaretlenir:
//   ① hesap onayı (profiles.status)  ② API anahtarı (user_api_keys_public)
//   ③ akış başlat (user_stream_settings)  ④ bildirimleri aç (push aboneliği)
// Hepsi tamamlanınca kart kendini gizler. SetupGuideCard'ın (Bot sekmesi) kısa,
// portföy-seviyesi özeti — anahtar nasıl oluşturulur detayı orada kalır.

const IconCheck = () => (
  <svg viewBox="0 0 20 20" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
    <path d="M4 10.6 8.2 14.6 16 5.6" />
  </svg>
);

// pushState() navigator.serviceWorker.ready bekler — SW hiç kayıtlı değilse (dev)
// sonsuza dek asılı kalabilir; zaman aşımıyla "desteklenmiyor" say.
const pushStateSafe = () => Promise.race([
  pushState(),
  new Promise((res) => setTimeout(() => res({ supported: false, subscribed: false }), 1500)),
]).catch(() => ({ supported: false, subscribed: false }));

export default function OnboardingCard() {
  const { t } = useLang();
  const { profile } = useAuth();
  const [s, setS] = useState(null);
  const [busy, setBusy] = useState(false);
  const [pushErr, setPushErr] = useState(false);

  const load = useCallback(async () => {
    try {
      const [keys, rows, push] = await Promise.all([
        getJSON('user_api_keys_public?select=network,status').catch(() => []),
        getJSON('user_stream_settings?select=enabled,symbols').catch(() => []),
        pushStateSafe(),
      ]);
      const live = (keys || []).filter((k) => k.status !== 'rotated');
      setS({
        validKey: live.some((k) => k.status === 'valid'),
        pendingKey: live.some((k) => k.status === 'pending_verify'),
        enabled: (rows || []).some((r) => r.enabled && (r.symbols || []).length > 0),
        pushSupported: push.supported,
        pushOk: push.supported && push.subscribed && push.permission === 'granted',
      });
    } catch { /* kart tavsiye niteliğinde — hata sessiz geçilir */ }
  }, []);

  useEffect(() => {
    load();
    window.addEventListener(SETTINGS_EVT, load);
    return () => window.removeEventListener(SETTINGS_EVT, load);
  }, [load]);

  const onPush = async () => {
    setBusy(true);
    setPushErr(false);
    try { await enablePush(); } catch { setPushErr(true); }
    setBusy(false);
    load();
  };

  if (!s) return null;
  const active = profile?.status === 'active';
  const steps = [
    {
      key: 'approve',
      done: active,
      pending: !active,
      label: active ? t('Hesap onaylandı') : t('Hesap onayı bekleniyor'),
      hint: active ? null : t('Yönetici onayladığında canlı işlem özellikleri açılır.'),
    },
    {
      key: 'key',
      done: s.validKey,
      pending: s.pendingKey && !s.validKey,
      label: s.validKey ? t('API anahtarı eklendi')
        : s.pendingKey ? t('API anahtarı doğrulanıyor…') : t('API anahtarınızı ekleyin'),
      to: '/bot',
    },
    {
      key: 'stream',
      done: s.enabled,
      label: s.enabled ? t('Bot çalışıyor') : t('Bir akışı başlatın'),
      hint: s.enabled ? null : t('Hazır şablonla tek dokunuşta sembol + risk kurulur.'),
      to: '/bot',
    },
    ...(s.pushSupported ? [{
      key: 'push',
      done: s.pushOk,
      label: s.pushOk ? t('Bildirimler açık') : t('Bildirimleri açın'),
      hint: s.pushOk ? null : t('İşlem açılış/kapanışları telefonunuza gelsin.'),
      action: onPush,
    }] : []),
  ];
  const doneCount = steps.filter((st) => st.done).length;
  if (doneCount === steps.length) return null;   // kurulum tamam → kart görünmez
  const current = steps.find((st) => !st.done)?.key;

  return (
    <section className="ush-card ush-onb">
      <div className="ush-onb__head">
        <h3>{t('Kurulum Adımları')}</h3>
        <span className="ush-onb__count mono">{doneCount}/{steps.length}</span>
      </div>
      <div className="ush-onb__bar" role="progressbar" aria-valuenow={doneCount} aria-valuemax={steps.length}>
        <span style={{ width: `${(doneCount / steps.length) * 100}%` }} />
      </div>
      <ol className="ush-onb__list">
        {steps.map((st) => {
          const cls = `ush-onb__step${st.done ? ' is-done' : ''}${st.key === current ? ' is-current' : ''}${st.pending && !st.done ? ' is-pending' : ''}`;
          const inner = (
            <>
              <span className="ush-onb__dot">{st.done ? <IconCheck /> : st.pending ? '…' : ''}</span>
              <span className="ush-onb__label">
                {st.label}
                {st.hint && <small>{st.hint}</small>}
                {st.key === 'push' && pushErr && (
                  <small className="ush-onb__err">{t('Bildirim izni verilemedi — Profil sayfasından deneyin.')}</small>
                )}
              </span>
              {!st.done && (st.to || st.action) && <span className="ush-onb__go">→</span>}
            </>
          );
          if (!st.done && st.to) {
            return <li key={st.key}><Link className={cls} to={st.to}>{inner}</Link></li>;
          }
          if (!st.done && st.action) {
            return (
              <li key={st.key}>
                <button type="button" className={cls} onClick={st.action} disabled={busy}>{inner}</button>
              </li>
            );
          }
          return <li key={st.key}><span className={cls}>{inner}</span></li>;
        })}
      </ol>
      <Link to="/yardim" className="ush-onb__help">{t('Nasıl çalışır? Yardım & SSS')} →</Link>
    </section>
  );
}
