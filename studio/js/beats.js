'use strict';
/* Beat Grid: tempo, frame rate, a shot list measured in beats, frame-exact cut points,
   a click-track transport with a live cue sheet, and Markdown/CSV export. */

const REEL01_SHOTS = [
  { name: 'Stopwatch card · 0.5s', beats: 2, note: 'Black card, four clock ticks' },
  { name: 'The usual ad in the feed', beats: 6, note: 'Flick past, drain to grey, orange ✕' },
  { name: 'Hook · glass macro', beats: 1, note: 'They’ll ask what you’re wearing.' },
  { name: 'Cap macro', beats: 1, note: '' },
  { name: 'Label macro', beats: 1, note: '' },
  { name: 'Whip turn', beats: 1, note: '' },
  { name: 'Three-panel split', beats: 2, note: '' },
  { name: 'Bottle drop', beats: 1, note: '' },
  { name: 'Light sweep · scent notes', beats: 2, note: 'Bergamot / amber' },
  { name: 'Hero turntable', beats: 3, note: 'Brand-orange wall, black gloss floor' },
  { name: 'Offer · shop the drop', beats: 4, note: '20% off, this week only' },
  { name: 'End card', beats: 6, note: 'Your brand next? DM us.' },
];

const beatState = Object.assign(
  { bpm: 120, fps: 30, target: 15, shots: REEL01_SHOTS.map((s) => Object.assign({}, s)) },
  store.get('beat', {}),
);

const spb = () => 60 / beatState.bpm;
const fpb = () => beatState.fps * spb();
const totalBeats = () => beatState.shots.reduce((a, s) => a + (Number(s.beats) || 0), 0);
const isWhole = (x) => Math.abs(x - Math.round(x)) < 1e-6;

function fmtS(s) { return (Math.round(s * 100) / 100).toFixed(2); }
function timecode(t) {
  const fps = beatState.fps;
  const totalFrames = Math.floor(t * fps + 1e-6);
  const sec = Math.floor(totalFrames / fps);
  const fr = totalFrames % fps;
  return `${String(sec).padStart(2, '0')}:${String(fr).padStart(2, '0')}`;
}

function saveBeat() { store.set('beat', beatState); }

/* Shot timing: start/end in beats, seconds and frames. */
function shotTimes() {
  let b = 0;
  const f = fpb();
  return beatState.shots.map((s) => {
    const beats = Number(s.beats) || 0;
    const start = b, end = b + beats;
    b = end;
    const fs = start * f, fe = end * f;
    return { start, end, t0: start * spb(), t1: end * spb(), f0: Math.round(fs), f1: Math.round(fe) - 1, exact: isWhole(fs) && isWhole(fe) };
  });
}

/* Tempos near the current one where a beat is a whole number of frames. */
function wholeFrameTempos() {
  const fps = beatState.fps;
  const out = [];
  for (let n = 6; n <= 60; n++) {
    const bpm = (60 * fps) / n;
    if (bpm >= 60 && bpm <= 200) out.push({ bpm: Math.round(bpm * 100) / 100, n });
  }
  out.sort((a, b) => Math.abs(a.bpm - beatState.bpm) - Math.abs(b.bpm - beatState.bpm));
  return out.slice(0, 6).sort((a, b) => a.bpm - b.bpm);
}

