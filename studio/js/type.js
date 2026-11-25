'use strict';
/* Type Studio: lines of copy become 1080×1920 kinetic type cards that cut on the beat.
   Four treatments, film grain, vignette, a timecode slate, a synthesised beat track,
   and real-time export to MP4 or WebM with MediaRecorder. */

const TW = 1080, TH = 1920;
const TYPE_PALETTES = [
  { name: 'Ink', bg: '#0E0D0C', fg: '#F0E9DD', accent: '#FF4D22' },
  { name: 'Cream', bg: '#ECE5D8', fg: '#0E0D0C', accent: '#FF4D22' },
  { name: 'Signal', bg: '#FF4D22', fg: '#0E0D0C', accent: '#F0E9DD' },
];
const TYPE_DEFAULT = {
  lines: 'You’ve got 0.5 seconds.\nThey’ll ask what you’re wearing.\n3 sprays. 12 hours.\n20% off, this week only.\nShop the drop →',
  style: 'slam', beatsPer: 2, bpm: 120, link: true,
  bg: '#0E0D0C', fg: '#F0E9DD', accent: '#FF4D22',
  grain: 45, vignette: true, slate: true, sound: true, tag: 'HALFSECOND',
};
const typeState = Object.assign({}, TYPE_DEFAULT, store.get('type', {}));
const STYLE_NAMES = { slam: 'Serif slam', type: 'Typewriter', stack: 'Stack', wipe: 'Mask wipe' };

const tyCanvas = () => $('#ty-canvas');
let tyCtx = null;
let tyPreviewT = 0;

function tyBpm() { return typeState.link ? beatState.bpm : typeState.bpm; }
function tyLines() {
  const ls = typeState.lines.split('\n').map((s) => s.trim()).filter(Boolean);
  return ls.length ? ls : ['Type a line'];
}
function tySpb() { return 60 / tyBpm(); }
function tyCardLen() { return typeState.beatsPer * tySpb(); }
function tyTotal() { return tyLines().length * tyCardLen(); }
function saveType() { store.set('type', typeState); }

/* ---------------------------------------------------------------- finish layers */
const grainLayers = [];
function buildGrain() {
  for (let k = 0; k < 4; k++) {
    const c = mkCanvas(540, 960);
    const x = c.getContext('2d');
    const img = x.createImageData(540, 960);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) {
      // roughly Gaussian luminance noise around mid-grey
      const v = 128 + (Math.random() + Math.random() + Math.random() - 1.5) * 120;
      d[i] = d[i + 1] = d[i + 2] = v;
      d[i + 3] = 255;
    }
    x.putImageData(img, 0, 0);
    grainLayers.push(c);
  }
}
let vignetteLayer = null;
function buildVignette() {
  const c = mkCanvas(TW, TH);
  const x = c.getContext('2d');
  const g = x.createRadialGradient(TW / 2, TH * 0.46, TH * 0.22, TW / 2, TH * 0.5, TH * 0.72);
  g.addColorStop(0, 'rgba(0,0,0,0)');
  g.addColorStop(1, 'rgba(0,0,0,0.55)');
  x.fillStyle = g;
  x.fillRect(0, 0, TW, TH);
  vignetteLayer = c;
}

/* ---------------------------------------------------------------- text layout */
const fitCache = new Map();
function wrapWords(ctx, text, maxW) {
  const words = text.split(/\s+/).filter(Boolean);
  const lines = [];
  let cur = '';
  for (const w of words) {
    const t = cur ? cur + ' ' + w : w;
    if (!cur || ctx.measureText(t).width <= maxW) cur = t;
    else { lines.push(cur); cur = w; }
  }
  if (cur) lines.push(cur);
  return lines;
}
function fitText(ctx, key, text, fontFn, maxSize, minSize, maxW, maxLines, maxH, lh) {
  const ck = key + '|' + text;
  if (fitCache.has(ck)) return fitCache.get(ck);
  let res = null;
  for (let s = maxSize; s >= minSize; s -= 4) {
    ctx.font = fontFn(s);
    const lines = wrapWords(ctx, text, maxW);
    const widest = Math.max(...lines.map((l) => ctx.measureText(l).width));
    if (lines.length <= maxLines && widest <= maxW && lines.length * s * lh <= maxH) { res = { size: s, lines }; break; }
  }
  if (!res) { ctx.font = fontFn(minSize); res = { size: minSize, lines: wrapWords(ctx, text, maxW) }; }
  fitCache.set(ck, res);
  return res;
}

