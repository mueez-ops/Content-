'use strict';
/* Shared helpers: DOM, storage, toasts, clipboard, saving files, Claude capabilities,
   the audio clock that Beat Grid and Type Studio both run on, and the safe-zone map. */

const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
const clamp = (x, a = 0, b = 1) => Math.max(a, Math.min(b, x));
const lerp = (a, b, t) => a + (b - a) * t;
const easeOut = (t) => 1 - Math.pow(1 - t, 3);
const easeInOut = (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2);
const REDUCED = window.matchMedia && matchMedia('(prefers-reduced-motion: reduce)').matches;

function mkCanvas(w, h) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  return c;
}

function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

/* ---------------------------------------------------------------- storage (per-viewer drafts only) */
const store = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem('hs:' + key);
      return v == null ? fallback : JSON.parse(v);
    } catch (e) { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem('hs:' + key, JSON.stringify(value)); } catch (e) { /* storage unavailable */ }
  },
};

/* ---------------------------------------------------------------- toast */
let toastTimer = 0;
function toast(msg) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), 2600);
}

/* ---------------------------------------------------------------- clipboard */
function copyText(text) {
  let p = null;
  try { p = navigator.clipboard && navigator.clipboard.writeText(text); } catch (e) { p = null; }
  if (p && p.then) p.then(() => toast('Copied'), () => fallbackCopy(text));
  else fallbackCopy(text);
}
function fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.setAttribute('readonly', '');
  ta.style.cssText = 'position:fixed;left:0;top:0;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  let ok = false;
  try { ok = document.execCommand('copy'); } catch (e) { ok = false; }
  ta.remove();
  toast(ok ? 'Copied' : 'Copying is blocked here. Select the text and copy it yourself.');
}

/* ---------------------------------------------------------------- Claude capabilities */
const HAS_CLAUDE = !!(window.claude && typeof window.claude.use === 'function');
function useCap(name) {
  if (!HAS_CLAUDE) return Promise.resolve(null);
  try { return Promise.resolve(window.claude.use(name)).catch(() => null); } catch (e) { return Promise.resolve(null); }
}
const CAPS = { sample: useCap('sample'), downloads: useCap('downloads') };

function claudeErrorText(e) {
  const code = e && e.code;
  switch (code) {
    case 'rate_limited': return e.reason === 'usage_limit' ? 'You have reached your Claude usage limit. Try again later.' : 'Claude is busy right now. Try again in a minute.';
    case 'refused': return 'Claude declined this one. Try changing the input.';
    case 'invalid_json': return 'Claude’s answer came back in the wrong shape. Try again.';
    case 'session_expired': return 'Your session expired. Sign in again to use Claude.';
    case 'image_rejected': return 'Claude couldn’t read that image. Try a JPEG or PNG.';
    case 'empty_completion': return 'Claude returned nothing. Try again with less input.';
    case 'cancelled': return '';
    default: return 'Couldn’t reach Claude. Try again.';
  }
}
/* Codes after which the feature should disappear for this view. */
const CLAUDE_GONE = new Set(['not_granted', 'sampling_disabled', 'not_declared', 'capability_disabled', 'capability_removed']);

/* ---------------------------------------------------------------- saving files */
async function saveFile(filename, blob) {
  if (HAS_CLAUDE) {
    const dl = await CAPS.downloads;
    if (!dl) { toast('Saving files isn’t available in this view.'); return false; }
    try {
      const r = await dl.save({ filename, data: blob });
      if (r && r.status === 'saved') toast('Saved ' + filename);
      return true;
    } catch (e) {
      const c = e && e.code;
      if (c === 'declined') toast('Save cancelled');
      else if (c === 'rate_limited') toast('A save is already waiting for you. Try again in a moment.');
      else if (c === 'host_unavailable') toast('This app can’t save files. Open the studio in a browser to save.');
      else toast('Couldn’t save ' + filename + '.');
      return false;
    }
  }
  // Opened straight from disk or another host: an ordinary download link works.
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = filename;
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 8000);
  toast('Saved ' + filename);
  return true;
}

/* ---------------------------------------------------------------- audio */
let AC = null;
function audio() {
  if (!AC) {
    const C = window.AudioContext || window.webkitAudioContext;
    if (!C) return null;
    try { AC = new C(); } catch (e) { return null; }
  }
  if (AC.state === 'suspended') AC.resume();
  return AC;
}

const noiseBuffers = new WeakMap();
function noiseBuf(ac) {
  let b = noiseBuffers.get(ac);
  if (!b) {
    b = ac.createBuffer(1, Math.floor(ac.sampleRate * 0.5), ac.sampleRate);
    const d = b.getChannelData(0);
    for (let i = 0; i < d.length; i++) d[i] = Math.random() * 2 - 1;
    noiseBuffers.set(ac, b);
  }
  return b;
}

