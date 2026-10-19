"""면 판정 배우기 — 사람이 확인한 면 목록(정답) 전부를 가장 많이 그대로 내는 판정 기준값을 골라 data/faces_params.json 에 적는다.
절차 2단계 「면 나누기」: 면 목록을 확인받아 faces.json 을 적을 때마다 돌린다. 확인한 책이 늘수록 판정이 그 책들에 맞춰진다.

    python3 tests/e2e/faces_learn.py            정답 모으기 → 기준값 고르기 → 적기 → 책마다 맞음/다름
    python3 tests/e2e/faces_learn.py --check    고르지 않고 지금 기준값으로 책마다 맞음/다름만

정답 = ① 디자인 폴더 faces.json(확인받은 면 목록) ② 대본 폴더 tests/e2e/replay/<책>/구성.json 의 「확인」 true(원본.pdf 가 그 폴더나 원본 카드에 있을 때).
고르는 순서: 정답과 똑같이 나온 책 수 → 쪽 짝 맞음(같은 면 / 다른 면을 정답과 같게 본 쪽 짝의 F1 평균) → 지금 값과 가까움.
기준값만으로 못 맞추는 책은 끝에 「다름」으로 남는다 — 판정 코드(routes/catalog.py _faces)에 새 기준이 필요하다는 뜻(사람에게 보고).
"""
import glob, itertools, json, os, sys, time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
os.chdir(REPO)

GRID = {"t_new": [0.5, 0.55, 0.6, 0.65, 0.7], "t_same": [0.85, 0.9, 0.95, 0.98], "pair": [0.6, 0.7, 0.8, 0.9]}


def answers():
    """[(이름, pdf, 틀, 판정 규칙, [[쪽…] 면마다])]"""
    from routes.catalog import _design_pdf
    out, seen = [], set()
    for fj in sorted(glob.glob("catalog/*/designs/*/faces.json")):
        series, _, did = fj.split("/")[1:4]
        dj = json.load(open(os.path.dirname(fj) + "/design.json", encoding="utf-8"))
        pdf = _design_pdf(series, did)
        if pdf:
            out.append((f"{series}/{did} {dj.get('name', '')}", pdf, series, dj.get("layout_rules", True),
                        [f["pages"] for f in json.load(open(fj, encoding="utf-8"))["faces"]]))
            seen.add(f"{series}/{did}")
    for cj in sorted(glob.glob("tests/e2e/replay/*/구성.json")):
        d = json.load(open(cj, encoding="utf-8"))
        if not d.get("확인") or d.get("원본") in seen:
            continue
        series, did = d["원본"].split("/")
        pdf = os.path.join(os.path.dirname(cj), "원본.pdf")
        pdf = pdf if os.path.exists(pdf) else _design_pdf(series, did)
        if pdf and os.path.exists(pdf):
            out.append((f"{os.path.basename(os.path.dirname(cj))} (대본 구성표)", pdf, series, False, [r["쪽"] for r in d["구성"]]))
    return out


def pairs_f1(pred, key):
    """쪽 짝마다 「같은 면인가」를 정답과 견준 F1."""
    fp = {p: k for k, ps in enumerate(pred) for p in ps}
    fk = {p: k for k, ps in enumerate(key) for p in ps}
    pages = sorted(set(fp) & set(fk))
    tp = fpos = fneg = 0
    for a, b in itertools.combinations(pages, 2):
        s1, s2 = fp[a] == fp[b], fk[a] == fk[b]
        tp += s1 and s2; fpos += s1 and not s2; fneg += s2 and not s1
    return 2 * tp / (2 * tp + fpos + fneg) if tp else (1.0 if not fpos and not fneg else 0.0)


def main():
    import fitz
    from routes.catalog import _page_tokens, _faces, _face_feats, face_params, FACE_PARAMS, _FACE_PARAMS_FILE
    books = []
    for name, pdf, series, rules, key in answers():
        t = time.time()
        doc = fitz.open(pdf)
        books.append((name, doc, _page_tokens(series, doc, rules), _face_feats(doc), sorted(sorted(ps) for ps in key)))
        print(f"정답 {name} — {doc.page_count}쪽 · 면 {len(key)}개 ({time.time() - t:.0f}s)", flush=True)
    if not books:
        sys.exit("정답(확인받은 면 목록)이 없다")

    def score(P):
        res = []
        for name, doc, tok, feats, key in books:
            pred = sorted(sorted(f["pages"]) for f in _faces(doc, tok, P, feats))
            res.append((pred == key, pairs_f1(pred, key)))
        return sum(e for e, _ in res), sum(f for _, f in res) / len(res), res

    cur = face_params()
    if "--check" not in sys.argv:
        dist = lambda P: sum(abs(P[k] - cur[k]) for k in P)
        best = None
        for vals in itertools.product(*GRID.values()):
            P = dict(zip(GRID, vals))
            ex, f1, _ = score(P)
            k = (ex, round(f1, 4), -dist(P))
            if best is None or k > best[0]:
                best = (k, P)
        old = score(cur)
        if best[0][:2] > (old[0], round(old[1], 4)):
            cur = best[1]
            json.dump({"params": cur, "learned": time.strftime("%Y-%m-%d %H:%M"), "books": [b[0] for b in books],
                       "exact": best[0][0], "f1": best[0][1]}, open(_FACE_PARAMS_FILE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            print(f"기준값 바꿈 → {cur} (적음: {os.path.relpath(_FACE_PARAMS_FILE, REPO)})")
        else:
            print(f"기준값 그대로 {cur} — 더 맞는 값 없음")
    ex, f1, res = score(cur)
    print(f"\n정답 {len(books)}권 중 똑같이 나옴 {ex}권 · 쪽 짝 맞음 평균 {f1:.3f}")
    for (name, *_), (e, f) in zip(books, res):
        print(f"  {'맞음' if e else '다름'}  {name}  (쪽 짝 {f:.3f})")
    if ex < len(books):
        print("다름 = 기준값만으로 못 맞춤 — 판정 코드에 새 기준이 필요하다(사람에게 보고)")


if __name__ == "__main__":
    main()
