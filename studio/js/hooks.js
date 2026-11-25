'use strict';
/* Hook Lab: a brief-driven hook generator, a live hook meter, a caption check,
   and (inside claude.ai) hooks written by Claude. */

const HOOK_BRIEF_DEFAULT = {
  product: 'VELOUR N°05',
  category: 'perfume',
  audience: 'people who hate smelling basic',
  pain: 'smelling like everyone else',
  payoff: 'they’ll ask what you’re wearing',
  proof: '3 sprays',
  tone: 'Confident and premium',
};

const HOOK_TEMPLATES = [
  ['Outcome', '{Payoff}.'],
  ['Outcome', '{Proof} and {payoff}.'],
  ['Outcome', '{Proof}. That’s all it takes.'],
  ['Pattern break', 'Stop {pain}.'],
  ['Pattern break', 'Put the old {category} down.'],
  ['Pattern break', 'Don’t buy {category} until you see this.'],
  ['Callout', 'For {audience} only.'],
  ['Callout', 'Calling all {audience}.'],
  ['Callout', 'If you’re done {pain}, stay.'],
  ['Curiosity', 'Nobody tells you why you’re {pain}.'],
  ['Curiosity', 'This is why {payoff}.'],
  ['Curiosity', 'The {category} nobody is talking about.'],
  ['POV', 'POV: {payoff}.'],
  ['POV', 'POV: you stopped {pain}.'],
  ['Contrarian', '{Pain} is a choice.'],
  ['Contrarian', 'Your {category} is the problem.'],
  ['Contrarian', 'More {category} won’t fix {pain}.'],
  ['Question', 'Still {pain}?'],
  ['Question', 'Why are you still {pain}?'],
  ['Number', '{Proof}. {Product}.'],
  ['Number', '3 reasons you’re {pain}.'],
  ['Confession', 'I was {pain} for years.'],
  ['Confession', 'I almost didn’t post this.'],
  ['Before / after', 'Before: {pain}. After: {payoff}.'],
  ['Challenge', 'Try {proof}. Then tell me I’m wrong.'],
  ['Product first', 'Meet {product}.'],
  ['Product first', '{Product}, in half a second.'],
  ['Warning', 'Don’t scroll if you like {pain}.'],
];

const WORDS_PER_SECOND = 4; // ≈ 240 words a minute, a typical adult silent-reading pace
const HOOK_FILLER = ['hey guys', 'hi guys', 'hey everyone', 'hi everyone', 'in this video', 'welcome back', 'today i', 'so today', 'let me show', 'check out', 'don’t forget to', "don't forget to", 'make sure to', 'link in bio'];
const HOOK_FRONT = new Set(['stop', 'wait', 'never', 'nobody', 'no', 'don’t', "don't", 'dont', 'why', 'how', 'secret', 'mistake', 'pov', 'pov:', 'this', 'still', 'before', 'truth', 'wrong', 'only', 'you', 'your', 'you’re', "you're", 'meet', 'try', 'what', 'they’ll', "they'll", 'calling', 'if', 'for', 'i', 'put', 'more', 'the', 'warning']);
const HOOK_TENSION = new Set(['not', 'never', 'nobody', 'no', 'stop', 'don’t', "don't", 'won’t', "won't", 'can’t', "can't", 'but', 'actually', 'instead', 'why', 'secret', 'mistake', 'wrong', 'problem', 'still', 'almost', 'until', 'only', 'truth', 'choice', 'before', 'after', 'what']);
const HOOK_DIRECT = new Set(['you', 'your', 'you’re', "you're", 'youre', 'yours', 'you’ll', "you'll", 'pov', 'pov:']);
const NUMBER_WORDS = new Set(['one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine', 'ten', 'twelve', 'half', 'first', 'zero']);

