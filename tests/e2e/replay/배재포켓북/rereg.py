"""등록된 배재1 포켓북 템플릿 다시 등록 — 관리 카드 「원고 넣기」로 편집기에서 열고(문서 묶음을 들여옴 · 카드 연결도 같이),
암기 TEST 페이지에 「두 페이지짜리」(펼침면 상위 페이지)를 켠 뒤 「관리에 등록」으로 같은 카드를 다시 그린다. 그다음 등록 PDF 맞대기(join.judge_reg).

    python3 tests/e2e/replay/배재포켓북/rereg.py
    RENAME_BASE=https://yos-studio.fly.dev python3 …/rereg.py      배포서버의 카드(배포는 새 카드만 옮긴다 — 있던 카드 고침은 그 서버에서 다시 등록)
"""
import json, os, subprocess, sys, urllib.error, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import join                                                              # noqa: E402 — 같은 빈 편집기 데이터 · 서버 · 맞대기
from mkpage import S                                                     # noqa: E402

SERIES, DID = "pocketbook", "x5e277563"
units = json.load(open(os.path.join(join.REPO, "catalog", SERIES, "designs", DID, "units.json"), encoding="utf-8"))
pages = {p["id"]: p["name"] for p in units["pages"]}
names = [pages[e["page"] if isinstance(e, dict) else e] for s in units["plan"]["sections"] for e in s["pages"]]
st = [S("관리 카드 「원고 넣기」 — 편집기에서 연다", 1500), {"until": "docPages().length > 0 && page", "wait": 800},
      {"clickif": {"at": "#tg-side", "when": "!document.querySelector('#side') || !document.querySelector('#side').offsetParent"}, "wait": 1000},
      {"js": "(() => '열린 문서 쪽 ' + docPages().length + ' · 카드 ' + JSON.stringify(plan.catalog))()"}]
for i, nm in enumerate(names):
    if nm.startswith("암기 TEST"):
        st += [S(f"두 페이지짜리 — {i + 1}쪽 「{nm}」 + 다음 쪽", 900),
               {"js": f"(() => {{ openPage(docPages()[{i}]); return '쪽 열기 {i + 1}'; }})()"}, {"wait": 1500},
               {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
               {"clickif": {"at": "#side #s-spread2", "when": "!document.querySelector('#side #s-spread2').checked"}, "wait": 1200},
               {"js": f"(() => {{ const q = planPg(docPages()[{i}].id); if (!q || !q.펼침면) throw new Error('두 페이지짜리 안 켜짐'); return '두 페이지짜리 ' + docPages()[{i}].name; }})()"}]
st += [S("관리에 등록 — 같은 카드를 다시 그린다", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"pick": {"at": "#side #s-reg-series", "value": SERIES}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
st += [{"until": "/등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 40
st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
              f"if (!plan.catalog || plan.catalog.design !== '{DID}') throw new Error('다른 카드로 등록 ' + JSON.stringify(plan.catalog)); "
              "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]

REMOTE = os.environ.get("RENAME_BASE")
os.makedirs(join.OUT, exist_ok=True)
if REMOTE:
    join.BASE = REMOTE.rstrip("/")
    srv = None
else:
    join.fresh_data()
    srv = join.server()
try:
    sf = os.path.join(join.OUT, "rereg_steps.json")
    json.dump(st, open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:                                                                 # 카드 「원고 넣기」 주소 → 편집기가 문서 묶음을 들여오고 그 문서 주소로 보낸다
        urllib.request.build_opener(_NoRedirect).open(f"{join.BASE}/units?design={SERIES}/{DID}")
        sys.exit("문서 주소로 안 보냄")
    except urllib.error.HTTPError as e:
        start = join.BASE + e.headers["Location"] if e.headers.get("Location", "").startswith("/") else e.headers.get("Location")
    print("문서 주소", start)
    r = subprocess.run([join.PY, "tests/e2e/rec.py", start, sf, os.path.join(join.OUT, "rereg.mp4"), "1600", "1000", "8"],
                       cwd=join.REPO, env=dict(os.environ, REC_FAST="1"), capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(join.OUT, "rereg.log"), "w").write(log)
    print("\n".join(ln for ln in log.splitlines() if "js →" in ln or "ERR" in ln))
    if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
        sys.exit("다시 등록 실패 — " + os.path.join(join.OUT, "rereg.log"))
finally:
    if srv:
        srv.kill()
if REMOTE:                                                               # 배포서버 — 등록된 PDF 를 내려받아 맞댄다
    ref = os.path.join(join.OUT, "remote_reference.pdf")
    urllib.request.urlretrieve(f"{join.BASE}/catalog/pdf/{SERIES}/{DID}", ref)
else:
    ref = os.path.join(join.REPO, "catalog", SERIES, "designs", DID, "참고", "reference.pdf")
print("9 맞대기 판정:", "통과" if join.judge_reg(ref) else "실패")
