// 작업대 전수 점검 — **보이는 창**에서 사람처럼 눌러 본다.
// (브라우저 패널은 숨겨져 있으면 스로틀링에 걸려 성능·타이밍 관찰이 다 틀린다.)
import puppeteer from '/Users/nhj/dev/yone-design-web/core/render_vivlio/node_modules/puppeteer-core/lib/puppeteer/puppeteer-core.js';

const OK = [], BAD = [];
const ok = (m) => { OK.push(m); console.log('  ✓ ' + m); };
const bad = (m) => { BAD.push(m); console.log('  ✗ ' + m); };

const b = await puppeteer.launch({
  // ⚠ 조판을 기다리는 evaluate 가 기본 180초를 넘긴다 — 늘려 둔다
  protocolTimeout: 900000,
  executablePath: '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
  headless: 'new', args: ['--no-sandbox'] });
const p = await b.newPage();
await p.setViewport({ width: 1680, height: 1020 });
const errs = [];
p.on('pageerror', e => errs.push(String(e).slice(0, 120)));
// 어느 책으로 점검할지 — `BOOK=광문보카 node audit.mjs`
const WANT = process.env.BOOK || '';
await p.goto('http://127.0.0.1:5099/book-studio', { waitUntil: 'networkidle2', timeout: 180000 });
if (WANT) {
  const picked = await p.evaluate((want) => {
    const sel = document.getElementById('ide-book');
    const o = [...sel.options].find(x => x.textContent.includes(want)
      || x.value.normalize('NFC').includes(want));
    if (!o) return '';
    sel.value = o.value;
    sel.dispatchEvent(new Event('change'));
    return o.textContent;
  }, WANT);
  if (!picked) { console.log('  ✗ 그런 책이 없다: ' + WANT); process.exit(1); }
  console.log('■ ' + picked);
}

const ready = () => p.waitForFunction(() => {
  const d = document.getElementById('ide-frame')?.contentDocument;
  return d && d.querySelectorAll('[data-vivliostyle-page-container]').length
    && !d.getElementById('ide-veil');
}, { timeout: 300000, polling: 800 });
await ready();
ok('첫 조판이 뜬다');

// ① 모든 패널이 내용을 가진다
const panels = await p.evaluate(async () => {
  document.querySelectorAll('details').forEach(d => { d.open = true; d.dispatchEvent(new Event('toggle')); });
  await new Promise(r => setTimeout(r, 2500));
  const out = {};
  document.querySelectorAll('[id^=pal-]').forEach(x => {
    out[x.id] = (x.innerText || '').replace(/\s+/g, ' ').trim().length;
  });
  return out;
});
for (const [id, len] of Object.entries(panels)) {
  if (id === 'pal-css' || id === 'pal-css-save') continue;
  (len > 5 ? ok : bad)('패널 ' + id + ' (' + len + '자)');
}

// ② 지면을 눌러 고른다 — 자리표가 있는 면까지 넘겨 가며
const picked = await p.evaluate(async () => {
  const has = () => {
    const d = document.getElementById('ide-frame').contentDocument;
    return [...d.querySelectorAll('[class*=vref]')]
      .find(e => (e.innerText || '').trim().length > 4);
  };
  for (let i = 0; i < 6 && !has(); i++) {
    document.getElementById('ide-next').click();
    await new Promise(r => setTimeout(r, 2500));
  }
  const el = has();
  if (!el) return 'no-ref';
  el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
  await new Promise(r => setTimeout(r, 600));
  return document.getElementById('pal-sel').innerText.replace(/\s+/g, ' ');
});
(/[a-z]+\.\d|book\.|#/.test(picked) ? ok : bad)('지면 클릭 → ' + picked.slice(0, 45));

// ③ 문자 패널이 실제 값을 읽는다
const charVals = await p.evaluate(() => {
  const rows = [...document.getElementById('pal-char').querySelectorAll('.ide-row')];
  return rows.slice(0, 4).map(r => r.querySelector('.ide-val')?.textContent || '');
});
(charVals.some(v => /pt|px/.test(v)) ? ok : bad)('문자 패널이 잰 값을 보여 준다 ' + JSON.stringify(charVals));

// ④ 보기 보조
for (const t of ['판면', '재단선', '기준선', '눈금자']) {
  const on = await p.evaluate((t) => {
    const btn = [...document.querySelectorAll('button')].find(b => (b.textContent || '').trim() === t);
    btn.click();
    const st = document.getElementById('ide-frame').contentDocument.getElementById('viv');
    return btn.classList.contains('on') && /show-/.test(st.className);
  }, t);
  (on ? ok : bad)('보기 ' + t);
}

// ⑤ 안내선 끌어내기
const gd = await p.evaluate(async () => {
  const d = document.getElementById('ide-frame').contentDocument;
  const st = d.getElementById('viv');
  const pg = [...d.querySelectorAll('[data-vivliostyle-page-container]')]
    .filter(x => getComputedStyle(x).display !== 'none').pop();
  const r = pg.getBoundingClientRect(), mm = r.width / 216;
  pg.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: r.left + 2 * mm, clientY: r.top + r.height / 2 }));
  st.dispatchEvent(new MouseEvent('mousemove', { bubbles: true, clientX: r.left + 25 * mm, clientY: r.top + r.height / 2 }));
  st.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  await new Promise(r2 => setTimeout(r2, 300));
  return d.querySelectorAll('.ide-gd').length;
});
(gd > 0 ? ok : bad)('안내선을 끌어내면 선이 생긴다 (' + gd + ')');

