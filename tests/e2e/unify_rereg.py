"""데이터 병합 원고 꼴 통일 — 등록된 워크북 · 분석본 템플릿을 편집기에서 열어 레코드 차례 꼴로 바꾸고 같은 카드로 다시 등록한다(2026-10-12).

    python3 tests/e2e/unify_rereg.py workbook/xe3a03cd7
    RENAME_BASE=https://yos-studio.fly.dev python3 tests/e2e/unify_rereg.py workbook/xe3a03cd7      배포서버의 카드

편집기에서(사람이 쪽 패널에서 하듯):
  - 원고가 오면 나오는 페이지(STEP 간지 + 차례, 분석본 간지, 실전 문제)를 「레코드마다」로
  - 늘 붙어 나오는 두 페이지의 첫 페이지에 「두 페이지짜리」(문제 페이지 + 둘째 페이지, STEP 간지 + 차례, 분석 펼침면, 실전 문제)
  - 데이터 필드가 같은 상위 페이지에 분류(STEP 1 · 2 · 3, C 빈칸 어휘 · 어법)
  - 샘플 레코드를 레코드 차례 꼴로(옛 샘플을 content.to_records 로 바꾼 것 — 「원고 넣기」)
그다음 「관리에 등록」으로 같은 카드를 다시 그린다. 확인: tests/e2e/regcheck.py(옛 꼴 책 = 새 꼴 책이라 바뀐 곳이 없어야 한다).
"""
import copy, json, os, subprocess, sys, urllib.error, urllib.request

E2E = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(E2E))
sys.path.insert(0, E2E)
sys.path.insert(0, os.path.join(E2E, "replay", "배재포켓북"))
import join                                                              # noqa: E402 — 빈 편집기 데이터 · 서버
from mkpage import S, put_content                                        # noqa: E402
sys.path.insert(0, REPO)
from core.units import content as C                                       # noqa: E402

card = sys.argv[1]
series, _, did = card.partition("/")
pkg = json.load(open(os.path.join(REPO, "catalog", series, "designs", did, "units.json"), encoding="utf-8"))
pages = {p["id"]: p for p in pkg["pages"]}
entries = [e for s in pkg["plan"]["sections"] for e in s["pages"]]


def want(i, e):
    """이 페이지에 둘 설정 — (레코드마다, 두 페이지짜리, 분류)"""
    nm = pages[e["page"]]["name"]
    each = e.get("repeat") == "each_set"
    if series == "workbook":
        if nm == "STEP 간지":
            return True, True, f"STEP {sum(1 for x in entries[:i + 1] if pages[x['page']]['name'] == 'STEP 간지')}"
        if nm in ("차례", "S실전문제 오른쪽"):
            return True, False, ""
        if nm == "S실전문제":
            return True, True, ""
        if each and not nm.startswith("빈 면"):
            return True, True, {"C빈칸어휘": "어휘", "C빈칸어법": "어법"}.get(nm, "")
        return each, False, ""
    if series == "analysis":
        if nm == "간지":
            return True, False, ""
        if nm == "분석 펼침면":
            return True, True, ""
        return each, False, ""
    sys.exit(f"이 도구가 모르는 틀 {series}")


new = copy.deepcopy(pkg["plan"])
st = [S("관리 카드 「원고 넣기」 — 편집기에서 연다", 1500), {"until": "docPages().length > 0 && page", "wait": 800},
      {"clickif": {"at": "#tg-side", "when": "!document.querySelector('#side') || !document.querySelector('#side').offsetParent"}, "wait": 1000},
      {"js": f"(() => {{ if (docPages().length !== {len(entries)}) throw new Error('쪽 수 ' + docPages().length); return '열린 문서 쪽 ' + docPages().length + ' · 카드 ' + JSON.stringify(plan.catalog); }})()"}]
