"""구성표 — 원본 카드의 구성 판정(관리 「지면 보기」 = routes/catalog.py design_layouts)을 대본 폴더에 옮겨 적는다.
절차 2단계 「구성 나누기」. 구성은 이 판정으로만 정한다 — 눈으로 나눈 목록은 쓰지 않는다.

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
    rows = [{"번호": k + 1, "이름": l["label"], "쪽": l["pages"], "견본": l["show"], "묶음": l["unit"]} for k, l in enumerate(r["layouts"])]
    return rows, hashlib.sha1(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:12]


def path_of(unit):
    return os.path.join(REPO, "tests", "e2e", "replay", unit, "구성.json")


def write(card, unit):
    series, did = card.split("/")
    rows, sig = judged(series, did)
    p = path_of(unit)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    json.dump({"원본": card, "판정": sig, "확인": False, "구성": rows}, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"구성 {len(rows)}개 → {p}")
    for r in rows:
        print(f"  {r['번호']}. {r['이름']} — {len(r['쪽'])}면 · 견본 {r['견본']}")


def check(unit):
    """→ (통과, 이유). 구성.json 이 없거나 · 판정과 다르거나 · 사용자 확인 전이면 실패"""
    p = path_of(unit)
    if not os.path.exists(p):
        return False, f"구성.json 없음 — 먼저 python3 tests/e2e/layouts.py <틀>/<카드> {unit}"
    d = json.load(open(p, encoding="utf-8"))
    series, did = d["원본"].split("/")
    rows, sig = judged(series, did)
    if d.get("판정") != sig or d.get("구성") != rows:
        return False, "구성.json 이 지금 구성 판정과 다르다 — 손으로 고치지 말고 판정 기준(design_layouts)을 고친 뒤 layouts.py 를 다시 돌린다"
    if not d.get("확인"):
        return False, "구성 목록을 사용자에게 보여 확인받은 뒤 구성.json 「확인」을 true 로"
    return True, f"구성 {len(rows)}개 · 판정 {sig}"


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--check":
        ok, why = check(sys.argv[2])
        print(("통과 — " if ok else "막힘 — ") + why)
        sys.exit(0 if ok else 1)
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    write(sys.argv[1], sys.argv[2])
