"""구성표 — 원본 카드의 면 판정(관리 「지면 보기」 = routes/catalog.py design_layouts 의 faces)을 대본 폴더에 옮겨 적는다.
절차 2단계 「면 나누기」. 만드는 단위(「구성」 번호)는 면 하나 — 이 판정으로만 정한다, 눈으로 나눈 목록은 쓰지 않는다.
판정이 찾은 되풀이 묶음은 「차례견본」으로 같이 적는다(7단계 책 만들기 검사에서 원본 차례와 맞대는 데만 쓴다).

    python3 tests/e2e/layouts.py <틀>/<카드> <대본 폴더 이름>     → tests/e2e/replay/<대본>/구성.json (판정 그대로)
    python3 tests/e2e/layouts.py --check <대본 폴더 이름>          → 구성.json 이 지금 판정과 같은가(replay.py 가 돌기 전에 부른다)

판정이 틀리면 구성.json 을 손으로 고치지 않는다 — design_layouts 기준을 고치고, 등록된 책 전체를 다시 돌려 전후를 비교해
사용자에게 보인 뒤 이 명령을 다시 돌린다. 구성.json 의 「확인」은 사용자가 구성 목록을 확인한 뒤에 true 로 적는다.
"""
import hashlib, json, os, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)


def judged(series, did):
    from routes.catalog import design_layouts
    r = design_layouts(series, did)
    rows = [{"번호": k + 1, "이름": f["label"], "크기": f.get("size", 1), "쪽": f["pages"], "견본": f["show"]} for k, f in enumerate(r.get("faces") or [])]
    return rows, hashlib.sha1(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12], \
        [{"이름": l["label"], "쪽": l["pages"], "묶음": l["unit"]} for l in r["layouts"]]


def path_of(unit):
    return os.path.join(REPO, "tests", "e2e", "replay", unit, "구성.json")


def write(card, unit):
    series, did = card.split("/")
    rows, sig, order = judged(series, did)
    p = path_of(unit)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump({"원본": card, "판정": sig, "확인": False, "구성": rows, "차례견본": order}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"면 {len(rows)}개 → {p}")
    for r in rows:
        print(f"  {r['번호']}. {r['이름']} — {r['크기']}쪽 면 · {len(r['쪽'])}쪽 · 견본 {r['견본']}")


def check(unit):
    """→ (통과, 이유). 구성.json 이 없거나 · 판정과 다르거나 · 사용자 확인 전이면 실패"""
    p = path_of(unit)
    if not os.path.exists(p):
        return False, f"구성.json 없음 — 먼저 python3 tests/e2e/layouts.py <틀>/<카드> {unit}"
    d = json.load(open(p, encoding="utf-8"))
    series, did = d["원본"].split("/")
    if not os.path.isdir(os.path.join(REPO, "catalog", series, "designs", did)) and d.get("확인"):
        return True, f"면 {len(d.get('구성') or [])}개 · 원본 카드 {d['원본']} 은 끝난 뒤 지웠다 — 확인받은 구성표 그대로"   # 다시 판정할 원본이 없다(편집기 제작 등록 뒤 PDF 카드 지움)
    rows, sig, _ = judged(series, did)
    if d.get("판정") != sig or d.get("구성") != rows:
        return False, "구성.json 이 지금 구성 판정과 다르다 — 손으로 고치지 말고 판정 기준(design_layouts)을 고친 뒤 layouts.py 를 다시 돌린다"
    if not d.get("확인"):
        return False, "면 목록을 사용자에게 보여 확인받은 뒤 구성.json 「확인」을 true 로"
    return True, f"면 {len(rows)}개 · 판정 {sig}"


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        ok, why = check(sys.argv[2])
        print(("통과 — " if ok else "막힘 — ") + why)
        sys.exit(0 if ok else 1)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    write(sys.argv[1], sys.argv[2])
