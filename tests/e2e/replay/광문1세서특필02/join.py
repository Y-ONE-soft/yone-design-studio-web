"""광문1 세서특필02 — 잇기 · 템플릿 등록 · 맞대기 (docs/편집기_재현/절차.md 맨 위 「★ 템플릿 등록 — 네 단계」 3단계).

    python3 tests/e2e/replay/광문1세서특필02/join.py
    → ~/Downloads/편집기재현/광문1세서특필02@합본/ (rec.log · 맞대기 결과)

잇기 — 면마다 사람 조작으로 만든 문서(replay.py 광문1세서특필02@<면> check 데이터)를 「문서 파일 내보내기」 묶음으로 꺼내, 빈 편집기에서
  「문서 파일 가져오기」(첫 묶음은 새 문서로, 나머지는 이 문서 끝에)로 원본 차례대로 잇는다.
등록 — 면 검사와 같은 견본 원고(make.py 가 원본 쪽에서 뽑은 원고.json)를 넣고 「관리에 등록」(특강교재 폴더) → 원본 PDF 를 템플릿에 붙인다.
맞대기 — 등록 PDF 쪽마다 그 면의 요소 목록(elems.json)으로 원본 그 쪽과 다시 판정(원고 요소 · 쪽 번호는 들어갔나만).
책 만들기(원고 전체)는 기능 테스트로 — contents 원고 연동 때(2026-10-20 사용자 확정).
"""
import json, os, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
E2E = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, E2E)
from mkpage import S, open_doc, put_content                             # noqa: E402
from cdp import free_port                                                 # noqa: E402
import pymupdf                                                            # noqa: E402

PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 0) or free_port()
BASE = f"http://127.0.0.1:{PORT}"
CACHE = os.path.expanduser("~/.cache/yone-replay")
BOOK = "광문1세서특필02"
OUT = os.path.expanduser(f"~/Downloads/편집기재현/{BOOK}@합본")
DATA = os.path.join(CACHE, f"{BOOK}@합본", "catalog")
NAME = "광문1 세서특필02 (편집기 제작)"
SERIES = "special-lecture"
UNITS = ["1", "2,3", "4,5", "6", "7,8", "9,10", "11"]                  # 원본 차례 — 표지 · 차례 · 간지 · 중요문장 · 대표유형 · 실전문제 · 정답 · 마지막
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
REF = os.path.join(REPO, STATE["ref"])


def unit_dir(g):
    """그 면의 판 — 통과 판이 있으면 그것, 없으면 가장 나중 판(사람 조작 판만 — 원본 일치는 등록 뒤 맞대기가 본다)"""
    best, any_ = None, None
    u = f"{BOOK}@{g}"
    try:
        v = json.load(open(os.path.expanduser(f"~/Downloads/편집기재현/{u}/판정.json"), encoding="utf-8"))
    except Exception:
        sys.exit(f"면 {g} 판 없음 — 먼저 REC_DIRECT=0 replay.py {u} check")
    if not v.get("통과"):
        print(f"  면 {g} — 통과 판 없음, 가장 나중 판으로({v.get('때')})", flush=True)
    return os.path.join(CACHE, u, "catalog")


def export_all():
    files = []
    for g in UNITS:
        cat = unit_dir(g)
        f = os.path.join(OUT, f"면_{g.replace(',', '_')}.json")
        code = ("import json, sys; from core.units import store, package; lib = store.library(); "
                "p = [x for x in lib['plans'] if x.get('name') == sys.argv[2]][-1]; "
                "json.dump(package.export(lib, p['id']), open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False)")
        subprocess.run([PY, "-c", code, f, NAME], cwd=REPO, env=dict(os.environ, YONE_CATALOG_DIR=cat, YONE_AUTH="off"), check=True)
        pk = json.load(open(f, encoding="utf-8"))
        print(f"  내보냄 면 {g} — 쪽 {len(pk['pages'])}", flush=True)
        files.append((f, [p["name"] for p in pk["pages"]]))
    return files


def sample():
    """견본 원고 — 면 검사 대본(make.py)이 원본 쪽에서 뽑은 원고 그대로(면 이름 → 레코드 목록)"""
    wd = os.path.join(OUT, "make")
    os.makedirs(wd, exist_ok=True)
    subprocess.run([PY, os.path.join(HERE, "make.py")], cwd=REPO, env=dict(os.environ, REPLAY_WORK=wd, GUSEONG=""), check=True, stdout=subprocess.DEVNULL)
    return json.load(open(os.path.join(wd, "원고.json"), encoding="utf-8"))


def fresh_data():
    shutil.rmtree(os.path.dirname(DATA), ignore_errors=True)
    os.makedirs(os.path.join(DATA, "_units"))
    src = os.path.join(REPO, "catalog")
    for n in os.listdir(src):
        if n != "_units":
            os.symlink(os.path.join(src, n), os.path.join(DATA, n))
    shutil.copy(os.path.join(src, "_units", "specs.json"), os.path.join(DATA, "_units", "specs.json"))
    base = {"id": "base", "name": "기본 (브랜드 없음)", "tokens": {"color": {"ink": "#231f20", "white": "#ffffff"}, "font": {"body": "Noto Sans CJK KR"}}, "styles": {}}
    for k, v in (("skins", [base]), ("blocks", []), ("parts", []), ("pages", []), ("plans", []), ("sets", [])):
        json.dump(v, open(os.path.join(DATA, "_units", k + ".json"), "w", encoding="utf-8"), ensure_ascii=False)


