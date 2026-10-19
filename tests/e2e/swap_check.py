"""다른 원고로 넣어 보기 — 재현 단위의 틀에 길이가 다른 원고를 바깥 시스템처럼(API) 넣고 깨지는 곳을 센다.

    python3 tests/e2e/swap_check.py <단위> [rotate|long|short]

  rotate  자리마다 원고를 한 칸씩 밀어 넣는다(1번 문항 자리에 2번 문항 글 …) — 길이가 다른 실제 원고
  long    글마다 첫 문장을 한 번 더 붙인다(길어진 원고)
  short   글마다 앞 절반만(짧아진 원고)
  file    SWAP_CONTENT=<json> 의 원고로 그 자리들을 바꿔 넣는다(다른 회차의 실제 원고 — 바깥 시스템이 보낼 꼴)

잰다(크롬이 실제로 그린 결과 — PDF 와 같은 코드 · units_compose.js 까지 돈 뒤):
  잘림    글상자 안 글이 상자 아래 끝을 넘어 잘린 상자(자동 크기 조정 꺼짐·글 잇기 끝 상자)
  넘침    글 잇기 끝 상자에서도 넘친 이야기(빨간 +)
  겹침    서로 다른 글상자의 글이 겹친 곳
  면 밖   글이 면 아래 끝을 넘은 곳
단위 데이터는 replay.py 가 남긴 ~/.cache/yone-replay/<단위>/catalog 를 쓴다(그 단위를 check 로 한 번 돌린 뒤).
"""
import json, os, re, subprocess, sys, tempfile, time, urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
PY = sys.executable
from cdp import free_port                                                 # noqa: E402
PORT = int(os.environ.get("SWAP_PORT") or 0) or free_port()            # 빈 포트 — 병렬
BASE = f"http://127.0.0.1:{PORT}"
CHROME = os.environ.get("YONE_VIV_BROWSER") or "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

unit = sys.argv[1]
mode = sys.argv[2] if len(sys.argv) > 2 else "rotate"
data = os.path.expanduser(f"~/.cache/yone-replay/{unit}/catalog")
if not os.path.isdir(data):
    sys.exit(f"데이터 없음 — 먼저 python3 tests/e2e/replay.py {unit} check")


def each(f, v):
    """글 하나 · 문항 하나(흐름 틀: [[자리, 글], …] 또는 {자리: 글}) 안의 글마다 f"""
    if isinstance(v, list):
        return [[x[0], f(x[1])] if isinstance(x, list) else x for x in v]
    if isinstance(v, dict):
        return {k: f(x) if isinstance(x, str) else x for k, x in v.items()}
    return f(v)


