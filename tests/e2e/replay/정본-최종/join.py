"""정본 7~9단계 — 잇기 → 편집기 제작 등록 → 맞대기 (docs/편집기_재현/절차.md 「작업 순서 — 확정」).

    python3 tests/e2e/replay/정본-최종/join.py
    → ~/Downloads/편집기재현/정본-최종@합본/ (rec.log · 맞대기 결과 · 등록 PDF)

7 잇기 — 구성마다 검사를 통과한 문서(replay.py 정본-최종@<구성> check 가 남긴 데이터)를 「문서 파일 내보내기」 묶음으로 꺼내,
  빈 편집기에서 「문서 파일 가져오기」(첫 묶음은 새 문서로, 나머지는 이 문서 끝에)로 책 차례대로 잇는다 — 사람처럼 조작.
8 편집기 제작 등록 — 구성마다 견본 원고 하나(make.py 를 구성 고르지 않고 돌린 「원고 넣기」 값)를 넣고 문서 패널 「관리에 등록」(워크북 폴더).
9 맞대기 — 등록 PDF 에서 견본 쪽마다 그 구성의 요소 목록(elems.json)으로 다시 판정한다(원고 요소는 들어갔나만 · 쪽 번호는 책 차례 번호라 들어갔나만).
"""
import json, os, re, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
E2E = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, E2E)
from mkpage import S, open_doc, put_content                            # noqa: E402

PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 5198)
BASE = f"http://127.0.0.1:{PORT}"
CACHE = os.path.expanduser("~/.cache/yone-replay")
OUT = os.path.expanduser("~/Downloads/편집기재현/정본-최종@합본")
DATA = os.path.join(CACHE, "정본-최종@합본", "catalog")
NAME = "스텝바이스텝 워크북 정본 (편집기 제작 최종)"
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
ORDER = ["1,2,3", "4", "5", "6", "7", "8", "9", "2.2,3.2", "10", "11", "12", "13", "2.3,3.3", "14", "15,16"]   # 책 차례(원본 쪽 차례)
NAMES = {"1,2,3": ["속표지", "STEP 간지", "차례"], "2.2,3.2": ["STEP 간지", "차례"], "2.3,3.3": ["STEP 간지", "차례"], "15,16": ["MEMO", "뒤표지"]}
# 면 이름 = 구성 이름 — 관리 「지면 보기」가 편집기 제작 카드의 구성을 면 이름으로 묶는다(routes/catalog.editor_layouts). 「원고마다」 면은 대본이 이름을 붙였다


def name_steps(counts):
    """이름 없는 「한 번만」 면에 구성 이름 — 쪽 목록에서 그 면을 눌러 고르고 쪽 패널 「이름」에 친다. counts = 구성 문서마다 쪽 수(책 차례)"""
    st, at = [], 0
    for g, n in zip(ORDER, counts):
        for k, nm in enumerate(NAMES.get(g, [])):
            i = at + k
            st += [S(f"면 이름 — {i + 1}쪽 「{nm}」", 900),                   # 가운데 지면을 그 쪽까지 굴려 누른다(아래 쪽 띠는 가로로 길어 뒤쪽이 화면 밖)
                   {"clickif": {"at": f'#pages .pslot[data-i="{i}"]', "when": f"idx() !== {i}"}, "wait": 1500},
                   {"js": f"(() => {{ if (idx() !== {i}) throw new Error('쪽 안 열림 ' + (idx() + 1)); return '{i + 1}쪽 열림'; }})()"},
                   {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"fill": {"at": "#side #s-pname", "value": nm}, "wait": 900},
                   {"js": f"(() => {{ const p = docPages()[{i}]; if (p.name !== {json.dumps(nm)}) throw new Error('면 이름 안 들어감 ' + p.name); return '면 이름 ' + p.name; }})()"}]
        at += n
    return st


