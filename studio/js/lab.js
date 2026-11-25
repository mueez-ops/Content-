'use strict';
/* Scroll-Stop Lab: reads the first frame of a creative, measures it, compares two versions,
   runs a half-second swipe test in a phone feed, and shows four "lenses" plus a palette.
   Inside claude.ai it can also ask Claude for a critique of the frame. */

const FW = 540, FH = 960; // working frame size, 9:16

const METRICS = [
  { key: 'contrast', name: 'Contrast', what: 'Light against dark. A high-contrast frame reads at a glance, even small.', fix: 'Make the subject much darker or lighter than what is behind it.' },
  { key: 'pop', name: 'Colour pop', what: 'How colourful the frame is, and how much of it is saturated rather than grey.', fix: 'Give the frame one saturated colour across a big area, ideally on or behind the subject.' },
  { key: 'focus', name: 'One place to look', what: 'Whether detail gathers in one area or is spread across the frame.', fix: 'Cut secondary elements so one thing owns the frame.' },
  { key: 'calm', name: 'Busyness', what: 'Some detail holds the eye; too many edges read as noise.', fix: 'Remove text and props until the subject has room.' },
  { key: 'safe', name: 'Clear of the app UI', what: 'How much of the detail sits outside the areas apps cover with buttons and captions.', fix: 'Pull key text and product into the middle of the frame.' },
];
const METRIC_WEIGHTS = { contrast: 0.22, pop: 0.18, focus: 0.25, calm: 0.15, safe: 0.2 };

const labState = {
  slots: {
    a: { name: 'The usual ad', sub: 'Sample · Reel 01', frame: null, m: null, pal: null },
    b: { name: 'The halfsecond hero', sub: 'Sample · Reel 01', frame: null, m: null, pal: null },
  },
  active: 'b',
  hold: 500,
};
let labFileTarget = 'b';

/* ---------------------------------------------------------------- frames */
function frameFrom(src, sw, sh) {
  const c = mkCanvas(FW, FH);
  const x = c.getContext('2d');
  x.fillStyle = '#0E0D0C';
  x.fillRect(0, 0, FW, FH);
  const k = Math.min(FW / sw, FH / sh);
  const fr = Math.abs(sw / sh - FW / FH) < 0.03 ? Math.max(FW / sw, FH / sh) : k; // near-9:16 fills; others letterbox
  const w = sw * fr, h = sh * fr;
  x.imageSmoothingQuality = 'high';
  x.drawImage(src, (FW - w) / 2, (FH - h) / 2, w, h);
  return c;
}
function loadImage(url) {
  return new Promise((res, rej) => {
    const img = new Image();
    img.onload = () => res(img);
    img.onerror = () => rej(new Error('That image couldn’t be read. Try a JPEG or PNG.'));
    img.src = url;
  });
}
function firstVideoFrame(url) {
  return new Promise((res, rej) => {
    const v = document.createElement('video');
    v.muted = true; v.playsInline = true; v.preload = 'auto';
    let done = false;
    const fail = () => { if (!done) { done = true; rej(new Error('That video couldn’t be read here. Try an MP4 or a screenshot of its first frame.')); } };
    v.onloadeddata = () => { v.currentTime = Math.min(0.04, (v.duration || 1) / 2); };
    v.onseeked = () => { if (!done) { done = true; res(v); } };
    v.onerror = fail;
    setTimeout(fail, 12000);
    v.src = url;
  });
}
async function frameFromFile(file) {
  const url = URL.createObjectURL(file);
  try {
    if (file.type.startsWith('video/')) {
      const v = await firstVideoFrame(url);
      return frameFrom(v, v.videoWidth, v.videoHeight);
    }
    const img = await loadImage(url);
    return frameFrom(img, img.naturalWidth, img.naturalHeight);
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

/* ---------------------------------------------------------------- analysis */
function boxBlur(src, w, h) {
  const tmp = new Float32Array(src.length), out = new Float32Array(src.length);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      tmp[i] = (src[i - (x > 0 ? 1 : 0)] + src[i] + src[i + (x < w - 1 ? 1 : 0)]) / 3;
    }
  }
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const i = y * w + x;
      out[i] = (tmp[i - (y > 0 ? w : 0)] + tmp[i] + tmp[i + (y < h - 1 ? w : 0)]) / 3;
    }
  }
  return out;
}

