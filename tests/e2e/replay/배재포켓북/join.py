"""배재1 포켓북 7단계 — 잇기 · 책 만들기 검사 (docs/편집기_재현/절차.md 「작업 순서 — 확정」 7).

    python3 tests/e2e/replay/배재포켓북/join.py
    → ~/Downloads/편집기재현/배재포켓북@합본/ (rec.log · 책.pdf · 맞대기 결과)

잇기 — 구성마다 검사를 통과한 문서(replay.py 배재포켓북@<구성> check 가 남긴 데이터)를 「문서 파일 내보내기」 묶음으로 꺼내,
  빈 편집기에서 「문서 파일 가져오기」(첫 묶음은 새 문서로, 나머지는 이 문서 끝에)로 앞면 → 면들 → 뒷면 차례로 잇는다.
  색만 다른 면(교과서 · 모의고사)은 쪽 패널 「구분」에 그 값을 친다 — 원고 덩어리의 「구분」으로 면이 골라진다.
책 만들기 검사 — 원본 원고 전체(원고.json 덩어리 88개 — 원본 차례)를 {원고: [레코드 …]} 로 넣어 책을 그리고(관리 등록과 같은 함수),
  쪽 수 · 쪽마다 원본 쪽(덩어리의 _원본쪽) · 면이 원본 판정의 그 쪽 구성과 같은지 맞댄다.
"""
import base64, json, os, shutil, subprocess, sys, time, urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(HERE))))
E2E = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, E2E)
from mkpage import S, open_doc                                          # noqa: E402

PY = sys.executable
PORT = int(os.environ.get("REPLAY_PORT") or 5197)
BASE = f"http://127.0.0.1:{PORT}"
CACHE = os.path.expanduser("~/.cache/yone-replay")
OUT = os.path.expanduser("~/Downloads/편집기재현/배재포켓북@합본")
DATA = os.path.join(CACHE, "배재포켓북@합본", "catalog")
NAME = "배재1 포켓북 (편집기 제작)"
ORDER = ["1", "2", "3", "4", "5", "6"]                                   # 앞면 · 분석 · FLOWNOTE · 암기 · 삽화 분석 · 뒷면
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
    for _ in range(240):
        try:
            urllib.request.urlopen(BASE + "/api/units/library", timeout=1)
            return p
        except Exception:
            time.sleep(0.5)
    p.kill()
    sys.exit(f"서버가 안 뜸 — {OUT}/server.log")


def steps(files):
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


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    files = export_all()
    fresh_data()
    srv = server()
    try:
        sf = os.path.join(OUT, "steps.json")
        json.dump(steps(files), open(sf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        r = subprocess.run([PY, "tests/e2e/rec.py", BASE + "/units", sf, os.path.join(OUT, "join.mp4"), "1600", "1000", "8"], cwd=REPO,
                           env=dict(os.environ, REC_FAST="1"), capture_output=True, text=True)
        log = r.stdout + r.stderr
        open(os.path.join(OUT, "rec.log"), "w").write(log)
        print("\n".join(ln for ln in log.splitlines() if "js →" in ln or "ERR" in ln)[-3000:])
        if any("ERR" in ln or "Traceback" in ln for ln in log.splitlines()):
            sys.exit("잇기 실패 — " + os.path.join(OUT, "rec.log"))
    finally:
        srv.kill()
    pdf, res = build(records())
    ok = judge(pdf, res)
    print("판정: 통과" if ok else "판정: 실패", "→", pdf)
