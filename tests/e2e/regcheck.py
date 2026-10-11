"""등록 카드 다시 그리기 — 편집기 코드를 바꾸면 main 에 올리기 전에 돌린다. 절차: docs/편집기_재현/절차.md 「지키는 장치」 5.

    python3 tests/e2e/regcheck.py                         등록된 편집기 제작 카드 전부 → 결과 파일
    python3 tests/e2e/regcheck.py --verdict <틀>/<카드> 가까워짐|멀어짐 "<근거>"
                                                          바뀐 카드에 판정을 적는다(그 책 원본과 맞대 본 결과)

카드마다 문서 묶음(units.json)을 빈 편집기 데이터에 들여와 등록 때와 같은 함수(routes.units.fill_svgs → core.units.pdf.to_pdf)로
① 이 체크아웃 코드 ② origin/main 코드 로 각각 그려 쪽마다 맞댄다 — 이 브랜치의 변경이 기존 책을 바꿨는가만 본다
(등록본과의 차이는 main 에 원래 있던 것일 수 있어 따로 적기만 한다). 바뀐 쪽은 나란히 그림
(~/Downloads/편집기재현/_regcheck/<틀>_<카드>/p<쪽>_side.png — 왼쪽 main · 오른쪽 이 브랜치)을 남긴다.

결과 파일 ~/Downloads/편집기재현/_regcheck/결과.json — {commit: 돌린 판의 HEAD, cards: {<틀>/<카드>: {changed: [...], verdict, why}}}.
main 머지 지킴 훅(.claude/hooks/editor-guard.py)이 이 파일을 본다: 머지할 브랜치 끝과 commit 이 같고, 바뀐 카드가 없거나
바뀐 카드마다 판정이 「가까워짐」이어야 머지가 된다(멀어졌으면 그 변경을 고친다).
"""
import glob, json, os, shutil, subprocess, sys, tempfile, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.path.expanduser("~/Downloads/편집기재현/_regcheck")
RESULT = os.path.join(OUT, "결과.json")

DRAW = r'''
import json, os, shutil, sys
series, did, tmp, pdf, code = sys.argv[1:6]
REPO = os.getcwd()
cat = os.path.join(tmp, "catalog")
os.makedirs(os.path.join(cat, "_units"))
for n in os.listdir(os.path.join(REPO, "catalog")):
    if n != "_units":
        os.symlink(os.path.join(REPO, "catalog", n), os.path.join(cat, n))
shutil.copy(os.path.join(REPO, "catalog", "_units", "specs.json"), os.path.join(cat, "_units", "specs.json"))
base = {"id": "base", "name": "기본 (브랜드 없음)", "tokens": {"color": {"ink": "#231f20", "white": "#ffffff"}, "font": {"body": "Noto Sans CJK KR"}}, "styles": {}}
for k, v in (("skins", [base]), ("blocks", []), ("parts", []), ("pages", []), ("plans", []), ("sets", [])):
    json.dump(v, open(os.path.join(cat, "_units", k + ".json"), "w", encoding="utf-8"))
os.environ["YONE_CATALOG_DIR"] = cat
sys.path.insert(0, code)
from core.units import package, store
from core.units import pdf as _pdf
from routes.units import fill_svgs, _ctx
ddir = os.path.join(REPO, "catalog", series, "designs", did)
pid, _ = package.load(json.load(open(os.path.join(ddir, "units.json"), encoding="utf-8")))
lib = store.library()
plan = store.by_id(lib["plans"])[pid]
svgs, _, spec = fill_svgs(lib, plan, plan.get("content") or {}, _ctx(lib, plan.get("skin")))
_pdf.to_pdf(svgs, float(spec["w"]), float(spec["h"]), pdf, title="regcheck")
print("ok")
'''


def cards():
    out = []
    for p in sorted(glob.glob(os.path.join(REPO, "catalog", "*", "designs", "*", "design.json"))):
        info = json.load(open(p, encoding="utf-8"))
        if info.get("made") == "editor" and os.path.exists(os.path.join(os.path.dirname(p), info.get("units") or "units.json")):
            out.append((p.split(os.sep)[-4], p.split(os.sep)[-2], info.get("name") or ""))
    return out


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()