function analyzeFrame(frame) {
  const w = 180, h = 320, N = w * h;
  const c = mkCanvas(w, h);
  const x = c.getContext('2d', { willReadFrequently: true });
  x.imageSmoothingQuality = 'high';
  x.drawImage(frame, 0, 0, w, h);
  const d = x.getImageData(0, 0, w, h).data;
  const Y = new Float32Array(N);
  let sY = 0, sY2 = 0, sRg = 0, sRg2 = 0, sYb = 0, sYb2 = 0, satPx = 0;
  for (let i = 0, p = 0; i < N; i++, p += 4) {
    const r = d[p], g = d[p + 1], b = d[p + 2];
    const y = (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255;
    Y[i] = y; sY += y; sY2 += y * y;
    const rg = r - g, yb = 0.5 * (r + g) - b;
    sRg += rg; sRg2 += rg * rg; sYb += yb; sYb2 += yb * yb;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b);
    if (mx > 60 && (mx - mn) / mx > 0.45) satPx++;
  }
  const satCover = satPx / N;
  const mY = sY / N;
  const stdY = Math.sqrt(Math.max(0, sY2 / N - mY * mY));
  const mRg = sRg / N, mYb = sYb / N;
  const vRg = Math.max(0, sRg2 / N - mRg * mRg), vYb = Math.max(0, sYb2 / N - mYb * mYb);
  const colorful = Math.sqrt(vRg + vYb) + 0.3 * Math.sqrt(mRg * mRg + mYb * mYb); // Hasler & Süsstrunk (2003)

  // Blur before measuring edges so film grain and sensor noise don't count as detail.
  const B = boxBlur(boxBlur(Y, w, h), w, h);
  const GX = 9, GY = 16;
  const cells = new Float32Array(GX * GY);
  let edges = 0, eTot = 0, eSafe = 0;
  for (let yy = 1; yy < h - 1; yy++) {
    for (let xx = 1; xx < w - 1; xx++) {
      const i = yy * w + xx;
      const gx = -B[i - w - 1] - 2 * B[i - 1] - B[i + w - 1] + B[i - w + 1] + 2 * B[i + 1] + B[i + w + 1];
      const gy = -B[i - w - 1] - 2 * B[i - w] - B[i - w + 1] + B[i + w - 1] + 2 * B[i + w] + B[i + w + 1];
      const m = Math.sqrt(gx * gx + gy * gy);
      if (m > 0.35) edges++;
      const e = Math.max(0, m - 0.1); // ignore grain-level gradients
      if (!e) continue;
      cells[Math.floor((yy / h) * GY) * GX + Math.floor((xx / w) * GX)] += e;
      eTot += e;
      if (!inZone(xx / w, yy / h)) eSafe += e;
    }
  }
  const order = Array.from(cells.keys()).sort((a, b) => cells[b] - cells[a]);
  const topN = Math.round(GX * GY * 0.15);
  const share = eTot ? order.slice(0, topN).reduce((a, k) => a + cells[k], 0) / eTot : 0;
  let fx = 0, fy = 0, fw = 0;
  for (const k of order.slice(0, 5)) { const v = cells[k]; fx += ((k % GX) + 0.5) / GX * v; fy += (Math.floor(k / GX) + 0.5) / GY * v; fw += v; }
  const density = edges / N;
  const safeShare = eTot ? eSafe / eTot : 1;

  const calm = density < 0.03 ? 0.5 + 0.5 * (density / 0.03) : density <= 0.13 ? 1 : clamp(1 - (density - 0.13) / 0.2, 0.15, 1);
  const s = {
    contrast: clamp(stdY / 0.27),
    pop: clamp(0.5 * clamp(colorful / 72) + 0.5 * clamp(satCover / 0.35)),
    focus: clamp((share - 0.3) / (0.75 - 0.3)),
    calm,
    safe: clamp((safeShare - 0.55) / (0.95 - 0.55)),
  };
  let total = 0;
  for (const k in METRIC_WEIGHTS) total += METRIC_WEIGHTS[k] * s[k];
  const score = Math.round(total * 100);
  return {
    s, score,
    raw: { stdY, colorful, satCover, share, density, safeShare },
    focal: fw ? { x: fx / fw, y: fy / fw } : { x: 0.5, y: 0.5 },
    verdict: score >= 70 ? 'Stops thumbs' : score >= 50 ? 'Gets a glance' : 'Scrolled past',
    tone: score >= 70 ? 'good' : score >= 50 ? 'warn' : 'bad',
  };
}

