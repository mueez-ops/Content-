'use strict';
/* Studio home (the half-second dial and the live bench) and app start-up. */

const DIAL_R = 150;
const DIAL_C = 2 * Math.PI * DIAL_R;

function buildDial() {
  const g = $('#dial-ticks');
  const ns = 'http://www.w3.org/2000/svg';
  for (let i = 0; i < 60; i++) {
    const major = i % 5 === 0;
    const a = (i / 60) * Math.PI * 2 - Math.PI / 2;
    const r1 = major ? 166 : 170, r2 = 180;
    const l = document.createElementNS(ns, 'line');
    l.setAttribute('x1', 200 + Math.cos(a) * r1);
    l.setAttribute('y1', 200 + Math.sin(a) * r1);
    l.setAttribute('x2', 200 + Math.cos(a) * r2);
    l.setAttribute('y2', 200 + Math.sin(a) * r2);
    l.setAttribute('stroke-width', major ? 2.4 : 1.2);
    l.setAttribute('class', 'tick' + (major ? ' major' : ''));
    g.appendChild(l);
  }
  const arc = $('#dial-arc');
  arc.setAttribute('stroke-dasharray', `${DIAL_C} ${DIAL_C}`);
  setDial(0.5);
}

/* The dial is a one-second face, so half a second fills half of it: the halfsecond mark. */
function setDial(sec) {
  $('#dial-arc').setAttribute('stroke-dashoffset', String(DIAL_C * (1 - clamp(sec))));
  $('#dial-num').textContent = sec.toFixed(3);
}

let dialRaf = 0;
function runDial() {
  cancelAnimationFrame(dialRaf);
  const fig = $('#dial');
  const cap = $('#dial-cap');
  if (REDUCED) { setDial(0.5); return; }
  const cycle = 3200; // 0.5 s count, then a hold
  let start = performance.now() + 900; // open on the resting 0.500 state
  const step = (now) => {
    if (currentRoute !== 'studio') return;
    const t = now - start;
    if (t < 0) { dialRaf = requestAnimationFrame(step); return; }
    const p = t % cycle;
    if (p < 500) {
      fig.classList.remove('gone');
      setDial(p / 1000);
      cap.textContent = 'On screen';
    } else if (p < 2600) {
      setDial(0.5);
      if (p > 900) { fig.classList.add('gone'); cap.textContent = 'Gone'; }
    } else {
      fig.classList.remove('gone');
      setDial(0.5 * (1 - easeInOut((p - 2600) / 600)));
      cap.textContent = 'Again';
    }
    dialRaf = requestAnimationFrame(step);
  };
  dialRaf = requestAnimationFrame(step);
}

function renderBench() {
  const parts = { hook: window.hookBench, beat: window.beatBench, type: window.typeBench, lab: window.labBench };
  for (const [k, fn] of Object.entries(parts)) {
    if (typeof fn !== 'function') continue;
    let info;
    try { info = fn(); } catch (e) { continue; }
    const v = $(`[data-bench="${k}"]`);
    const d = $(`[data-bench="${k}-d"]`);
    if (v) v.textContent = info.value;
    if (d) d.textContent = info.detail;
  }
}

function boot() {
  buildDial();
  initHooks();
  initBeats();
  initType();
  initLab();
  routeHooks.studio = {
    enter() { renderBench(); runDial(); },
    leave() { cancelAnimationFrame(dialRaf); $('#dial').classList.remove('gone'); setDial(0.5); $('#dial-cap').textContent = 'The whole window'; },
  };
  window.addEventListener('hashchange', route);
  route();
}

boot();