def draw(series, did, code, pdf):
    tmp = tempfile.mkdtemp(prefix="regcheck_")
    try:
        r = subprocess.run([sys.executable, "-W", "ignore", "-c", DRAW, series, did, tmp, pdf, code], cwd=REPO, capture_output=True, text=True)
        return None if r.returncode == 0 and os.path.exists(pdf) else ((r.stderr.strip().splitlines() or ["?"])[-1])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def compare(a_pdf, b_pdf, out):
    """쪽마다 다른 화소(110dpi · 48 넘는 차이). 바뀐 쪽은 나란히 그림"""
    import pymupdf
    from PIL import Image, ImageChops
    a, b = pymupdf.open(a_pdf), pymupdf.open(b_pdf)
    changed = [f"쪽 수 {a.page_count} → {b.page_count}"] if a.page_count != b.page_count else []
    for i in range(min(a.page_count, b.page_count)):
        pa, pb = a[i].get_pixmap(dpi=110), b[i].get_pixmap(dpi=110)
        A = Image.frombytes("RGB", (pa.width, pa.height), pa.samples)
        B = Image.frombytes("RGB", (pb.width, pb.height), pb.samples).resize(A.size)
        d = ImageChops.difference(A, B).convert("L").point(lambda v: 255 if v > 48 else 0)
        n = sum(d.histogram()[255:])
        if n:
            bb = [round(v / 110 * 25.4, 1) for v in d.getbbox()]
            if out:
                os.makedirs(out, exist_ok=True)
                side = Image.new("RGB", (A.width * 2 + 10, A.height), "red")
                side.paste(A, (0, 0)); side.paste(B, (A.width + 10, 0)); side.save(os.path.join(out, f"p{i + 1}_side.png"))
            changed.append(f"{i + 1}쪽 다른 화소 {n} · 자리 {bb} mm")
    return a.page_count, changed


def run():
    dirty = git("status", "--porcelain", "--", "core", "routes", "templates", "static")
    if dirty:
        print("⚠ 커밋 안 한 편집기 코드가 있다 — 결과는 이 상태로 그린 것. 머지 확인에 쓰려면 커밋한 뒤 다시 돌린다")
    git("fetch", "-q", "origin", "main")
    base_code = tempfile.mkdtemp(prefix="regcheck_main_")
    arc = subprocess.run(["git", "archive", "origin/main", "core", "routes", "templates", "static"], cwd=REPO, capture_output=True)
    subprocess.run(["tar", "-x", "-C", base_code], input=arc.stdout, check=True)
    res = {"commit": git("rev-parse", "HEAD"), "main": git("rev-parse", "origin/main"), "dirty": bool(dirty),
           "time": time.strftime("%Y-%m-%d %H:%M"), "cards": {}}
    try:
        for series, did, name in cards():
            key = f"{series}/{did}"
            out = os.path.join(OUT, f"{series}_{did}")
            shutil.rmtree(out, ignore_errors=True)
            work = tempfile.mkdtemp(prefix="regcheck_pdf_")
            new, old = os.path.join(work, "new.pdf"), os.path.join(work, "main.pdf")
            err = draw(series, did, REPO, new) or draw(series, did, base_code, old)
            if err:
                res["cards"][key] = {"name": name, "error": err}
                print(f"✗ {key} 「{name}」 — 다시 그리기 실패: {err}")
                continue
            pages, changed = compare(old, new, out)
            _, vs_reg = compare(os.path.join(REPO, "catalog", series, "designs", did, "참고", "reference.pdf"), new, None)
            res["cards"][key] = {"name": name, "pages": pages, "changed": changed, "등록본과_다름": len(vs_reg)}
            shutil.rmtree(work, ignore_errors=True)
            note = f" (등록본과는 {len(vs_reg)}쪽 다름 — main 에 원래 있던 차이)" if vs_reg and not changed else ""
            if changed:
                print(f"△ {key} 「{name}」 — 이 브랜치가 {len(changed)}곳 바꿈 (그림: 왼쪽 main · 오른쪽 이 브랜치 {out})")
                for c in changed[:12]:
                    print("    " + c)
            else:
                print(f"○ {key} 「{name}」 — {pages}쪽 그대로{note}")
    finally:
        shutil.rmtree(base_code, ignore_errors=True)
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    bad = [k for k, v in res["cards"].items() if v.get("error") or v.get("changed")]
    print(f"바뀐 카드 {len(bad)}" + (" — 바뀐 카드마다 그 책 원본과 맞대 --verdict 로 판정을 적는다" if bad else ""))
    return 1 if bad else 0


def verdict(key, v, why):
    res = json.load(open(RESULT, encoding="utf-8"))
    if key not in res["cards"]:
        sys.exit(f"결과에 없는 카드 {key}")
    if v not in ("가까워짐", "멀어짐"):
        sys.exit("판정은 가까워짐 · 멀어짐 중 하나")
    res["cards"][key].update(verdict=v, why=why)
    json.dump(res, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"{key} 판정 {v} — {why}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verdict":
        verdict(sys.argv[2], sys.argv[3], " ".join(sys.argv[4:]))
    else:
        sys.exit(run())
