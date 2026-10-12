"""템플릿 되돌리기 — 리포의 템플릿 파일(catalog/<틀>/designs/<카드>/units.json)을 편집기 「문서 파일 가져오기(새 문서로)」로 들여와
「관리에 등록」으로 같은 카드에 다시 그린다(템플릿 파일이 제 카드를 기억한다 — plan.catalog).

    RENAME_BASE=https://yos-studio.fly.dev python3 tests/e2e/restore_card.py analysis/x009d5556

배포서버 편집기로 열어 다시 등록하다 그 서버 브랜드가 섞인 카드를 리포 것으로 되돌릴 때(2026-10-12 광문 분석본).
"""
import json, os, subprocess, sys

E2E = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(E2E))
sys.path.insert(0, E2E)
sys.path.insert(0, os.path.join(E2E, "replay", "배재포켓북"))
import join                                                              # noqa: E402
from mkpage import S, open_doc                                           # noqa: E402

series, _, did = sys.argv[1].partition("/")
src = os.path.join(REPO, "catalog", series, "designs", did, "units.json")
pkg = json.load(open(src, encoding="utf-8"))
if (pkg["plan"].get("catalog") or {}).get("design") != did:
    sys.exit("템플릿 파일이 이 카드를 기억하지 않는다")
st = open_doc(f"되돌리기 {did}")
st += [S("문서 파일 가져오기 — 리포의 템플릿 파일(새 문서로)", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"pick": {"at": "#side #s-pkg-mode", "value": "new"}, "wait": 700},
       {"upload": {"at": "#side #s-pkg-file", "click": "#side #s-pkg-in", "path": src}, "wait": 5000},
       {"until": f"docPages().length === {sum(len(s['pages']) for s in pkg['plan']['sections'])} && plan.catalog && plan.catalog.design === '{did}'", "wait": 1500},
       {"js": f"(() => {{ if (docPages().length !== {sum(len(s['pages']) for s in pkg['plan']['sections'])}) throw new Error('쪽 수 ' + docPages().length); "
              "return '가져옴 쪽 ' + docPages().length + ' · 카드 ' + JSON.stringify(plan.catalog) + ' · 브랜드 ' + plan.skin; })()"}]
st += [S("관리에 등록 — 같은 카드", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"pick": {"at": "#side #s-reg-series", "value": series}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
st += [{"until": "/등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 60
st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
              f"if (!plan.catalog || plan.catalog.design !== '{did}') throw new Error('다른 카드로 등록 ' + JSON.stringify(plan.catalog)); "
              "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]
OUT = os.path.expanduser(f"~/Downloads/편집기재현/되돌리기_{series}_{did}")
os.makedirs(OUT, exist_ok=True)
join.OUT = OUT
REMOTE = os.environ.get("RENAME_BASE")
if REMOTE:
    join.BASE = REMOTE.rstrip("/")
    srv = None
else:
    join.DATA = os.path.join(join.CACHE, f"되돌리기_{did}", "catalog")
    join.fresh_data()
    srv = join.server()
try:
    sf = os.path.join(OUT, "steps.json")
    json.dump(st, open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    r = subprocess.run([join.PY, "tests/e2e/rec.py", join.BASE + "/units", sf, os.path.join(OUT, "restore.mp4"), "1600", "1000", "8"],
                       cwd=REPO, env=dict(os.environ, REC_FAST="1"), capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(OUT, "rec.log"), "w").write(log)
    print("\n".join(ln for ln in log.splitlines() if ("js →" in ln and ("등록" in ln or "가져옴" in ln)) or "ERR" in ln))
    if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
        sys.exit("되돌리기 실패 — " + os.path.join(OUT, "rec.log"))
finally:
    if srv:
        srv.kill()
