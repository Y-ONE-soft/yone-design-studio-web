// 작업대 점검 ② — **고치는 일**을 사람처럼 해 본다(그리고 되돌린다).
//
// ⚠ 진짜 책 폴더를 고친다. 끝에서 이력을 되감지만 납품 중인 책에는 돌리지 말 것.
import puppeteer from '../../core/render_vivlio/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';

const OK = [], BAD = [];
const ok = (m) => { OK.push(m); console.log('  ✓ ' + m); };
const bad = (m) => { BAD.push(m); console.log('  ✗ ' + m); };
const wait = (ms) => new Promise(r => setTimeout(r, ms));

const b = await puppeteer.launch({
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new', args: ['--no-sandbox'] });
const p = await b.newPage();
await p.setViewport({ width: 1680, height: 1020 });
const errs = [];
p.on('pageerror', e => errs.push(String(e).slice(0, 140)));
await p.goto('http://127.0.0.1:5099/book-studio', { waitUntil: 'networkidle2', timeout: 180000 });

const ready = () => p.waitForFunction(() => {
  const d = document.getElementById('ide-frame')?.contentDocument;
  return d && d.querySelectorAll('[data-vivliostyle-page-container]').length
    && !d.getElementById('ide-veil');
}, { timeout: 300000, polling: 800 });
await ready();

const hist = () => p.evaluate(async () => {
  const key = document.getElementById('ide-book').value;
  const r = await fetch('/api/book-studio/history?b=' + encodeURIComponent(key));
  return r.json();
});
const before = (await hist()).head || 0;

// ① 글 고치기 — 글자 도구로 그 줄을 열고 굵게
const edited = await p.evaluate(async () => {
  document.querySelector('[data-tool="text"]').click();
  const d = document.getElementById('ide-frame').contentDocument;
  const el = [...d.querySelectorAll('[class*=vref]')]
    .find(e => /My name is Lee/.test(e.innerText || '') && !/Band United/.test((e.innerText || '').slice(0, 25)));
  el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 900));
  const e = d.querySelector('.ide-editing');
  if (!e) return 'editor-not-open';
  const tn = [...e.childNodes].find(n => n.nodeType === 3 && n.length > 20);
  const rng = d.createRange(); rng.setStart(tn, 0); rng.setEnd(tn, 11);
  const sel = d.getSelection(); sel.removeAllRanges(); sel.addRange(rng);
  document.querySelectorAll('#ide-fmt button')[0].click();
  await new Promise(r => setTimeout(r, 300));
  const html = e.innerHTML.slice(0, 40);
  document.getElementById('ide-commit').click();
  return html;
});
(/<b>/.test(edited) ? ok : bad)('글자 굵게 → ' + edited);
await wait(2500); await ready();
const bolded = await p.evaluate(() => {
  const d = document.getElementById('ide-frame').contentDocument;
  return [...d.querySelectorAll('b')].some(x => /My name is/.test(x.textContent));
});
(bolded ? ok : bad)('조판본에 굵게가 남는다');

// ② 표 넣고 칸 합치기
const tbl = await p.evaluate(async () => {
  const key = document.getElementById('ide-book').value;
  const call = (body) => fetch('/api/book-studio/table', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(Object.assign({ b: key }, body)) }).then(r => r.json());
  const ins = await call({ action: 'insert', ref: 'lessons.0.vocab.0.paras.0', cols: 3, rows: 3 });
  if (!ins.ok) return 'insert:' + JSON.stringify(ins);
  const mg = await call({ action: 'merge', ref: ins.ref, r0: 1, c0: 0, r1: 2, c1: 1 });
  return mg.ok ? ins.ref : 'merge:' + JSON.stringify(mg);
});
(/\./.test(tbl) ? ok : bad)('표 넣고 2×2 합치기 → ' + tbl);
await p.evaluate(() => document.getElementById('ide-reload').click());
await wait(1500); await ready();
const spans = await p.evaluate(() => {
  const d = document.getElementById('ide-frame').contentDocument;
  const t = d.querySelector('table.viv-tbl');
  return t ? [...t.querySelectorAll('td')].filter(x => x.colSpan > 1 || x.rowSpan > 1).length : -1;
});
(spans === 1 ? ok : bad)('합친 칸이 지면에 나온다 (' + spans + ')');

// ③ 상자 넣고 모서리로 크기 바꾸기
const boxRef = await p.evaluate(async () => {
  const key = document.getElementById('ide-book').value;
  const r = await fetch('/api/book-studio/box', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ b: key, action: 'insert', ref: 'lessons.0.vocab.0.paras.0', kind: 'text' }) });
  return (await r.json()).ref || '';
});
await p.evaluate(() => document.getElementById('ide-reload').click());
await wait(1500); await ready();
const resized = await p.evaluate(async () => {
  document.querySelector('[data-tool="sel"]').click();
  const d = document.getElementById('ide-frame').contentDocument;
  const st = d.getElementById('viv');
  const box = d.querySelector('.viv-box');
  if (!box) return 'no-box';
  box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 400));
  const se = [...d.querySelectorAll('.ide-hd')].find(h => h.dataset.h === 'se');
  if (!se) return 'no-handle';
  const pg = [...d.querySelectorAll('[data-vivliostyle-page-container]')]
    .filter(x => getComputedStyle(x).display !== 'none').pop();
  const ppm = pg.getBoundingClientRect().width / 216;
  const r0 = se.getBoundingClientRect();
  se.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: r0.left + 1, clientY: r0.top + 1 }));
  st.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: r0.left + 1 + 20 * ppm, clientY: r0.top + 1 + 10 * ppm }));
  const got = box.style.width + ' / ' + box.style.left + ' / ' + box.style.top;
  st.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  return got;
});
(/^(69|70|71)(\.\d+)?mm \/ 20mm \/ 20mm/.test(resized) ? ok : bad)('상자 크기 조절(위·왼쪽 그대로) → ' + resized);

