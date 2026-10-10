/* 단락 컴포저 — 양끝맞춤 문단의 줄 끝을 문단 전체를 보고 고른다 (인디자인 「Adobe 단락 컴포저」와 같은 생각, Knuth–Plass).
 *
 * 브라우저는 한 줄씩 꽉 채우고(그리디) 공백을 늘리기만 한다. 인디자인은 문단 전체에서 줄마다 공백이 고르게 되는 줄 끝을 고르고,
 * 낱말 간격을 최소~최대(기본 80~133%) 안에서 줄이거나 늘린다. 원고로 들어온 글도 인디자인처럼 꺾이게 이것을 쓴다.
 *
 * 쓰는 곳: 편집기 화면(지면 그림을 넣을 때마다) · PDF(인쇄 전에) — 둘 다 크롬이 그리므로 실제 글자 폭으로 잰다.
 * 대상: 렌더러가 data-jc 를 붙인 단락(양끝맞춤 · 손으로 친 줄 나눔이 없는 것). data-jc="최소,최대" = 낱말 간격 %.
 */
(function () {
  "use strict";

  const CJK = /[\u1100-\u11FF\u3130-\u318F\uAC00-\uD7A3\u3040-\u30FF\u4E00-\u9FFF]/;
  const ENC = /[\u2460-\u24FF\u2776-\u2793\u3251-\u325F\u32B1-\u32BF]/;   // 원문자 ①②… — 한중일 글자처럼 앞뒤에서 꺾을 수 있다(인디자인: 「③shouting」 을 ③ 뒤에서 꺾음, 단위 14c)
  const OPEN = /[(\[{‘“「『（]/, CLOSE = /[)\]}’”」』）.,;:!?。、]/;   // 금칙 — 여는 괄호 뒤·닫는 괄호와 문장부호 앞에서는 안 꺾는다(「(④)」, 단위 06)
  const brkOK = (a, b) => !OPEN.test(a) && !CLOSE.test(b) && ((CJK.test(a) && CJK.test(b)) || (ENC.test(a) && !isSp(b)) || (!isSp(a) && ENC.test(b))
    || (a === "/" && !isSp(b) && !/\d/.test(b)));   // 공백 없이 꺾을 수 있는 글자 사이 — 빗금 뒤도(「(T/ | F)」, 인디자인·유니코드 줄 나눔, 단위 14a)
  const isSp = (c) => c === " " || c === "\u00a0";

  function tokens(p) {
    // 글자 단위로 펴서 낱말(공백 아닌 것의 연속)과 공백 덩어리로 — 낱말이 서식 경계를 넘어도 하나로.
    // 글자가 아닌 칸(빈칸 밑줄 같은 inline-block)도 낱말의 한 글자로 센다(폭이 있다).
    // 한글·한자·가나는 글자 사이에서도 꺾을 수 있다(인디자인처럼) — 폭 0 인 끊을 자리를 둔다.
    const chars = [];
    // 글자가 아닌 칸·개체(inline-block — 빈칸 밑줄, 글 끝에 붙인 O/X 상자)는 안을 보지 않고 한 글자로
    const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {acceptNode: (n) =>
      n.nodeType === 1 && getComputedStyle(n).display === "inline-block" ? (chars.push([n, -1, "\ufffc"]), NodeFilter.FILTER_REJECT) : NodeFilter.FILTER_ACCEPT});
    let n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) for (let i = 0; i < n.data.length; i++) chars.push([n, i, n.data[i]]);
    }
    const out = [];
    let i = 0;
    while (i < chars.length) {
      const sp = isSp(chars[i][2]);
      let j = i + 1;
      if (sp) while (j < chars.length && isSp(chars[j][2])) j++;
      else while (j < chars.length && !isSp(chars[j][2]) && !brkOK(chars[j - 1][2], chars[j][2])) j++;
      const seg = chars.slice(i, j);
      out.push({space: sp, a: seg[0], b: seg[seg.length - 1], breakable: sp && seg.some(c => c[2] === " "), n: sp ? seg.length : 0, seg: sp ? seg : null,
                c: seg.length});                                                // 글자 수 — 인디자인 자간은 글자마다 붙는다
      if (!sp && j < chars.length && brkOK(chars[j - 1][2], chars[j][2]))
        out.push({space: true, zero: true, breakable: true, n: 0, w: 0, sp0: 0, c: 0});    // 한글 음절 사이 — 폭 0, 여기서도 꺾을 수 있다
      i = j;
    }
    while (out.length && out[0].space && out[0].breakable) out.shift();             // 줄 안 바뀜 공백(렌더러가 지킨 첫·끝 공백)은 남긴다
    while (out.length && out[out.length - 1].space && out[out.length - 1].breakable) out.pop();
    return out;
  }

  function setA(r, a) { if (a[1] < 0) r.setStartBefore(a[0]); else r.setStart(a[0], a[1]); }
  function setB(r, b) { if (b[1] < 0) r.setEndAfter(b[0]); else r.setEnd(b[0], b[1] + 1); }
  function rangeOf(t) {
    const r = document.createRange();
    setA(r, t.a);
    setB(r, t.b);
    return r;
  }

  // 줄을 꺾는 공백이 밑줄 친 글 안이면 그 밑줄 모양(굵기·내림·색)과 공백 하나 폭 — 없으면 null
  function brkUnderline(t, p) {
    if (!t || !t.space || t.zero || !t.a || t.a[1] < 0) return null;
    for (let el = t.a[0].parentElement; el && el !== p; el = el.parentElement) {
      const cs = getComputedStyle(el);
      if (!(cs.textDecorationLine || "").includes("underline")) continue;
      const fs = parseFloat(cs.fontSize) || 10;
      const th = cs.textDecorationThickness, off = cs.textUnderlineOffset;
      const lg = t.a[0].parentElement.closest("[lang]");
      return {w: t.w / Math.max(t.n, 1), col: cs.textDecorationColor || cs.color, lang: lg ? lg.lang : "",   // 공백 꼴도 같은 언어로(한국어 0.280em)
              th: th && th !== "auto" && th !== "from-font" ? th : (fs * 0.05).toFixed(3) + "px",
              off: off && off !== "auto" ? off : (fs * 0.1).toFixed(3) + "px"};
    }
    return null;
  }

  // ── 자간 축소 (인디자인 문자 패널 「자간 축소」, Tsume) ──
  // 글자마다 양옆 빈 곳(글리프 폭 안 · 잉크 밖)을 t% 줄인다 — 줄 첫 글자의 왼쪽도. 공백은 그대로.
  // 원본 d1 발문(48~74쪽) 글자 쌍 2,384개: 자간 −40‰ + 축소 40% 로 2,380쌍이 3‰ 안(나머지 4쌍은 PDF 의 fi 합자 표기).
  // 렌더러가 data-tsume(%)을 붙인 글상자에서, 글자를 하나씩 span 으로 나눠 margin 으로 줄인다. 잉크 상자는 캔버스로 잰다.
  // span 으로 나누면 크롬 커닝이 끊기므로 캔버스로 잰 쌍 커닝(쌍 폭 − 낱자 폭 합)을 오른쪽 여백에 되돌린다. 합자(fi·ff…)는 한 덩어리.
  const LIG = /^(?:ffi|ffl|ff|fi|fl)/;
  const noInk = (c) => /^[\s ⁠​]+$/.test(c);
  const _ink = new Map();
  let _cv = null;
  function inkOf(font, s) {                                            // 100px 글자의 [왼쪽 빈 곳, 오른쪽 빈 곳, 폭] px
    const key = font + "\u0000" + s;
    let v = _ink.get(key);
    if (!v) {
      _cv = _cv || document.createElement("canvas").getContext("2d");
      _cv.font = font;
      const m = _cv.measureText(s);
      v = [-m.actualBoundingBoxLeft, m.width - m.actualBoundingBoxRight, m.width];
      _ink.set(key, v);
    }
    return v;
  }
  function tsume(root) {
    [...root.querySelectorAll("[data-tsume]")].reverse().forEach(box => {   // 안쪽(문단마다 다른 값)부터 — 바깥 상자는 이미 나눈 글자를 다시 안 나눈다
      if (box.dataset.tsumeDone) return;
      box.dataset.tsumeDone = "1";
      const t = (+box.dataset.tsume || 0) / 100;
      if (!(t > 0)) return;
      const nodes = [];
      const w = document.createTreeWalker(box, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {acceptNode: (n) =>   // 칸·개체(inline-block) 속은 그대로
        n.nodeType === 1 && getComputedStyle(n).display === "inline-block" ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT});
      let n;
      while ((n = w.nextNode())) if (n.nodeType === 3 && !noInk(n.data) && !(n.parentElement && n.parentElement.dataset.ts)) nodes.push(n);
      for (const tn of nodes) {
        const cs = getComputedStyle(tn.parentElement), px = parseFloat(cs.fontSize);
        if (!(px > 0)) continue;
        const font = `${cs.fontStyle} ${cs.fontWeight} 100px ${cs.fontFamily}`, k = px / 100, kern = cs.fontKerning !== "none";
        const g = [], s = tn.data;                                         // 글자(합자는 한 덩어리)
        for (let i = 0; i < s.length;) {
          const m = s.slice(i).match(LIG), c = m ? m[0] : String.fromCodePoint(s.codePointAt(i));
          g.push(c);
          i += c.length;
        }
        const frag = document.createDocumentFragment();
        let plain = "";
        g.forEach((c, i) => {
          if (noInk(c)) { plain += c; return; }
          if (plain) { frag.appendChild(document.createTextNode(plain)); plain = ""; }
          const [l, r] = inkOf(font, c), nx = g[i + 1];
          let mr = -t * r;
          if (kern && nx && !noInk(nx)) mr += inkOf(font, c + nx)[2] - inkOf(font, c)[2] - inkOf(font, nx)[2];
          const sp = document.createElement("span");
          sp.dataset.ts = "1";
          sp.textContent = c;
          sp.style.marginLeft = (-t * l * k).toFixed(4) + "px";
          sp.style.marginRight = (mr * k).toFixed(4) + "px";
          frag.appendChild(sp);
        });
        if (plain) frag.appendChild(document.createTextNode(plain));
        tn.replaceWith(frag);
      }
    });
  }
  // 자간 축소 글자의 펜 자리(화면 px) — 글자 범위는 span 여백을 빼고 잡히므로 여백을 되돌린다. k = 화면 px / CSS px
  function tsMargin(c, side) {
    if (c[1] < 0) return 0;
    const e = c[0].parentElement;
    if (!e || !e.dataset.ts || (side === "L" ? c[1] !== 0 : c[1] !== c[0].data.length - 1)) return 0;
    return parseFloat(side === "L" ? e.style.marginLeft : e.style.marginRight) || 0;
  }
  function penX(c, k, side) {
    const r = document.createRange();
    if (c[1] < 0) r.selectNode(c[0]); else { r.setStart(c[0], c[1]); r.setEnd(c[0], c[1] + 1); }
    const b = r.getBoundingClientRect();
    return side === "L" ? b.left - tsMargin(c, "L") * k : b.right + tsMargin(c, "R") * k;
  }

  function compose(p) {
    if (p.dataset.jcDone) return;
    const OK = new Set(["span", "b", "i", "u", "s", "sup", "sub"]);        // 글 안 표·떠 있는 그림 등은 건드리지 않는다 — inline-block 개체 속(SVG)은 괜찮다
    if ([...p.querySelectorAll("*")].some(e => !OK.has(e.tagName.toLowerCase()) && !(e.parentElement && e.parentElement.closest("span[style*='inline-block']")))) return;
    // 인디자인 「양끝 정렬」 설정 — 낱말 간격 최소·최대 %(공백 글리프 폭 기준) · 자간 최소·최대 ‰em · 줄이기 비용 배수 · 줄 하나 비용 · 끝 줄 자간 최소 ‰em.
    // 원본 d1 PDF 에서 읽은 규칙(2026-10-08 scratch justify-analysis): 낱말 간격은 100%(희망) → 133%(최대)까지 먼저 늘고, 모자라면 자간이 는다
    // (낱말은 133% 에 멈춤 — 4~37쪽 줄 87개 모두 0.33×공백 ±0.6‰). 줄일 땐 낱말은 100% 아래로 안 가고 자간만 준다(-1~-5‰ 관찰). 글리프 비율 100%.
    // 공백 기준 = 서체의 U+0020 폭(Noto CJK KR 224/1000 — 인디자인이 실제로 놓는 locl 공백 280 이 아니다). 줄 끝 맞춤 4·5·8·9·16·17쪽 60/62.
    const [wmn, wmx, lmn, lmx, sw, lp, lastLmn] = (p.dataset.jc || "80,133,0,0,1,20,0").split(",").map(Number);
    const cs1 = getComputedStyle(p), lh1 = parseFloat(cs1.lineHeight);   // 브라우저가 한 줄에 다 넣은 단락 — 끝 줄 하나뿐이라 고를 게 없다.
    if (lh1 > 0 && p.offsetHeight - parseFloat(cs1.paddingTop) - parseFloat(cs1.paddingBottom) < lh1 * 1.5) return;   // 글 폭에 맞춘 상자(자동 크기 높이와 너비)에서 낱자 폭 합의 반올림으로 두 줄로 꺾이던 것
    const save = [p.style.whiteSpace, p.style.textAlign];
    p.style.whiteSpace = "nowrap";
    p.style.textAlign = "left";                                         // 늘이기 전 자연 폭으로 잰다
    const toks = tokens(p);
    if (toks.length < 3) { p.style.whiteSpace = save[0]; p.style.textAlign = save[1]; return; }
    for (const t of toks) if (!t.zero) t.w = rangeOf(t).getBoundingClientRect().width;
    const rect = p.getBoundingClientRect();
    const k = rect.width / (p.offsetWidth || 1);                         // 화면 px / 이 단락의 px (zoom·확대 포함)
    if (p.closest("[data-tsume]")) {                                     // 자간 축소 — 낱말 폭 = 펜 자리에서 다음 낱말 펜 자리까지(낱말 끝 글자 여백이 범위 밖이다)
      const real = toks.filter(t => !t.zero);
      real.forEach((t, i) => { t.w = (i + 1 < real.length ? penX(real[i + 1].a, k, "L") : penX(t.b, k, "R")) - penX(t.a, k, "L"); });
    }
    const cs = getComputedStyle(p);
    const W = rect.width - (parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight)) * k;
    const indent = parseFloat(cs.textIndent) * k || 0;
    const em = parseFloat(cs.fontSize) * k;
    const ls = parseFloat(cs.letterSpacing) * k || 0, wsp = parseFloat(cs.wordSpacing) * k || 0;   // 단락 자간 · 낱말 간격(보정) — 공백 글리프 폭을 꺼내려고
    for (const t of toks) if (t.space && !t.zero) t.sp0 = Math.max(0, t.w - t.n * (ls + wsp));       // 공백 글리프 폭 합 = 낱말 간격 % 의 기준
    // 글 언어로 감싼 공백(렌더러 locl_html — Noto CJK 한국어 꼴 0.280em)도 기준은 서체의 U+0020 폭(0.224em)이다: 인디자인이 그렇게 늘린다
    const notEn = (l) => l && !/^en/i.test(l);
    if ([...p.querySelectorAll("span[lang]")].some(e => notEn(e.lang))) {
      const m = (lang, s) => { const e = document.createElement("span"); e.lang = lang; e.style.whiteSpace = "pre"; e.textContent = s; p.appendChild(e);
                               const w = e.getBoundingClientRect().width; e.remove(); return w; };
      const g = (lang) => m(lang, "x x") - m(lang, "xx") - ls - wsp;
      const ge = g("en"), r = {};
      for (const t of toks) if (t.space && !t.zero && t.a[1] >= 0) {
        const l = t.a[0].parentElement && t.a[0].parentElement.closest("[lang]");
        if (!l || !notEn(l.lang)) continue;
        if (!(l.lang in r)) { const gl = g(l.lang); r[l.lang] = gl > 0 ? ge / gl : 1; }
        t.sp0 *= r[l.lang];
      }
    }
    p.style.whiteSpace = save[0];
    p.style.textAlign = save[1];
    const Lmx = lmx / 1000 * em, Lmn = -lmn / 1000 * em, LLmn = -lastLmn / 1000 * em;   // 글자 사이 하나가 늘·줄 수 있는 폭(px)

    // 줄 끝 후보 = 끊을 수 있는 공백. 줄 = 후보 a 다음 낱말부터 후보 b 앞 낱말까지.
    // 늘릴 수 있는 폭 = 공백 기준 × (최대-100)% + 글자 사이 수 × 자간 최대 · 줄일 수 있는 폭 = 공백 기준 × (100-최소)% + 글자 사이 수 × |자간 최소|
    const brk = [-1];
    toks.forEach((t, i) => { if (t.space && t.breakable) brk.push(i); });
    brk.push(toks.length);
    const best = new Array(brk.length).fill(Infinity), from = new Array(brk.length).fill(-1);
    best[0] = 0;
    for (let a = 0; a < brk.length - 1; a++) {
      if (best[a] === Infinity) continue;
      const g0 = a > 0 ? toks[brk[a]] : null;                          // 공백 여러 칸에서 꺾이면 첫 칸만 줄 끝 — 나머지는 이 줄 앞에 남는다(인디자인)
      const f0 = g0 && g0.n > 1 ? (g0.n - 1) / g0.n : 0;
      let L = f0 ? g0.w * f0 : 0, S0 = f0 ? g0.sp0 * f0 : 0, nc = f0 ? g0.n - 1 : 0;
      const lw = W - (a === 0 ? indent : 0);
      for (let b = a + 1; b < brk.length; b++) {
        const s = brk[b - 1] + 1, e = brk[b];
        for (let i = (b === a + 1 ? brk[a] + 1 : s - 1); i < e; i++) {
          const t = toks[i];
          L += t.w;
          nc += t.c;
          if (t.space) S0 += t.sp0;
        }
        const last = b === brk.length - 1;
        const ng = Math.max(0, nc - 1);                                 // 글자 사이 수(공백 포함 — 인디자인 자간은 공백 뒤에도 붙는다)
        let bad;
        if (L <= lw) {
          const Y = S0 * (wmx - 100) / 100 + ng * Lmx;
          bad = last ? 0 : Math.min(10000, 100 * Math.pow(Y > 0 ? (lw - L) / Y : 10, 2));   // 늘림은 제곱 — 인디자인은 성긴 줄을 세제곱만큼 꺼리지 않는다(14b 「…that a photo」, 30쪽 첫 줄)
        } else {
          const z = S0 * (100 - wmn) / 100 + ng * (last ? LLmn : Lmn);  // 끝 줄은 자간을 조금 더 줄여 넣는다
          const r = z > 0 ? (lw - L) / z : -10;
          if (r < -1) break;                                           // 더 붙이면 줄여도 안 들어간다
          bad = last ? 0 : Math.min(10000, sw * 100 * Math.pow(-r, 3));
        }
        const gb = b < brk.length - 1 ? toks[brk[b]] : null;               // 공백 여러 칸 안에서 꺾으면 다음 줄이 공백으로 시작 — 꼭 필요할 때만(작은 비용)
        const dem = Math.pow(lp + bad, 2) + (gb && gb.n > 1 ? 30 : 0);
        if (best[a] + dem < best[b]) { best[b] = best[a] + dem; from[b] = a; }
      }
    }
    if (best[brk.length - 1] === Infinity) return;                      // 못 고르면 브라우저 줄바꿈 그대로
    const cut = [];
    for (let b = brk.length - 1; b > 0; b = from[b]) cut.unshift(b);

    const lines = [];
    let s = 0;
    for (const b of cut) {
      const e = brk[b];
      const ws = toks.slice(s, e);
      const g0 = s > 0 ? toks[s - 1] : null;                             // 앞 줄 끝 공백 덩어리의 둘째 칸부터 — 이 줄 앞에 남긴다
      const lead = g0 && g0.space && g0.n > 1 && g0.seg ? g0.seg[1] : null;
      const f0 = lead ? (g0.n - 1) / g0.n : 0;
      const sum = (f) => ws.reduce((x, t) => x + f(t), 0);
      lines.push({first: toks[s], last: toks[e - 1], start: lead, L: sum(t => t.w) + (lead ? g0.w * f0 : 0),
                  nsp: sum(t => t.space ? t.n : 0) + (lead ? g0.n - 1 : 0), S0: sum(t => t.space ? t.sp0 : 0) + (lead ? g0.sp0 * f0 : 0),
                  nc: sum(t => t.c) + (lead ? g0.n - 1 : 0), ul: brkUnderline(toks[e], p)});
      s = e + 1;
    }
    const frag = [];
    lines.forEach((ln, li) => {
      const r = document.createRange();
      setA(r, ln.start || ln.first.a);
      setB(r, ln.last.b);
      frag.push(r.cloneContents());
    });
    const isLast = (li) => li === lines.length - 1;
    const lw0 = (li) => W - (li === 0 ? indent : 0);
    p.textContent = "";
    lines.forEach((ln, li) => {
      const sp = document.createElement("span");
      let st = "display:block;white-space:nowrap;" + (li ? "text-indent:0;" : "");   // 줄 끝은 컴포저가 정했다 — 인쇄 때 다시 꺾지 않게
      // 줄마다 인디자인 순서로 나눈다: 낱말 간격(최소~최대) 먼저, 남는 것은 자간. 끝 줄은 넘칠 때만(줄여 넣기).
      const slack = lw0(li) - ln.L, ng = Math.max(1, ln.nc - 1);
      let xw = 0, dl = 0;
      if (slack < 0) { xw = Math.max(slack, -ln.S0 * (100 - wmn) / 100); dl = (slack - xw) / ng; }
      else if (!isLast(li)) { xw = lmx > 0 ? Math.min(slack, ln.S0 * (wmx - 100) / 100) : slack; dl = (slack - xw) / ng; }   // 자간 최대 0(인디자인 기본) — 낱말 최대를 넘겨 낱말로
      if (!isLast(li) || slack < 0) {
        st += "text-align-last:justify;";                               // 반올림 찌꺼기만 크롬이 공백에 나눈다
        if (ln.nsp && xw) st += `word-spacing:${((wsp + xw / ln.nsp) / k).toFixed(4)}px;`;
        // 자간은 끝 글자 뒤에도 붙으므로(크롬) 그만큼 줄을 넓혀 끝 글자 자리를 지킨다 — 인디자인은 글자 사이(n-1)에만
        if (Math.abs(dl) > 0.001) st += `letter-spacing:${((ls + dl) / k).toFixed(4)}px;margin-right:${(-dl / k).toFixed(4)}px;`;
      }
      sp.setAttribute("style", st);
      sp.appendChild(frag[li]);
      if (ln.ul && !isLast(li)) {                                         // 줄 끝 공백에 걸린 밑줄 — 인디자인은 그 공백까지 긋는다(단 끝을 넘어). 폭은 0 으로 쳐서 양끝맞춤은 그대로
        const u = document.createElement("span"), v = document.createElement("span");   // 같은 서체의 공백에 같은 밑줄 — 자리가 글 밑줄과 똑같다
        u.setAttribute("style", `display:inline-block;white-space:pre;text-indent:0;width:${(ln.ul.w / k).toFixed(4)}px;margin-right:${(-ln.ul.w / k).toFixed(4)}px`);   // 줄 폭에 0 — 양끝맞춤 그대로
        v.setAttribute("style", `word-spacing:0;text-decoration:underline;text-decoration-thickness:${ln.ul.th};text-underline-offset:${ln.ul.off};` +
          `text-decoration-color:${ln.ul.col};text-decoration-skip-ink:none`);
        v.textContent = " ";
        if (ln.ul.lang) v.lang = ln.ul.lang;
        u.appendChild(v);
        sp.appendChild(u);
      }
      p.appendChild(sp);
    });
    p.dataset.jcDone = "1";
  }

  // ── 글 잇기 (인디자인 텍스트 스레드) ──
  // 렌더러(render._atom_svg_raw)가 첫 상자에 글 전체를 넣고, 이어지는 상자는 빈 그릇으로 둔다 — 둘 다 data-story(이야기 이름)·data-seq(순서).
  // 상자 높이를 넘는 줄을 줄 경계에서 잘라 다음 상자 맨 위로 옮긴다. 잘린 단락의 뒷부분은 같은 단락 모양으로(들여쓰기·앞 간격 없이).
  // 끝 상자에서도 넘치면 넘침 표시(.story-over — 화면에만, PDF 는 숨김). 여러 번 불러도 된다 — 넘친 것만 다음 상자로 가므로
  // 쪽 하나로 먼저 흘리고(편집기) 나중에 여러 쪽을 한꺼번에 불러도 이어진다. 높이 비교는 모두 화면 px(getBoundingClientRect) — zoom(TEXT_ZOOM)·확대가 같이 든다.
  const seqOf = (o) => +o.dataset.seq || 1;
  const boxOf = (o) => o.firstElementChild;                            // 높이·안쪽 여백을 가진 상자 — render._text_html
  function holder(o) {                                                 // 단락(<p>)들의 부모 — 상자 자신 또는 장평 감싸개
    const p = boxOf(o) && boxOf(o).querySelector("p");
    return p ? p.parentElement : null;
  }
  const paras = (h) => [...h.children].filter(e => e.tagName === "P");

  function limitOf(o) {                                                // 이 상자에서 글이 내려갈 수 있는 끝(화면 px)과 허용 오차(0.5 CSS px)
    const b = boxOf(o), r = b.getBoundingClientRect(), k = r.height / (b.offsetHeight || 1) || 1;
    return r.bottom - parseFloat(getComputedStyle(b).paddingBottom || 0) * k + 0.5 * k;
  }

  function charsOf(p) {                                                // 글자 자리 — 컴포저의 tokens 와 같게 펴고, inline-block 개체는 한 글자로
    const out = [];
    const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT, {acceptNode: (n) =>
      n.nodeType === 1 && getComputedStyle(n).display === "inline-block" ? (out.push([n, -1]), NodeFilter.FILTER_REJECT) : NodeFilter.FILTER_ACCEPT});
    let n;
    while ((n = w.nextNode())) if (n.nodeType === 3) for (let i = 0; i < n.data.length; i++) out.push([n, i]);
    return out;
  }
  function bottomOf(c) {                                               // 그 글자의 아래 끝 — 공백·안 그려진 글자는 null
    if (c[1] < 0) { const r = c[0].getBoundingClientRect(); return r.height ? r.bottom : null; }
    if (/\s/.test(c[0].data[c[1]])) return null;
    const r = document.createRange();
    r.setStart(c[0], c[1]);
    r.setEnd(c[0], c[1] + 1);
    const rs = r.getClientRects();
    return rs.length ? rs[rs.length - 1].bottom : null;
  }
  function firstOver(cs, L) {                                          // 아래 끝이 L 을 넘는 첫 (보이는) 글자 — 줄은 위에서 아래로 차례라 이분 탐색
    const vis = (i) => { for (let j = i; j < cs.length; j++) { const b = bottomOf(cs[j]); if (b != null) return [j, b]; } return [cs.length, null]; };
    let lo = 0, hi = cs.length;
    while (lo < hi) {
      const mid = (lo + hi) >> 1, [j, b] = vis(mid);
      if (j >= cs.length || b > L) hi = mid; else lo = j + 1;
    }
    return vis(lo)[0];
  }

  function cutFrom(o) {                                                // 이 상자에서 넘는 것 → 다음 상자로 갈 단락들(잘린 뒷부분 포함). 안 넘치면 null
    const h = holder(o), L = limitOf(o), ps = paras(h);
    const i = ps.findIndex(p => p.getBoundingClientRect().bottom > L);
    if (i < 0) return null;
    const p = ps[i], rest = ps.slice(i + 1);
    let p2 = null, whole = !!(p.dataset.keep && i > 0);               // 쪼개지 않기 — 문단 전체를 다음 상자로(상자 첫 문단이면 어쩔 수 없이 자른다)
    if (whole) { /* 자르지 않는다 */ }
    else if (p.dataset.jcDone) {                                       // 컴포저 단락 — 줄마다 span
      const lines = [...p.children];
      let k = lines.findIndex(s => s.getBoundingClientRect().bottom > L);
      // 행 유지(인디자인 「처음 N행 · 마지막 N행」) — 상자 끝에 처음 몇 줄만, 다음 상자에 마지막 몇 줄만 남지 않게
      const kf = +p.dataset.keepFirst || 0, kl = +p.dataset.keepLast || 0;
      if (k > 0 && kl && lines.length - k < kl) k = lines.length - kl;   // 넘어갈 줄이 모자라면 더 넘긴다
      if (k > 0 && kf && k < kf && i > 0) k = 0;                       // 남을 줄이 모자라면 통째로
      if (k === 0) whole = true;
      else if (k > 0) { p2 = p.cloneNode(false); [...p.children].slice(k).forEach(s => p2.appendChild(s)); }
    } else {                                                           // 브라우저가 꺾은 단락 — 넘는 줄의 첫 글자에서 자른다
      const cs = charsOf(p), j = firstOver(cs, L);
      if (j < cs.length) {
        let before = false;
        for (let q = 0; q < j && !before; q++) before = bottomOf(cs[q]) != null;
        if (!before) whole = true;
        else {
          const r = document.createRange();
          if (cs[j][1] < 0) r.setStartBefore(cs[j][0]); else r.setStart(cs[j][0], cs[j][1]);
          r.setEnd(p, p.childNodes.length);
          p2 = p.cloneNode(false);
          p2.appendChild(r.extractContents());
          if (getComputedStyle(p).textAlign === "justify") p.style.textAlignLast = "justify";   // 앞 상자 끝 줄은 단락 끝이 아니다 — 양끝 그대로
        }
      }
    }
    if (whole) {                                                       // 다음 문단과 함께 — 그 앞 문단(번호·발문)이 상자 끝에 혼자 남지 않게 같이 넘긴다
      let s = i;
      for (;;) {                                                       // 쪼개지 않기는 같은 자리 묶음 전체(선지 ①~⑤) · 다음 문단과 함께(번호·발문)
        if (s > 0 && ps[s].dataset.keep && ps[s - 1].dataset.keep && ps[s - 1].dataset.slot === ps[s].dataset.slot) { s--; continue; }
        if (s > 0 && ps[s - 1].dataset.keepNext) { s--; continue; }
        break;
      }
      return ps.slice(s > 0 ? s : i);                                  // 상자가 통째로 비게 되면 그대로(무한히 넘기지 않게)
    }
    if (p2) {
      p2.style.textIndent = "0";                                       // 단락 가운데서 이어진다 — 첫 줄 들여쓰기·앞 간격·위 경계선·글머리 없이
      p2.style.marginTop = "0";
      if (p.style.borderTopStyle) { p2.style.borderTop = "none"; p2.style.paddingTop = "0"; }
      if (getComputedStyle(p).display === "list-item") p2.style.listStyleType = "none";
      if (p.style.borderBottomStyle) { p.style.borderBottom = "none"; p.style.paddingBottom = "0"; }   // 아래 경계선은 단락 끝(뒷부분)에만
      p2.dataset.storyCont = "1";
      return [p2, ...rest];
    }
    return rest.length ? rest : null;
  }

  function put(o, nodes, head, from) {                                 // 이어지는 상자 맨 위에 — 처음이면 빈 그릇을 비우고 첫 상자의 글 모양을 입힌다
    const h = holder(o);
    if (!h) return false;
    if (!o.dataset.storyFilled) {
      paras(h).forEach(e => e.remove());
      const z = o.style.zoom;
      o.setAttribute("style", head.getAttribute("style"));           // 서체·크기·행간·색·정렬 — 배율(zoom)은 이 상자 것
      o.style.zoom = z;
      o.lang = head.lang;
      o.dataset.storyFilled = "1";
    }
    const first = paras(h)[0] || null;
    nodes.forEach(n => h.insertBefore(n, first));
    if (Math.abs(h.offsetWidth - from.offsetWidth) > 0.5) {           // 폭이 다른 상자 — 옮긴 컴포저 단락은 새 폭으로 다시 고른다
      nodes.forEach(p => {
        if (!p.dataset.jcDone) return;
        const lines = [...p.children];
        p.textContent = "";
        lines.forEach((s, i) => { if (i) p.appendChild(document.createTextNode(" ")); while (s.firstChild) p.appendChild(s.firstChild); });
        delete p.dataset.jcDone;
        try { compose(p); } catch (e) { /* 브라우저 줄바꿈 */ }
      });
    }
    return true;
  }

  function markOver(o) {                                               // 끝 상자에서도 넘친다 — 인디자인의 빨간 + (인쇄엔 안 나온다)
    o.dataset.overflow = "1";
    const b = boxOf(o);
    if (getComputedStyle(b).position === "static") b.style.position = "relative";
    const m = document.createElement("span");
    m.className = "story-over";
    m.title = "글이 넘친다 — 이을 상자가 더 없다";
    m.setAttribute("style", "position:absolute;right:0;bottom:0;width:2.4px;height:2.4px;background:#e0245e;color:#fff;font:bold 2.2px/2.4px sans-serif;text-align:center;text-indent:0;letter-spacing:0;z-index:2");
    m.textContent = "+";
    b.appendChild(m);
  }

  function chains(root) {                                              // 이야기마다 [첫 상자, 이어지는 상자(순서대로)…] — 같은 쪽의 첫 상자, 없으면 앞에서 가장 가까운 첫 상자에 붙는다
    const all = [...root.querySelectorAll("[data-story]")];
    const pg = (o) => o.closest("svg[data-tpl]");
    const heads = all.filter(o => seqOf(o) <= 1);
    const by = new Map(heads.map(o => [o, [o]]));
    all.forEach((o, i) => {
      if (seqOf(o) <= 1) return;
      const st = o.dataset.story;
      let hd = heads.find(x => x.dataset.story === st && pg(x) && pg(x) === pg(o));
      for (let j = i - 1; !hd && j >= 0; j--) if (all[j].dataset.story === st && seqOf(all[j]) <= 1) hd = all[j];
      if (hd) by.get(hd).push(o);
    });
    return [...by.values()].map(c => [c[0], ...c.slice(1).sort((a, b) => seqOf(a) - seqOf(b))]);
  }

  function thread(root) {
    for (const ch of chains(root || document)) {
      if (!ch.every(o => holder(o))) continue;
      if (ch.some(o => parseInt(getComputedStyle(holder(o)).columnCount) > 1)) continue;   // 상자 안 다단은 아직 — 브라우저 단 나눔 그대로
      ch.forEach(o => {                                                // 지난번 넘침을 되돌린다 — 그사이 이을 상자가 생겼으면(여러 쪽을 한꺼번에) 그리로 간다
        delete o.dataset.overflow;
        o.querySelectorAll(".story-over").forEach(m => m.remove());
        const rest = o.querySelector(".story-rest");
        if (rest) { const h = holder(o); while (rest.firstChild) h.appendChild(rest.firstChild); rest.remove(); }
      });
      for (let i = 0; i < ch.length; i++) {
        const nodes = cutFrom(ch[i]);
        if (!nodes) continue;
        if (i < ch.length - 1) { put(ch[i + 1], nodes, ch[0], holder(ch[i])); continue; }
        const rest = document.createElement("div");                    // 끝 상자에서도 넘친 줄 — 반쯤 잘린 줄이 보이지 않게 숨겨 둔다(인디자인의 넘친 글)
        rest.className = "story-rest";
        rest.style.display = "none";
        nodes.forEach(n => rest.appendChild(n));
        boxOf(ch[i]).appendChild(rest);
        markOver(ch[i]);
      }
    }
  }

  // ── 자동 크기 바로잡기 (인디자인 텍스트 프레임 「자동 크기 조정 — 높이만」) ──
  // 서버는 글 높이를 어림해(render.text_h) 상자를 키우고 아래 것을 민다. 원고가 바뀌면 어림이 실제와 어긋나 글이 잘리거나 겹친다
  // (02B 다른 원고: 지문이 6.1mm 잘림). 여기서 크롬이 실제로 그린 높이로 상자를 다시 맞추고 아래 것을 민다 — 서버와 같은 규칙:
  //   상자(그린 높이 = 최소 높이) 아래 끝보다 아래에 선 것을, 글이 그린 높이를 넘은 만큼.
  //   부품 안은 원자끼리(가로 위치는 안 본다, 감싸는 면은 늘인다), 지면은 개체끼리(가로로 겹치는 것만, 고정 개체는 그대로).
  // 상자 영역 안에 놓인 것은 밀지 않는다 — 상자를 글보다 크게 그려 그 안에 다른 것을 두면 원고가 길어질 때 덮인다(틀 검사: swap_check 「영역 안」).
  // 렌더러(render.py)가 붙인 표시: 글 div[data-grow](data-h0 설계 · data-hcur 서버 높이) · 원자 g[data-ai] · 개체 g[data-fi].
  const num = (e, k) => parseFloat(e.getAttribute(k)) || 0;
  function shiftY(g, d) {                                              // 그 묶음을 d mm 아래로 — transform 앞에 붙인다
    const t = g.getAttribute("transform") || "";
    const m = /^translate\(0 ([-\d.]+)\) /.exec(t);
    g.setAttribute("transform", m ? `translate(0 ${(+m[1] + d).toFixed(3)}) ${t.slice(m[0].length)}` : `translate(0 ${d.toFixed(3)}) ${t}`);
  }
  function pushOf(r, y) {                                              // 자란 글 r 때문에 위 끝이 y 인 것을 더 밀 양(서버가 어림으로 민 만큼은 뺀다)
    return y >= r.y0 + r.h0 - (r.tol || 0) - 0.01 ? Math.max(0, r.need - r.h0) - (r.hc - r.h0) : 0;   // tol = 줄 높이 30%(render.below_tol)
  }
  function grow(root) {
    const recs = [];
    root.querySelectorAll("div[data-grow]").forEach(div => {
      if (div.dataset.grown) return;
      div.dataset.grown = "1";
      const box = div.firstElementChild, fo = div.parentElement;
      if (!box || !fo || fo.tagName.toLowerCase() !== "foreignobject") return;
      const h0 = +div.dataset.h0, hc = +div.dataset.hcur;
      if (!(hc > 0)) return;
      const fixed = !!box.style.height;                                // 바탕(칠·획)이 있는 상자는 높이를 안 박는다 — 글 크기를 따라 그려진다
      const k = (fixed ? box.getBoundingClientRect().height : fo.getBoundingClientRect().height) / hc;    // 화면 px / mm
      if (!(k > 0)) return;
      const natural = (el) => { const s = el.style.height; el.style.height = "auto"; const v = el.getBoundingClientRect().height / k; el.style.height = s; return v; };
      const need = natural(box);                                       // 글이 실제로 차지하는 높이(여백 포함)
      const shown = fixed ? Math.max(h0, need) : need;                 // 보이는 높이 — 바탕 상자는 글 크기 그대로
      const z = num(fo, "height") / hc;                                // 글 배치 배율(TEXT_ZOOM)
      if (Math.abs(Math.max(shown, h0) - hc) > 0.05) fo.setAttribute("height", (Math.max(shown, h0) * z).toFixed(2));
      if (fixed && Math.abs(shown - hc) > 0.05) box.style.height = shown.toFixed(3) + "px";
      div.dataset.hcur = Math.max(h0, need).toFixed(3);
      const ag = div.closest("g[data-ai]");
      if (ag) recs.push({ag, need, h0, hc, tol: +div.dataset.tol || 0, y0: num(ag, "data-ay"), x0: num(ag, "data-ax"), x1: num(ag, "data-ax") + num(ag, "data-aw")});
    });
    const byPart = new Map();
    for (const r of recs) { const pg = r.ag.parentElement; if (!byPart.has(pg)) byPart.set(pg, []); byPart.get(pg).push(r); }
    const pageRecs = new Map();                                        // 지면(svg) → 자란 개체들
    byPart.forEach((gr, pg) => {
      const atoms = [...pg.children].filter(e => e.matches && e.matches("g[data-ai]"));
      const bot = (e) => num(e, "data-ay") + num(e, "data-ady") + num(e, "data-ah");
      const before = Math.max(...atoms.map(bot));
      for (const e of atoms) {
        const y = num(e, "data-ay"), h0 = num(e, "data-ah0"), x0 = num(e, "data-ax"), x1 = x0 + num(e, "data-aw");
        let dy = 0, dh = 0;
        for (const r of gr) {
          if (r.ag === e) { dh += Math.max(r.h0, r.need) - num(e, "data-ah"); continue; }
          const d = pushOf(r, y);
          if (d) { dy += d; continue; }
          if (e.dataset.at === "rect" && y <= r.y0 + 0.01 && y + h0 >= r.y0 + r.h0 - 0.01 && x0 <= r.x0 + 0.01 && x1 >= r.x1 - 0.01) {
            const g = Math.max(0, r.need - r.h0) - (r.hc - r.h0), rc = e.querySelector("rect");   // 감싸는 면 → 늘인다(모서리 둥근 면·경로는 그대로)
            if (rc && Math.abs(g) > 0.01) { rc.setAttribute("height", (num(rc, "height") + g).toFixed(3)); dh += g; }
          }
        }
        if (Math.abs(dy) > 0.01) { shiftY(e, dy); e.setAttribute("data-ady", (num(e, "data-ady") + dy).toFixed(3)); }
        if (Math.abs(dh) > 0.01) e.setAttribute("data-ah", (num(e, "data-ah") + dh).toFixed(3));
      }
      const it = pg.closest("g[data-fi]");
      if (!it) return;
      const svg = it.closest("svg"), s = num(it, "data-s") || 1, iy = num(it, "data-y0");
      if (!pageRecs.has(svg)) pageRecs.set(svg, []);
      if (atoms.length === 1 && gr.length === 1) {                     // 글상자 하나 = 개체 하나 — 같은 규칙을 지면 자리로
        const r = gr[0];
        pageRecs.get(svg).push({it, r: {need: r.need * s, h0: r.h0 * s, hc: r.hc * s, tol: r.tol * s, y0: iy + r.y0 * s}});
      } else {
        const after = Math.max(...atoms.map(bot));                     // 여러 원자 부품 — 부품 아래 끝이 늘어난 만큼
        if (Math.abs(after - before) > 0.01) pageRecs.get(svg).push({it, d: (after - before) * s, b0: iy + num(it, "data-h0")});
      }
    });
    pageRecs.forEach((gr, svg) => {
      const all = [...svg.querySelectorAll("g[data-fi]")].filter(g => g.hasAttribute("data-y0"));
      const pr = svg.getAttribute("data-push") === "row" ? svg : svg.closest("[data-push]");
      const row = !!pr && pr.getAttribute("data-push") === "row";
      const [tx0, tx1] = ((pr && pr.getAttribute("data-tx")) || "0 9999").split(" ").map(Number);   // 본문 영역 — 여백 밖 장식(옆 탭)은 안 민다
      for (const e of all) {
        if (e.hasAttribute("data-fixed")) continue;
        const y = num(e, "data-y0"), x0 = num(e, "data-x"), x1 = x0 + num(e, "data-w");
        let dy = 0;
        for (const g of gr) {
          if (g.it === e) continue;
          const gx0 = num(g.it, "data-x"), gx1 = gx0 + num(g.it, "data-w");
          const inside = x0 < tx1 - 0.01 && x1 > tx0 + 0.01;
          if (!(row && inside) && !(x0 < gx1 - 0.01 && x1 > gx0 + 0.01)) continue;   // 가로로 겹치는 것만 — 「모두 밀기」면 본문 영역 안 아래 것 전부
          dy += g.r ? pushOf(g.r, y) : (y >= g.b0 - 0.01 ? g.d : 0);
        }
        if (Math.abs(dy) > 0.01) { shiftY(e, dy); e.setAttribute("data-dy", (num(e, "data-dy") + dy).toFixed(2)); }
      }
    });
  }

  function dropSpares(root) {                                          // 덧쪽(render.story_spares) 중 글이 안 흘러온 쪽은 지운다
    (root || document).querySelectorAll("svg[data-spare]").forEach(svg => {
      const bx = [...svg.querySelectorAll("[data-story]")].filter(o => o.dataset.story === svg.dataset.spare);
      if (bx.some(o => o.dataset.storyFilled)) return;
      (svg.closest(".p") || svg).remove();
    });
  }

  function composeAll(root) {
    try { tsume(root || document); } catch (e) { /* 못 하면 자간 축소 없이 */ }
    (root || document).querySelectorAll("[data-jc]").forEach(p => { try { compose(p); } catch (e) { /* 못 하면 브라우저 줄바꿈 */ } });
    try { thread(root || document); } catch (e) { /* 못 하면 첫 상자 안에서 잘린 채 */ }
    try { dropSpares(root || document); } catch (e) { /* 못 하면 빈 덧쪽이 남는다 */ }
    try { grow(root || document); } catch (e) { /* 못 하면 서버 어림 높이 그대로 */ }
  }

  window.unitsCompose = composeAll;
  try {                                                                // 잇는 상자 맨 위 문단은 「앞 간격」을 버린다(인디자인 — 프레임 맨 위)
    const css = document.createElement("style");
    css.textContent = "[data-story] p[data-slot]:first-child{margin-top:0!important}";
    (document.head || document.documentElement).appendChild(css);
  } catch (e) { /* 그대로 */ }
  if (document.readyState !== "loading" && document.querySelector("[data-jc],[data-tsume]") && document.fonts) {
    document.fonts.ready.then(() => composeAll(document));
  } else if (document.fonts) {
    document.addEventListener("DOMContentLoaded", () => document.fonts.ready.then(() => composeAll(document)));
  }
})();