/* k-means palette, largest cluster first */
function extractPalette(frame, k = 5) {
  const w = 90, h = 160;
  const c = mkCanvas(w, h);
  const x = c.getContext('2d', { willReadFrequently: true });
  x.drawImage(frame, 0, 0, w, h);
  const d = x.getImageData(0, 0, w, h).data;
  const px = [];
  for (let p = 0; p < d.length; p += 4 * 2) px.push([d[p], d[p + 1], d[p + 2]]);
  const dist = (a, b) => (a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2 + (a[2] - b[2]) ** 2;
  const cents = [px[Math.floor(px.length / 2)].slice()];
  while (cents.length < k) {
    let best = null, bd = -1;
    for (let i = 0; i < px.length; i += 7) {
      const md = Math.min(...cents.map((c2) => dist(px[i], c2)));
      if (md > bd) { bd = md; best = px[i]; }
    }
    cents.push(best.slice());
  }
  let counts = new Array(k).fill(0);
  for (let it = 0; it < 10; it++) {
    const sums = cents.map(() => [0, 0, 0]);
    counts = new Array(k).fill(0);
    for (const p of px) {
      let bi = 0, bd = Infinity;
      for (let j = 0; j < k; j++) { const dd = dist(p, cents[j]); if (dd < bd) { bd = dd; bi = j; } }
      sums[bi][0] += p[0]; sums[bi][1] += p[1]; sums[bi][2] += p[2]; counts[bi]++;
    }
    for (let j = 0; j < k; j++) if (counts[j]) cents[j] = sums[j].map((v) => v / counts[j]);
  }
  return cents
    .map((rgb, j) => ({ rgb: rgb.map(Math.round), hex: rgbToHex(...rgb), share: counts[j] / px.length }))
    .filter((c2) => c2.share > 0)
    .sort((a, b) => b.share - a.share);
}

/* ---------------------------------------------------------------- feed placeholders */
function seeded(seed) {
  let s = seed >>> 0;
  return () => { s = (s * 1664525 + 1013904223) >>> 0; return s / 4294967296; };
}
function placeholder(seed) {
  const r = seeded(seed);
  const c = mkCanvas(270, 480);
  const x = c.getContext('2d');
  const tones = [['#3B4A55', '#8FA3A8'], ['#6E5B4B', '#D9C3A5'], ['#2F4A3A', '#9DB89A'], ['#4C3D58', '#B9A6C9'], ['#5A4A3A', '#C9B79C']];
  const [a, b] = tones[seed % tones.length];
  const g = x.createLinearGradient(0, 0, 0, 480);
  g.addColorStop(0, b); g.addColorStop(1, a);
  x.fillStyle = g; x.fillRect(0, 0, 270, 480);
  for (let i = 0; i < 5; i++) {
    const cx = r() * 270, cy = 80 + r() * 320, rad = 40 + r() * 110;
    const rg = x.createRadialGradient(cx, cy, 0, cx, cy, rad);
    rg.addColorStop(0, `rgba(255,255,255,${0.12 + r() * 0.18})`);
    rg.addColorStop(1, 'rgba(255,255,255,0)');
    x.fillStyle = rg; x.fillRect(0, 0, 270, 480);
  }
  x.fillStyle = 'rgba(0,0,0,.18)';
  x.beginPath(); x.ellipse(135, 250 + r() * 40, 60 + r() * 30, 90 + r() * 30, 0, 0, Math.PI * 2); x.fill();
  return c;
}

/* ---------------------------------------------------------------- render */
let feedItems = [];
function buildFeed() {
  const feed = $('#lab-feed');
  feed.textContent = '';
  feedItems = [placeholder(3), placeholder(1), null, placeholder(2), placeholder(4)];
  feedItems.forEach((c, i) => {
    if (i === 2) { const cv = mkCanvas(FW, FH); cv.id = 'lab-creative'; feed.appendChild(cv); }
    else feed.appendChild(c);
  });
}
function feedY(pos) {
  const h = $('#lab-viewport').clientHeight;
  $('#lab-feed').style.transform = `translateY(${-pos * h}px)`;
}

function renderPhone() {
  const slot = labState.slots[labState.active];
  const cv = $('#lab-creative');
  if (cv && slot.frame) cv.getContext('2d').drawImage(slot.frame, 0, 0);
  feedY(2);
  const cap = $('#lab-ui .cap');
  const line = (hookState.line || '').trim();
  cap.textContent = (line || 'They’ll ask what you’re wearing.') + ' … more';
}

function renderSlots() {
  const wrap = $('#lab-slots');
  wrap.textContent = '';
  for (const key of ['a', 'b']) {
    const s = labState.slots[key];
    const card = document.createElement('div');
    card.className = 'slot' + (labState.active === key ? ' on' : '');
    card.dataset.key = key;
    const cv = mkCanvas(168, 299);
    if (s.frame) { const x = cv.getContext('2d'); x.imageSmoothingQuality = 'high'; x.drawImage(s.frame, 0, 0, 168, 299); }
    const body = document.createElement('div'); body.className = 's-body';
    const lab = document.createElement('span'); lab.className = 'label';
    const key2 = document.createElement('span'); key2.className = 'key ' + key;
    lab.append(key2, document.createTextNode(`Version ${key.toUpperCase()} · ${s.sub}`));
    const name = document.createElement('span'); name.className = 's-name'; name.textContent = s.name; name.title = s.name;
    const sc = document.createElement('div'); sc.className = 'row';
    const num = document.createElement('span'); num.className = 's-score';
    num.textContent = s.m ? s.m.score : '–';
    const small = document.createElement('small'); small.textContent = '/100'; num.appendChild(small);
    const pill = document.createElement('span'); pill.className = 'pill ' + (s.m ? s.m.tone : '');
    pill.textContent = s.m ? s.m.verdict : 'Loading';
    sc.append(num, pill);
    const acts = document.createElement('div'); acts.className = 's-acts';
    const pick = document.createElement('button'); pick.type = 'button'; pick.className = 'btn sm' + (labState.active === key ? ' dark' : '');
    pick.textContent = labState.active === key ? 'Inspecting' : 'Inspect';
    pick.setAttribute('aria-pressed', String(labState.active === key));
    pick.addEventListener('click', (e) => { e.stopPropagation(); selectSlot(key); });
    const rep = document.createElement('button'); rep.type = 'button'; rep.className = 'btn sm'; rep.textContent = 'Replace';
    rep.addEventListener('click', (e) => { e.stopPropagation(); labFileTarget = key; $('#lab-file').click(); });
    acts.append(pick, rep);
    body.append(lab, name, sc, acts);
    card.append(cv, body);
    card.addEventListener('click', () => selectSlot(key));
    card.addEventListener('dragover', (e) => { e.preventDefault(); card.classList.add('drag'); });
    card.addEventListener('dragleave', () => card.classList.remove('drag'));
    card.addEventListener('drop', (e) => {
      e.preventDefault(); card.classList.remove('drag');
      const f = e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0];
      if (f) loadIntoSlot(key, f);
    });
    wrap.appendChild(card);
  }
  $('#lab-key-a').textContent = 'A · ' + labState.slots.a.name;
  $('#lab-key-b').textContent = 'B · ' + labState.slots.b.name;
}

