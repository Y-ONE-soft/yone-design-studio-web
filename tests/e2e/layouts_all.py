"""구성 판정 전후 비교 — 판정 기준(routes/catalog.py pdf_layouts)을 고치면 등록된 PDF 디자인 전부를 origin/main 코드와
이 체크아웃 코드로 각각 판정해 구성 목록이 바뀐 책만 보인다. 절차: 판정이 틀리면 기준을 고치고 전부 다시 돌려 전후 비교.

    python3 tests/e2e/layouts_all.py              바뀐 책만 전후 목록
    python3 tests/e2e/layouts_all.py --all        안 바뀐 책도 목록
    python3 tests/e2e/layouts_all.py --pdf        절차로 등록한 책(관리 「PDF 등록」, design.json made: pdf)만
    python3 tests/e2e/layouts_all.py --pdf workbook/d3   그 표시 전에 올린 책(워크북 정본 원본 10-09)을 더해서
"""
import glob, json, os, subprocess, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

JUDGE = r'''
import json, sys
sys.path[:0] = [sys.argv[1], sys.argv[4]]          # 판정 코드는 그 판 · 나머지 모듈은 이 체크아웃

from routes.catalog import pdf_layouts
out = {}
for key, pdf, rules in json.load(open(sys.argv[2], encoding="utf-8")):
    r = pdf_layouts(pdf, key.split("/")[0], rules)
    out[key] = [f"{l['label']} — {len(l['pages'])}면 · 묶음 {l['unit']}" for l in r["layouts"]]
json.dump(out, open(sys.argv[3], "w", encoding="utf-8"), ensure_ascii=False)
'''


def designs():
    sys.path.insert(0, REPO)
    from routes.catalog import _design_pdf
    out = []
    for p in sorted(glob.glob(os.path.join(REPO, "catalog", "*", "designs", "*", "design.json"))):
        series, did = p.split(os.sep)[-4], p.split(os.sep)[-2]
        dj = json.load(open(p, encoding="utf-8"))
        pdf = _design_pdf(series, did)
        pick = [a for a in sys.argv[1:] if "/" in a]
        if pdf and dj.get("made") != "editor" and ("--pdf" not in sys.argv or dj.get("made") == "pdf" or f"{series}/{did}" in pick):
            out.append((f"{series}/{did}", pdf, dj.get("layout_rules", True)))
    return out


def judge(code, items, tmp, tag):
    src, dst = os.path.join(tmp, "items.json"), os.path.join(tmp, tag + ".json")
    json.dump(items, open(src, "w", encoding="utf-8"), ensure_ascii=False)
    r = subprocess.run([sys.executable, "-W", "ignore", "-c", JUDGE, code, src, dst, REPO], cwd=REPO, capture_output=True, text=True)
    if r.returncode:
        sys.exit(f"{tag} 판정 실패: {r.stderr.strip().splitlines()[-1:]}")
    return json.load(open(dst, encoding="utf-8"))


def main(show_all):
    items = designs()
    with tempfile.TemporaryDirectory() as tmp:
        base = os.path.join(tmp, "main")
        os.makedirs(base)
        subprocess.run(["git", "fetch", "-q", "origin", "main"], cwd=REPO)
        arc = subprocess.run(["git", "archive", "origin/main", "core", "routes", "templates", "static"], cwd=REPO, capture_output=True, check=True)
        subprocess.run(["tar", "-x", "-C", base], input=arc.stdout, check=True)
        old, new = judge(base, items, tmp, "main"), judge(REPO, items, tmp, "new")
    changed = 0
    for key, _, _ in items:
        same = old[key] == new[key]
        changed += not same
        if same and not show_all:
            continue
        print(f"{'○' if same else '△'} {key}")
        if same:
            for l in new[key]:
                print("    " + l)
        else:
            print("  main:")
            for l in old[key]:
                print("    " + l)
            print("  고친 뒤:")
            for l in new[key]:
                print("    " + l)
    print(f"디자인 {len(items)}개 · 바뀐 책 {changed}")


if __name__ == "__main__":
    main("--all" in sys.argv)
