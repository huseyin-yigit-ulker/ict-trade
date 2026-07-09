import { useCallback, useEffect, useState } from 'react';
import { useLang } from '../context/LanguageContext';
import { useAuth } from '../context/AuthContext';
import { getJSON, rpc } from '../utils/supa';
import { signUp as gtSignUp } from '../utils/gotrue';
import { reqJSON } from '../components/trading/streams';

// Yönetim — admin console: TÜM kullanıcı kontrolleri burada. Kullanıcı ekleme
// (GoTrue signup + admin_set_user ile anında aktivasyon), silme (admin_delete_user
// RPC — açık pozisyon/canonical korumalı), onay/devre dışı/rol (admin_set_user),
// yüzey erişimleri (admin_set_features: backtest/istihbarat/işlem), per-user kill,
// key-status board ve son 50 audit kaydı. Admin RLS branches let this page read
// every user's profiles / user_api_keys_public / user_features / audit_log rows.

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

// Yüzey anahtarları — admin_set_features RPC'siyle birebir aynı sıra/adlar.
const FEATURE_KEYS = [
  { k: 'backtest', label: 'BT', title: 'Backtest' },
  { k: 'intelligence', label: 'İSTH', title: 'İstihbarat' },
  { k: 'trading', label: 'İŞL', title: 'İşlem Merkezi' },
];
// Backtest opt-in (araştırma laboratuvarı) → varsayılan KAPALI; İSTH/İŞL opt-out → açık.
// (AuthContext.DEFAULT_FEATURES ile birebir aynı — admin bir çipi değiştirdiğinde tam
// üçlü upsert edildiği için backtest sessizce açılmasın diye buradaki default da false.)
const DEFAULT_FEAT = { backtest: false, intelligence: true, trading: true };

