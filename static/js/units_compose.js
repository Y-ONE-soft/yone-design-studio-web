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
    const w = document.createTreeWalker(p, NodeFilter.SHOW_TEXT | NodeFilter.SHOW_ELEMENT);
    let n;
    while ((n = w.nextNode())) {
      if (n.nodeType === 3) { for (let i = 0; i < n.data.length; i++) chars.push([n, i, n.data[i]]); }
      else if (!n.firstChild && getComputedStyle(n).display === "inline-block") chars.push([n, -1, "\ufffc"]);
    }
    const out = [];
    let i = 0;
    while (i < chars.length) {
      const sp = isSp(chars[i][2]);
      let j = i + 1;
      if (sp) while (j < chars.length && isSp(chars[j][2])) j++;
      else while (j < chars.length && !isSp(chars[j][2]) && !(CJK.test(chars[j - 1][2]) && CJK.test(chars[j][2]))) j++;
      const seg = chars.slice(i, j);
      out.push({space: sp, a: seg[0], b: seg[seg.length - 1], breakable: sp && seg.some(c => c[2] === " "), n: sp ? seg.length : 0});
      if (!sp && j < chars.length && CJK.test(chars[j - 1][2]) && CJK.test(chars[j][2]))
        out.push({space: true, zero: true, breakable: true, n: 0, w: 0});    // 한글 음절 사이 — 폭 0, 여기서도 꺾을 수 있다
      i = j;
    }
    while (out.length && out[0].space) out.shift();
    while (out.length && out[out.length - 1].space) out.pop();
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
    if (p.querySelector(":not(span):not(b):not(i):not(u):not(s):not(sup):not(sub)")) return;   // 글 안 그림·표 등은 건드리지 않는다
    // 낱말 간격 최소 % · 최대 % · 줄이기 비용 배수 · 줄 하나 비용 · 끝 줄 최소 % — 원본 인디자인 지문 4개(줄 끝 32개)에 맞춘 값
    // (scratch jc_fit.py: 브라우저 그대로 17/32 → 이 값 30/32). 인디자인은 많이 늘리고 조금 줄이며, 끝 줄은 89.5% 까지 줄여 넣는다
    // (단위 02 지문 1 끝 줄 89.9% 는 줄여 넣고, 단위 06 문장 (D) 88% 는 다음 줄로 넘김 — 2026-10-08).
    const [mn, mx, sw, lp, lastMn] = (p.dataset.jc || "92,400,0.5,5,89.5").split(",").map(Number);
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
    p.style.whiteSpace = save[0];
    p.style.textAlign = save[1];

    // 줄 끝 후보 = 끊을 수 있는 공백. 줄 = 후보 a 다음 낱말부터 후보 b 앞 낱말까지.
    const brk = [-1];
    toks.forEach((t, i) => { if (t.space && t.breakable) brk.push(i); });
    brk.push(toks.length);
    const best = new Array(brk.length).fill(Infinity), from = new Array(brk.length).fill(-1);
    best[0] = 0;
    for (let a = 0; a < brk.length - 1; a++) {
      if (best[a] === Infinity) continue;
      let L = 0, Y = 0, Z = 0, nsp = 0;
      const lw = W - (a === 0 ? indent : 0);
      for (let b = a + 1; b < brk.length; b++) {
        // a 다음 ~ b 앞까지 더한다
        const s = brk[b - 1] + 1, e = brk[b];
        for (let i = (b === a + 1 ? brk[a] + 1 : s - 1); i < e; i++) {
          const t = toks[i];
          L += t.w;
          if (t.space) { Y += t.w * (mx - 100) / 100; Z += t.w * (100 - mn) / 100; nsp += t.n; }
        }
        const last = b === brk.length - 1;
        let bad;
        if (L <= lw) bad = last ? 0 : Math.min(10000, 100 * Math.pow(Y > 0 ? (lw - L) / Y : 10, 3));
        else {
          const z = last ? Z * (100 - lastMn) / (100 - mn) : Z;          // 끝 줄은 더 줄일 수 있다
          const r = z > 0 ? (lw - L) / z : -10;
          if (r < -1) break;                                           // 더 붙이면 줄여도 안 들어간다
          bad = last ? 0 : Math.min(10000, sw * 100 * Math.pow(-r, 3));
        }
        const dem = Math.pow(lp + bad, 2);
        if (best[a] + dem < best[b]) { best[b] = best[a] + dem; from[b] = a; }
      }
    }
    if (best[brk.length - 1] === Infinity) return;                      // 못 고르면 브라우저 줄바꿈 그대로
    const cut = [];
    for (let b = brk.length - 1; b > 0; b = from[b]) cut.unshift(b);

    // 줄마다 블록으로 — 앞줄은 양끝까지, 줄여야 들어가는 줄은 그만큼 낱말 간격을 줄인다. 마지막 줄은 그대로.
    const lines = [];
    let s = 0;
    for (const b of cut) {
      const e = brk[b];
      const ws = toks.slice(s, e);
      lines.push({first: toks[s], last: toks[e - 1], L: ws.reduce((x, t) => x + t.w, 0), nsp: ws.filter(t => t.space).reduce((x, t) => x + t.n, 0),
                  glue: e < toks.length ? toks[e] : null});
      s = e + 1;
    }
    const frag = [];
    lines.forEach((ln, li) => {
      const r = document.createRange();
      setA(r, ln.first.a);
      setB(r, ln.last.b);
      frag.push(r.cloneContents());
    });
    const isLast = (li) => li === lines.length - 1;
    const lw0 = (li) => W - (li === 0 ? indent : 0);
    p.textContent = "";
    lines.forEach((ln, li) => {
      const sp = document.createElement("span");
      let st = "display:block;" + (li ? "text-indent:0;" : "");
      if (!isLast(li)) st += "text-align-last:justify;";
      const over = ln.L - lw0(li);                                     // 줄여야 들어가는 줄 — 끝 줄도(인디자인은 끝 줄을 줄여 넣는다)
      if (over > 0 && ln.nsp) st += `word-spacing:${(-over / ln.nsp / k).toFixed(4)}px;`;
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
