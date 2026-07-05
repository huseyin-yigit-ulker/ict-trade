import { useCallback, useEffect, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { getJSON, rpc } from '../utils/supa';
import { reqJSON } from '../components/trading/streams';

// Yönetim — admin console: user approval (admin_set_user RPC), the key-status
// board and the last 50 audit entries. Admin RLS branches let this page read
// every user's profiles / user_api_keys_public / audit_log rows and PATCH a
// per-user killswitch on user_stream_settings.

const STATUS_CHIP = {
  active: 'chip--ok',
  pending: 'chip--warn',
  disabled: 'chip--err',
};
const KEY_CHIP = {
  valid: 'chip--ok',
  pending_verify: 'chip--warn',
  invalid: 'chip--err',
  rotated: '',
};

const compactDetail = (d) => {
  if (d == null) return '—';
  const s = typeof d === 'string' ? d : JSON.stringify(d);
  return s.length > 80 ? `${s.slice(0, 77)}…` : s;
};

export default function AdminPage() {
  const { t, locale } = useLang();
  const [profiles, setProfiles] = useState([]);
  const [keys, setKeys] = useState([]);
  const [audit, setAudit] = useState([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  const [busy, setBusy] = useState({});   // user_id -> bool

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    const [p, k, a] = await Promise.allSettled([
      getJSON('profiles?select=*&order=created_at.desc'),
      getJSON('user_api_keys_public?select=*&order=created_at.desc'),
      getJSON('audit_log?select=*&order=created_at.desc&limit=50'),
    ]);
    if (p.status === 'fulfilled') setProfiles(p.value || []); else setErr(p.reason?.message || 'profiles');
    if (k.status === 'fulfilled') setKeys(k.value || []); else setErr((e) => e || k.reason?.message);
    if (a.status === 'fulfilled') setAudit(a.value || []); else setErr((e) => e || a.reason?.message);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const emailOf = (uid) => profiles.find((p) => p.user_id === uid)?.email || uid?.slice(0, 8) || '—';
  const fmtTime = (iso) => (iso ? new Date(iso).toLocaleString(locale) : '—');

  const withBusy = async (uid, fn) => {
    if (busy[uid]) return;
    setBusy((b) => ({ ...b, [uid]: true }));
    setErr('');
    setOk('');
    try {
      await fn();
    } catch (e) {
      setErr(e.message);
    } finally {
      setBusy((b) => ({ ...b, [uid]: false }));
    }
  };

  const setUserStatus = (p, status) => withBusy(p.user_id, async () => {
    await rpc('admin_set_user', { p_user: p.user_id, p_status: status, p_role: p.role || 'user' });
    await load();
  });

  const killUser = (p) => {
    const yes = window.confirm(
      t("{email}: kullanıcının TÜM akışlarında pozisyonlar kapatılacak (kill). Emin misiniz?", { email: p.email }),
    );
    if (!yes) return;
    withBusy(p.user_id, async () => {
      await reqJSON(`user_stream_settings?user_id=eq.${p.user_id}`, {
        method: 'PATCH',
        body: JSON.stringify({ kill_requested: true }),
      });
      setOk(t('Kill istendi — ≤2 dk içinde uygulanır.'));
    });
  };

  const statusLabel = (s) => (
    s === 'active' ? t('Aktif') : s === 'disabled' ? t('Devre dışı') : t('Onay bekleniyor')
  );

  return (
    <div className="settings-page admin-page">
      <div className="settings-head admin-head">
        <div>
          <div className="summary-kicker">PUSU</div>
          <h2>{t('Yönetim')}</h2>
        </div>
        <button className="header-btn" onClick={load} disabled={loading}>⟳ {t('Yenile')}</button>
      </div>

      {err && <div className="form-note form-note--err">{err}</div>}
      {ok && <div className="form-note form-note--ok">{ok}</div>}

      {/* ── users ── */}
      <section className="overview-card admin-card">
        <div className="summary-title">{t('Kullanıcılar')} ({profiles.length})</div>
        {profiles.length === 0 ? <div className="summary-empty">{loading ? t('Yükleniyor…') : t('Kayıt yok')}</div> : (
          <div className="admin-tablewrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{t('E-posta')}</th>
                  <th>{t('İsim')}</th>
                  <th>{t('Rol')}</th>
                  <th>{t('Durum')}</th>
                  <th>{t('Kayıt Tarihi')}</th>
                  <th>{t('İşlemler')}</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => (
                  <tr key={p.user_id}>
                    <td className="mono">{p.email}</td>
                    <td>{p.display_name || '—'}</td>
                    <td>{p.role === 'admin' ? <span className="chip st-active">ADMIN</span> : p.role}</td>
                    <td><span className={`chip ${STATUS_CHIP[p.status] || ''}`}>{statusLabel(p.status)}</span></td>
                    <td className="mono">{fmtTime(p.created_at)}</td>
                    <td>
                      <div className="admin-actions">
                        {p.status === 'pending' && (
                          <button className="apply-btn" disabled={busy[p.user_id]}
                            onClick={() => setUserStatus(p, 'active')}>{t('Onayla')}</button>
                        )}
                        {p.status === 'active' && (
                          <button className="header-btn" disabled={busy[p.user_id]}
                            onClick={() => setUserStatus(p, 'disabled')}>{t('Devre Dışı')}</button>
                        )}
                        {p.status === 'disabled' && (
                          <button className="apply-btn" disabled={busy[p.user_id]}
                            onClick={() => setUserStatus(p, 'active')}>{t('Yeniden Aktifle')}</button>
                        )}
                        <button className="kill-btn" disabled={busy[p.user_id]} onClick={() => killUser(p)}>
                          KILL
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── API keys ── */}
      <section className="overview-card admin-card">
        <div className="summary-title">{t('API Anahtarları')} ({keys.length})</div>
        {keys.length === 0 ? <div className="summary-empty">{loading ? t('Yükleniyor…') : t('Kayıt yok')}</div> : (
          <div className="admin-tablewrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{t('E-posta')}</th>
                  <th>{t('Ağ')}</th>
                  <th>{t('Son 4')}</th>
                  <th>{t('Durum')}</th>
                  <th>{t('Bakiye')}</th>
                  <th>{t('Tarih')}</th>
                </tr>
              </thead>
              <tbody>
                {keys.map((k) => (
                  <tr key={k.id}>
                    <td className="mono">{emailOf(k.user_id)}</td>
                    <td>{k.network}</td>
                    <td className="mono">•••• {k.key_last4 || '????'}</td>
                    <td>
                      <span className={`chip ${KEY_CHIP[k.status] || ''}`}>{k.status}</span>
                      {k.status === 'invalid' && k.invalid_reason && (
                        <span className="form-note form-note--err admin-reason" title={k.invalid_reason}>
                          {compactDetail(k.invalid_reason)}
                        </span>
                      )}
                    </td>
                    <td className="mono">{k.balance_usdt != null ? `${Number(k.balance_usdt).toFixed(2)} USDT` : '—'}</td>
                    <td className="mono">{fmtTime(k.verified_at || k.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── audit log ── */}
      <section className="overview-card admin-card">
        <div className="summary-title">{t('Denetim Kaydı (son 50)')}</div>
        {audit.length === 0 ? <div className="summary-empty">{loading ? t('Yükleniyor…') : t('Kayıt yok')}</div> : (
          <div className="admin-tablewrap">
            <table className="admin-table">
              <thead>
                <tr>
                  <th>{t('Zaman')}</th>
                  <th>{t('E-posta')}</th>
                  <th>{t('Aktör')}</th>
                  <th>{t('Eylem')}</th>
                  <th>{t('Detay')}</th>
                </tr>
              </thead>
              <tbody>
                {audit.map((a) => (
                  <tr key={a.id}>
                    <td className="mono">{fmtTime(a.created_at)}</td>
                    <td className="mono">{emailOf(a.user_id)}</td>
                    <td>{a.actor || '—'}</td>
                    <td><b>{a.action}</b></td>
                    <td className="mono admin-detail" title={typeof a.detail === 'string' ? a.detail : JSON.stringify(a.detail)}>
                      {compactDetail(a.detail)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