function renderMetrics() {
  const wrap = $('#lab-metrics');
  wrap.textContent = '';
  const A = labState.slots.a.m, B = labState.slots.b.m;
  const act = labState.slots[labState.active].m;
  const rows = [{ key: 'score', name: 'Stop score', what: 'Weighted from the five measures below.' }].concat(METRICS);
  for (const mt of rows) {
    const row = document.createElement('div'); row.className = 'metric';
    const left = document.createElement('div');
    const h = document.createElement('h4'); h.textContent = mt.name;
    const p = document.createElement('p'); p.textContent = mt.what;
    left.append(h, p);
    const val = (m) => (m ? (mt.key === 'score' ? m.score : Math.round(m.s[mt.key] * 100)) : 0);
    if (mt.fix && act && act.s[mt.key] < 0.55) {
      const f = document.createElement('p'); f.className = 'fix';
      f.textContent = `Fix for ${labState.active.toUpperCase()}: ${mt.fix}`;
      left.appendChild(f);
    }
    const bars = document.createElement('div'); bars.className = 'bars';
    for (const [k, m] of [['a', A], ['b', B]]) {
      const line = document.createElement('div'); line.className = k;
      const tag = document.createElement('span'); tag.className = 'tag'; tag.textContent = k.toUpperCase();
      const tr = document.createElement('span'); tr.className = 'track';
      const i = document.createElement('i'); i.style.width = val(m) + '%';
      tr.appendChild(i);
      const v = document.createElement('span'); v.textContent = m ? val(m) : '–';
      line.append(tag, tr, v);
      bars.appendChild(line);
    }
    row.append(left, bars);
    wrap.appendChild(row);
  }
}