const F_SLAM = (s) => `italic 400 ${s}px "Instrument Serif", "Times New Roman", serif`;
const F_WIPE = (s) => `400 ${s}px "Instrument Serif", "Times New Roman", serif`;
const F_TYPE = (s) => `700 ${s}px "Space Mono", ui-monospace, monospace`;
const F_STACK = (s) => `400 ${s}px Anton, Impact, "Arial Narrow", sans-serif`;
const F_SLATE = '400 30px "Space Mono", ui-monospace, monospace';
const CY = 880; // optical centre of the safe area

function bestText(bg, a, b) {
  return contrastRatio(hexToRgb(bg), hexToRgb(a)) >= contrastRatio(hexToRgb(bg), hexToRgb(b)) ? a : b;
}

/* ---------------------------------------------------------------- treatments */
function drawSlam(ctx, text, tl, c) {
  const fit = fitText(ctx, 'slam', text, F_SLAM, 196, 72, 880, 4, 880, 0.98);
  const k = easeOut(clamp(tl / 0.16));
  const scale = 1 + 0.38 * (1 - k);
  let sx = 0, sy = 0;
  if (!REDUCED && tl > 0.14 && tl < 0.3) {
    const a = (0.3 - tl) / 0.16;
    sx = Math.sin(tl * 95) * 9 * a;
    sy = Math.cos(tl * 71) * 7 * a;
  }
  const lh = fit.size * 0.98;
  const blockH = fit.lines.length * lh;
  ctx.save();
  ctx.translate(TW / 2 + sx, CY + sy);
  ctx.scale(scale, scale);
  ctx.globalAlpha = clamp(tl / 0.05);
  ctx.font = F_SLAM(fit.size);
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  let y = -blockH / 2 + lh * 0.8;
  fit.lines.forEach((ln, j) => {
    ctx.fillStyle = c.fg;
    ctx.fillText(ln, 0, y);
    if (j === fit.lines.length - 1) {
      const w = ctx.measureText(ln).width;
      const p = easeOut(clamp((tl - 0.16) / 0.3));
      ctx.fillStyle = c.accent;
      ctx.fillRect(-w / 2, y + fit.size * 0.16, w * p, Math.max(8, fit.size * 0.065));
    }
    y += lh;
  });
  ctx.restore();
}

function drawTypewriter(ctx, text, tl, L, c, spb) {
  const fit = fitText(ctx, 'type', text, F_TYPE, 112, 44, 860, 7, 980, 1.2);
  ctx.font = F_TYPE(fit.size);
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  const totalChars = fit.lines.reduce((a, l) => a + l.length, 0);
  const reveal = Math.floor(totalChars * clamp(tl / Math.max(0.2, L * 0.55)));
  const lh = fit.size * 1.2;
  const x0 = 110;
  let y = CY - (fit.lines.length * lh) / 2 + lh * 0.78;
  let shown = 0;
  let caret = null;
  ctx.fillStyle = c.fg;
  for (const ln of fit.lines) {
    const take = clamp(reveal - shown, 0, ln.length);
    const part = ln.slice(0, take);
    ctx.fillText(part, x0, y);
    if (caret === null && (take < ln.length || shown + ln.length >= totalChars)) caret = { x: x0 + ctx.measureText(part).width, y };
    shown += ln.length;
    y += lh;
  }
  const done = reveal >= totalChars;
  if (caret && (!done || Math.floor(tl / (spb / 2)) % 2 === 0)) {
    ctx.fillStyle = c.accent;
    ctx.fillRect(caret.x + fit.size * 0.08, caret.y - fit.size * 0.8, fit.size * 0.56, fit.size * 0.96);
  }
}

