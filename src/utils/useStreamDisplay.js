// React hook: the ONE way components resolve a stream's display name / label / info
// card / chart-refline tag. Default = anonymized codename (streamMask); when the
// logged-in profile is an ADMIN, the real names lazy-load from adminStreamInfo.js
// and transparently replace the codenames.
//
// Usage:
//   const sd = useStreamDisplay();
//   sd.name('d30so8f3h7')      -> 'ATLAS'   (admin: 'OPUS')
//   sd.label('midas')          -> 'Otonom işlem akışı · detaylar gizli' (admin: real label)
//   sd.info('d30so8c', lang)   -> null      (admin: the full strategy card)
//   sd.refline()               -> 'T-REF'   (admin: 'VWAP')

import { useEffect, useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { codenameFor, loadAdminStreamInfo, REFLINE_LABEL } from './streamMask';
import { useLang } from '../context/LanguageContext';

export function useStreamDisplay() {
  const { isAdmin } = useAuth();
  const { t, lang } = useLang();
  const [adm, setAdm] = useState(null);

  useEffect(() => {
    let alive = true;
    if (isAdmin) {
      loadAdminStreamInfo().then((m) => { if (alive) setAdm(m); }).catch(() => {});
    } else {
      setAdm(null);
    }
    return () => { alive = false; };
  }, [isAdmin]);

  return {
    isAdmin,
    /** Short display name (card titles, nav, tabs). */
    name: (key) => adm?.REAL_NAMES?.[key] || codenameFor(key),
    /** Sublabel line (the old technical label slot). */
    label: (key) => adm?.REAL_LABELS?.[key] || t('Otonom işlem akışı · detaylar gizli'),
    /** Full strategy card ({title, tagline, summary, sections, caveat}) — admin only, else null. */
    info: (key, l = lang) => (adm ? adm.infoFor(key, l) : null),
    /** Chart anchor-line tag (XAU). */
    refline: () => adm?.REAL_REFLINE || REFLINE_LABEL,
    /** TOTAL page research footnote (names real streams) — admin only, else null. */
    marketcapNote: (l = lang) => adm?.MARKETCAP_NOTE?.[l] || adm?.MARKETCAP_NOTE?.tr || null,
    /** XAU signal-condition pill labels — real for admin, neutral otherwise. */
    midasConds: () => adm?.REAL_MIDAS_CONDS || {
      slopeUp: 'Koşul A', above: 'Koşul B', pullLong: 'Koşul C', bull: 'Koşul D', sess: 'Koşul E',
      slopeDn: 'Koşul A', below: 'Koşul B', pullShort: 'Koşul C', bear: 'Koşul D',
    },
    /** TALOS (Keltner) variant of the same checklist. */
    talosConds: () => adm?.REAL_TALOS_CONDS || {
      slopeUp: 'Koşul A', above: 'Koşul B', pullLong: 'Koşul C', bull: 'Koşul D', sess: 'Koşul E',
      slopeDn: 'Koşul A', below: 'Koşul B', pullShort: 'Koşul C', bear: 'Koşul D',
    },
    /** TALOS-ICHI = TALOS checklist + the Ichimoku Kumo-colour direction gate. */
    talosIchiConds: () => adm?.REAL_TALOS_ICHI_CONDS || {
      slopeUp: 'Koşul A', above: 'Koşul B', pullLong: 'Koşul C', bull: 'Koşul D', kumoLong: 'Koşul F', sess: 'Koşul E',
      slopeDn: 'Koşul A', below: 'Koşul B', pullShort: 'Koşul C', bear: 'Koşul D', kumoShort: 'Koşul F',
    },
  };
}