for i, e in enumerate(entries):
    each, spread, gub = want(i, e)
    ne = [x for s in new["sections"] for x in s["pages"]][i]
    if each:
        ne["repeat"] = "each_set"
    if spread:
        ne["펼침면"] = True
    if gub:
        ne["구분"] = gub
    if (each == (e.get("repeat") == "each_set")) and not spread and not gub:
        continue
    nm = pages[e["page"]]["name"]
    st += [S(f"{i + 1}쪽 「{nm}」 — {'레코드마다 · ' if each else ''}{'두 페이지짜리 · ' if spread else ''}{'분류 ' + gub if gub else ''}", 900),
           {"js": f"(() => {{ openPage(docPages()[{i}]); return '쪽 열기 {i + 1}'; }})()"}, {"wait": 1500},
           {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}]
    if each and e.get("repeat") != "each_set":
        st += [{"pick": {"at": "#side #s-rep", "value": "each_set"}, "wait": 1500}]
    if spread:
        st += [{"clickif": {"at": "#side #s-spread2", "when": "!document.querySelector('#side #s-spread2').checked"}, "wait": 1200}]
    if gub:
        st += [{"fill": {"at": "#side #s-gubun", "value": gub}, "wait": 1200}]
    st += [{"js": f"(() => {{ const q = planPg(docPages()[{i}].id) || {{}}; "
                  f"if ({'true' if each else 'false'} && q.repeat !== 'each_set') throw new Error('레코드마다 안 됨'); "
                  f"if ({'true' if spread else 'false'} && !q.펼침면) throw new Error('두 페이지짜리 안 켜짐'); "
                  f"if ({json.dumps(gub)} && q.구분 !== {json.dumps(gub)}) throw new Error('분류 안 들어감'); "
                  f"return '{i + 1}쪽 ' + JSON.stringify({{repeat: q.repeat, 펼침면: q.펼침면, 구분: q.구분}}); }})()"}]
sample = C.to_records(new, pages, pkg["plan"].get("content") or {})
st += put_content(sample, "샘플 레코드 — 레코드 차례 꼴(옛 샘플을 바꾼 것)")
st += [S("관리에 등록 — 같은 카드를 다시 그린다", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
       {"pick": {"at": "#side #s-reg-series", "value": series}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
st += [{"until": "/등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 60
st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
              f"if (!plan.catalog || plan.catalog.design !== '{did}') throw new Error('다른 카드로 등록 ' + JSON.stringify(plan.catalog)); "
              "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]

OUT = os.path.expanduser(f"~/Downloads/편집기재현/통일_{series}_{did}")
os.makedirs(OUT, exist_ok=True)
join.OUT = OUT
REMOTE = os.environ.get("RENAME_BASE")
if REMOTE:
    join.BASE = REMOTE.rstrip("/")
    srv = None
else:
    join.DATA = os.path.join(join.CACHE, f"통일_{did}", "catalog")
    join.fresh_data()
    srv = join.server()
try:
    sf = os.path.join(OUT, "steps.json")
    json.dump(st, open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    try:
        urllib.request.build_opener(_NoRedirect).open(f"{join.BASE}/units?design={series}/{did}")
        sys.exit("문서 주소로 안 보냄")
    except urllib.error.HTTPError as e:
        start = join.BASE + e.headers["Location"] if e.headers.get("Location", "").startswith("/") else e.headers.get("Location")
    print("문서 주소", start, flush=True)
    r = subprocess.run([join.PY, "tests/e2e/rec.py", start, sf, os.path.join(OUT, "rereg.mp4"), "1600", "1000", "8"],
                       cwd=REPO, env=dict(os.environ, REC_FAST="1"), capture_output=True, text=True)
    log = r.stdout + r.stderr
    open(os.path.join(OUT, "rec.log"), "w").write(log)
    print("\n".join(ln for ln in log.splitlines() if ("js →" in ln and ("등록" in ln or "쪽 수" in ln or "원고" in ln)) or "ERR" in ln))
    if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
        sys.exit("다시 등록 실패 — " + os.path.join(OUT, "rec.log"))
    print("다시 등록 끝 — 샘플 레코드", len(sample["원고"]))
finally:
    if srv:
        srv.kill()