function drawStack(ctx, text, tl, L, c) {
  let words = text.toUpperCase().split(/\s+/).filter(Boolean);
  if (words.length > 6) {
    const rows = [];
    for (let i = 0; i < words.length; i += 2) rows.push(words.slice(i, i + 2).join(' '));
    words = rows;
  }
  const key = 'stack|' + words.join('/');
  let layout = fitCache.get(key);
  if (!layout) {
    const rows = words.map((w) => {
      ctx.font = F_STACK(200);
      const m = ctx.measureText(w);
      let size = Math.min(380, (200 * 860) / Math.max(1, m.width));
      ctx.font = F_STACK(size);
      const mm = ctx.measureText(w);
      const asc = mm.actualBoundingBoxAscent || size * 0.74;
      const desc = mm.actualBoundingBoxDescent || 0;
      return { w, size, h: asc + desc, asc };
    });
    const gap = 26;
    let total = rows.reduce((a, r) => a + r.h, 0) + gap * (rows.length - 1);
    const maxH = 1150;
    const k = total > maxH ? maxH / total : 1;
    rows.forEach((r) => { r.size *= k; r.h *= k; r.asc *= k; });
    total = total * k;
    layout = { rows, gap: gap * k, total };
    fitCache.set(key, layout);
  }
  const per = Math.min(0.2, (L * 0.6) / layout.rows.length);
  let y = CY - layout.total / 2;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'alphabetic';
  layout.rows.forEach((r, j) => {
    const t = tl - j * per;
    if (t >= 0) {
      const p = easeOut(clamp(t / 0.1));
      ctx.save();
      ctx.globalAlpha = p;
      ctx.font = F_STACK(r.size);
      ctx.fillStyle = j === layout.rows.length - 1 ? c.accent : c.fg;
      ctx.fillText(r.w, TW / 2, y + r.asc - (1 - p) * 50);
      ctx.restore();
    }
    y += r.h + layout.gap;
  });
}

function wipeCard(ctx, text, c) {
  ctx.fillStyle = c.bg;
  ctx.fillRect(0, 0, TW, TH);
  const fit = fitText(ctx, 'wipe', text, F_WIPE, 184, 72, 860, 4, 860, 1.0);
  ctx.font = F_WIPE(fit.size);
  ctx.fillStyle = c.fg;
  ctx.textAlign = 'left';
  ctx.textBaseline = 'alphabetic';
  const lh = fit.size;
  let y = CY - (fit.lines.length * lh) / 2 + lh * 0.8;
  for (const ln of fit.lines) { ctx.fillText(ln, 110, y); y += lh; }
}
function wipeColors(i) {
  const s = typeState;
  const flip = i % 2 === 1;
  const bg = flip ? s.accent : s.bg;
  return { bg, fg: bestText(bg, s.fg, flip ? s.bg : s.accent), edge: flip ? s.bg : s.accent };
}

/* ---------------------------------------------------------------- frame */
function renderTypeFrame(ctx, t, opts = {}) {
  const lines = tyLines();
  const L = tyCardLen();
  const n = lines.length;
  const total = n * L;
  t = clamp(t, 0, total - 1e-4);
  const i = Math.min(n - 1, Math.floor(t / L));
  const tl = t - i * L;
  const spb = tySpb();
  const s = typeState;
  const c = { bg: s.bg, fg: s.fg, accent: s.accent };
  ctx.save();
  ctx.globalAlpha = 1;
  ctx.globalCompositeOperation = 'source-over';

  if (s.style === 'wipe') {
    const p = easeInOut(clamp(tl / 0.3));
    const prev = (i - 1 + n) % n;
    if (p < 1) wipeCard(ctx, lines[prev], wipeColors(prev));
    ctx.save();
    ctx.beginPath();
    ctx.rect(0, 0, TW * p, TH);
    ctx.clip();
    wipeCard(ctx, lines[i], wipeColors(i));
    ctx.restore();
    if (p > 0 && p < 1) { ctx.fillStyle = wipeColors(i).edge; ctx.fillRect(TW * p - 7, 0, 14, TH); }
  } else {
    ctx.fillStyle = c.bg;
    ctx.fillRect(0, 0, TW, TH);
    if (s.style === 'slam') drawSlam(ctx, lines[i], tl, c);
    else if (s.style === 'type') drawTypewriter(ctx, lines[i], tl, L, c, spb);
    else drawStack(ctx, lines[i], tl, L, c);
    // a two-frame flash on every cut
    if (!REDUCED && tl < 2 / 30) {
      ctx.globalAlpha = 0.07 * (1 - tl / (2 / 30));
      ctx.fillStyle = c.fg;
      ctx.fillRect(0, 0, TW, TH);
      ctx.globalAlpha = 1;
    }
  }

  if (s.slate) {
    const slateFg = s.style === 'wipe' ? wipeColors(i).fg : c.fg;
    ctx.font = F_SLATE;
    ctx.fillStyle = slateFg;
    ctx.globalAlpha = 0.62;
    ctx.textBaseline = 'alphabetic';
    ctx.textAlign = 'left';
    const fr = Math.floor(t * 30);
    const tc = `${String(Math.floor(fr / 1800)).padStart(2, '0')}:${String(Math.floor(fr / 30) % 60).padStart(2, '0')}:${String(fr % 30).padStart(2, '0')}`;
    ctx.fillText(tc, 80, 310);
    ctx.textAlign = 'right';
    const tag = (s.tag || '').toUpperCase();
    ctx.fillText(`${tag ? tag + ' / ' : ''}${String(i + 1).padStart(3, '0')}`, TW - 80, 310);
    ctx.globalAlpha = 1;
  }

  if (s.vignette && vignetteLayer) ctx.drawImage(vignetteLayer, 0, 0);
  if (s.grain > 0 && grainLayers.length) {
    const g = grainLayers[opts.still ? 0 : Math.floor(Math.random() * grainLayers.length)];
    const dx = opts.still ? 0 : Math.random() * 40, dy = opts.still ? 0 : Math.random() * 40;
    ctx.globalCompositeOperation = 'overlay';
    ctx.globalAlpha = (s.grain / 100) * 0.55;
    ctx.drawImage(g, -dx, -dy, TW + 40, TH + 40);
  }
  ctx.restore();
  return { i, n, t, total };
}