/* ---------------------------------------------------------------- render */
function renderStats() {
  const f = fpb();
  const tb = totalBeats();
  const len = tb * spb();
  const diff = len - beatState.target;
  const tiles = [
    { label: 'One beat', big: fmtS(spb()), unit: 's', note: `${isWhole(f) ? f : '≈ ' + f.toFixed(2)} frames at ${beatState.fps} fps`, flag: !isWhole(f) },
    { label: 'One bar (4 beats)', big: fmtS(spb() * 4), unit: 's', note: `${isWhole(f * 4) ? f * 4 : '≈ ' + (f * 4).toFixed(1)} frames` },
    { label: 'Frames per beat', big: isWhole(f) ? String(f) : f.toFixed(2), unit: '', note: isWhole(f) ? 'Every beat lands exactly on a frame.' : 'Beats fall between frames, so cuts drift up to a frame. Try a tempo below.', flag: !isWhole(f) },
    { label: 'Cut length', big: fmtS(len), unit: 's', note: Math.abs(diff) < 0.01 ? `${tb} beats, exactly on target.` : `${tb} beats, ${Math.abs(diff).toFixed(2)} s ${diff > 0 ? 'over' : 'under'} the ${beatState.target} s target.`, flag: Math.abs(diff) >= 0.01 },
  ];
  const wrap = $('#bt-stats');
  wrap.textContent = '';
  for (const t of tiles) {
    const d = document.createElement('div');
    d.className = 'stat' + (t.flag ? ' flag' : '');
    const l = document.createElement('span'); l.className = 'label'; l.textContent = t.label;
    const b = document.createElement('b'); b.textContent = t.big;
    if (t.unit) { const sm = document.createElement('small'); sm.textContent = t.unit; b.appendChild(sm); }
    const p = document.createElement('p'); p.textContent = t.note;
    d.append(l, b, p);
    wrap.appendChild(d);
  }
  const chips = $('#bt-chips');
  chips.textContent = '';
  for (const c of wholeFrameTempos()) {
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'chip' + (Math.abs(c.bpm - beatState.bpm) < 0.01 ? ' on' : '');
    b.textContent = `${c.bpm} · ${c.n}f`;
    b.title = `${c.bpm} BPM = ${c.n} frames a beat`;
    b.addEventListener('click', () => setBpm(c.bpm));
    chips.appendChild(b);
  }
  $('#bt-total').textContent = `${beatState.shots.length} shots · ${tb} beats · ${fmtS(len)} s`;
}