// ⑥ 찾기 — **지면에 있는 낱말**로 찾는다(책마다 다르니까)
const found = await p.evaluate(async () => {
  const d = document.getElementById('ide-frame').contentDocument;
  // ⚠ 머리말·꼬리말은 **책 설정**이라 지면에는 있어도 원고에는 없다
  //   (그래서 "GWANGMUN"·"SANGIL" 로 찾다가 0곳이 나왔다). 여러 개를 시도한다.
  // ⚠ 지금 면에 **본문 자리표가 없을 수도 있다**(간지·표지는 머리말뿐이다).
  //   그럴 때를 위해 아무 책에나 있는 낱말을 뒤에 붙인다.
  const words = [...new Set(
    ([...d.querySelectorAll('[class*=vref]')]
      .map(e => (e.innerText || '')).join(' ')
      .match(/[A-Za-z]{5,}|[가-힣]{2,}/g) || [])
      .concat(['the', 'and', '의', '다']))].slice(0, 14);
  for (const w of words) {
    document.getElementById('find-q').value = w;
    document.getElementById('find-go').click();
    await new Promise(r => setTimeout(r, 2500));
    const n = document.querySelectorAll('#find-out a[data-ref]').length;
    if (n > 0) return w + ':' + n;
  }
  // 원고 자료가 없는 계열(포켓북)은 찾을 대상이 아예 없다 — 그건 결함이 아니다
  const last = document.getElementById('ide-msg').innerText;
  if (/원고 자료가 없습니다/.test(last)) return '원고자료없음';
  return (words[0] || '?') + ':0';
});
(found === '원고자료없음'
  ? ok : (parseInt(String(found).split(':')[1] || 0) > 0 ? ok : bad))(
  '찾기 ' + (found === '원고자료없음'
    ? '— 이 계열은 원고 자료가 없다(정상)' : found + '곳'));

// ⑦ 색상 견본
const sw = await p.evaluate(() => document.querySelectorAll('#pal-color button').length);
(sw > 0 ? ok : bad)('색상 견본 ' + sw + '개');

// ⑧ 면 넘기기 — **있는 면** 중에서 고른다(책마다 면수가 다르다)
const jump = await p.evaluate(async () => {
  const a = [...document.querySelectorAll('#pal-pages a[data-pg]')];
  if (!a.length) return 'no-list';
  const want = String(Math.min(5, a.length));
  a.find(x => x.dataset.pg === want).click();
  for (let i = 0; i < 90; i++) {
    await new Promise(r => setTimeout(r, 500));
    const t = document.getElementById('ide-pageno').innerText;
    if (t.startsWith(want + ' ')) return t;
    if (/까지입니다/.test(document.getElementById('ide-msg').innerText))
      return t + ' (판의 끝)';
  }
  return document.getElementById('ide-pageno').innerText + ' (못 감)';
});
(!/못 감|no-list/.test(jump) ? ok : bad)('면 넘기기 → ' + jump);

// ⑨ 펼침(2면 보기)
const spread = await p.evaluate(async () => {
  document.getElementById('ide-spread').click();
  await new Promise(r => setTimeout(r, 6000));
  const d = document.getElementById('ide-frame').contentDocument;
  return [...d.querySelectorAll('[data-vivliostyle-page-container]')]
    .filter(x => getComputedStyle(x).display !== 'none').length;
});
(spread >= 2 ? ok : bad)('펼침 보기 — 보이는 면 ' + spread);

console.log('\n합계  ✓ ' + OK.length + '   ✗ ' + BAD.length);
if (errs.length) console.log('자바스크립트 오류:', [...new Set(errs)].slice(0, 5));
await b.close();