function tyDraw(t, still) {
  if (!tyCtx) return;
  const r = renderTypeFrame(tyCtx, t, { still });
  $('#ty-time').textContent = `${r.t.toFixed(2)} / ${r.total.toFixed(2)} s`;
}
function tyDrawPreview() {
  tyDraw(tyPreviewT, true);
  $('#ty-scrub').value = Math.round((tyPreviewT / tyTotal()) * 1000);
}

/* ---------------------------------------------------------------- transport + beat track */
function scheduleBeat(ac, when, k, spb, dest) {
  const per = typeState.beatsPer;
  if (k % per === 0) { SFX.kick(ac, when, dest); SFX.snap(ac, when, dest, 0.22); }
  else SFX.kick(ac, when, dest, 0.6);
  SFX.hat(ac, when + spb / 2, dest);
}
const transportType = new Transport({
  spb: tySpb,
  loopBeats: () => tyLines().length * typeState.beatsPer,
  onBeat(ac, when, k, spb) { if (typeState.sound) scheduleBeat(ac, when, k, spb); },
  onFrame(t) { tyPreviewT = t; tyDraw(t, false); $('#ty-scrub').value = Math.round((t / tyTotal()) * 1000); },
  onStop() { setTypePlay(false); },
});
function setTypePlay(on) {
  const b = $('#ty-play');
  b.setAttribute('aria-label', on ? 'Pause' : 'Play');
  b.querySelector('path').setAttribute('d', on ? 'M4 3h3v10H4zM9 3h3v10H9z' : 'M4 2.5v11l9-5.5z');
}