function hookWords(text) {
  return text.trim().split(/\s+/).filter(Boolean);
}
function normWord(w) {
  return w.toLowerCase().replace(/[^\p{L}\p{N}'’:%]/gu, '');
}

/* Heuristic score for a single on-screen hook line. Returns {score, verdict, tone, checks[]}. */
function scoreHook(text) {
  const clean = (text || '').trim();
  const words = hookWords(clean);
  const n = words.length;
  const lw = words.map(normWord);
  const lower = clean.toLowerCase();
  const checks = [];
  if (!n) return { score: 0, verdict: 'Empty', tone: 'bad', checks: [] };

  const len = n <= 7 ? 1 : n <= 10 ? 0.7 : n <= 14 ? 0.4 : 0.15;
  checks.push({
    state: n <= 7 ? 'ok' : n <= 10 ? 'warn' : 'bad',
    title: `${n} word${n === 1 ? '' : 's'}`,
    note: n <= 7 ? 'Short enough to take in at a glance.' : `About ${(n / WORDS_PER_SECOND).toFixed(1)} s to read. Aim for 7 words or fewer.`,
  });

  const first2 = lw.slice(0, 2);
  const front = first2.some((w) => HOOK_FRONT.has(w) || /\d/.test(w) || NUMBER_WORDS.has(w)) || /^[A-Z0-9]{2,}/.test(words[0]);
  checks.push({
    state: front ? 'ok' : 'warn',
    title: 'Front-loaded',
    note: front ? `“${words.slice(0, 2).join(' ')}” carries the hook inside half a second.` : `The first two words, “${words.slice(0, 2).join(' ')}”, don’t say much yet. Lead with the strongest word.`,
  });

  const specific = /\d/.test(clean) || lw.some((w) => NUMBER_WORDS.has(w)) || words.slice(1).some((w) => /^[A-Z]/.test(w)) || /[°№]/.test(clean);
  checks.push({
    state: specific ? 'ok' : 'warn',
    title: 'Specific',
    note: specific ? 'Has a number or a name to grab onto.' : 'Add a number, a name or a concrete detail.',
  });

  const tension = /\?/.test(clean) || lw.some((w) => HOOK_TENSION.has(w));
  checks.push({
    state: tension ? 'ok' : 'warn',
    title: 'Tension',
    note: tension ? 'Opens a question the video can answer.' : 'Nothing is at stake yet. Try a question, a “not” or a “why”.',
  });

  const direct = lw.some((w) => HOOK_DIRECT.has(w));
  checks.push({
    state: direct ? 'ok' : 'warn',
    title: 'Talks to the viewer',
    note: direct ? 'Uses “you”, so it reads as personal.' : 'Say “you” so the viewer sees themselves in it.',
  });

  const filler = HOOK_FILLER.find((f) => lower.includes(f));
  const caps = words.filter((w) => /[A-Z]{2,}/.test(w) && w === w.toUpperCase()).length;
  const hype = /!{2,}/.test(clean) || /%\s?off|buy now|sale\b|discount|limited time|free shipping/i.test(clean) || (n > 2 && caps / n > 0.6);
  checks.push({
    state: filler || hype ? 'bad' : 'ok',
    title: filler ? 'Filler opener' : hype ? 'Reads like an ad' : 'No ad-speak',
    note: filler ? `“${filler}” spends the half second on nothing.` : hype ? 'Discounts, caps and “!!” in the first line read as an ad and get skipped. Save the offer for the end.' : 'No discount talk or filler in the opening line.',
  });

  let score = 100 * (0.32 * len + 0.2 * (front ? 1 : 0) + 0.16 * (specific ? 1 : 0) + 0.17 * (tension ? 1 : 0) + 0.15 * (direct ? 1 : 0));
  if (filler) score -= 35;
  if (hype) score -= 25;
  score = Math.round(clamp(score, 0, 100));
  const verdict = score >= 75 ? 'Stops thumbs' : score >= 55 ? 'Gets a glance' : 'Scrolled past';
  const tone = score >= 75 ? 'good' : score >= 55 ? 'warn' : 'bad';
  return { score, verdict, tone, checks };
}

/* ---------------------------------------------------------------- generator */
function cleanField(v) {
  return (v || '').trim().replace(/[.!?]+$/, '');
}
function fillTemplate(tpl, brief) {
  let missing = false;
  const out = tpl.replace(/\{(\w+)\}/g, (m, key) => {
    const v = cleanField(brief[key.toLowerCase()]);
    if (!v) { missing = true; return ''; }
    return key[0] === key[0].toUpperCase() ? v[0].toUpperCase() + v.slice(1) : v;
  });
  if (missing) return null;
  const s = out.replace(/\s+/g, ' ').trim();
  return s[0].toUpperCase() + s.slice(1);
}

const hookState = {
  brief: Object.assign({}, HOOK_BRIEF_DEFAULT, store.get('hook-brief', {})),
  line: store.get('hook-line', 'They’ll ask what you’re wearing.'),
  results: [],
  showing: 12,
  claude: [],
};

function generateHooks() {
  const seen = new Set();
  const out = [];
  for (const [angle, tpl] of HOOK_TEMPLATES) {
    const text = fillTemplate(tpl, hookState.brief);
    if (!text || seen.has(text.toLowerCase())) continue;
    seen.add(text.toLowerCase());
    out.push({ text, angle, src: 'formula', s: scoreHook(text) });
  }
  out.sort((a, b) => b.s.score - a.s.score);
  hookState.results = out;
}

/* ---------------------------------------------------------------- rendering */
function renderMeter() {
  const text = $('#hk-line').value;
  hookState.line = text;
  store.set('hook-line', text);
  const words = hookWords(text);
  const g = $('#hk-glance');
  g.textContent = '';
  words.forEach((w, i) => {
    const t = (i + 1) / WORDS_PER_SECOND;
    const span = document.createElement('span');
    span.className = t <= 0.5 + 1e-9 ? 'w1' : t <= 1.5 + 1e-9 ? 'w2' : 'w3';
    span.textContent = w;
    g.appendChild(span);
    if (i < words.length - 1) g.appendChild(document.createTextNode(' '));
  });
  const s = scoreHook(text);
  $('#hk-score').innerHTML = '';
  $('#hk-score').append(String(s.score));
  const small = document.createElement('small'); small.textContent = '/100';
  $('#hk-score').appendChild(small);
  const v = $('#hk-verdict');
  v.className = 'pill ' + s.tone;
  v.textContent = s.verdict;
  const ul = $('#hk-checks');
  ul.textContent = '';
  for (const c of s.checks) {
    const li = document.createElement('li');
    li.className = c.state;
    const div = document.createElement('div');
    const b = document.createElement('b'); b.textContent = c.title + '. ';
    div.appendChild(b);
    div.appendChild(document.createTextNode(c.note));
    li.appendChild(div);
    ul.appendChild(li);
  }
  renderBench();
}

function hookCard(h) {
  const card = document.createElement('article');
  card.className = 'hook-card' + (h.src === 'claude' ? ' is-claude' : '');
  const p = document.createElement('p'); p.className = 'text'; p.textContent = h.text;
  card.appendChild(p);
  if (h.why) { const w = document.createElement('p'); w.className = 'why'; w.textContent = h.why; card.appendChild(w); }
  const meta = document.createElement('div'); meta.className = 'meta';
  const ang = document.createElement('span'); ang.className = 'angle'; ang.textContent = h.angle || 'Hook';
  const pills = document.createElement('span'); pills.className = 'row';
  if (h.src === 'claude') { const c = document.createElement('span'); c.className = 'pill claude'; c.textContent = 'Claude'; pills.appendChild(c); }
  const sc = document.createElement('span'); sc.className = 'pill ' + h.s.tone; sc.textContent = h.s.score;
  sc.title = h.s.verdict;
  pills.appendChild(sc);
  meta.append(ang, pills);
  const acts = document.createElement('div'); acts.className = 'acts';
  const mk = (label, fn) => { const b = document.createElement('button'); b.type = 'button'; b.className = 'btn sm'; b.textContent = label; b.addEventListener('click', fn); return b; };
  acts.append(
    mk('Test it', () => { $('#hk-line').value = h.text; renderMeter(); $('#hk-line').scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'center' }); }),
    mk('Copy', () => copyText(h.text)),
    mk('To Type Studio', () => { typeSetOpener(h.text); toast('Set as the first card in Type Studio'); }),
  );
  card.append(meta, acts);
  return card;
}