def vary(content):
    if mode == "file":                                                   # 다른 회차 원고 — 파일의 자리만 바꿔 넣고 나머지는 그대로
        return dict(content, **json.load(open(os.environ["SWAP_CONTENT"], encoding="utf-8")))
    out = {}
    for k, v in content.items():
        vs = list(v) if isinstance(v, list) else [v]
        if mode == "rotate":
            vs = vs[1:] + vs[:1] if len(vs) > 1 else vs
        elif mode == "long":
            def longer(t):
                m = re.match(r"(.+?[.?!。])(\s|$)", t)
                return t + " " + m.group(1) if m and len(t) > 40 else t
            vs = [each(longer, t) for t in vs]
        elif mode == "short":
            vs = [each(lambda t: t[: max(1, len(t) // 2)] if len(t) > 40 else t, t) for t in vs]
        out[k] = vs
    return out


CHECK = r"""
(document.fonts ? document.fonts.ready : Promise.resolve()).then(() => setTimeout(() => {
  const res = {clip: [], over: [], overlap: [], off: [], inside: []};
  document.querySelectorAll('.p').forEach((pg, pi) => {
    const pr = pg.getBoundingClientRect();
    const boxes = [];
    pg.querySelectorAll('foreignObject').forEach(fo => {
      const div = fo.firstElementChild; if (!div) return;
      const g = fo.closest('[data-fi]'); const fi = g ? g.dataset.fi : '?';
      const r = fo.getBoundingClientRect();
      // 보이는 글자만 — 보이지 않는 임시 글(data-ref)과 감춘 글(글 폭 칸 · overflow 숨김 칸 · 투명 글) 속은 빼고
      const root = div.firstElementChild || div, rs = [], range = document.createRange();
      const tw = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {acceptNode: (n) => {
        for (let e = n.parentElement; e && e !== root; e = e.parentElement) {
          const c = getComputedStyle(e);
          if (c.overflow === 'hidden' || c.visibility === 'hidden' || c.color === 'rgba(0, 0, 0, 0)' || c.color === 'transparent') return NodeFilter.FILTER_REJECT;
        }
        return n.data.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT; }});
      for (let n; (n = tw.nextNode());) { range.selectNodeContents(n); rs.push(...[...range.getClientRects()].filter(x => x.width > 0.5 && x.height > 0.5)); }
      if (!rs.length) return;
      const top = Math.min(...rs.map(x => x.top)), bot = Math.max(...rs.map(x => x.bottom));
      const left = Math.min(...rs.map(x => x.left)), right = Math.max(...rs.map(x => x.right));
      const k = pr.width / 210;                                     // 화면 px / mm (쪽 폭 210 기준은 아래에서 바로잡는다)
      const txt = (div.textContent || '').trim().slice(0, 24);
      const cs = getComputedStyle(div);
      if (bot > r.bottom + 1 && cs.overflowY !== 'visible' && !div.querySelector('.story-rest')) res.clip.push([pi + 1, fi, txt, ((bot - r.bottom) / k).toFixed(1)]);
      if (bot > pr.bottom + 1) res.off.push([pi + 1, fi, txt]);
      boxes.push({fi, txt, rs: rs.filter(x => x.bottom <= r.bottom + 1)});             // 줄 상자들(잘려 안 보이는 줄은 빼고)
    });
    // 틀 검사 「영역 안」 — 자동 크기 글상자의 그린 영역 안(글 위 끝 아래)에 다른 개체가 들어가 있다: 원고가 길어지면 상자 안에서 자라 덮는다(밀지 않는다)
    const its = [...pg.querySelectorAll('g[data-fi]')].filter(g => g.hasAttribute('data-y0'));
    const num = (e, k) => parseFloat(e.getAttribute(k)) || 0;
    // 위험 = 글의 실제 아래 끝과 상자(그린 높이) 아래 끝 사이에 위 끝이 놓인 개체(글 옆에 나란히 선 번호 등은 빼고)
    const kk = pr.width / 210;
    for (const t of its) {
      const dv = t.querySelector('div[data-grow]');
      if (!dv || !dv.dataset.slot || t.querySelectorAll('g[data-ai]').length > 1) continue;      // 원고 자리 글상자만(고정 글은 길이가 안 바뀐다)
      const bx = boxes.find(b => b.fi === t.dataset.fi);
      if (!bx || !bx.rs.length) continue;
      const tb = Math.max(...bx.rs.map(x => x.bottom)), tl = Math.min(...bx.rs.map(x => x.left)), tr = Math.max(...bx.rs.map(x => x.right));
      const ty = num(t, 'data-y0') + num(t, 'data-dy'), th = num(t, 'data-h0'), top = pr.top + ty * kk, dbot = top + th * kk;   // 밀린 뒤 자리(data-dy — 서버·크롬이 민 양)
      for (const o of its) {
        if (o === t) continue;
        const r2 = o.getBoundingClientRect();
        if (r2.top >= tb - 0.5 && r2.top < dbot - ((+dv.dataset.tol || 0) + 0.05) * kk && r2.left < tr - 1 && r2.right > tl + 1)   // 줄 높이 30% 안은 「아래 것」(밀린다)
          res.inside.push([pi + 1, t.dataset.fi, (t.textContent || '').trim().slice(0, 16), o.dataset.fi, (o.textContent || '').trim().slice(0, 12), ((dbot - r2.top) / kk).toFixed(1)]);
      }
    }
    pg.querySelectorAll('[data-overflow]').forEach(o => { const g = o.closest('[data-fi]'); res.over.push([pi + 1, g ? g.dataset.fi : '?', (o.textContent || '').trim().slice(0, 24)]); });
    for (let i = 0; i < boxes.length; i++) for (let j = i + 1; j < boxes.length; j++) {
      const a = boxes[i], b = boxes[j];
      if (a.fi === b.fi) continue;
      const hit = a.rs.some(x => b.rs.some(y => Math.min(x.right, y.right) - Math.max(x.left, y.left) > 2 && Math.min(x.bottom, y.bottom) - Math.max(x.top, y.top) > 2));
      if (hit) res.overlap.push([pi + 1, a.fi, a.txt, b.fi, b.txt]);
    }
  });
  document.getElementById('swap-out').textContent = JSON.stringify(res);
}, 800));
"""


def run_check(plan, content):
    from core.units import pdf
    req = urllib.request.Request(BASE + "/api/units/fill", data=json.dumps({"plan": plan["id"], "content": content, "as": "svg"}).encode(),
                                 headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=300))
    if os.environ.get("SWAP_PDF") and content is not plan["content"]:               # 다른 원고 판을 PDF 로 남긴다(눈으로 보기)
        pdf.to_pdf(r["svgs"], 210, 297, os.environ["SWAP_PDF"])
    html = pdf.html_of(r["svgs"], 210, 297).replace("</body>", f'<pre id="swap-out"></pre><script>{CHECK}</script></body>')
    fd, path = tempfile.mkstemp(suffix=".html"); os.write(fd, html.encode("utf-8")); os.close(fd)
    out = subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--virtual-time-budget=15000", "--window-size=1200,1700", "--dump-dom", "file://" + path],
                         capture_output=True, text=True, timeout=300).stdout
    os.remove(path)
    i = out.find('<pre id="swap-out">')
    return json.loads(out[i + 19: out.find("</pre>", i)] or "{}"), r


def main():
    plans = json.load(open(os.path.join(data, "_units", "plans.json"), encoding="utf-8"))
    plan = next((p for p in plans if p.get("content")), None)
    if not plan:
        sys.exit("원고가 든 문서가 없다")
    env = dict(os.environ, YONE_CATALOG_DIR=data, YONE_AUTH="off")
    log = open(os.path.join(tempfile.gettempdir(), f"swap_{PORT}.log"), "w")
    srv = subprocess.Popen([PY, "-u", "studio_server.py", "--port", str(PORT)], cwd=REPO, env=env, stdout=log, stderr=log)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen(BASE + "/api/v1/health", timeout=2); break
            except Exception:
                time.sleep(0.5)
        base, _ = run_check(plan, plan["content"])                    # 원본 원고 판 — 디자인이 원래 붙여 둔 글은 빼려고
        res, r = run_check(plan, vary(plan["content"]))
        print(f"{unit} · {mode} · 쪽 {len(r['svgs'])} · 넣은 자리 {r['report'].get('filled')} · 보고 {r['report']}")
        key = lambda k, x: tuple(x[:2]) if k != "overlap" else (x[0], x[1], x[3])
        for k, name in (("clip", "잘림"), ("over", "넘침"), ("overlap", "겹침"), ("off", "면 밖")):
            had = {key(k, x) for x in base.get(k) or []}
            v = [x for x in res.get(k) or [] if key(k, x) not in had]
            print(f"  {name} {len(v)}" + (f"  (원본 원고에서도 {len(had)})" if had else ""))
            for x in v[:15]:
                print("    ", x)
        ins = base.get("inside") or []                                   # 틀 검사 — 원본 원고 판에서(틀 자체의 문제)
        print(f"  틀 검사 「영역 안」 {len(ins)}" + ("  — 자동 크기 글상자 영역 안에 다른 개체: 상자를 글 높이로 줄이거나 개체를 상자 아래로" if ins else ""))
        for x in ins[:15]:
            print("    ", x)
        warns = [w for w in r.get("warnings") or [] if "넘" in w or "길다" in w]
        if warns:
            print("  편집기 경고", len(warns), warns[:5])
    finally:
        srv.kill()


main()