def server():
    env = dict(os.environ, YONE_CATALOG_DIR=DATA, YONE_AUTH="off", YONE_WARM="0")
    p = subprocess.Popen([PY, "-u", "studio_server.py", "--port", str(PORT)], cwd=REPO, env=env,
                         stdout=open(os.path.join(OUT, "server.log"), "w"), stderr=subprocess.STDOUT)
    for _ in range(960):
        try:
            urllib.request.urlopen(BASE + "/api/units/library", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    sys.exit(f"서버가 안 뜸 — {OUT}/server.log")


def steps(files, content):
    st = open_doc(NAME)
    got = 0
    for k, (f, ns) in enumerate(files):
        got += len(ns)
        st += [S(f"문서 파일 가져오기 — {os.path.basename(f)} ({'새 문서로' if k == 0 else '이 문서 끝에'})", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
               {"pick": {"at": "#side #s-pkg-mode", "value": "new" if k == 0 else "append"}, "wait": 700},
               {"upload": {"at": "#side #s-pkg-file", "click": "#side #s-pkg-in", "path": f}, "wait": 4000},
               {"until": f"docPages().length === {got}", "wait": 500},
               {"js": "(() => '쪽 ' + docPages().length + ' · ' + document.querySelector('#st').textContent)()"}]
    names = [n for _, ns in files for n in ns]
    st += [{"js": f"(() => {{ const n = docPages().length; if (n !== {len(names)}) throw new Error('이은 쪽 ' + n); return '이은 쪽 ' + n; }})()"}]
    st += put_content(content, "원고 넣기 — 면마다 견본 원고 하나(면 검사와 같은 원본 쪽)")
    st += [S("관리에 등록 — 특강교재 폴더", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
           {"pick": {"at": "#side #s-reg-series", "value": SERIES}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
    st += [{"until": "plan.catalog && plan.catalog.design && /등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 60
    st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
                  "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]
    return st


def judge_reg(reg_pdf):
    import pagecmp
    reg = pymupdf.open(reg_pdf)
    units, want = {}, []
    for g in UNITS:
        wd = os.path.join(os.path.dirname(unit_dir(g)), "work")
        st = json.load(open(os.path.join(wd, "상태.json"), encoding="utf-8"))
        el = json.load(open(os.path.join(wd, "elems.json"), encoding="utf-8"))
        for k, rp in enumerate(st["pages"]):
            units[rp] = (g, el[str(k + 1)])
            want.append(rp)
    if reg.page_count != len(want):
        print(f"  ✗ 등록 쪽 {reg.page_count} ≠ {len(want)} (견본 원고 차례 {want})")
    last = [rp for rp in want if units[rp][0] == UNITS[-1]]               # 마지막 면은 등록 PDF 끝에서 — 앞 면 글이 넘쳐 쪽이 늘어도 맞는 쪽끼리
    order = [(rp, i) for i, rp in enumerate(want) if rp not in last and i < reg.page_count]
    order += [(rp, reg.page_count - len(last) + k) for k, rp in enumerate(last)]
    tot, bad = 0, []
    for rp, i in order:
        g, elems = units[rp]
        one = pymupdf.open()
        one.insert_pdf(reg, from_page=i, to_page=i)
        pdf = os.path.join(OUT, f"p{rp}_reg.pdf")
        one.save(pdf)
        es = []
        for e in elems:
            if e.get("원고") or (str(e.get("text", "")).strip().isdigit() and int(e["text"]) == rp):
                e = dict({kk: vv for kk, vv in e.items() if kk != "text"}, pad=8.0, search=8.0, 원고=True)
            es.append(e)
        res = pagecmp.measure(REF, rp, pdf, es)
        n_bad = 0
        for r, e in zip(res, es):
            ok = r.get("my") is not None if e.get("원고") else r["ok"]
            tot += 1
            if not ok:
                n_bad += 1
                bad.append(f"면 {g} · 원본 {rp}쪽(등록 {i + 1}쪽) {r['id']}")
        print(f"  면 {g} · 원본 {rp}쪽 → 등록 {i + 1}쪽{' · 틀림 ' + str(n_bad) if n_bad else ''}", flush=True)
    print(f"맞대기 — 요소 {tot - len(bad)}/{tot} 맞음")
    for b in bad[:40]:
        print("  ✗", b)
    return not bad and reg.page_count == len(want)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    content = sample()
    print("견본 원고 면", list(content))
    files = export_all()
    fresh_data()
    srv = server()
    try:
        sf = os.path.join(OUT, "steps.json")
        json.dump(steps(files, content), open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        r = subprocess.run([PY, "tests/e2e/rec.py", BASE + "/units", sf, os.path.join(OUT, "join.mp4"), "1600", "1000", "8"], cwd=REPO,
                           env=dict(os.environ, REC_FAST="1", REC_DIRECT="1"), capture_output=True, text=True)
        log = r.stdout + r.stderr
        open(os.path.join(OUT, "rec.log"), "w").write(log)
        print("\n".join(ln for ln in log.splitlines() if "js →" in ln or "ERR" in ln)[-3000:])
        if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
            sys.exit("잇기 실패 — " + os.path.join(OUT, "rec.log"))
        cat = next(p["catalog"] for p in json.load(open(os.path.join(DATA, "_units", "plans.json"), encoding="utf-8")) if p.get("catalog"))
        if subprocess.run([PY, os.path.join(E2E, "attach_origin.py"), f"{cat['series']}/{cat['design']}", REF, "--base", BASE], cwd=REPO).returncode:
            sys.exit("템플릿 보기 확인 실패 — 원본 페이지 차례가 안 나온다")
    finally:
        srv.kill()
    ddir = os.path.join(REPO, "catalog", cat["series"], "designs", cat["design"])
    print("등록 카드", ddir)
    print("맞대기 판정:", "통과" if judge_reg(os.path.join(ddir, "참고", "reference.pdf")) else "실패")
