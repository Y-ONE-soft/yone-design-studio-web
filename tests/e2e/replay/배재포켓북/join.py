"""배재1 포켓북 7단계 — 잇기 · 책 만들기 검사 (docs/편집기_재현/절차.md 「작업 순서 — 확정」 7).

    python3 tests/e2e/replay/배재포켓북/join.py
    → ~/Downloads/편집기재현/배재포켓북@합본/ (rec.log · 책.pdf · 맞대기 결과)

잇기 — 구성마다 검사를 통과한 문서(replay.py 배재포켓북@<구성> check 가 남긴 데이터)를 「문서 파일 내보내기」 묶음으로 꺼내,
  빈 편집기에서 「문서 파일 가져오기」(첫 묶음은 새 문서로, 나머지는 이 문서 끝에)로 앞면 → 면들 → 뒷면 차례로 잇는다.
  색만 다른 면(교과서 · 모의고사)은 쪽 패널 「구분」에 그 값을 친다 — 원고 덩어리의 「구분」으로 면이 골라진다.
8 편집기 제작 등록 — 이은 문서에 면마다 견본 원고 하나(SAMPLE 원본 쪽 덩어리)를 「원고 넣기」로 넣고 문서 패널 「관리에 등록」(포켓북 폴더).
9 맞대기 — 등록 PDF 의 쪽마다 그 구성의 요소 목록(5단계 elems.json)으로 원본 그 쪽과 다시 판정(원고 요소 · 쪽 번호는 들어갔나만).
책 만들기 검사 — 원본 원고 전체(원고.json 덩어리 88개 — 원본 차례)를 {원고: [레코드 …]} 로 넣어 책을 그리고(관리 등록과 같은 함수),
  쪽 수 · 쪽마다 원본 쪽(덩어리의 _원본쪽) · 면이 원본 판정의 그 쪽 구성과 같은지 맞댄다.
"""
import base64, json, os, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
E2E = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, E2E)
from mkpage import S, open_doc, put_content                             # noqa: E402

PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 5197)
BASE = f"http://127.0.0.1:{PORT}"
CACHE = os.path.expanduser("~/.cache/yone-replay")
OUT = os.path.expanduser("~/Downloads/편집기재현/배재포켓북@합본")
DATA = os.path.join(CACHE, "배재포켓북@합본", "catalog")
NAME = "배재1 포켓북 (편집기 제작)"
ORDER = ["1", "2", "3", "4", "5", "6"]                                   # 앞면 · 분석 · FLOWNOTE · 암기 · 삽화 분석 · 뒷면
SAMPLE = [2, 42, 3, 5, 45, 12, 46, 44]                                   # 면마다 견본 원고 — 5단계 대본이 그린 원본 쪽(면 차례)
SRC = json.load(open(os.path.join(HERE, "원고.json"), encoding="utf-8"))
GUSEONG = json.load(open(os.path.join(HERE, "구성.json"), encoding="utf-8"))


def unit_dir(g):
    """그 구성의 마지막 통과 판 — 사람 조작 판 · 바로 넣기 판 중 나중 것"""
    best = None
    for u in (f"배재포켓북@{g}", f"배재포켓북@{g}~바로"):
        try:
            v = json.load(open(os.path.expanduser(f"~/Downloads/편집기재현/{u}/판정.json"), encoding="utf-8"))
        except Exception:
            continue
        if v.get("통과") and (best is None or v["때"] > best[1]):
            best = (u, v["때"])
    if not best:
        sys.exit(f"구성 {g} 통과 판 없음 — 먼저 replay.py 배재포켓북@{g} check")
    return os.path.join(CACHE, best[0], "catalog")


def export_all():
    files = []
    for g in ORDER:
        cat = unit_dir(g)
        f = os.path.join(OUT, f"구성_{g}.json")
        code = ("import json, sys; from core.units import store, package; lib = store.library(); "
                "p = [x for x in lib['plans'] if x.get('name') == sys.argv[2]][-1]; "
                "json.dump(package.export(lib, p['id']), open(sys.argv[1], 'w', encoding='utf-8'), ensure_ascii=False)")
        subprocess.run([PY, "-c", code, f, NAME], cwd=REPO, env=dict(os.environ, YONE_CATALOG_DIR=cat, YONE_AUTH="off"), check=True)
        pk = json.load(open(f, encoding="utf-8"))
        print(f"  내보냄 구성 {g} — 쪽 {len(pk['pages'])} ({os.path.basename(os.path.dirname(cat))})", flush=True)
        files.append((f, [p["name"] for p in pk["pages"]]))
    return files


