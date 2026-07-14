// Uygulamanın CSS design token'larını çözülmüş renk değerleri olarak okur.
// lightweight-charts canvas'ı CSS var çözemez -> getComputedStyle ile resolve edilir.
// DOM inline stilleri için CSS var string'i kullanın; buradaki değerler yalnız canvas için.

// 6 haneli hex'i {r,g,b}'ye çevirir; değilse null (rgba() vb. token değerleri için).
function hexToRgb(hex) {
  const m = /^#([0-9a-fA-F]{6})$/.exec((hex || '').trim());
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return { r: (n >> 16) & 255, g: (n >> 8) & 255, b: n & 255 };
}

// Karanlık-mod dim paleti — ChartModal'daki mevcut değerlerle birebir aynı.
const DIM_DARK = {
  pre:    { color: '#322B45', wick: '#7C6BB0', border: '#473A66' },
  post:   { color: '#2B3139', wick: '#5E6673', border: '#2B3139' },
  cancel: { color: '#3D331C', wick: '#C99A3E', border: '#5C4B28' },
};
// Açık-mod eşdeğerleri: beyaz zeminde okunur pastel dolgular + koyu fitiller.
const DIM_LIGHT = {
  pre:    { color: '#E9E4F5', wick: '#8A7BC0', border: '#D6CCEE' },
  post:   { color: '#ECEEF1', wick: '#9AA4B2', border: '#E3E6EA' },
  cancel: { color: '#F5EBD6', wick: '#B08A3E', border: '#EAD9B0' },
};

export function readChartTheme() {
  const root = document.documentElement;
  const cs = getComputedStyle(root);
  const read = (name, fallback) => (cs.getPropertyValue(name) || '').trim() || fallback;

  const dark = root.dataset.theme !== 'light'; // varsayılan dark

  const bg     = read('--bg', '#0B0E11');
  const panel  = read('--panel-2', '#1E2329');
  const text   = read('--text', '#EAECEF');
  const muted  = read('--muted', '#848E9C');
  const border = read('--border', '#2B3139');
  const up     = read('--win', '#0ECB81');
  const down   = read('--loss', '#F6465D');
  const accent = read('--accent', '#F0B90B');

  // Token 6 haneli hex değilse dark varsayılanına düş (rgba üretimi için).
  const upRgb = hexToRgb(up) || hexToRgb('#0ECB81');
  const downRgb = hexToRgb(down) || hexToRgb('#F6465D');

  return {
    dark,
    bg, panel, text, muted, border, up, down, accent,
    upSoft: (a) => `rgba(${upRgb.r}, ${upRgb.g}, ${upRgb.b}, ${a})`,
    downSoft: (a) => `rgba(${downRgb.r}, ${downRgb.g}, ${downRgb.b}, ${a})`,
    dim: dark ? DIM_DARK : DIM_LIGHT,
  };
}
