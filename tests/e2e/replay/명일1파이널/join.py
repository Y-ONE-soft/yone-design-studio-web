"""명일1 파이널(Vol1) 7~9단계 — 잇기 · 책 만들기 검사 · 편집기 제작 등록 · 맞대기 (docs/편집기_재현/절차.md 「작업 순서 — 확정」).

    python3 tests/e2e/replay/명일1파이널/join.py            (JOIN_REGISTER=0 이면 등록 없이 잇기 · 책 만들기만)
    → ~/Downloads/편집기재현/명일1파이널@합본/ (rec.log · 책.pdf · 맞대기 결과)

잇기 — 면마다 검사를 통과한 문서(replay.py 명일1파이널@<면> check 데이터)를 「문서 파일 내보내기」 묶음으로 꺼내, 빈 편집기에서
  「문서 파일 가져오기」(첫 묶음은 새 문서로, 나머지는 이 문서 끝에)로 표지 → 지문 펼침면 → 요약 펼침면 → 마지막 차례로 잇는다.
책 만들기 검사 — 원본 원고 전체(단원마다 덩어리 하나 — 문장 배열 · 문장 삽입 / 순서 배열 · 중요 어휘 / 요약문)를 {원고: [레코드 …]} 로 넣어 책을 그리고
  쪽 수 · 쪽 차례가 원본과 같은지 맞댄다.
8 편집기 제작 등록 — 견본 원고(면 검사와 같은 2 · 3쪽 지문 · 14 · 15쪽 요약)를 넣고 「관리에 등록」(직전보충 폴더) → 원본 PDF 를 템플릿에 붙인다.
9 맞대기 — 등록 PDF 쪽마다 그 면의 요소 목록(5단계 elems.json)으로 원본 그 쪽과 다시 판정(원고 요소 · 쪽 번호는 들어갔나만).
"""
import json, os, re, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
E2E = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, E2E)
sys.path.insert(0, HERE)
from mkpage import S, open_doc, put_content                             # noqa: E402
from cdp import free_port                                                 # noqa: E402
import entries as EN                                                      # noqa: E402

PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 0) or free_port()
BASE = f"http://127.0.0.1:{PORT}"
CACHE = os.path.expanduser("~/.cache/yone-replay")
OUT = os.path.expanduser("~/Downloads/편집기재현/명일1파이널@합본")
DATA = os.path.join(CACHE, "명일1파이널@합본", "catalog")
NAME = "명일1 파이널 (편집기 제작)"
UNITS = ["1", "2", "3", "4"]                                         # 가져올 문서(면 검사 판) 차례 — 표지 · 지문 펼침면 · 요약 펼침면 · 마지막(한 번만 쪽은 원고마다 면 앞 · 뒤 그대로)
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
REF = os.path.join(REPO, STATE["ref"])
FACES = json.load(open(os.path.join(REPO, "catalog", "final", "designs", "x93773c9f", "faces.json"), encoding="utf-8"))["faces"]
J_BIND = "출처+발문+주어진문장+본문+문장"
Y_BIND = "출처+빈칸지문+빈칸요약+정답지문+정답요약"


def unit_dir(g):
    """그 면의 마지막 판 — 통과 판이 있으면 그것, 없으면 마지막 바로 넣기 판(2026-10-20 사용자 「일단 다 올려두고 쓰면서 고친다」 — 원본 일치는 9 맞대기가 본다)"""
    best, any_ = None, None
    for u in (f"명일1파이널@{g}", f"명일1파이널@{g}~바로"):
        try:
            v = json.load(open(os.path.expanduser(f"~/Downloads/편집기재현/{u}/판정.json"), encoding="utf-8"))
        except Exception:
            continue
        if v.get("통과") and (best is None or v["때"] > best[1]):
            best = (u, v["때"])
        if u.endswith("~바로") and (any_ is None or v["때"] > any_[1]):
            any_ = (u, v["때"])
    if not best and any_:
        print(f"  면 {g} — 통과 판 없음, 마지막 바로 넣기 판으로({any_[0]})", flush=True)
        best = any_
    if not best:
        sys.exit(f"면 {g} 판 없음 — 먼저 REC_DIRECT=1 replay.py 명일1파이널@{g} check")
    return os.path.join(CACHE, best[0], "catalog")


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
        print(f"  내보냄 면 {g} — 쪽 {len(pk['pages'])} ({os.path.basename(os.path.dirname(cat))})", flush=True)
        files.append((f, [p["name"] for p in pk["pages"]]))
    return files