function renderNotes() {
  const rows = [['Sixteenth', 0.25], ['Eighth', 0.5], ['Quarter (one beat)', 1], ['Half', 2], ['Bar', 4], ['Two bars', 8]];
  const tb = $('#bt-notes');
  tb.textContent = '';
  for (const [name, beats] of rows) {
    const tr = document.createElement('tr');
    const fr = beats * fpb();
    const cells = [name, String(beats), fmtS(beats * spb()) + ' s', isWhole(fr) ? String(fr) : '≈ ' + fr.toFixed(2)];
    cells.forEach((c, i) => {
      const td = document.createElement('td');
      td.textContent = c;
      if (i > 0) td.className = 'm' + (i === 3 && !isWhole(fr) ? ' off' : '');
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  }
}

let tlPx = 32; // pixels per beat
function renderTimeline() {
  const tl = $('#bt-tl');
  const scroll = $('#bt-tl-scroll');
  const tb = Math.max(totalBeats(), beatState.target / spb());
  const span = Math.ceil(tb + 1);
  tlPx = Math.max(26, (scroll.clientWidth - 2) / span);
  const width = Math.round(span * tlPx);
  tl.style.width = width + 'px';
  tl.textContent = '';

  const grid = document.createElement('div');
  grid.className = 'tl-grid';
  grid.style.backgroundImage = `repeating-linear-gradient(to right, var(--line-2) 0 1px, transparent 1px ${tlPx * 4}px), repeating-linear-gradient(to right, var(--line) 0 1px, transparent 1px ${tlPx}px)`;
  tl.appendChild(grid);

  const bars = document.createElement('div'); bars.className = 'tl-bars';
  for (let b = 0; b < span; b += 4) {
    const s = document.createElement('span'); s.style.left = b * tlPx + 'px'; s.textContent = 'Bar ' + (b / 4 + 1);
    bars.appendChild(s);
  }
  tl.appendChild(bars);

  const secs = document.createElement('div'); secs.className = 'tl-secs';
  const totalSec = span * spb();
  const stepSec = totalSec > 40 ? 5 : totalSec > 20 ? 2 : 1;
  for (let s = 0; s <= totalSec; s += stepSec) {
    const e = document.createElement('span'); e.style.left = (s / spb()) * tlPx + 'px'; e.textContent = s + 's';
    secs.appendChild(e);
  }
  tl.appendChild(secs);

  const target = document.createElement('div'); target.className = 'tl-target';
  target.style.left = (beatState.target / spb()) * tlPx + 'px';
  const tspan = document.createElement('span'); tspan.textContent = 'Target ' + beatState.target + 's';
  target.appendChild(tspan);
  tl.appendChild(target);

  const shots = document.createElement('div'); shots.className = 'tl-shots';
  const times = shotTimes();
  beatState.shots.forEach((s, i) => {
    const t = times[i];
    if (t.end <= t.start) return;
    const b = document.createElement('button');
    b.type = 'button';
    b.className = 'tl-shot';
    b.dataset.i = i;
    b.style.left = t.start * tlPx + 1 + 'px';
    b.style.width = Math.max(4, (t.end - t.start) * tlPx - 2) + 'px';
    const nm = document.createElement('span'); nm.textContent = s.name || 'Shot ' + (i + 1);
    const em = document.createElement('em'); em.textContent = `${Number(s.beats)}b · f${t.f0}`;
    b.append(nm, em);
    b.title = `${s.name}: ${fmtS(t.t0)}–${fmtS(t.t1)} s, frames ${t.f0}–${t.f1}`;
    b.addEventListener('click', () => {
      const input = $(`#bt-rows tr[data-i="${i}"] input`);
      if (input) { input.focus(); input.select(); }
    });
    shots.appendChild(b);
  });
  tl.appendChild(shots);

  const head = document.createElement('div'); head.className = 'tl-head'; head.id = 'bt-head';
  tl.appendChild(head);
}

function renderRows() {
  const tbody = $('#bt-rows');
  tbody.textContent = '';
  const times = shotTimes();
  beatState.shots.forEach((s, i) => {
    const t = times[i];
    const tr = document.createElement('tr');
    tr.dataset.i = i;
    const td = (cls) => { const d = document.createElement('td'); if (cls) d.className = cls; tr.appendChild(d); return d; };
    td('idx').textContent = String(i + 1).padStart(2, '0');
    const name = document.createElement('input');
    name.type = 'text'; name.value = s.name; name.id = 'bt-name-' + i; name.setAttribute('aria-label', `Shot ${i + 1} name`);
    name.addEventListener('input', () => { s.name = name.value; saveBeat(); renderTimeline(); });
    td().appendChild(name);
    const beats = document.createElement('input');
    beats.type = 'number'; beats.min = '0.25'; beats.step = '0.25'; beats.value = s.beats; beats.id = 'bt-beats-' + i; beats.setAttribute('aria-label', `Shot ${i + 1} length in beats`);
    beats.addEventListener('input', () => {
      const v = parseFloat(beats.value);
      if (!(v > 0)) return;
      s.beats = v; saveBeat(); refreshTimes(); renderTimeline(); renderStats(); transportBeat.restart();
    });
    td().appendChild(beats);
    td('t').textContent = `${fmtS(t.t0)}–${fmtS(t.t1)} s`;
    const fr = td('t' + (t.exact ? '' : ' off'));
    fr.textContent = `${t.exact ? '' : '≈ '}${t.f0}–${t.f1}`;
    if (!t.exact) fr.title = 'This cut falls between frames at this tempo.';
    const note = document.createElement('input');
    note.type = 'text'; note.value = s.note || ''; note.id = 'bt-note-' + i; note.setAttribute('aria-label', `Shot ${i + 1} note`);
    note.addEventListener('input', () => { s.note = note.value; saveBeat(); });
    td().appendChild(note);
    const acts = document.createElement('div'); acts.className = 'acts';
    const ib = (label, title, fn) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'icon-btn'; b.textContent = label; b.title = title; b.setAttribute('aria-label', title); b.addEventListener('click', fn); return b; };
    acts.append(
      ib('↑', `Move shot ${i + 1} up`, () => moveShot(i, -1)),
      ib('↓', `Move shot ${i + 1} down`, () => moveShot(i, 1)),
      ib('×', `Remove shot ${i + 1}`, () => { beatState.shots.splice(i, 1); beatChanged(true); }),
    );
    td().appendChild(acts);
    tbody.appendChild(tr);
  });
}

/* Update only the time and frame cells, so typing in a row keeps focus. */
function refreshTimes() {
  const times = shotTimes();
  $$('#bt-rows tr').forEach((tr, i) => {
    const t = times[i];
    if (!t) return;
    const cells = tr.querySelectorAll('td.t');
    cells[0].textContent = `${fmtS(t.t0)}–${fmtS(t.t1)} s`;
    cells[1].textContent = `${t.exact ? '' : '≈ '}${t.f0}–${t.f1}`;
    cells[1].className = 't' + (t.exact ? '' : ' off');
  });
}

function moveShot(i, d) {
  const j = i + d;
  if (j < 0 || j >= beatState.shots.length) return;
  const [s] = beatState.shots.splice(i, 1);
  beatState.shots.splice(j, 0, s);
  beatChanged(true);
}

function beatChanged(rows) {
  saveBeat();
  renderStats();
  renderNotes();
  renderTimeline();
  if (rows) renderRows(); else refreshTimes();
  transportBeat.restart();
  typeOnTempo();
  renderBench();
}

function setBpm(v) {
  const n = clamp(Math.round(Number(v) * 100) / 100, 40, 240);
  if (!isFinite(n)) return;
  beatState.bpm = n;
  $('#bt-bpm').value = n;
  beatChanged(false);
}

/* ---------------------------------------------------------------- cue sheet + transport */
let lastCueShot = -2;
function cueAt(t) {
  const times = shotTimes();
  const beatPos = t / spb();
  let idx = times.findIndex((x) => beatPos >= x.start - 1e-9 && beatPos < x.end - 1e-9);
  if (idx === -1 && times.length) idx = times.length - 1;
  const shot = beatState.shots[idx];
  $('#bt-tc').textContent = timecode(t);
  const beatIdx = Math.floor(beatPos + 1e-6);
  $('#bt-barbeat').textContent = `Bar ${Math.floor(beatIdx / 4) + 1} · Beat ${(beatIdx % 4) + 1}`;
  $$('#bt-dots i').forEach((d, i) => { d.classList.toggle('on', i === beatIdx % 4); d.classList.toggle('down', i === 0); });
  const head = $('#bt-head');
  if (head) head.style.left = beatPos * tlPx + 'px';
  if (idx !== lastCueShot) {
    lastCueShot = idx;
    $('#bt-now').textContent = shot ? shot.name : '–';
    const next = beatState.shots[idx + 1];
    $('#bt-next').textContent = next ? `Next: ${next.name} at frame ${times[idx + 1].f0}` : 'Last shot. Loops to the top.';
    $$('.tl-shot').forEach((b) => b.classList.toggle('now', Number(b.dataset.i) === idx));
    $$('#bt-rows tr').forEach((tr) => tr.classList.toggle('now', Number(tr.dataset.i) === idx));
    if (transportBeat.playing) {
      const btn = $(`.tl-shot[data-i="${idx}"]`);
      const sc = $('#bt-tl-scroll');
      if (btn && sc && (btn.offsetLeft < sc.scrollLeft || btn.offsetLeft + btn.offsetWidth > sc.scrollLeft + sc.clientWidth)) {
        sc.scrollTo({ left: Math.max(0, btn.offsetLeft - 40), behavior: REDUCED ? 'auto' : 'smooth' });
      }
    }
  }
}

const transportBeat = new Transport({
  spb,
  loopBeats: () => Math.max(1, Math.ceil(totalBeats())),
  onBeat(ac, when, k) { SFX.click(ac, when, k % 4 === 0); },
  onFrame: cueAt,
  onStop() { setPlayLabel(false); },
});

function setPlayLabel(on) {
  const b = $('#bt-play');
  b.querySelector('span').textContent = on ? 'Stop' : 'Play with click';
  b.querySelector('path').setAttribute('d', on ? 'M3.5 3h9v10h-9z' : 'M4 2.5v11l9-5.5z');
}

/* ---------------------------------------------------------------- tap tempo */
let taps = [];
function tap() {
  const now = performance.now();
  if (taps.length && now - taps[taps.length - 1] > 2000) taps = [];
  taps.push(now);
  if (taps.length > 9) taps.shift();
  const b = $('#bt-tap');
  b.classList.add('hit');
  setTimeout(() => b.classList.remove('hit'), 90);
  if (taps.length >= 2) {
    const iv = [];
    for (let i = 1; i < taps.length; i++) iv.push(taps[i] - taps[i - 1]);
    const avg = iv.reduce((a, x) => a + x, 0) / iv.length;
    setBpm(Math.round((60000 / avg) * 2) / 2);
    $('#bt-tap-n').textContent = `· ${taps.length} taps`;
  } else {
    $('#bt-tap-n').textContent = '· keep tapping';
  }
}

/* ---------------------------------------------------------------- export */
function shotTable() {
  const times = shotTimes();
  return beatState.shots.map((s, i) => {
    const t = times[i];
    return { n: i + 1, shot: s.name, beats: Number(s.beats), time: `${fmtS(t.t0)}–${fmtS(t.t1)} s`, frames: `${t.f0}–${t.f1}`, note: s.note || '' };
  });
}
function exportMarkdown() {
  const rows = shotTable();
  const esc = (v) => String(v).replace(/\|/g, '\\|');
  const head = `Cut list · ${beatState.bpm} BPM · ${beatState.fps} fps · 1 beat = ${fmtS(spb())} s = ${isWhole(fpb()) ? fpb() : fpb().toFixed(2)} frames\n\n`;
  const md = ['| # | Time | Frames | Beats | Shot | Note |', '|---|---|---|---|---|---|']
    .concat(rows.map((r) => `| ${r.n} | ${r.time} | ${r.frames} | ${r.beats} | ${esc(r.shot)} | ${esc(r.note)} |`))
    .join('\n');
  copyText(head + md);
}
function exportCsv() {
  const rows = shotTable();
  const q = (v) => `"${String(v).replace(/"/g, '""')}"`;
  const csv = ['#,Start (s),End (s),First frame,Last frame,Beats,Shot,Note']
    .concat(rows.map((r) => {
      const [a, b] = r.time.replace(' s', '').split('–');
      const [fa, fb] = r.frames.split('–');
      return [r.n, a, b, fa, fb, r.beats, q(r.shot), q(r.note)].join(',');
    }))
    .join('\n');
  saveFile(`cut-list-${beatState.bpm}bpm-${beatState.fps}fps.csv`, new Blob([csv], { type: 'text/csv' }));
}

function beatBench() {
  const f = fpb();
  return { value: `${beatState.bpm} BPM`, detail: `${isWhole(f) ? f : f.toFixed(2)} frames a beat at ${beatState.fps} fps · ${beatState.shots.length} shots, ${fmtS(totalBeats() * spb())} s` };
}

function initBeats() {
  $('#bt-bpm').value = beatState.bpm;
  $('#bt-fps').value = String(beatState.fps);
  $('#bt-target').value = beatState.target;
  $('#bt-bpm').addEventListener('change', () => setBpm($('#bt-bpm').value));
  $('#bt-minus').addEventListener('click', () => setBpm(Math.round(beatState.bpm) - 1));
  $('#bt-plus').addEventListener('click', () => setBpm(Math.round(beatState.bpm) + 1));
  $('#bt-fps').addEventListener('change', () => { beatState.fps = Number($('#bt-fps').value); beatChanged(true); });
  $('#bt-target').addEventListener('change', () => { const v = parseFloat($('#bt-target').value); if (v > 0) { beatState.target = v; beatChanged(false); } });
  $('#bt-tap').addEventListener('pointerdown', (e) => { e.preventDefault(); tap(); });
  $('#bt-tap').addEventListener('keydown', (e) => { if (e.key === ' ' || e.key === 'Enter') { e.preventDefault(); tap(); } });
  document.addEventListener('keydown', (e) => {
    if (currentRoute !== 'beats' || e.repeat) return;
    const tag = (e.target && e.target.tagName) || '';
    if (/INPUT|TEXTAREA|SELECT|BUTTON/.test(tag)) return;
    if (e.key === 't' || e.key === 'T') tap();
  });
  $('#bt-play').addEventListener('click', () => {
    if (transportBeat.playing) transportBeat.stop();
    else { transportBeat.play(0); setPlayLabel(true); }
  });
  $('#bt-add').addEventListener('click', () => {
    beatState.shots.push({ name: 'New shot', beats: 1, note: '' });
    beatChanged(true);
    const inp = $(`#bt-name-${beatState.shots.length - 1}`);
    if (inp) { inp.focus(); inp.select(); }
  });
  $('#bt-reset').addEventListener('click', () => {
    Object.assign(beatState, { bpm: 120, fps: 30, target: 15, shots: REEL01_SHOTS.map((s) => Object.assign({}, s)) });
    $('#bt-bpm').value = 120; $('#bt-fps').value = '30'; $('#bt-target').value = 15;
    beatChanged(true);
    toast('Loaded the Reel 01 cut list');
  });
  $('#bt-md').addEventListener('click', exportMarkdown);
  $('#bt-csv').addEventListener('click', exportCsv);
  if (window.ResizeObserver) new ResizeObserver(() => { if (currentRoute === 'beats') { renderTimeline(); lastCueShot = -2; cueAt(0); } }).observe($('#bt-tl-scroll'));

  renderStats();
  renderNotes();
  renderRows();
  routeHooks.beats = {
    enter() { renderTimeline(); lastCueShot = -2; cueAt(0); },
    leave() { transportBeat.stop(); },
  };
}