export default function AdminPage() {
  const { t, locale } = useLang();
  const { user: me } = useAuth();
  const [profiles, setProfiles] = useState([]);
  const [keys, setKeys] = useState([]);
  const [audit, setAudit] = useState([]);
  const [featMap, setFeatMap] = useState({});   // user_id -> {backtest, intelligence, trading}
  const [authMeta, setAuthMeta] = useState({}); // user_id -> {email_confirmed, last_sign_in_at} (009)
  const [statsMap, setStatsMap] = useState({}); // user_id -> {open_count, today_usd, total_usd} (009)
  const [overview, setOverview] = useState(null); // admin_overview() jsonb (009)
  const [digestOn, setDigestOn] = useState(true); // app_flags.positions_digest (017)
  const [digestBusy, setDigestBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [ok, setOk] = useState('');
  const [busy, setBusy] = useState({});   // user_id -> bool
  // yeni-kullanıcı formu
  const [nu, setNu] = useState({ email: '', password: '', name: '', activate: true });
  const [nuBusy, setNuBusy] = useState(false);
  // duyuru formu
  const [an, setAn] = useState({ target: 'all', title: '', body: '' });
  const [anBusy, setAnBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setErr('');
    const [p, k, a, f, lu, st, ov, fl] = await Promise.allSettled([
      getJSON('profiles?select=*&order=created_at.desc'),
      getJSON('user_api_keys_public?select=*&order=created_at.desc'),
      getJSON('audit_log?select=*&order=created_at.desc&limit=50'),
      getJSON('user_features?select=user_id,backtest,intelligence,trading'),
      rpc('admin_list_users'),      // 009: e-posta onayı + son giriş
      rpc('admin_user_stats'),      // 009: açık poz / bugün$ / toplam$
      rpc('admin_overview'),        // 009: sistem sağlık özeti
      getJSON('app_flags?select=key,enabled&key=eq.positions_digest'), // 017: cron aç/kapa
    ]);
    if (p.status === 'fulfilled') setProfiles(p.value || []); else setErr(p.reason?.message || 'profiles');
    if (k.status === 'fulfilled') setKeys(k.value || []); else setErr((e) => e || k.reason?.message);
    if (a.status === 'fulfilled') setAudit(a.value || []); else setErr((e) => e || a.reason?.message);
    // user_features migration'ı henüz uygulanmadıysa sessizce boş kalır (hepsi açık sayılır).
    if (f.status === 'fulfilled') {
      setFeatMap(Object.fromEntries((f.value || []).map((r) => [r.user_id, r])));
    }
    // 009 RPC'leri uygulanmadıysa sessizce eski görünüm kalır.
    if (lu.status === 'fulfilled') {
      setAuthMeta(Object.fromEntries((lu.value || []).map((r) => [r.user_id, r])));
    }
    if (st.status === 'fulfilled') {
      setStatsMap(Object.fromEntries((st.value || []).map((r) => [r.user_id, r])));
    }
    if (ov.status === 'fulfilled') setOverview(ov.value || null);
    // 017 app_flags migration'ı henüz uygulanmadıysa sessizce AÇIK varsayılır.
    if (fl.status === 'fulfilled') setDigestOn(fl.value?.[0]?.enabled ?? true);
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

  const setUserRole = (p, role) => withBusy(p.user_id, async () => {
    await rpc('admin_set_user', { p_user: p.user_id, p_status: p.status, p_role: role });
    await load();
  });

  // Yüzey erişimi (backtest/istihbarat/işlem) — RPC tam üçlüyü upsert eder.
  const toggleFeature = (p, key) => withBusy(p.user_id, async () => {
    const cur = { ...DEFAULT_FEAT, ...(featMap[p.user_id] || {}) };
    const next = { ...cur, [key]: !cur[key] };
    await rpc('admin_set_features', {
      p_user: p.user_id,
      p_backtest: next.backtest,
      p_intelligence: next.intelligence,
      p_trading: next.trading,
    });
    setFeatMap((m) => ({ ...m, [p.user_id]: next }));
  });

  const deleteUser = (p) => {
    const yes = window.confirm(
      t('{email}: hesap KALICI olarak silinecek (profil, anahtarlar, ayarlar, abonelikler). Emin misiniz?', { email: p.email }),
    );
    if (!yes) return;
    const yes2 = window.confirm(t('Son onay: {email} silinsin mi?', { email: p.email }));
    if (!yes2) return;
    withBusy(p.user_id, async () => {
      await rpc('admin_delete_user', { p_user: p.user_id });
      setOk(t('{email} silindi.', { email: p.email }));
      await load();
    });
  };

  // Kullanıcı ekleme: anonim GoTrue signup (admin oturumu etkilenmez; dönen yeni-kullanıcı
  // session'ı KAYDEDİLMEZ) → profil trigger'la pending doğar → istenirse anında aktive edilir.
  const createUser = async (e) => {
    e.preventDefault();
    if (nuBusy) return;
    setNuBusy(true);
    setErr('');
    setOk('');
    try {
      const email = nu.email.trim();
      if (!email || nu.password.length < 10) {
        throw new Error(t('E-posta girin; şifre en az 10 karakter olmalı.'));
      }
      const { user: created } = await gtSignUp(email, nu.password, nu.name.trim());
      const uid = created?.id;
      if (nu.activate && uid) {
        await rpc('admin_set_user', { p_user: uid, p_status: 'active', p_role: 'user' });
      }
      setOk(nu.activate
        ? t('{email} oluşturuldu ve aktive edildi. Geçici şifreyi kullanıcıya iletin.', { email })
        : t('{email} oluşturuldu (onay bekliyor). Geçici şifreyi kullanıcıya iletin.', { email }));
      setNu({ email: '', password: '', name: '', activate: true });
      await load();
    } catch (e2) {
      setErr(e2?.message || 'signup');
    } finally {
      setNuBusy(false);
    }
  };

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

  // 009: e-posta onayı ("Confirm email" açıkken kullanıcı girişinin önünü açar).
  const confirmEmail = (p) => withBusy(p.user_id, async () => {
    await rpc('admin_confirm_email', { p_user: p.user_id });
    setOk(t('{email} e-postası onaylandı — artık giriş yapabilir.', { email: p.email }));
    await load();
  });

  // 009: GLOBAL kill — tüm kullanıcıların tüm aktif akışları.
  const killAll = async () => {
    if (!window.confirm(t('GLOBAL ACİL DURDURMA: TÜM kullanıcıların TÜM pozisyonları kapatılacak ve akışları devre dışı kalacak. Emin misiniz?'))) return;
    if (!window.confirm(t('Son onay: global kill gönderilsin mi?'))) return;
    setErr(''); setOk('');
    try {
      const n = await rpc('admin_kill_all');
      setOk(t('{n} akışa kill gönderildi — ≤2 dk içinde uygulanır.', { n }));
    } catch (e) { setErr(e.message); }
  };

  // 017: açık-işlem Telegram özeti cron'unu (positions_digest.py) aç/kapa. Crontab girişi
  // sabit kalır; bayrak KAPALI olduğunda cron her tetiklemede sessizce no-op yapar.
  const toggleDigest = async () => {
    if (digestBusy) return;
    setDigestBusy(true); setErr(''); setOk('');
    const next = !digestOn;
    try {
      await rpc('admin_set_flag', { p_key: 'positions_digest', p_enabled: next });
      setDigestOn(next);
      setOk(next
        ? t('Açık işlem özeti AÇIK — 5 dk’da bir Telegram mesajı.')
        : t('Açık işlem özeti KAPALI — cron sessizce atlar.'));
    } catch (e) { setErr(e.message); } finally { setDigestBusy(false); }
  };

  // 009: duyuru — push_outbox kuyruğuna yazar, mevcut --drain cron'u dağıtır.
  const sendAnnouncement = async (e) => {
    e.preventDefault();
    if (anBusy || !an.title.trim()) return;
    setAnBusy(true); setErr(''); setOk('');
    try {
      const n = await rpc('admin_notify', {
        p_title: an.title.trim(),
        p_body: an.body.trim(),
        p_user: an.target === 'all' ? null : an.target,
      });
      setOk(t('Duyuru {n} kullanıcıya kuyruklandı (≤1 dk içinde gider).', { n }));
      setAn({ target: 'all', title: '', body: '' });
    } catch (e2) { setErr(e2.message); } finally { setAnBusy(false); }
  };

  // Kalp atışı tazeliği: executor */2 koşar — 6 dk'dan eski yazım sorun işaretidir.
  const freshness = (iso) => {
    if (!iso) return { cls: 'chip--err', label: '—' };
    const ageS = (Date.now() - new Date(iso).getTime()) / 1000;
    const label = ageS < 90 ? t('şimdi') : t('{m} dk önce', { m: Math.round(ageS / 60) });
    return { cls: ageS < 360 ? 'chip--ok' : 'chip--err', label };
  };
  const fmtUsd = (v) => (v == null ? '—' : `${Number(v) >= 0 ? '+' : ''}${Number(v).toFixed(2)}$`);

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

      {/* ── system overview (009) ── */}
      {overview && (
        <section className="overview-card admin-card">
          <div className="summary-title admin-ov-head">
            <span>{t('Sistem Durumu')}</span>
            <button
              className={`header-btn admin-digest${digestOn ? ' on' : ''}`}
              onClick={toggleDigest}
              disabled={digestBusy}
              title={t('Açık işlem Telegram özeti (5 dk’da bir tek mesaj). Kapalıyken cron sessizce atlar; sinyaller/işlemler etkilenmez.')}
            >
              {digestOn ? '🔔' : '🔕'} {t('Açık İşlem Özeti')}: {digestOn ? t('AÇIK') : t('KAPALI')}
            </button>
            <button className="kill-btn admin-globalkill" onClick={killAll}>
              ⛔ {t('GLOBAL KILL')}
            </button>
          </div>
          <div className="admin-stats">
            <div className="admin-stat">
              <span className="admin-stat__label">{t('Kullanıcılar')}</span>
              <b>{overview.users?.active || 0} {t('aktif')}</b>
              <span className="admin-stat__sub">
                {overview.users?.pending || 0} {t('bekleyen')} · {overview.users?.disabled || 0} {t('devre dışı')}
              </span>
            </div>
            <div className="admin-stat">
              <span className="admin-stat__label">{t('Açık Pozisyon')}</span>
              <b>{overview.open_positions ?? '—'}</b>
              <span className="admin-stat__sub">{overview.enabled_streams ?? 0} {t('aktif akış')}</span>
            </div>
            {['mainnet', 'testnet'].map((net) => {
              const f = freshness(overview.exec_heartbeat?.[net]);
              return (
                <div className="admin-stat" key={net}>
                  <span className="admin-stat__label">Executor · {net}</span>
                  <span className={`chip ${f.cls}`}>{f.label}</span>
                </div>
              );
            })}
            <div className="admin-stat">
              <span className="admin-stat__label">{t('Son Sinyal')}</span>
              <b className="mono">{fmtTime(overview.last_signal)}</b>
            </div>
            <div className="admin-stat">
              <span className="admin-stat__label">{t('Anahtar Doğrulama')}</span>
              <span className={`chip ${freshness(overview.last_key_verify).cls === 'chip--ok' || (Date.now() - new Date(overview.last_key_verify || 0).getTime()) < 26 * 3600 * 1000 ? 'chip--ok' : 'chip--warn'}`}>
                {fmtTime(overview.last_key_verify)}
              </span>
              {overview.invalid_keys > 0 && (
                <span className="chip chip--err">{overview.invalid_keys} {t('geçersiz')}</span>
              )}
            </div>
            <div className="admin-stat">
              <span className="admin-stat__label">{t('Bekleyen Bildirim')}</span>
              <b>{overview.outbox_pending ?? 0}</b>
            </div>
          </div>
        </section>
      )}

      {/* ── add user ── */}
      <section className="overview-card admin-card">
        <div className="summary-title">{t('Kullanıcı Ekle')}</div>
        <form className="admin-newuser" onSubmit={createUser}>
          <input
            type="email" required placeholder={t('E-posta')}
            value={nu.email} onChange={(e) => setNu((s) => ({ ...s, email: e.target.value }))}
            autoComplete="off"
          />
          <input
            type="text" required minLength={10} placeholder={t('Geçici şifre (≥10)')}
            value={nu.password} onChange={(e) => setNu((s) => ({ ...s, password: e.target.value }))}
            autoComplete="off"
          />
          <input
            type="text" placeholder={t('İsim (opsiyonel)')}
            value={nu.name} onChange={(e) => setNu((s) => ({ ...s, name: e.target.value }))}
            autoComplete="off"
          />
          <label className="admin-newuser__opt">
            <input
              type="checkbox" checked={nu.activate}
              onChange={(e) => setNu((s) => ({ ...s, activate: e.target.checked }))}
            />
            {t('Aktif olarak başlat')}
          </label>
          <button className="apply-btn" type="submit" disabled={nuBusy}>
            {nuBusy ? '…' : `+ ${t('Kullanıcı Ekle')}`}
          </button>
        </form>
        <div className="form-note">
          {t('Hesap admin tarafından açılır; geçici şifreyi kullanıcıya güvenli bir kanaldan iletin. Kullanıcı girişten sonra şifresini değiştirebilir.')}
        </div>
      </section>

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
                  <th>{t('Erişim')}</th>
                  <th>{t('Son Giriş')}</th>
                  <th>{t('Açık Poz.')}</th>
                  <th>{t('Bugün')}</th>
                  <th>{t('Kayıt Tarihi')}</th>
                  <th>{t('İşlemler')}</th>
                </tr>
              </thead>
              <tbody>
                {profiles.map((p) => {
                  const isSelf = p.user_id === me?.id;
                  const feat = { ...DEFAULT_FEAT, ...(featMap[p.user_id] || {}) };
                  const meta = authMeta[p.user_id];
                  const stat = statsMap[p.user_id];
                  return (
                  <tr key={p.user_id}>
                    <td className="mono">
                      {p.email}{isSelf ? ' ·siz' : ''}
                      {meta && !meta.email_confirmed && (
                        <span className="chip chip--warn" title={t('E-posta onaylanmamış — giriş yapamaz')}>✉ ?</span>
                      )}
                    </td>
                    <td>{p.display_name || '—'}</td>
                    <td>{p.role === 'admin' ? <span className="chip st-active">ADMIN</span> : p.role}</td>
                    <td><span className={`chip ${STATUS_CHIP[p.status] || ''}`}>{statusLabel(p.status)}</span></td>
                    <td>
                      {/* Yüzey erişimleri — tıkla/aç-kapa; adminin kendi erişimi kısıtlanmaz. */}
                      <div className="admin-feats">
                        {FEATURE_KEYS.map((f) => (
                          <button
                            key={f.k} type="button" title={t(f.title)}
                            className={`admin-feat${feat[f.k] ? ' on' : ''}`}
                            disabled={busy[p.user_id] || isSelf}
                            onClick={() => toggleFeature(p, f.k)}
                          >
                            {f.label}
                          </button>
                        ))}
                      </div>
                    </td>
                    <td className="mono">{meta ? fmtTime(meta.last_sign_in_at) : '—'}</td>
                    <td className="mono">{stat ? stat.open_count : '—'}</td>
                    <td className={`mono ${stat && Number(stat.today_usd) < 0 ? 'loss' : stat && Number(stat.today_usd) > 0 ? 'win' : ''}`}>
                      {stat ? fmtUsd(stat.today_usd) : '—'}
                    </td>
                    <td className="mono">{fmtTime(p.created_at)}</td>
                    <td>
                      <div className="admin-actions">
                        {meta && !meta.email_confirmed && (
                          <button className="apply-btn" disabled={busy[p.user_id]}
                            onClick={() => confirmEmail(p)}>{t('E-postayı Onayla')}</button>
                        )}
                        {p.status === 'pending' && (
                          <button className="apply-btn" disabled={busy[p.user_id]}
                            onClick={() => setUserStatus(p, 'active')}>{t('Onayla')}</button>
                        )}
                        {p.status === 'active' && !isSelf && (
                          <button className="header-btn" disabled={busy[p.user_id]}
                            onClick={() => setUserStatus(p, 'disabled')}>{t('Devre Dışı')}</button>
                        )}
                        {p.status === 'disabled' && (
                          <button className="apply-btn" disabled={busy[p.user_id]}
                            onClick={() => setUserStatus(p, 'active')}>{t('Yeniden Aktifle')}</button>
                        )}
                        {!isSelf && (
                          p.role === 'admin' ? (
                            <button className="header-btn" disabled={busy[p.user_id]}
                              onClick={() => setUserRole(p, 'user')}>{t('Adminliği Al')}</button>
                          ) : (
                            <button className="header-btn" disabled={busy[p.user_id]}
                              onClick={() => setUserRole(p, 'admin')}>{t('Admin Yap')}</button>
                          )
                        )}
                        <button className="kill-btn" disabled={busy[p.user_id]} onClick={() => killUser(p)}>
                          KILL
                        </button>
                        {!isSelf && !p.is_canonical && (
                          <button className="kill-btn admin-del" disabled={busy[p.user_id]}
                            onClick={() => deleteUser(p)}>{t('Sil')}</button>
                        )}
                      </div>
                    </td>
                  </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* ── announcement (009) ── */}
      <section className="overview-card admin-card">
        <div className="summary-title">{t('Duyuru Gönder')}</div>
        <form className="admin-newuser" onSubmit={sendAnnouncement}>
          <select
            className="tinput"
            value={an.target}
            onChange={(e) => setAn((s) => ({ ...s, target: e.target.value }))}
          >
            <option value="all">{t('Tüm aktif kullanıcılar')}</option>
            {profiles.map((p) => (
              <option key={p.user_id} value={p.user_id}>{p.email}</option>
            ))}
          </select>
          <input
            type="text" required maxLength={80} placeholder={t('Başlık')}
            value={an.title} onChange={(e) => setAn((s) => ({ ...s, title: e.target.value }))}
          />
          <input
            type="text" maxLength={200} placeholder={t('Mesaj (opsiyonel)')}
            value={an.body} onChange={(e) => setAn((s) => ({ ...s, body: e.target.value }))}
          />
          <button className="apply-btn" type="submit" disabled={anBusy || !an.title.trim()}>
            {anBusy ? '…' : `📣 ${t('Gönder')}`}
          </button>
        </form>
        <div className="form-note">
          {t('Push bildirimi olarak gider (aboneliği açık cihazlara, ≤1 dk). Strateji adları içeren metin yazma — kullanıcılar kod adlarını görür.')}
        </div>
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