# ── 원본 원고 — 원본 차례 덩어리 ──────────────────────────────────────
import pymupdf                                                            # noqa: E402
DOC = pymupdf.open(REF)


def line(pno, lo, hi, x0=0, x1=220):
    """그 쪽 기준선 lo~hi 의 글 — 글자 사이가 떨어진 곳은 띄어쓰기(entries.line_text)"""
    sp = [s for s in EN._spans(DOC[pno - 1]) if lo <= s["base"] <= hi and x0 <= s["x"] < x1]
    return " ".join(EN.line_text(r) for r in EN._lines(sp)).strip()


def face_of(p):
    return next((f["label"] for f in FACES if p in f["pages"]), None)


def head(p):
    """그 쪽 머리 — 단원 번호 · 단원 제목(왼쪽 쪽 모양)"""
    return {"단원번호": line(p, 12.5, 13.5, 0, 30), "단원": line(p, 14.8, 15.8, 30, 140)}


CHAPTER = {"챕터": "", "챕터번호": ""}


def records():
    """단원마다 덩어리 하나 — 머리 단원 제목이 바뀌는 쪽에서 새 덩어리(단원 제목은 왼쪽 쪽 머리에만 — 오른쪽 쪽은 앞 쪽을 따른다)"""
    sp3 = EN._spans(DOC[2])
    raw = [sp for b in DOC[2].get_text("rawdict")["blocks"] for l in b.get("lines", []) for sp in l["spans"]]
    CHAPTER["챕터"] = next("".join(c["c"] for c in sp["chars"]).strip() for sp in raw if "Chapter" in "".join(c["c"] for c in sp["chars"]))   # 탭 글 — 띄어쓰기(공백 문자) 그대로
    CHAPTER["챕터번호"] = next(s["text"] for s in sp3 if s["base"] > 284 and s["text"].startswith("CHAPTER"))
    groups, cur = [], None
    for p in range(2, DOC.page_count):
        h = head(p)
        if h["단원"] and (cur is None or h["단원"] != cur[0]["단원"]):
            cur = (h, [])
            groups.append(cur)
        cur[1].append(p)
    recs = []
    for h, pages in groups:
        if face_of(pages[0]) == "요약 펼침면":
            recs.append(dict(h, **CHAPTER, **{Y_BIND: EN.summaries(REF, pages)}, _원본쪽=pages))
        else:
            recs.append(dict(h, **CHAPTER, **{J_BIND: EN.passages(REF, pages)}, _원본쪽=pages))
    toc = []
    sp1 = EN._spans(DOC[0])
    rows = sorted({round(s["base"], 2) for s in sp1 if 205 < s["base"] < 230})
    for b0 in rows:
        no = "".join(s["text"] for s in sp1 if abs(s["base"] - b0) < 0.2 and s["x"] < 133)
        if no and toc:
            toc.append("")
        toc.append(no + "\t" + line(1, b0 - 0.2, b0 + 0.2, 133))
    return {"챕터": CHAPTER["챕터"], "차례": "\n".join(toc), "원고": recs}


SAMPLE = {"지문": [2, 3], "요약": [14, 15]}                               # 견본 원고 — 5단계 대본이 그린 원본 쪽