def records():
    """원고.json(yos-pocketbook-v1 덩어리) → 편집기 원고 {원고: [레코드 …]} — 자리 이름은 대본(make.py)의 자리와 같다"""
    recs = []
    for it in SRC["원고"]:
        if "지문" in it:
            r = {"출처": it["출처"], "지문": [it["지문"]], "해석": it["해석"], "책이름": SRC["book"]["책이름"], "구분": it["구분"]}
            if it.get("그림"):
                r["그림"] = "data:image/png;base64," + base64.b64encode(open(os.path.join(HERE, it["그림"]), "rb").read()).decode()
        elif "흐름" in it:
            r = {"흐름제목+흐름글": [[{"흐름제목": f["제목"], "흐름글": f["글"]}] for f in it["흐름"]], "주제": it["주제"], "요약문": it["요약문"],
                 "낱말+뜻+동의어+반의어": [[{k: v[k] for k in ("낱말", "뜻", "동의어", "반의어")} for v in it["동반의어"]]],
                 "단원": it["단원"], "구분": it["구분"]}
        else:
            r = {"암기지문": [it["암기지문"], it["암기지문"]], "단원": it["단원"], "구분": it["구분"]}
        r["_원본쪽"] = it["_원본쪽"]
        recs.append(r)
    return {"원고": recs, "학교": ["배재1", "배재1"], "시험": ["2학기 중간고사", "2학기 중간고사"]}


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
    for _ in range(480):                                                 # 4분 — 기동 때 모든 디자인 구성을 미리 계산한다(warm_layouts)
        try:
            urllib.request.urlopen(BASE + "/api/units/library", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    sys.exit(f"서버가 안 뜸 — {OUT}/server.log")


def sample(content):
    """견본 원고 — 면마다 그 면을 그린 원본 쪽의 덩어리 하나(면 차례)"""
    by = {r["_원본쪽"][0]: r for r in content["원고"]}
    return dict(content, 원고=[by[p] for p in SAMPLE])


def steps(files, content):
    st = open_doc(NAME)
    for k, (g, (f, _)) in enumerate(zip(ORDER, files)):
        st += [S(f"문서 파일 가져오기 — 구성 {g} ({'새 문서로' if k == 0 else '이 문서 끝에'})", 1200), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
               {"pick": {"at": "#side #s-pkg-mode", "value": "new" if k == 0 else "append"}, "wait": 700},
               {"upload": {"at": "#side #s-pkg-file", "click": "#side #s-pkg-in", "path": f}, "wait": 4000},
               {"js": "(() => '쪽 ' + docPages().length + ' · ' + document.querySelector('#st').textContent)()"}]
    names = [n for _, ns in files for n in ns]
    st += [{"js": f"(() => {{ const n = docPages().length; if (n !== {len(names)}) throw new Error('이은 쪽 ' + n); return '이은 쪽 ' + n; }})()"}]
    for i, nm in enumerate(names):                                     # 색만 다른 면 — 쪽 패널 「구분」
        g = "교과서" if "교과서" in nm else "모의고사" if "모의고사" in nm else None
        if not g:
            continue
        st += [S(f"구분 — {i + 1}쪽 「{nm}」 → {g}", 900),
               {"js": f"(() => {{ openPage(docPages()[{i}]); return '쪽 열기 {i + 1}'; }})()"}, {"wait": 1500},   # 쪽 찾아가기만 바로 — 가운데 지면을 굴린 직후 누르면 옆 지면이 눌려 구분이 한 칸씩 밀렸다
               {"js": f"(() => {{ if (idx() !== {i}) throw new Error('쪽 안 열림 ' + (idx() + 1)); return '{i + 1}쪽 열림'; }})()"},
               {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800}, {"fill": {"at": "#side #s-gubun", "value": g}, "wait": 1200},
               {"js": f"(() => {{ const q = planPg(docPages()[{i}].id); if (!q || q.구분 !== {json.dumps(g)}) throw new Error('구분 안 들어감'); return '구분 ' + q.구분; }})()"}]
    st += put_content(sample(content), "원고 넣기 — 면마다 견본 원고 하나(원고 덩어리 차례 — 바깥 시스템이 보내는 꼴)")
    st += [S("관리에 등록 — 포켓북 폴더", 1500), {"key": "Escape", "wait": 500}, {"key": "Escape", "wait": 800},
           {"pick": {"at": "#side #s-reg-series", "value": "pocketbook"}, "wait": 900}, {"click": "#side #s-reg", "wait": 3000}]
    st += [{"until": "plan.catalog && plan.catalog.design && /등록됨/.test(document.querySelector('#s-reg-st').textContent)", "wait": 300}] * 40
    st += [{"js": "(() => { const t = document.querySelector('#s-reg-st').textContent; if (!/등록됨/.test(t)) throw new Error('관리 등록 안 됨 — ' + t); "
                  "return '등록 ' + JSON.stringify(plan.catalog) + ' · ' + t; })()"}]
    return st


def build(content):
    """원고 전체로 책 — 관리 등록과 같은 함수(routes.units.fill_svgs → core.units.pdf.to_pdf). 면마다 받은 레코드도 돌려준다"""
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
_pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), sys.argv[3], title="배재1 포켓북")
json.dump({"names": [s.get("label") for s in svgs], "orig": [(r or {}).get("_원본쪽") for r in recs], "report": rep}, open(sys.argv[4], "w", encoding="utf-8"), ensure_ascii=False)
'''
    cf, pdf, res = os.path.join(OUT, "원고.json"), os.path.join(OUT, "책.pdf"), os.path.join(OUT, "책.json")
    json.dump(content, open(cf, "w", encoding="utf-8"), ensure_ascii=False)
    subprocess.run([PY, "-W", "ignore", "-c", code, NAME, cf, pdf, res], cwd=REPO, env=dict(os.environ, YONE_CATALOG_DIR=DATA, YONE_AUTH="off"), check=True)
    return pdf, json.load(open(res, encoding="utf-8"))


def judge(pdf, res):
    """쪽 수 = 원본 쪽 수 · 쪽마다 원본 쪽 차례 · 그 쪽의 면 = 원본 판정에서 그 쪽이 든 구성"""
    import pymupdf
    ref = pymupdf.open(os.path.join(REPO, json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))["ref"]))
    book = pymupdf.open(pdf)
    bad = []
    if book.page_count != ref.page_count:
        bad.append(f"쪽 수 {book.page_count} ≠ 원본 {ref.page_count}")
    bw, bh, tw, th = book[0].rect.width, book[0].rect.height, ref[0].trimbox.width, ref[0].trimbox.height
    if abs(bw - tw) > 1 or abs(bh - th) > 1:                             # 쪽 크기 = 원본 재단 크기(도련 뺀 것)
        bad.append(f"쪽 크기 {bw / 72 * 25.4:.1f}×{bh / 72 * 25.4:.1f}mm ≠ 원본 {tw / 72 * 25.4:.1f}×{th / 72 * 25.4:.1f}mm")
    seq, seen = [], {}
    for o in res["orig"]:                                                # 면마다 받은 덩어리의 원본 쪽 — 펼침면이면 왼쪽 · 오른쪽 차례로
        i = seen.get(str(o), 0) if o else 0
        if o:
            seen[str(o)] = i + 1
        seq.append(o[i] if o and i < len(o) else None)
    if seq and seq[0] is None:
        seq[0] = 1
    if seq and seq[-1] is None:
        seq[-1] = ref.page_count
    for k, (o, nm) in enumerate(zip(seq, res["names"])):
        if o != k + 1:
            bad.append(f"{k + 1}쪽 — 원본 {o}쪽 덩어리가 왔다(면 {nm})")
    print(f"책 {book.page_count}쪽 · 원본 {ref.page_count}쪽 · 넣은 보고 {res['report']}")
    for b in bad[:30]:
        print("  ✗", b)
    return not bad


def judge_reg(reg_pdf):
    """9 맞대기 — 등록 PDF 쪽 = 앞면 · 견본 면들(펼침면은 두 쪽) · 뒷면. 쪽마다 그 구성 요소 목록으로 원본 그 쪽과 판정"""
    import pymupdf
    import pagecmp
    ref_path = os.path.join(REPO, json.load(open(os.path.join(HERE, "상태.json"), encoding="utf-8"))["ref"])
    reg = pymupdf.open(reg_pdf)
    units = {}
    for g in ORDER:
        wd = os.path.join(os.path.dirname(unit_dir(g)), "work")
        st = json.load(open(os.path.join(wd, "상태.json"), encoding="utf-8"))
        el = json.load(open(os.path.join(wd, "elems.json"), encoding="utf-8"))
        for k, rp in enumerate(st["pages"]):
            units[rp] = (g, el[str(k + 1)])
    want = [1] + [q for p in SAMPLE for q in ([p, p + 1] if p in (12, 46) else [p])] + [118]
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
            if e.get("원고") or (str(e.get("text", "")).strip().isdigit() and int(e["text"]) == rp):   # 원고 · 쪽 번호(책 차례 번호) — 들어갔나만
                e = dict({kk: vv for kk, vv in e.items() if kk != "text"}, pad=8.0, search=8.0, 원고=True)
            es.append(e)
        res = pagecmp.measure(ref_path, rp, pdf, es)
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
    fresh_data()
    srv = server()
    try:
        sf = os.path.join(OUT, "steps.json")
        content = records()
        json.dump(steps(files, content), open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        r = subprocess.run([PY, "tests/e2e/rec.py", BASE + "/units", sf, os.path.join(OUT, "join.mp4"), "1600", "1000", "8"], cwd=REPO,
                           env=dict(os.environ, REC_FAST="1"), capture_output=True, text=True)
        log = r.stdout + r.stderr
        open(os.path.join(OUT, "rec.log"), "w").write(log)
        print("\n".join(ln for ln in log.splitlines() if "js →" in ln or "ERR" in ln)[-3000:])
        if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
            sys.exit("잇기 실패 — " + os.path.join(OUT, "rec.log"))
    finally:
        srv.kill()
    pdf, res = build(content)
    ok = judge(pdf, res)
    print("7 책 만들기 판정:", "통과" if ok else "실패", "→", pdf)
    plans = json.load(open(os.path.join(DATA, "_units", "plans.json"), encoding="utf-8"))
    cat = next(p["catalog"] for p in plans if p.get("catalog"))
    ddir = os.path.join(REPO, "catalog", cat["series"], "designs", cat["design"])
    print("8 등록 카드", ddir)
    ok9 = judge_reg(os.path.join(ddir, "참고", "reference.pdf"))
    print("9 맞대기 판정:", "통과" if ok9 else "실패")