function renderHookCards() {
  const wrap = $('#hk-cards');
  wrap.textContent = '';
  const all = hookState.claude.concat(hookState.results);
  const shown = all.slice(0, hookState.showing + hookState.claude.length);
  shown.forEach((h) => wrap.appendChild(hookCard(h)));
  $('#hk-count').textContent = `${shown.length} of ${all.length}`;
  $('#hk-more').hidden = shown.length >= all.length;
}

function readBrief() {
  const b = {};
  for (const k of ['product', 'category', 'audience', 'pain', 'payoff', 'proof']) b[k] = $('#hk-' + k).value;
  b.tone = $('#hk-tone').value;
  hookState.brief = b;
  store.set('hook-brief', b);
  return b;
}

/* ---------------------------------------------------------------- Claude */
let hookAbort = null;
async function claudeHooks() {
  const sample = await CAPS.sample;
  if (!sample) return;
  const b = readBrief();
  const btn = $('#hk-claude');
  const status = $('#hk-status');
  if (hookAbort) hookAbort.abort();
  hookAbort = new AbortController();
  btn.disabled = true;
  status.textContent = 'Claude is writing…';
  const prompt = [
    'You write hooks for vertical short-form video ads: the line on screen in the very first frame, which a viewer reads in about half a second.',
    '',
    'Brief:',
    `- Product: ${b.product}`,
    `- What it is: ${b.category}`,
    `- For: ${b.audience}`,
    `- Problem it solves: ${b.pain}`,
    `- Payoff: ${b.payoff}`,
    `- Proof or number: ${b.proof}`,
    `- Tone: ${b.tone}`,
    '',
    'Rules: at most 8 words each. The first two words must carry the hook. Talk to the viewer. Be concrete. No discounts, prices, hashtags, emoji or "link in bio". No filler openers like "Hey guys" or "In this video". Use a different angle for each: outcome, pattern break, callout, curiosity, POV, contrarian, question, number, confession, challenge.',
    '',
    'Reply with only a JSON array of 10 objects, like [{"hook":"They\'ll ask what you\'re wearing.","angle":"Outcome","why":"Promises a social payoff in five words."}]. Keep each "why" under 12 words.',
  ].join('\n');
  try {
    const arr = await sample.json(prompt, { signal: hookAbort.signal });
    const list = Array.isArray(arr) ? arr : (arr && Array.isArray(arr.hooks) ? arr.hooks : []);
    const got = list
      .filter((x) => x && typeof x.hook === 'string' && x.hook.trim())
      .slice(0, 12)
      .map((x) => ({ text: x.hook.trim(), angle: typeof x.angle === 'string' ? x.angle : 'Claude', why: typeof x.why === 'string' ? x.why : '', src: 'claude', s: scoreHook(x.hook) }));
    if (!got.length) throw { code: 'invalid_json' };
    hookState.claude = got.concat(hookState.claude).slice(0, 30);
    renderHookCards();
    status.textContent = `Claude wrote ${got.length}. They’re at the top, outlined in orange.`;
  } catch (e) {
    if (e && CLAUDE_GONE.has(e.code)) { btn.hidden = true; status.textContent = 'Claude isn’t available in this view.'; }
    else status.textContent = claudeErrorText(e);
  } finally {
    btn.disabled = false;
  }
}

