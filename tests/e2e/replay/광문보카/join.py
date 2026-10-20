"""광문보카 01 7~9단계 — 잇기 · 책 만들기 검사 · 편집기 제작 등록 · 맞대기 (docs/편집기_재현/절차.md 「작업 순서 — 확정」).

    python3 tests/e2e/replay/광문보카/join.py            (JOIN_REGISTER=0 이면 등록 없이 잇기 · 책 만들기만)
    → ~/Downloads/편집기재현/광문보카@합본/ (rec.log · 책.pdf · 맞대기 결과)

잇기 — 면마다 검사를 통과한 문서(replay.py 광문보카@<면> check 데이터)를 「문서 파일 내보내기」 묶음으로 꺼내, 빈 편집기에서
  「문서 파일 가져오기」(첫 묶음은 새 문서로, 나머지는 이 문서 끝에)로 표지 → 간지 · 차례 · MEMO · 마지막 → 단어 면들 → 지문형 면 차례로 잇는다.
  MEMO 면은 쪽 패널 「분류」 MEMO(자리 없는 면 — 원고 덩어리 {"구분": "MEMO"} 가 고른다),
  지문형 면 오른쪽은 「넘치면 더할 페이지」 본문 왼쪽(지문형 검사는 그 면 혼자 돌아 이어 갈 페이지가 없었다).
책 만들기 검사 — 원본 원고 전체(원본 차례 덩어리)를 {원고: [레코드 …]} 로 넣어 책을 그리고(관리 등록과 같은 함수)
  쪽 수 · 쪽마다 원본 쪽 차례(덩어리의 _원본쪽, 넘쳐 더한 쪽은 앞 쪽 + 1)가 같은지 맞댄다.
8 편집기 제작 등록 — 면마다 견본 원고 하나(SAMPLE)를 넣고 「관리에 등록」(단어장 폴더) → 원본 PDF 를 템플릿에 붙인다(attach_origin.py).
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
OUT = os.path.expanduser("~/Downloads/편집기재현/광문보카@합본")
DATA = os.path.join(CACHE, "광문보카@합본", "catalog")
NAME = "광문보카 (편집기 제작)"
UNITS = ["1", "2,3,7,8", "4", "9"]                                       # 가져올 문서(면 검사 판) 차례 — 표지 · 간지 · 차례 · MEMO · 마지막 · 단어 면 · 지문형
STATE = json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))
REF = os.path.join(REPO, STATE["ref"])
FACES = json.load(open(os.path.join(REPO, "catalog", "vocab", "designs", "xe164a0e5", "faces.json"), encoding="utf-8"))["faces"]
BIND = "번호+표제어+발음+파생어+파생품사+파생뜻+품사+뜻+예문+해석"
BIND9 = "꼬리표+번호+낱말+품사+뜻+예문"


def unit_dir(g):
    """그 면의 마지막 통과 판 — 사람 조작 판 · 바로 넣기 판 중 나중 것"""
    best = None
    for u in (f"광문보카@{g}", f"광문보카@{g}~바로"):
        try:
            v = json.load(open(os.path.expanduser(f"~/Downloads/편집기재현/{u}/판정.json"), encoding="utf-8"))
        except Exception:
            continue
        if v.get("통과") and (best is None or v["때"] > best[1]):
            best = (u, v["때"])
    if not best:
        sys.exit(f"면 {g} 통과 판 없음 — 먼저 replay.py 광문보카@{g} check")
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


def line(pno, lo, hi, x0=0, x1=200):
    """그 쪽 기준선 lo~hi 의 글(띄어쓰기 그대로)"""
    sp = [s for s in EN._spans(DOC[pno - 1]) if lo <= s["base"] <= hi and x0 <= s["x"] < x1]
    return re.sub(r"\s+", " ", "".join(s["text"] for s in sorted(sp, key=lambda s: (round(s["base"], 1), s["x"])))).strip()


def face_of(p):
    return next((f["label"] for f in FACES if p in f["pages"]), None)


def records():
    recs, p, last = [], 2, DOC.page_count
    while p < last:
        lab = face_of(p)
        if lab == "PART 간지":
            recs.append({"파트번호": re.sub(r"\s+", "", line(p, 38, 42)).replace("PART", "PART "), "파트": line(p, 53, 56), "파트설명": line(p, 63, 66), "_원본쪽": [p]})
            p += 1
        elif lab == "PART 차례":
            sp = EN._spans(DOC[p - 1])
            tot = max(s["base"] for s in sp if s["x"] > 100 and s["base"] > 50)                 # 합계(모두 …개) — 오른쪽 맨 아래 줄
            rows = sorted({round(s["base"], 1) for s in sp if 50 < s["base"] < tot - 1 and s["x"] < 100})
            recs.append({"파트": line(p, 43, 46), "단원+낱말수": [{"단원": line(p, b - .3, b + .3, 0, 100), "낱말수": line(p, b - .3, b + .3, 100)} for b in rows],
                         "합계": line(p, tot - .3, tot + .3), "_원본쪽": [p]})
            p += 1
        elif lab in ("UNIT 첫 면", "UNIT 첫 면 (지문형)"):
            pages = [p, p + 1]
            q = p + 2
            while q < last and face_of(q) in ("본문 왼쪽 면", "본문 오른쪽 면"):
                pages.append(q)
                q += 1
            head = {"파트": line(p, 0, 6), "단원이름": line(p, 8, 11), "단원번호": line(p, 13, 16)}
            if lab == "UNIT 첫 면":
                head[BIND] = [r for x in pages for r in EN.entries(REF, x)]
            else:
                head[BIND9] = [r for x in pages for r in EN.compact(REF, x)]
            recs.append(dict(head, _원본쪽=pages))
            p = q
        elif lab == "MEMO 면":
            recs.append({"구분": "MEMO", "_원본쪽": [p]})
            p += 1
        else:
            sys.exit(f"{p}쪽 면을 모른다 — {lab}")
    return {"원고": recs}


SAMPLE = {2: None, 3: None, 4: [4, 5, 6, 7], 76: [76, 77], 17: None}    # 견본 원고 — 5단계 대본이 그린 원본 쪽(단어 면은 그 쪽들 단어만)


def sample(content):
    out = []
    for r in content["원고"]:
        p0 = r["_원본쪽"][0]
        if p0 not in SAMPLE:
            continue
        r = dict(r)
        if SAMPLE[p0]:
            r["_원본쪽"] = SAMPLE[p0]
            if BIND in r:
                r[BIND] = [x for q in SAMPLE[p0] for x in EN.entries(REF, q)]
            if BIND9 in r:
                r[BIND9] = [x for q in SAMPLE[p0] for x in EN.compact(REF, q)]
        out.append(r)
    return {"원고": out}


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
    env = dict(os.environ, YONE_CATALOG_DIR=DATA, YONE_AUTH="off")
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
    i = names.index("MEMO 면")
    st += page_step(i, f"분류 — {i + 1}쪽 「MEMO 면」 → MEMO(원고 덩어리 「구분: MEMO」가 고른다)", [
        {"fill": {"at": "#side #s-gubun", "value": "MEMO"}, "wait": 1200},
        {"js": f"(() => {{ const q = planPg(docPages()[{i}].id); if (!q || q.구분 !== 'MEMO') throw new Error('분류 안 들어감'); return '분류 ' + q.구분; }})()"}])
    i = names.index("UNIT 첫 면 (지문형) 오른쪽")
    st += page_step(i, f"넘치면 더할 페이지 — {i + 1}쪽 「UNIT 첫 면 (지문형) 오른쪽」 → 본문 왼쪽", [
        {"pick": {"at": "#side #s-cont", "text": "본문 왼쪽"}, "wait": 900},
        {"js": f"(() => {{ const p = docPages()[{i}]; const t = docPages().find(x => x.id === p.cont); if (!t || t.name !== '본문 왼쪽') throw new Error('이어 갈 면 지정 실패'); return '이어 갈 면 ' + t.name; }})()"}])
    if os.environ.get("JOIN_REGISTER", "1") == "0":
        return st
    st += put_content(sample(content), "원고 넣기 — 면마다 견본 원고 하나(원고 덩어리 차례 — 바깥 시스템이 보내는 꼴)")
    st += [S("관리에 등록 — 단어장 폴더", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
           {"pick": {"at": "#side #s-reg-series", "value": "vocab"}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
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
_pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), sys.argv[3], title="광문보카", timeout=1800)
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
    want = [1, 2, 3, 4, 5, 6, 7, 17, 76, 77, 160]                       # 견본 원고 차례(원본 차례) — 간지 · 차례 · 단어 면(덧쪽 둘) · MEMO · 지문형 · 마지막
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
    pdf, res = build(content)
    ok, _ = judge(pdf, res)
    ok_u = per_unit(pdf)
    allow = STATE.get("허용") or {}
    for k, why in allow.items():                                         # 사용자 확정 예외 — 판정에서 빼되 늘 보인다
        if k.startswith("책:"):
            print(f"  허용 「{k[2:]}」 — {why}")
    if not (ok and ok_u) and any(k.startswith("책:") for k in allow):
        print("  → 쪽 수 · 단원 시작 쪽 차이는 위 허용(사용자 확정)으로 판정에서 뺌 — 원고 1,260자리 들어감 · 덩어리 차례는 원본과 같음")
        ok = ok_u = res["report"].get("unfilled") == {} and not res["report"].get("unknown")
    print("7 책 만들기 판정:", "통과" if ok and ok_u else "실패", "→", pdf)
    if os.environ.get("JOIN_REGISTER", "1") == "0":
        sys.exit(0)
    plans = json.load(open(os.path.join(DATA, "_units", "plans.json"), encoding="utf-8"))
    cat = next(p["catalog"] for p in plans if p.get("catalog"))
    ddir = os.path.join(REPO, "catalog", cat["series"], "designs", cat["design"])
    print("8 등록 카드", ddir)
    ok9 = judge_reg(os.path.join(ddir, "참고", "reference.pdf"))
    print("9 맞대기 판정:", "통과" if ok9 else "실패")