/* ---------------------------------------------------------------- export */
function pickMime(withAudio) {
  if (!window.MediaRecorder || !MediaRecorder.isTypeSupported) return '';
  const list = withAudio
    ? ['video/mp4;codecs=avc1.42E01E,mp4a.40.2', 'video/mp4', 'video/webm;codecs=vp9,opus', 'video/webm;codecs=vp8,opus', 'video/webm']
    : ['video/mp4;codecs=avc1.42E01E', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'];
  return list.find((m) => MediaRecorder.isTypeSupported(m)) || '';
}

let exporting = null;
async function exportVideo() {
  const canvas = tyCanvas();
  if (!canvas.captureStream || !window.MediaRecorder) { toast('This browser can’t record video. Try Chrome, Edge or Safari.'); return; }
  if (exporting) return;
  transportType.stop();
  const withAudio = typeState.sound;
  let ac = null, dest = null;
  if (withAudio) {
    const C = window.AudioContext || window.webkitAudioContext;
    try { ac = new C(); dest = ac.createMediaStreamDestination(); } catch (e) { ac = null; }
  }
  const stream = canvas.captureStream(30);
  if (ac && dest) stream.addTrack(dest.stream.getAudioTracks()[0]);
  const mime = pickMime(!!ac);
  let rec;
  try { rec = new MediaRecorder(stream, mime ? { mimeType: mime, videoBitsPerSecond: 10e6 } : { videoBitsPerSecond: 10e6 }); }
  catch (e) { toast('This browser refused to record. Try Chrome, Edge or Safari.'); if (ac) ac.close(); return; }
  const chunks = [];
  rec.ondataavailable = (e) => { if (e.data && e.data.size) chunks.push(e.data); };
  const stopped = new Promise((r) => { rec.onstop = r; });
  const total = tyTotal();
  const veil = $('#ty-veil');
  const bar = $('#ty-veil-bar');
  veil.hidden = false;
  $('#ty-cancel').focus();
  exporting = { cancelled: false };
  const job = exporting;

  renderTypeFrame(tyCtx, 0);
  rec.start(250);
  const clock = () => (ac ? ac.currentTime : performance.now() / 1000);
  if (ac && ac.state === 'suspended') await ac.resume();
  const t0 = clock() + 0.12;
  if (ac) {
    const spb = tySpb();
    const beats = Math.round(total / spb);
    for (let k = 0; k < beats; k++) scheduleBeat(ac, t0 + k * spb, k, spb, dest);
  }
  await new Promise((resolve) => {
    const step = () => {
      if (job.cancelled) { resolve(); return; }
      const t = clock() - t0;
      renderTypeFrame(tyCtx, Math.max(0, t));
      bar.style.width = clamp(t / total) * 100 + '%';
      if (t >= total + 0.1) { resolve(); return; }
      requestAnimationFrame(step);
    };
    step();
  });
  rec.stop();
  await stopped;
  stream.getTracks().forEach((tr) => tr.stop());
  if (ac) ac.close();
  veil.hidden = true;
  exporting = null;
  tyDrawPreview();
  if (job.cancelled) { toast('Export cancelled'); return; }
  const type = (rec.mimeType || mime || 'video/webm').split(';')[0];
  const ext = type.includes('mp4') ? 'mp4' : 'webm';
  const blob = new Blob(chunks, { type });
  await saveFile(`type-reel-${stamp()}.${ext}`, blob);
}

function savePng() {
  const c = mkCanvas(TW, TH);
  renderTypeFrame(c.getContext('2d'), tyPreviewT, { still: true });
  c.toBlob((b) => { if (b) saveFile(`type-frame-${stamp()}.png`, b); }, 'image/png');
}

/* ---------------------------------------------------------------- hand-offs from other tools */
function typeSetOpener(text) {
  if (!text) return;
  const lines = typeState.lines.split('\n');
  lines[0] = text;
  typeState.lines = lines.join('\n');
  $('#ty-lines').value = typeState.lines;
  fitCache.clear();
  saveType();
  tyPreviewT = 0.6;
  typeChanged();
}
function typeSetPalette(p) {
  Object.assign(typeState, p);
  syncTypeInputs();
  saveType();
  typeChanged();
}
function typeOnTempo() {
  if (typeState.link) { $('#ty-bpm').value = beatState.bpm; transportType.restart(); typeChanged(); }
}

function typeChanged() {
  const n = tyLines().length;
  $('#ty-lines-d').textContent = `${n} card${n === 1 ? '' : 's'} × ${typeState.beatsPer} beat${typeState.beatsPer === 1 ? '' : 's'} at ${tyBpm()} BPM = ${tyTotal().toFixed(2)} s. Each line is one card.`;
  if (!transportType.playing) tyDrawPreview();
  renderBench();
}

function syncTypeInputs() {
  $('#ty-lines').value = typeState.lines;
  $$('#ty-style button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.v === typeState.style)));
  $$('#ty-beats button').forEach((b) => b.setAttribute('aria-pressed', String(Number(b.dataset.v) === typeState.beatsPer)));
  $('#ty-bpm').value = tyBpm();
  $('#ty-bpm').disabled = typeState.link;
  $('#ty-link').checked = typeState.link;
  $('#ty-bg').value = typeState.bg;
  $('#ty-fg').value = typeState.fg;
  $('#ty-accent').value = typeState.accent;
  $('#ty-grain').value = typeState.grain;
  $('#ty-vignette').checked = typeState.vignette;
  $('#ty-slate').checked = typeState.slate;
  $('#ty-sound').checked = typeState.sound;
  $('#ty-tag').value = typeState.tag;
}

function typeBench() {
  return { value: `${tyLines().length} cards · ${tyTotal().toFixed(1)} s`, detail: `${STYLE_NAMES[typeState.style]} at ${tyBpm()} BPM, ${typeState.beatsPer} beat${typeState.beatsPer === 1 ? '' : 's'} a card` };
}

function initType() {
  tyCtx = tyCanvas().getContext('2d');
  buildGrain();
  buildVignette();
  renderZones($('#ty-zones'));

  const presets = $('#ty-presets');
  for (const p of TYPE_PALETTES) {
    const b = document.createElement('button');
    b.type = 'button'; b.className = 'preset';
    const i = document.createElement('i');
    for (const col of [p.bg, p.fg, p.accent]) { const s = document.createElement('b'); s.style.background = col; i.appendChild(s); }
    b.append(i, document.createTextNode(p.name));
    b.addEventListener('click', () => typeSetPalette({ bg: p.bg, fg: p.fg, accent: p.accent }));
    presets.appendChild(b);
  }

  syncTypeInputs();
  $('#ty-lines').addEventListener('input', () => { typeState.lines = $('#ty-lines').value; fitCache.clear(); saveType(); transportType.restart(); typeChanged(); });
  $$('#ty-style button').forEach((b) => b.addEventListener('click', () => { typeState.style = b.dataset.v; syncTypeInputs(); saveType(); typeChanged(); }));
  $$('#ty-beats button').forEach((b) => b.addEventListener('click', () => { typeState.beatsPer = Number(b.dataset.v); syncTypeInputs(); saveType(); transportType.restart(); typeChanged(); }));
  $('#ty-link').addEventListener('change', () => { typeState.link = $('#ty-link').checked; if (!typeState.link) typeState.bpm = beatState.bpm; syncTypeInputs(); saveType(); transportType.restart(); typeChanged(); });
  $('#ty-bpm').addEventListener('change', () => { const v = clamp(parseFloat($('#ty-bpm').value) || 120, 40, 240); typeState.bpm = v; saveType(); transportType.restart(); typeChanged(); });
  for (const k of ['bg', 'fg', 'accent']) $('#ty-' + k).addEventListener('input', (e) => { typeState[k] = e.target.value.toUpperCase(); saveType(); typeChanged(); });
  $('#ty-grain').addEventListener('input', () => { typeState.grain = Number($('#ty-grain').value); saveType(); typeChanged(); });
  for (const k of ['vignette', 'slate', 'sound']) $('#ty-' + k).addEventListener('change', (e) => { typeState[k] = e.target.checked; saveType(); typeChanged(); });
  $('#ty-tag').addEventListener('input', () => { typeState.tag = $('#ty-tag').value; saveType(); typeChanged(); });
  $('#ty-safe').addEventListener('change', () => { $('#ty-zones').hidden = !$('#ty-safe').checked; });
  $('#ty-scrub').addEventListener('input', () => { transportType.stop(); tyPreviewT = (Number($('#ty-scrub').value) / 1000) * tyTotal(); tyDraw(tyPreviewT, true); });
  $('#ty-play').addEventListener('click', () => {
    if (transportType.playing) { transportType.stop(); return; }
    const from = tyPreviewT >= tyTotal() - 0.05 ? 0 : tyPreviewT;
    transportType.play(from);
    setTypePlay(true);
  });
  $('#ty-export').addEventListener('click', exportVideo);
  $('#ty-cancel').addEventListener('click', () => { if (exporting) exporting.cancelled = true; });
  $('#ty-png').addEventListener('click', savePng);

  tyPreviewT = Math.min(tyCardLen() * 1 + 0.6, tyTotal() - 0.01);
  typeChanged();
  if (document.fonts && document.fonts.load) {
    Promise.all([
      document.fonts.load('italic 120px "Instrument Serif"'),
      document.fonts.load('120px "Instrument Serif"'),
      document.fonts.load('700 80px "Space Mono"'),
      document.fonts.load('400 30px "Space Mono"'),
      document.fonts.load('120px Anton'),
    ]).catch(() => {}).then(() => { fitCache.clear(); if (!transportType.playing) tyDrawPreview(); });
  }
  routeHooks.type = {
    enter() { syncTypeInputs(); typeChanged(); },
    leave() { transportType.stop(); },
  };
}