def export_all():
    """구성 문서마다 「문서 파일 내보내기」와 같은 묶음(core/units/package.export — 편집기 /api/units/package 와 같은 함수)"""
    files = []
    for g in ORDER:
        cat = os.path.join(CACHE, f"정본-최종@{g}", "catalog")
        if not os.path.isdir(cat):
            sys.exit(f"구성 문서 없음 — 먼저 replay.py 정본-최종@{g} check")
        f = os.path.join(OUT, f"구성_{g}.json")
        code = ("import json, sys; from core.units import store, package; lib = store.library(); "
                "p = [x for x in lib['plans'] if x.get('name') == sys.argv[2]][-1]; "
                "json.dump(package.export(lib, p['id']), open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False)")
        subprocess.run([PY, "-c", code, f, NAME], cwd=REPO, env=dict(os.environ, YONE_CATALOG_DIR=cat, YONE_AUTH="off"), check=True)
        print(f"  내보냄 구성 {g} — 쪽 {len(json.load(open(f, encoding='utf-8'))['pages'])}", flush=True)
        files.append(f)
    return files


def sample_content():
    """견본 원고 — make.py 를 구성 고르지 않고 돌리면 「원고 넣기」 값이 구성마다 견본 원고 하나다"""
    w = os.path.join(OUT, "work")
    os.makedirs(w, exist_ok=True)
    subprocess.run([PY, os.path.join(HERE, "make.py")], check=True, env=dict(os.environ, REPLAY_WORK=w, GUSEONG=""), capture_output=True)
    st = json.load(open(os.path.join(w, "steps.json"), encoding="utf-8"))
    return json.loads(next(s["fill"]["value"] for s in st if isinstance(s.get("fill"), dict) and s["fill"].get("at") == "#side #s-content"))


def fresh_data():
    """replay.py 와 같은 빈 편집기 데이터(판형 · 빈 브랜드)"""
    shutil.rmtree(os.path.dirname(DATA), ignore_errors=True)
    os.makedirs(os.path.join(DATA, "_units"))
    src = os.path.join(REPO, "catalog")
    for n in os.listdir(src):
        if n != "_units":
            os.symlink(os.path.join(src, n), os.path.join(DATA, n))
    shutil.copy(os.path.join(src, "_units", "specs.json"), os.path.join(DATA, "_units", "specs.json"))
    base = {"id": "base", "name": "기본 (브랜드 없음)",
            "tokens": {"color": {"ink": "#231f20", "white": "#ffffff", "rule": "#b8b8b8", "gray": "#e6e6e6"},
                       "font": {"body": "Noto Sans CJK KR"}}, "styles": {}}
    for k, v in (("skins", [base]), ("blocks", []), ("parts", []), ("pages", []), ("plans", []), ("sets", [])):
        json.dump(v, open(os.path.join(DATA, "_units", k + ".json"), "w", encoding="utf-8"), ensure_ascii=False)


