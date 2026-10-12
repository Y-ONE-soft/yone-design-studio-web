"""등록된 편집기 제작 카드의 면 이름 고치기 — 관리 카드 「원고 넣기」로 편집기에서 열고(카드의 문서 묶음을 들여옴 · 카드 연결도 같이),
이름 없는 「한 번만」 면에 구성 이름을 붙인 뒤 「관리에 등록」으로 같은 카드를 다시 그린다. 그다음 등록 PDF 맞대기(join.judge).

    python3 tests/e2e/replay/정본-최종/rename.py workbook/xe3a03cd7
    RENAME_BASE=https://yos-studio.fly.dev python3 …/rename.py workbook/xe3a03cd7     배포서버의 카드(배포는 새 카드만 옮긴다 — 있던 카드 고침은 그 서버에서 다시 등록)
"""
import json, os, subprocess, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import join                                                              # noqa: E402 — 같은 빈 편집기 데이터 · 서버 · 이름 · 맞대기
from mkpage import S                                                     # noqa: E402

card = sys.argv[1]
series, _, did = card.partition("/")
os.makedirs(join.OUT, exist_ok=True)
counts = []
for g in join.ORDER:                                                     # 구성 문서마다 쪽 수 — 잇기 때 내보낸 묶음에서
    counts.append(len(json.load(open(os.path.join(join.OUT, f"구성_{g}.json"), encoding="utf-8"))["pages"]))
st = [S("관리 카드 「원고 넣기」 — 편집기에서 연다", 1500), {"until": "docPages().length > 0 && page", "wait": 800},
      {"clickif": {"at": "#tg-side", "when": "!document.querySelector('#side') || !document.querySelector('#side').offsetParent"}, "wait": 1000},
      {"js": "(() => '열린 문서 쪽 ' + docPages().length + ' · 카드 ' + JSON.stringify(plan.catalog))()"}]
st += join.name_steps(counts)
DOCNAME = os.environ.get("RENAME_DOCNAME", "")                          # 문서 이름 바로잡기(2026-10-11 들여오기 버그로 「logo_back.svg」가 됐다)
if DOCNAME:
    st += [S(f"문서 이름 「{DOCNAME}」", 900), {"fill": {"at": "#plname", "value": DOCNAME}, "wait": 1500},
           {"js": f"(() => {{ if (plan.name !== {json.dumps(DOCNAME)}) throw new Error('문서 이름 안 들어감 ' + plan.name); return '문서 이름 ' + plan.name; }})()"}]
SKIN = os.environ.get("RENAME_SKIN", "base")                              # 문서 브랜드 — 비어 있으면 그 편집기의 첫 브랜드로 그린다(배포서버에서 스타일이 빠졌다 2026-10-11)
st += [S(f"문서 패널 — 브랜드 「{SKIN}」", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"pick": {"at": "#side #s-skin", "value": SKIN}, "wait": 1500},
       {"js": f"(() => {{ if (plan.skin !== {json.dumps(SKIN)}) throw new Error('브랜드 안 들어감 ' + plan.skin); return '브랜드 ' + plan.skin; }})()"}]
st += [S("원고 자리 글 → «자리 이름» (틀에는 책 글을 두지 않는다)", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"click": "#side #s-slot-names", "wait": 2000},
       {"until": "/데이터 필드 \\d+곳/.test(document.querySelector('#st').textContent)", "wait": 500},
       {"js": "(() => { const bad = docPages().flatMap(p => (p.items || []).filter(it => it.atom && it.atom.t === 'text' && it.atom.bind && !String(it.atom.bind).startsWith('sys.') && it.atom.text !== '«' + it.atom.bind + '»')); if (bad.length) throw new Error('자리 이름 안 된 곳 ' + bad.length); return '원고 자리 모두 «자리 이름»'; })()"}]
st += [S("관리에 등록 — 같은 카드를 다시 그린다", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"pick": {"at": "#side #s-reg-series", "value": series}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
st += [{"until": "/등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 30
st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
              "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]
REMOTE = os.environ.get("RENAME_BASE")
if REMOTE:
    join.BASE = REMOTE.rstrip("/")
    srv = None
else:
    join.fresh_data()
    srv = join.server()
try:
    sf = os.path.join(join.OUT, "rename_steps.json")
    json.dump(st, open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:                                                                 # 카드 「원고 넣기」 주소 → 편집기가 문서 묶음을 들여오고 그 문서 주소로 보낸다
        urllib.request.build_opener(_NoRedirect).open(f"{join.BASE}/units?design={card}")
        sys.exit("문서 주소로 안 보냄")
    except urllib.error.HTTPError as e:
        start = join.BASE + e.headers["Location"] if e.headers.get("Location", "").startswith("/") else e.headers.get("Location")
    print("문서 주소", start)
    r = subprocess.run([join.PY, "tests/e2e/rec.py", start, sf, os.path.join(join.OUT, "rename.mp4"), "1600", "1000", "8"],
                       cwd=join.REPO, env=dict(os.environ, REC_FAST="1"), capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(join.OUT, "rename.log"), "w").write(log)
    print("\n".join(ln for ln in log.splitlines() if "js →" in ln or "ERR" in ln))
    if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
        sys.exit("면 이름·등록 실패 — " + os.path.join(join.OUT, "rename.log"))
finally:
    if srv:
        srv.kill()
if REMOTE:                                                               # 배포서버 — 등록된 PDF 를 내려받아 맞댄다
    ref = os.path.join(join.OUT, "remote_reference.pdf")
    urllib.request.urlretrieve(f"{join.BASE}/catalog/pdf/{series}/{did}", ref)
else:
    ddir = os.path.join(join.DATA, series, "designs", did)
    dj = json.load(open(os.path.join(ddir, "design.json"), encoding="utf-8"))
    print("design.json", {k: dj.get(k) for k in ("name", "pages", "updated")})
    ref = os.path.join(ddir, "참고", "reference.pdf")
print("판정: 통과" if join.judge(ref) else "판정: 실패")