function renderLenses() {
  const slot = labState.slots[labState.active];
  const f = slot.frame;
  if (!f) return;
  $('#lab-lens-name').textContent = `Version ${labState.active.toUpperCase()}`;
  // At scroll speed: average of vertically shifted copies
  const blur = $('#lens-blur').getContext('2d');
  const n = 18;
  for (let k = 0; k < n; k++) {
    blur.globalAlpha = 1 / (k + 1);
    blur.drawImage(f, 0, ((k / (n - 1)) - 0.5) * 90, 270, 480);
  }
  blur.globalAlpha = 1;
  // Squint: down-sample hard, scale back up
  const tiny = mkCanvas(18, 32);
  const tx = tiny.getContext('2d');
  tx.imageSmoothingQuality = 'high';
  tx.drawImage(f, 0, 0, 18, 32);
  const sq = $('#lens-squint').getContext('2d');
  sq.imageSmoothingEnabled = true;
  sq.imageSmoothingQuality = 'high';
  sq.drawImage(tiny, 0, 0, 270, 480);
  if (slot.m) {
    const { x, y } = slot.m.focal;
    sq.strokeStyle = '#FF4D22'; sq.lineWidth = 4;
    sq.beginPath(); sq.arc(x * 270, y * 480, 26, 0, Math.PI * 2); sq.stroke();
    sq.strokeStyle = 'rgba(255,255,255,.85)'; sq.lineWidth = 1.5;
    sq.beginPath(); sq.arc(x * 270, y * 480, 32, 0, Math.PI * 2); sq.stroke();
  }
  // Values: five tones
  const vc = $('#lens-values').getContext('2d', { willReadFrequently: true });
  vc.drawImage(f, 0, 0, 270, 480);
  const img = vc.getImageData(0, 0, 270, 480);
  const d = img.data;
  const tones = [14, 70, 128, 186, 240];
  for (let p = 0; p < d.length; p += 4) {
    const y = (0.2126 * d[p] + 0.7152 * d[p + 1] + 0.0722 * d[p + 2]) / 255;
    const t = tones[Math.min(4, Math.floor(y * 5))];
    d[p] = d[p + 1] = d[p + 2] = t;
  }
  vc.putImageData(img, 0, 0);
  // Thumbnail
  const th = $('#lens-thumb').getContext('2d');
  th.imageSmoothingQuality = 'high';
  th.drawImage(f, 0, 0, 92, 164);
}

function renderPalette() {
  const slot = labState.slots[labState.active];
  const wrap = $('#lab-palette');
  wrap.textContent = '';
  (slot.pal || []).forEach((c) => {
    const b = document.createElement('button');
    b.type = 'button';
    b.title = 'Copy ' + c.hex;
    const i = document.createElement('i'); i.style.background = c.hex;
    const s = document.createElement('span'); s.textContent = c.hex;
    const sm = document.createElement('small'); sm.textContent = Math.round(c.share * 100) + '% of frame';
    s.appendChild(sm);
    b.append(i, s);
    b.addEventListener('click', () => copyText(c.hex));
    wrap.appendChild(b);
  });
}