def server():
    env = dict(os.environ, YONE_CATALOG_DIR=DATA, YONE_AUTH="off")
    p = subprocess.Popen([PY, "-u", "studio_server.py", "--port", str(PORT)], cwd=REPO, env=env,
                         stdout=open(os.path.join(OUT, "server.log"), "w"), stderr=subprocess.STDOUT)
    for _ in range(120):
        try:
            urllib.request.urlopen(BASE + "/api/units/library", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    sys.exit(f"서버가 안 뜸 — {OUT}/server.log")


def steps(files, content):
    st = open_doc(NAME)
    for k, (g, f) in enumerate(zip(ORDER, files)):
        st += [S(f"문서 파일 가져오기 — 구성 {g} ({'새 문서로' if k == 0 else '이 문서 끝에'})", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
               {"pick": {"at": "#side #s-pkg-mode", "value": "new" if k == 0 else "append"}, "wait": 700},
               {"upload": {"at": "#side #s-pkg-file", "click": "#side #s-pkg-in", "path": f}, "wait": 4000},
               {"js": "(() => '쪽 ' + docPages().length + ' · ' + document.querySelector('#st').textContent)()"}]
    st += [{"js": "(() => { const n = docPages().length; if (n < 30) throw new Error('이은 쪽 ' + n); return '이은 쪽 ' + n; })()"}]
    st += name_steps([len(json.load(open(f, encoding="utf-8"))["pages"]) for f in files])
    st += [S("원고 자리 글 → «자리 이름» (틀에는 책 글을 두지 않는다)", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
            {"click": "#side #s-slot-names", "wait": 2000},
       {"until": "/원고 자리 \\d+곳/.test(document.querySelector('#st').textContent)", "wait": 500},
            {"js": "(() => { const bad = docPages().flatMap(p => (p.items || []).filter(it => it.atom && it.atom.t === 'text' && it.atom.bind && !String(it.atom.bind).startsWith('sys.') && it.atom.text !== '«' + it.atom.bind + '»')); if (bad.length) throw new Error('자리 이름 안 된 곳 ' + bad.length); return '원고 자리 모두 «자리 이름»'; })()"}]
    st += put_content(content, "원고 넣기 — 구성마다 견본 원고 하나(바깥 시스템이 보내는 꼴)")
    st += [S("관리에 등록 — 워크북 폴더", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
           {"pick": {"at": "#side #s-reg-series", "value": "workbook"}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
    st += [{"until": "plan.catalog && plan.catalog.design && /등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 30
    st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
                  "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]
    return st


def words(t):
    return set(re.findall(r"[A-Za-z가-힣]{3,}", t))


def judge(reg_pdf):
    """9 맞대기 — 등록 PDF 에서 견본 쪽을 책 차례대로 찾아(원본 그 쪽과 글이 가장 닮은 다음 쪽) 그 구성의 요소 목록으로 판정"""
    import pymupdf
    import pagecmp
    ref = pymupdf.open(os.path.join(REPO, STATE["ref"]))
    reg = pymupdf.open(reg_pdf)
    rw = [words(p.get_text()) for p in reg]
    at, tot, bad = 0, 0, []
    for g in ORDER:
        wd = os.path.join(CACHE, f"정본-최종@{g}", "work")
        st = json.load(open(os.path.join(wd, "상태.json"), encoding="utf-8"))
        elems = json.load(open(os.path.join(wd, "elems.json"), encoding="utf-8"))
        for k, rp in enumerate(st["pages"]):
            want = words(ref[rp - 1].get_text())
            cand = range(at, min(at + 8, len(reg)))
            i = max(cand, key=lambda j: len(want & rw[j]) / (len(want | rw[j]) or 1))
            at = i + 1
            one = pymupdf.open()
            one.insert_pdf(reg, from_page=i, to_page=i)
            pdf = os.path.join(OUT, f"p{rp}_reg.pdf")
            one.save(pdf)
            es = []
            for e in elems[str(k + 1)]:
                if e.get("원고") or (str(e.get("text", "")).strip().isdigit() and int(e["text"]) == rp):   # 원고 · 쪽 번호(책 차례 번호) — 들어갔나만
                    e = dict({kk: vv for kk, vv in e.items() if kk != "text"}, pad=8.0, search=8.0, 원고=True)
                es.append(e)
            res = pagecmp.measure(os.path.join(REPO, STATE["ref"]), rp, pdf, es)
            for r, e in zip(res, es):
                ok = r.get("my") is not None if e.get("원고") else r["ok"]
                tot += 1
                if not ok:
                    bad.append(f"구성 {g} · 원본 {rp}쪽(등록 {i + 1}쪽) {r['id']}")
            print(f"  구성 {g} · 원본 {rp}쪽 → 등록 {i + 1}쪽", flush=True)
    print(f"맞대기 — 요소 {tot - len(bad)}/{tot} 맞음")
    for b in bad[:30]:
        print("  ✗", b)
    return not bad


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    files = export_all()
    content = sample_content()
    print("  견본 원고 자리", len(content), flush=True)
    fresh_data()
    srv = server()
    try:
        sf = os.path.join(OUT, "steps.json")
        json.dump(steps(files, content), open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        r = subprocess.run([PY, "tests/e2e/rec.py", BASE + "/units", sf, os.path.join(OUT, "join.mp4"), "1600", "1000", "8"], cwd=REPO,
                           env=dict(os.environ, REC_FAST="1"), capture_output=True, text=True)
        log = r.stdout + r.stderr
        open(os.path.join(OUT, "rec.log"), "w").write(log)
        print("\n".join(ln for ln in log.splitlines() if "js →" in ln or "ERR" in ln))
        if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
            sys.exit("잇기·등록 실패 — " + os.path.join(OUT, "rec.log"))
    finally:
        srv.kill()
    plans = json.load(open(os.path.join(DATA, "_units", "plans.json"), encoding="utf-8"))
    cat = next(p["catalog"] for p in plans if p.get("catalog"))
    ddir = os.path.join(DATA, cat["series"], "designs", cat["design"])
    print("등록 폴더", ddir)
    ok = judge(os.path.join(ddir, "참고", "reference.pdf"))
    print("판정: 통과" if ok else "판정: 실패")