def sample(content):
    j = next(r for r in content["원고"] if J_BIND in r)
    y = next(r for r in content["원고"] if Y_BIND in r)
    j = dict(j, _원본쪽=SAMPLE["지문"], **{J_BIND: EN.passages(REF, SAMPLE["지문"])})
    y = dict(y, _원본쪽=SAMPLE["요약"], **{Y_BIND: EN.summaries(REF, SAMPLE["요약"])})
    return {"챕터": content["챕터"], "차례": content["차례"], "원고": [j, y]}


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
    for _ in range(960):                                                 # 8분 — 기동 때 모든 디자인 구성을 미리 계산(다른 세션이 바쁘면 늦다)
        try:
            urllib.request.urlopen(BASE + "/api/units/library", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    sys.exit(f"서버가 안 뜸 — {OUT}/server.log")


def page_step(i, label, body):
    return ([S(label, 900), {"js": f"(() => {{ openPage(docPages()[{i}]); return '쪽 열기 {i + 1}'; }})()"}, {"wait": 1500},
             {"js": f"(() => {{ if (idx() !== {i}) throw new Error('쪽 안 열림 ' + (idx() + 1)); return '{i + 1}쪽 열림'; }})()"},
             {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}] + body)


def steps(files, content):
    st = open_doc(NAME)
    got = 0
    for k, (f, ns) in enumerate(files):
        got += len(ns)
        st += [S(f"문서 파일 가져오기 — {os.path.basename(f)} ({'새 문서로' if k == 0 else '이 문서 끝에'})", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
               {"pick": {"at": "#side #s-pkg-mode", "value": "new" if k == 0 else "append"}, "wait": 700},
               {"upload": {"at": "#side #s-pkg-file", "click": "#side #s-pkg-in", "path": f}, "wait": 4000},
               {"until": f"docPages().length === {got}", "wait": 500},                 # 가져오기가 끝날 때까지(바로 넣기는 기다림이 짧다)
               {"js": "(() => '쪽 ' + docPages().length + ' · ' + document.querySelector('#st').textContent)()"}]
    names = [n for _, ns in files for n in ns]
    st += [{"js": f"(() => {{ const n = docPages().length; if (n !== {len(names)}) throw new Error('이은 쪽 ' + n); return '이은 쪽 ' + n; }})()"}]
    if os.environ.get("JOIN_REGISTER", "1") == "0":
        return st
    st += put_content(sample(content), "원고 넣기 — 면마다 견본 원고 하나(원고 덩어리 차례 — 바깥 시스템이 보내는 꼴)")
    st += [S("관리에 등록 — 단어장 폴더", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
           {"pick": {"at": "#side #s-reg-series", "value": "final"}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
    st += [{"until": "plan.catalog && plan.catalog.design && /등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 40
    st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
                  "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]
    return st


def build(content):
    code = r'''
import json, sys
from core.units import store
from core.units import pdf as _pdf
from routes.units import fill_svgs, _ctx
lib = store.library()
plan = [p for p in lib["plans"] if p.get("name") == sys.argv[1]][-1]
content = json.load(open(sys.argv[2], encoding="utf-8"))
recs = []
svgs, rep, spec = fill_svgs(lib, plan, content, _ctx(lib, plan.get("skin")), recs=recs)
_pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), sys.argv[3], title="명일1 파이널", timeout=1800)
json.dump({"names": [s.get("label") for s in svgs], "orig": [(r or {}).get("_원본쪽") for r in recs], "report": rep}, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False)
'''
    cf, pdf, res = os.path.join(OUT, "원고.json"), os.path.join(OUT, "책.pdf"), os.path.join(OUT, "책.json")
    json.dump(content, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    subprocess.run([PY, "-W", "ignore", "-c", code, NAME, cf, pdf, res], cwd=REPO, env=dict(os.environ, YONE_CATALOG_DIR=DATA, YONE_AUTH="off"), check=True)
    return pdf, json.load(open(res, encoding="utf-8"))


def judge(pdf, res):
    """쪽 수 = 원본 쪽 수 · 쪽마다 원본 쪽 차례 — 덩어리를 받은 면은 그 덩어리의 원본 쪽을 차례로, 넘쳐 더한 쪽(받은 덩어리 없음)은 앞 쪽 + 1.
    PDF 쪽 = 그려진 면(빈 덧쪽은 크롬이 지움) — 면 목록(names)과 PDF 쪽 수가 다르면 덧쪽이 지워진 것이라 PDF 쪽 수로 본다"""
    ref = pymupdf.open(REF)
    book = pymupdf.open(pdf)
    bad = []
    if book.page_count != ref.page_count:
        bad.append(f"쪽 수 {book.page_count} ≠ 원본 {ref.page_count}")
    seq, seen, prev = [], {}, 0
    for o in res["orig"]:
        if o:
            i = seen.get(str(o), 0)
            seen[str(o)] = i + 1
            cur = o[i] if i < len(o) else prev + 1
        else:
            cur = prev + 1 if prev else 1
        seq.append(cur)
        prev = cur
    print(f"책 {book.page_count}쪽 · 원본 {ref.page_count}쪽 · 면 {len(seq)}개(빈 덧쪽 포함) · 넣은 보고 {res['report']}")
    for b in bad[:30]:
        print("  ✗", b)
    return not bad, seq


def per_unit(pdf):
    """단원마다 쪽 수 — 원본과 책에서 단원 첫 면(머리 「UNIT/LESSON …」 큰 번호)이 놓인 쪽을 찾아 맞댄다"""
    ref, book = pymupdf.open(REF), pymupdf.open(pdf)
    heads = lambda d: [k + 1 for k in range(d.page_count) if any(s["size"] > 20 for b in d[k].get_text("dict")["blocks"] for l in b.get("lines", []) for s in l["spans"]
                                                                if s["text"].strip() and s["bbox"][1] < 20 / 25.4 * 72 + 30)]
    a, b = heads(ref), heads(book)
    print("원본 단원 첫 쪽:", a)
    print("책 단원 첫 쪽:  ", b)
    return a == b


def judge_reg(reg_pdf):
    import pagecmp
    reg = pymupdf.open(reg_pdf)
    units = {}
    for g in UNITS:
        wd = os.path.join(os.path.dirname(unit_dir(g)), "work")
        st = json.load(open(os.path.join(wd, "상태.json"), encoding="utf-8"))
        el = json.load(open(os.path.join(wd, "elems.json"), encoding="utf-8"))
        for k, rp in enumerate(st["pages"]):
            units[rp] = (g, el[str(k + 1)])
    want = [1, 2, 3, 14, 15, 25]                                         # 견본 원고 차례(원본 차례) — 표지 · 지문 펼침면 · 요약 펼침면 · 마지막
    if reg.page_count != len(want):
        print(f"  ✗ 등록 쪽 {reg.page_count} ≠ {len(want)}")
        return False
    tot, bad = 0, []
    for i, rp in enumerate(want):
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
        for r, e in zip(res, es):
            ok = r.get("my") is not None if e.get("원고") else r["ok"]
            tot += 1
            if not ok:
                bad.append(f"면 {g} · 원본 {rp}쪽(등록 {i + 1}쪽) {r['id']}")
        print(f"  면 {g} · 원본 {rp}쪽 → 등록 {i + 1}쪽", flush=True)
    print(f"맞대기 — 요소 {tot - len(bad)}/{tot} 맞음")
    for b in bad[:30]:
        print("  ✗", b)
    return not bad


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    content = records()
    json.dump(content, open(os.path.join(OUT, "원고_전체.json"), "w", encoding="utf-8"), ensure_ascii=False)
    print("원고 덩어리", len(content["원고"]), "·", [(r["_원본쪽"][0], len(r["_원본쪽"])) for r in content["원고"]])
    if os.environ.get("JOIN_ONLY_RECORDS"):
        sys.exit(0)
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
        if os.environ.get("JOIN_REGISTER", "1") != "0":
            cat = next(p["catalog"] for p in json.load(open(os.path.join(DATA, "_units", "plans.json"), encoding="utf-8")) if p.get("catalog"))
            if subprocess.run([PY, os.path.join(E2E, "attach_origin.py"), f"{cat['series']}/{cat['design']}", REF, "--base", BASE], cwd=REPO).returncode:
                sys.exit("템플릿 보기 확인 실패 — 원본 페이지 차례가 안 나온다")
    finally:
        srv.kill()
    if os.environ.get("JOIN_BOOK", "0") == "1":                         # 책 만들기 검사 — 2026-10-20 사용자 「템플릿만 만들어지면 된다, 책 만들기는 contents 원고 연동 때」 · 켤 때만
        pdf, res = build(content)
        ok, _ = judge(pdf, res)
        ok_u = per_unit(pdf)
        allow = STATE.get("허용") or {}
        for k, why in allow.items():                                         # 사용자 확정 예외 — 판정에서 빼되 늘 보인다
            if k.startswith("책:"):
                print(f"  허용 「{k[2:]}」 — {why}")
        if not (ok and ok_u) and any(k.startswith("책:") for k in allow):
            print("  → 쪽 수 · 파트 시작 쪽 차이는 위 허용(사용자 확정)으로 판정에서 뺌 — 원고 다 들어감 · 덩어리 차례는 원본과 같음")
            ok = ok_u = res["report"].get("unfilled") == {} and not res["report"].get("unknown")
        print("7 책 만들기 판정:", "통과" if ok and ok_u else "실패", "→", pdf)
    else:
        print("7 책 만들기 — 건너뜀(JOIN_BOOK=1 이면 돈다 · contents 원고 연동 때)")
    if os.environ.get("JOIN_REGISTER", "1") == "0":
        sys.exit(0)
    plans = json.load(open(os.path.join(DATA, "_units", "plans.json"), encoding="utf-8"))
    cat = next(p["catalog"] for p in plans if p.get("catalog"))
    ddir = os.path.join(REPO, "catalog", cat["series"], "designs", cat["design"])
    print("8 등록 카드", ddir)
    ok9 = judge_reg(os.path.join(ddir, "참고", "reference.pdf"))
    print("9 맞대기 판정:", "통과" if ok9 else "실패")