function renderLab() {
  renderSlots();
  renderMetrics();
  renderLenses();
  renderPalette();
  renderPhone();
  renderBench();
}

function selectSlot(key) {
  if (labState.active === key) return;
  labState.active = key;
  $('#lab-critique').textContent = '';
  renderLab();
}

function setSlotFrame(key, frame, name, sub) {
  const s = labState.slots[key];
  s.frame = frame;
  if (name) s.name = name;
  if (sub) s.sub = sub;
  s.m = analyzeFrame(frame);
  s.pal = extractPalette(frame);
}

async function loadIntoSlot(key, file) {
  if (!/^(image|video)\//.test(file.type)) { toast('Load an image or a video file.'); return; }
  try {
    const frame = await frameFromFile(file);
    setSlotFrame(key, frame, file.name.replace(/\.[^.]+$/, ''), file.type.startsWith('video/') ? 'Video · first frame' : 'Your upload');
    labState.active = key;
    $('#lab-critique').textContent = '';
    renderLab();
    toast(`Loaded into version ${key.toUpperCase()}`);
  } catch (e) {
    toast(e.message || 'That file couldn’t be read.');
  }
}

/* ---------------------------------------------------------------- half-second test */
let testing = false;
function runTest() {
  if (testing) return;
  testing = true;
  $('#lab-veil').hidden = true;
  const hold = labState.hold;
  if (REDUCED) {
    feedY(2);
    setTimeout(() => { feedY(3); setTimeout(endTest, 250); }, hold);
    return;
  }
  const start = performance.now();
  const swipe = 260, lead = 380;
  const step = () => {
    const t = performance.now() - start;
    let pos;
    if (t < lead) pos = 1;
    else if (t < lead + swipe) pos = 1 + easeInOut((t - lead) / swipe);
    else if (t < lead + swipe + hold) pos = 2;
    else if (t < lead + 2 * swipe + hold) pos = 2 + easeInOut((t - lead - swipe - hold) / swipe);
    else pos = 3;
    feedY(pos);
    if (t > lead + 2 * swipe + hold + 280) { endTest(); return; }
    requestAnimationFrame(step);
  };
  feedY(1);
  requestAnimationFrame(step);
}
function endTest() {
  testing = false;
  const s = labState.hold / 1000;
  $('#lab-veil-p').textContent = `That was ${s} s on screen. Could you name the product, and what they wanted you to do?`;
  $('#lab-veil').hidden = false;
  $('#lab-replay').focus();
}

/* ---------------------------------------------------------------- Claude critique */
let critiqueAbort = null;
async function askCritique() {
  const sample = await CAPS.sample;
  if (!sample) return;
  const key = labState.active;
  const slot = labState.slots[key];
  if (!slot.frame || !slot.m) return;
  const out = $('#lab-critique');
  const ask = $('#lab-ask');
  const stop = $('#lab-stop');
  const blob = await new Promise((r) => slot.frame.toBlob(r, 'image/jpeg', 0.86));
  if (!blob) { toast('Couldn’t prepare the frame.'); return; }
  const m = slot.m;
  const pct = (k) => Math.round(m.s[k] * 100);
  const prompt = [
    'You are a creative director reviewing the first frame of a vertical 9:16 short-form video ad. The attached image is that first frame, the one a scrolling viewer sees for about half a second.',
    `Measurements the page took from the pixels (heuristics, 0-100): overall ${m.score}, contrast ${pct('contrast')}, colour pop ${pct('pop')}, one clear place to look ${pct('focus')}, busyness balance ${pct('calm')}, detail clear of the app's UI overlays ${pct('safe')}.`,
    'Reply in plain text with no markdown, headings or bullet symbols, under 130 words.',
    'First line: a one-sentence verdict on whether this frame stops a thumb in half a second, and why.',
    'Then exactly three lines, each starting with "Fix:", each one concrete change to this frame (what to move, cut, enlarge, recolour or rewrite), most important first.',
  ].join('\n');
  if (critiqueAbort) critiqueAbort.abort();
  critiqueAbort = new AbortController();
  out.textContent = 'Claude is looking…';
  ask.disabled = true;
  stop.hidden = false;
  try {
    await sample(prompt, { images: [blob], signal: critiqueAbort.signal, onText: ({ text }) => { out.textContent = text; } });
  } catch (e) {
    const code = e && e.code;
    if (code === 'refused') out.textContent = '';
    else if (e && e.text) out.textContent = e.text;
    else out.textContent = '';
    if (CLAUDE_GONE.has(code) || code === 'images_unavailable') $('#lab-claude').hidden = true;
    const msg = claudeErrorText(e);
    if (msg) $('#lab-ask-d').textContent = msg;
  } finally {
    ask.disabled = false;
    stop.hidden = true;
  }
}

/* ---------------------------------------------------------------- palette hand-off */
function paletteToType() {
  const pal = labState.slots[labState.active].pal;
  if (!pal || !pal.length) return;
  const bg = pal[0];
  const rest = pal.slice(1);
  const fg = rest.slice().sort((a, b) => contrastRatio(b.rgb, bg.rgb) - contrastRatio(a.rgb, bg.rgb))[0] || bg;
  const pool = rest.filter((c) => c !== fg).sort((a, b) => saturation(b.rgb) - saturation(a.rgb));
  const accent = pool[0] && saturation(pool[0].rgb) > 0.35 ? pool[0] : { hex: typeState.accent };
  let fgHex = fg.hex;
  if (contrastRatio(hexToRgb(fgHex), bg.rgb) < 4.5) fgHex = relLum(bg.rgb) > 0.4 ? '#0E0D0C' : '#F0E9DD';
  typeSetPalette({ bg: bg.hex, fg: fgHex, accent: accent.hex });
  toast('Palette sent to Type Studio');
}

function labBench() {
  const A = labState.slots.a, B = labState.slots.b;
  if (!A.m || !B.m) return { value: '–', detail: 'Load a creative to score it' };
  return { value: `B ${B.m.score} · A ${A.m.score}`, detail: `${B.name} vs ${A.name}` };
}

async function initLab() {
  buildFeed();
  renderZones($('#lab-zones'));
  $$('#lab-hold button').forEach((b) => {
    b.setAttribute('aria-pressed', String(Number(b.dataset.v) === labState.hold));
    b.addEventListener('click', () => {
      labState.hold = Number(b.dataset.v);
      $$('#lab-hold button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    });
  });
  $('#lab-test').addEventListener('click', runTest);
  $('#lab-replay').addEventListener('click', runTest);
  $('#lab-look').addEventListener('click', () => { $('#lab-veil').hidden = true; feedY(2); });
  $('#lab-ui-t').addEventListener('change', (e) => { $('#lab-ui').hidden = !e.target.checked; });
  $('#lab-zones-t').addEventListener('change', (e) => { $('#lab-zones').hidden = !e.target.checked; });
  $('#lab-file').addEventListener('change', (e) => {
    const f = e.target.files && e.target.files[0];
    if (f) loadIntoSlot(labFileTarget, f);
    e.target.value = '';
  });
  $('#lab-to-type').addEventListener('click', paletteToType);
  $('#lab-ask').addEventListener('click', askCritique);
  $('#lab-stop').addEventListener('click', () => { if (critiqueAbort) critiqueAbort.abort(); });
  if (window.ResizeObserver) new ResizeObserver(() => { if (!testing) feedY(2); }).observe($('#lab-viewport'));

  CAPS.sample.then(async (s) => {
    if (!s) return;
    const lim = await s.limits().catch(() => null);
    if (lim && lim.images) $('#lab-claude').hidden = false;
  });

  routeHooks['scroll-stop'] = { enter() { renderPhone(); feedY(2); }, leave() { $('#lab-veil').hidden = true; } };

  try {
    const [a, b] = await Promise.all([loadImage(SAMPLES.usual), loadImage(SAMPLES.halfsecond)]);
    setSlotFrame('a', frameFrom(a, a.naturalWidth, a.naturalHeight));
    setSlotFrame('b', frameFrom(b, b.naturalWidth, b.naturalHeight));
  } catch (e) {
    toast('The sample frames didn’t load. Load your own creative instead.');
  }
  renderLab();
}
