"""두 디자인 폴더가 같은가 — 검사(화면 대본)로 등록한 것과 제작(build.py)으로 등록한 것을 맞댄다.

    python3 tests/e2e/same_design.py <디자인 폴더 A> <디자인 폴더 B>

  문서 — units.json 의 쪽 차례(이름 · 원고마다 · 요소 수 · 요소 내용(id 빼고)) · 원고(content)
  면  — 참고/reference.pdf 면 수 · 면마다 화소(110dpi) 다른 비율
같으면 끝 줄이 「같음」, 아니면 다른 곳을 줄마다.
"""
import json, os, sys
import pymupdf
from PIL import Image, ImageChops


def doc(d):
    u = json.load(open(os.path.join(d, "units.json"), encoding="utf-8"))
    pages = {p["id"]: p for p in u["pages"]}
    seq = [(e["page"], e.get("repeat", "once")) for s in u["plan"]["sections"] for e in s["pages"]]
    seq = [(pid, rep) for pid, rep in (([(i, "once") for i in u["plan"].get("front") or []]) + seq + [(i, "once") for i in u["plan"].get("back") or []])]
    ids = {pid for pid, _ in seq}

    def strip(o):                                                      # 문서마다 새로 매긴 id·쪽 참조는 빼고 비교
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in ("id", "cont", "part", "block") and not (isinstance(v, str) and v in ids)}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o
    return [(pages[pid].get("name"), rep, json.dumps(strip(pages[pid]), ensure_ascii=False, sort_keys=True)) for pid, rep in seq], u["plan"].get("content")


def main(a, b):
    bad = 0
    da, ca = doc(a)
    db, cb = doc(b)
    if len(da) != len(db):
        print(f"쪽 수 다름 {len(da)} · {len(db)}"); bad += 1
    for k, (x, y) in enumerate(zip(da, db)):
        if x[:2] != y[:2]:
            print(f"쪽 {k + 1} 이름·원고마다 다름 {x[:2]} · {y[:2]}"); bad += 1
        elif x[2] != y[2]:
            print(f"쪽 {k + 1} ({x[0]}) 요소 다름"); bad += 1
    if ca != cb:
        print("원고 다름 — 키", sorted(set(ca or {}) ^ set(cb or {})) or "값"); bad += 1
    pa, pb = (pymupdf.open(os.path.join(d, "참고", "reference.pdf")) for d in (a, b))
    if pa.page_count != pb.page_count:
        print(f"면 수 다름 {pa.page_count} · {pb.page_count}"); bad += 1
    worst = 0.0
    for k in range(min(pa.page_count, pb.page_count)):
        im = [Image.frombytes("RGB", (p.width, p.height), p.samples) for p in (pa[k].get_pixmap(dpi=110), pb[k].get_pixmap(dpi=110))]
        diff = ImageChops.difference(*im).convert("L").point(lambda v: 255 if v > 24 else 0)
        r = sum(diff.histogram()[255:]) / (diff.width * diff.height) * 100
        worst = max(worst, r)
        if r > 0.05:
            print(f"면 {k + 1} 화소 {r:.2f}% 다름"); bad += 1
    print(f"면 {pa.page_count} · 가장 큰 화소 차이 {worst:.3f}%")
    print("같음" if not bad else f"다른 곳 {bad}")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main(sys.argv[1], sys.argv[2]) else 0)