/* ---------------------------------------------------------------- caption check */
const CAPTION_DEFAULT = 'They’ll ask what you’re wearing.\n\nVELOUR N°05. Bergamot up top, amber underneath, 12 hours on skin. 20% off this week only, then it’s gone.\n\n#perfume #fragrance #scentoftheday';
const CAPTION_PREVIEW_CHARS = 125;
const CAPTION_MAX = 2200;

function renderCaption() {
  const text = $('#cap-text').value;
  store.set('caption', text);
  const lines = text.split('\n');
  const first = lines[0].trim();
  const rest = text.slice(lines[0].length).trim();
  const pv = $('#cap-preview');
  pv.textContent = '';
  const who = document.createElement('span'); who.className = 'who'; who.textContent = 'yourbrand';
  pv.appendChild(who);
  let visible = first;
  let cut = !!rest;
  if (first.length > CAPTION_PREVIEW_CHARS) {
    visible = first.slice(0, CAPTION_PREVIEW_CHARS).replace(/\s+\S*$/, '');
    cut = true;
  }
  pv.appendChild(document.createTextNode(visible || ' '));
  if (cut) { const m = document.createElement('span'); m.className = 'more'; m.textContent = '… more'; pv.appendChild(m); }

  const tags = (text.match(/(^|\s)#[\p{L}\p{N}_]+/gu) || []).length;
  $('#cap-chars').textContent = text.length.toLocaleString();
  $('#cap-chars-d').textContent = `of ${CAPTION_MAX.toLocaleString()} allowed`;
  $('#cap-tags').textContent = tags;
  const fs = scoreHook(first);
  $('#cap-first').textContent = first ? fs.score : '–';

  const notes = [];
  if (!first) notes.push('Start with a line of text. The first line is all most people see.');
  else if (fs.score < 55) notes.push('The first line is weak as a hook. Try one from Hook Lab above.');
  else notes.push('The first line works as a hook, so the preview earns the tap on “more”.');
  if (first.length > CAPTION_PREVIEW_CHARS) notes.push(`The first line is ${first.length} characters, so it gets cut mid-thought. Keep it under ${CAPTION_PREVIEW_CHARS}.`);
  if (tags > 5) notes.push(`${tags} hashtags. Cut to the 3–5 most relevant.`);
  if (tags === 0) notes.push('No hashtags. One to three specific ones help people find it.');
  if (text.length > CAPTION_MAX) notes.push(`Over the limit by ${text.length - CAPTION_MAX} characters.`);
  if (/%\s?off|buy now/i.test(first)) notes.push('The offer is in the first line. Lead with the hook and save the offer for later.');
  const ul = $('#cap-notes');
  ul.textContent = '';
  notes.forEach((n) => { const li = document.createElement('li'); li.textContent = n; ul.appendChild(li); });
}

/* ---------------------------------------------------------------- bench + init */
function hookBench() {
  const s = scoreHook(hookState.line || '');
  return { value: hookState.line ? `“${hookState.line.trim()}”` : '–', detail: hookState.line ? `Scores ${s.score}/100 · ${s.verdict.toLowerCase()}` : 'Write one in Hook Lab' };
}

function initHooks() {
  for (const k of ['product', 'category', 'audience', 'pain', 'payoff', 'proof']) $('#hk-' + k).value = hookState.brief[k] || '';
  $('#hk-tone').value = hookState.brief.tone || HOOK_BRIEF_DEFAULT.tone;
  $('#hk-line').value = hookState.line;
  $('#hk-line').addEventListener('input', renderMeter);
  $('#hk-brief').addEventListener('submit', (e) => {
    e.preventDefault();
    readBrief();
    generateHooks();
    hookState.showing = 12;
    renderHookCards();
    $('#hk-status').textContent = `${hookState.results.length} hooks from ${HOOK_TEMPLATES.length} formulas, sorted by score.`;
  });
  $('#hk-more').addEventListener('click', () => { hookState.showing += 12; renderHookCards(); });
  $('#hk-copy').addEventListener('click', () => copyText($('#hk-line').value.trim()));
  $('#hk-to-type').addEventListener('click', () => { typeSetOpener($('#hk-line').value.trim()); location.hash = 'type'; });
  $('#hk-claude').addEventListener('click', claudeHooks);
  $('#cap-text').value = store.get('caption', CAPTION_DEFAULT);
  $('#cap-text').addEventListener('input', renderCaption);
  $('#cap-copy').addEventListener('click', () => copyText($('#cap-text').value));

  CAPS.sample.then((s) => { if (s) $('#hk-claude').hidden = false; });

  generateHooks();
  renderMeter();
  renderHookCards();
  renderCaption();
}
