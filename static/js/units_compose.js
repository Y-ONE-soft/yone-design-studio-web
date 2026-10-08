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
      else while (j < chars.length && !isSp(chars[j][2]) && !(CJK.test(chars[j - 1][2]) && CJK.test(chars[j][2]))) j++;
      const seg = chars.slice(i, j);
      out.push({space: sp, a: seg[0], b: seg[seg.length - 1], breakable: sp && seg.some(c => c[2] === " "), n: sp ? seg.length : 0, seg: sp ? seg : null,
                c: seg.length});                                                // 글자 수 — 인디자인 자간은 글자마다 붙는다
      if (!sp && j < chars.length && CJK.test(chars[j - 1][2]) && CJK.test(chars[j][2]))
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

  function compose(p) {
    if (p.dataset.jcDone) return;
    const OK = new Set(["span", "b", "i", "u", "s", "sup", "sub"]);        // 글 안 표·떠 있는 그림 등은 건드리지 않는다 — inline-block 개체 속(SVG)은 괜찮다
    if ([...p.querySelectorAll("*")].some(e => !OK.has(e.tagName.toLowerCase()) && !(e.parentElement && e.parentElement.closest("span[style*='inline-block']")))) return;
    // 인디자인 「양끝 정렬」 설정 — 낱말 간격 최소·최대 %(공백 글리프 폭 기준) · 자간 최소·최대 ‰em · 줄이기 비용 배수 · 줄 하나 비용 · 끝 줄 자간 최소 ‰em.
    // 원본 d1 PDF 에서 읽은 규칙(2026-10-08 scratch justify-analysis): 낱말 간격은 100%(희망) → 133%(최대)까지 먼저 늘고, 모자라면 자간이 는다
    // (낱말은 133% 에 멈춤 — 4~37쪽 줄 87개 모두 0.33×공백 ±0.6‰). 줄일 땐 낱말은 100% 아래로 안 가고 자간만 준다(-1~-5‰ 관찰). 글리프 비율 100%.
    // 공백 기준 = 서체의 U+0020 폭(Noto CJK KR 224/1000 — 인디자인이 실제로 놓는 locl 공백 280 이 아니다). 줄 끝 맞춤 4·5·8·9·16·17쪽 60/62.
    const [wmn, wmx, lmn, lmx, sw, lp, lastLmn] = (p.dataset.jc || "100,133,-8,120,1,5,-10").split(",").map(Number);
    const save = [p.style.whiteSpace, p.style.textAlign];
    p.style.whiteSpace = "nowrap";
    p.style.textAlign = "left";                                         // 늘이기 전 자연 폭으로 잰다
    const toks = tokens(p);
    if (toks.length < 3) { p.style.whiteSpace = save[0]; p.style.textAlign = save[1]; return; }
    for (const t of toks) if (!t.zero) t.w = rangeOf(t).getBoundingClientRect().width;
    const rect = p.getBoundingClientRect();
    const k = rect.width / (p.offsetWidth || 1);                         // 화면 px / 이 단락의 px (zoom·확대 포함)
    const cs = getComputedStyle(p);
    const W = rect.width - (parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight)) * k;
    const indent = parseFloat(cs.textIndent) * k || 0;
    const em = parseFloat(cs.fontSize) * k;
    const ls = parseFloat(cs.letterSpacing) * k || 0, wsp = parseFloat(cs.wordSpacing) * k || 0;   // 단락 자간 · 낱말 간격(보정) — 공백 글리프 폭을 꺼내려고
    for (const t of toks) if (t.space && !t.zero) t.sp0 = Math.max(0, t.w - t.n * (ls + wsp));       // 공백 글리프 폭 합 = 낱말 간격 % 의 기준
    // 한국어 꼴로 감싼 공백(렌더러 ko_spaces — 0.280em)도 기준은 서체의 U+0020 폭(0.224em)이다: 인디자인이 그렇게 늘린다
    if (p.querySelector("span[lang='ko']")) {
      const m = (lang, s) => { const e = document.createElement("span"); e.lang = lang; e.style.whiteSpace = "pre"; e.textContent = s; p.appendChild(e);
                               const w = e.getBoundingClientRect().width; e.remove(); return w; };
      const g = (lang) => m(lang, "x x") - m(lang, "xx") - ls - wsp;
      const gk = g("ko"), r = gk > 0 ? g("en") / gk : 1;
      for (const t of toks) if (t.space && !t.zero && t.a[1] >= 0) {
        const l = t.a[0].parentElement && t.a[0].parentElement.closest("[lang]");
        if (l && l.lang === "ko") t.sp0 *= r;
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
          bad = last ? 0 : Math.min(10000, 100 * Math.pow(Y > 0 ? (lw - L) / Y : 10, 3));
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
                  nc: sum(t => t.c) + (lead ? g0.n - 1 : 0)});
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
      else if (!isLast(li)) { xw = Math.min(slack, ln.S0 * (wmx - 100) / 100); dl = (slack - xw) / ng; }
      if (!isLast(li) || slack < 0) {
        st += "text-align-last:justify;";                               // 반올림 찌꺼기만 크롬이 공백에 나눈다
        if (ln.nsp && xw) st += `word-spacing:${((wsp + xw / ln.nsp) / k).toFixed(4)}px;`;
        // 자간은 끝 글자 뒤에도 붙으므로(크롬) 그만큼 줄을 넓혀 끝 글자 자리를 지킨다 — 인디자인은 글자 사이(n-1)에만
        if (Math.abs(dl) > 0.001) st += `letter-spacing:${((ls + dl) / k).toFixed(4)}px;margin-right:${(-dl / k).toFixed(4)}px;`;
      }
      sp.setAttribute("style", st);
      sp.appendChild(frag[li]);
      p.appendChild(sp);
    });
    p.dataset.jcDone = "1";
  }

  function composeAll(root) {
    (root || document).querySelectorAll("[data-jc]").forEach(p => { try { compose(p); } catch (e) { /* 못 하면 브라우저 줄바꿈 */ } });
  }

  window.unitsCompose = composeAll;
  if (document.readyState !== "loading" && document.querySelector("[data-jc]") && document.fonts) {
    document.fonts.ready.then(() => composeAll(document));
  } else if (document.fonts) {
    document.addEventListener("DOMContentLoaded", () => document.fonts.ready.then(() => composeAll(document)));
  }
})();