/* Small synthesised voices. `dest` defaults to the speakers; exports pass a recorder destination. */
const SFX = {
  click(ac, when, accent, dest) {
    const o = ac.createOscillator();
    const g = ac.createGain();
    o.type = 'square';
    o.frequency.value = accent ? 1760 : 1175;
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(accent ? 0.26 : 0.14, when + 0.002);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.045);
    o.connect(g); g.connect(dest || ac.destination);
    o.start(when); o.stop(when + 0.06);
  },
  kick(ac, when, dest, level = 0.9) {
    const o = ac.createOscillator();
    const g = ac.createGain();
    o.type = 'sine';
    o.frequency.setValueAtTime(150, when);
    o.frequency.exponentialRampToValueAtTime(42, when + 0.13);
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(level, when + 0.004);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.34);
    o.connect(g); g.connect(dest || ac.destination);
    o.start(when); o.stop(when + 0.36);
  },
  hat(ac, when, dest, level = 0.12) {
    const s = ac.createBufferSource();
    s.buffer = noiseBuf(ac);
    const f = ac.createBiquadFilter();
    f.type = 'highpass'; f.frequency.value = 7200;
    const g = ac.createGain();
    g.gain.setValueAtTime(level, when);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.05);
    s.connect(f); f.connect(g); g.connect(dest || ac.destination);
    s.start(when, Math.random() * 0.3); s.stop(when + 0.06);
  },
  snap(ac, when, dest, level = 0.42) {
    const s = ac.createBufferSource();
    s.buffer = noiseBuf(ac);
    const f = ac.createBiquadFilter();
    f.type = 'bandpass'; f.frequency.value = 1900; f.Q.value = 0.9;
    const g = ac.createGain();
    g.gain.setValueAtTime(0.0001, when);
    g.gain.exponentialRampToValueAtTime(level, when + 0.003);
    g.gain.exponentialRampToValueAtTime(0.0001, when + 0.14);
    s.connect(f); f.connect(g); g.connect(dest || ac.destination);
    s.start(when, Math.random() * 0.3); s.stop(when + 0.16);
  },
};

/* A looping beat transport on the audio clock, so sound and picture stay locked.
   opts: spb() seconds per beat, loopBeats() beats per loop, onBeat(ac, when, beatInLoop, spb),
         onFrame(tInLoop), onStop() */
class Transport {
  constructor(opts) { this.o = opts; this.playing = false; this.raf = 0; this.ac = null; }
  now() { return this.ac ? this.ac.currentTime : performance.now() / 1000; }
  play(fromT = 0) {
    this.ac = audio();
    const spb = this.o.spb();
    this.t0 = this.now() + 0.06 - fromT;
    this.k = Math.ceil(fromT / spb - 1e-6);
    this.playing = true;
    cancelAnimationFrame(this.raf);
    this.tick();
  }
  stop() {
    if (!this.playing) return;
    this.playing = false;
    cancelAnimationFrame(this.raf);
    if (this.o.onStop) this.o.onStop();
  }
  restart() {
    if (!this.playing) return;
    const spb = this.o.spb();
    const loop = Math.max(1, this.o.loopBeats()) * spb;
    const t = Math.max(0, this.now() - this.t0) % loop;
    this.play(t);
  }
  tick() {
    if (!this.playing) return;
    const spb = this.o.spb();
    const loopBeats = Math.max(1, this.o.loopBeats());
    const now = this.now();
    if (this.ac) {
      while (this.t0 + this.k * spb < now + 0.12) {
        const when = this.t0 + this.k * spb;
        if (when >= now - 0.03) this.o.onBeat(this.ac, when, this.k % loopBeats, spb);
        this.k++;
      }
    }
    const tAbs = Math.max(0, now - this.t0);
    this.o.onFrame(tAbs % (loopBeats * spb));
    this.raf = requestAnimationFrame(() => this.tick());
  }
}

/* ---------------------------------------------------------------- safe zones
   Approximate areas that short-video apps cover with their own UI on a 9:16 frame.
   They vary by app and device; these are deliberately cautious. */
const ZONES = [
  { x: 0, y: 0, w: 1, h: 0.13, label: 'Top bar' },
  { x: 0, y: 0.78, w: 1, h: 0.22, label: 'Caption & CTA' },
  { x: 0.86, y: 0.42, w: 0.14, h: 0.36, label: 'Buttons' },
];
function inZone(fx, fy) {
  return ZONES.some((z) => fx >= z.x && fx <= z.x + z.w && fy >= z.y && fy <= z.y + z.h);
}
function renderZones(container) {
  container.textContent = '';
  for (const z of ZONES) {
    const d = document.createElement('div');
    d.className = 'zone';
    d.style.left = z.x * 100 + '%';
    d.style.top = z.y * 100 + '%';
    d.style.width = z.w * 100 + '%';
    d.style.height = z.h * 100 + '%';
    const s = document.createElement('span');
    s.textContent = z.label;
    d.appendChild(s);
    container.appendChild(d);
  }
}

/* ---------------------------------------------------------------- colour */
function hexToRgb(hex) {
  const h = hex.replace('#', '');
  const n = parseInt(h.length === 3 ? h.split('').map((c) => c + c).join('') : h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
function rgbToHex(r, g, b) {
  return '#' + [r, g, b].map((v) => Math.round(clamp(v, 0, 255)).toString(16).padStart(2, '0')).join('').toUpperCase();
}
function relLum([r, g, b]) {
  const f = (v) => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
}
function contrastRatio(a, b) {
  const la = relLum(a), lb = relLum(b);
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05);
}
function saturation([r, g, b]) {
  const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
  return mx === 0 ? 0 : (mx - mn) / mx;
}

/* ---------------------------------------------------------------- router */
const ROUTES = ['studio', 'hooks', 'beats', 'type', 'scroll-stop'];
const routeHooks = {}; // name -> { enter(), leave() }
let currentRoute = null;
function route() {
  const want = location.hash.replace('#', '');
  const name = ROUTES.includes(want) ? want : 'studio';
  if (name === currentRoute) return;
  if (currentRoute && routeHooks[currentRoute] && routeHooks[currentRoute].leave) routeHooks[currentRoute].leave();
  currentRoute = name;
  $$('.view').forEach((v) => { v.hidden = v.dataset.view !== name; });
  $$('[data-route]').forEach((a) => {
    if (a.dataset.route === name) a.setAttribute('aria-current', 'page');
    else a.removeAttribute('aria-current');
  });
  if (routeHooks[name] && routeHooks[name].enter) routeHooks[name].enter();
  window.scrollTo(0, 0);
}