// ③-2 상자를 면에 맞추기
const aligned = await p.evaluate(async () => {
  const d = document.getElementById('ide-frame').contentDocument;
  const box = d.querySelector('.viv-box');
  if (!box) return 'no-box';
  const was = box.style.left + '|' + box.style.right;
  box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 500));
  const btn = [...document.querySelectorAll('#pal-box button')]
    .find(b => b.textContent === '가로 가운데');
  if (!btn) return 'no-button';
  btn.click();
  await new Promise(r => setTimeout(r, 400));
  window.__alignMsg = document.getElementById('ide-msg').innerText;
  // ⚠ **바뀔 때까지 기다린다.** 다시 조판이 끝나기 전에 재면 옛 자리를 잰다
  //   (실제로 그래서 "105px 어긋남" 이 나왔다 — 계산은 맞았다).
  for (let i = 0; i < 60; i++) {
    await new Promise(r => setTimeout(r, 500));
    const b2 = document.getElementById('ide-frame').contentDocument.querySelector('.viv-box');
    if (b2 && (b2.style.left + '|' + b2.style.right) !== was) return 'moved';
  }
  return 'timeout: 직후=' + window.__alignMsg + ' 지금='
    + document.getElementById('ide-msg').innerText
    + ' / was=' + was;
});
const centered = await p.evaluate(() => {
  const d = document.getElementById('ide-frame').contentDocument;
  const box = d.querySelector('.viv-box');
  if (!box) return 'gone';
  // ⚠ **그 상자가 있는 면**과 재야 한다(지나온 면이 DOM 에 남아 있다).
  let pg = box;
  while (pg && !(pg.hasAttribute && pg.hasAttribute('data-vivliostyle-page-container')))
    pg = pg.parentElement;
  if (!pg) return 'no-page';
  const br = box.getBoundingClientRect(), pr = pg.getBoundingClientRect();
  return Math.abs((br.left + br.right) / 2 - (pr.left + pr.right) / 2).toFixed(1) + 'px 어긋남';
});
(parseFloat(centered) < 3 ? ok : bad)('상자를 면 가운데로 (' + aligned + ') → ' + centered);

const glyph = await p.evaluate(async () => {
  document.querySelector('[data-tool="text"]').click();
  const d = document.getElementById('ide-frame').contentDocument;
  const el = [...d.querySelectorAll('[class*=vref]')]
    .find(e => /Growing up/.test(e.innerText || ''));
  el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 900));
  const before = d.querySelector('.ide-editing');
  if (!before) return 'editor-not-open';
  const g = [...document.querySelectorAll('#pal-glyph button')].find(b => b.textContent === '①');
  if (!g) return 'no-glyph';
  const sel = d.getSelection(); const rng = d.createRange();
  rng.setStart(before.firstChild, 0); rng.collapse(true);
  sel.removeAllRanges(); sel.addRange(rng);
  g.click();
  await new Promise(r => setTimeout(r, 300));
  const got = (before.innerText || '').slice(0, 3);
  document.getElementById('ide-cancel').click();
  return got;
});
(/①/.test(glyph) ? ok : bad)('특수문자 ① 넣기 → ' + JSON.stringify(glyph));

// ④ 마스터 페이지 — 여백 한 줄
await wait(2500); await ready();
const master = await p.evaluate(async () => {
  const key = document.getElementById('ide-book').value;
  const r = await fetch('/api/book-studio/pagerules', { method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ b: key, sel: ':left', props: { 'margin-left': '33mm' } }) });
  const j = await r.json();
  return j.ok ? JSON.stringify(j.rules[':left']) : JSON.stringify(j);
});
(/33mm/.test(master) ? ok : bad)('마스터 페이지 여백 → ' + master);

// ⑤ 되돌리기로 전부 원상복구
const after = (await hist()).head || 0;
let undone = 0;
for (let i = 0; i < after - before; i++) {
  await p.evaluate(async () => {
    const key = document.getElementById('ide-book').value;
    await fetch('/api/book-studio/history', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ b: key, action: 'undo' }) });
  });
  undone++;
}
const end = (await hist()).head || 0;
(end === before ? ok : bad)('되돌리기로 원상복구 (' + before + ' → ' + after + ' → ' + end + ')');

console.log('\n합계  ✓ ' + OK.length + '   ✗ ' + BAD.length);
if (errs.length) console.log('자바스크립트 오류:', [...new Set(errs)].slice(0, 5));
await b.close();
process.exit(BAD.length ? 1 : 0);
