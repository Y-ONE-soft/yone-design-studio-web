"""해 본 동작 목록 — 편집기 재현 4단계 「가르기」. 절차: docs/편집기_재현/절차.md

    python3 tests/e2e/actions.py build              검사를 통과한 판의 대본에서 동작을 모아 목록을 새로 쓴다
    python3 tests/e2e/actions.py split <steps.json> …   대본마다 처음 보는 동작 → 처음 보는 종류 / 검증한 종류

동작 = 「무엇을 어디에 했나」(누르기 · 칸 입력 · 목록 고르기 · 그리기 · 파일 올리기 …). 넣은 값은 보지 않는다
(서체 칸에 무엇을 쳤나, 지면 몇 mm 를 눌렀나는 같은 동작). 확인용 js · 기다림 · 자막 · 사진은 동작이 아니다.
목록에 없는 동작이 하나라도 든 대본은 처음 보는 종류 — 사람 조작으로 검사한다.

목록의 출처 = 검사 판정이 「통과」인 판(~/Downloads/편집기재현/<단위>/판정.json)의 대본(~/.cache/yone-replay/<단위>/work/steps.json).
조작 도구(rec.py)가 목록을 사람처럼 펼쳐 고르게 바뀐 뒤(SINCE)의 판만 센다 — 그 전 판은 값을 코드로 넣었다.
"""
import glob, json, os, re, sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
LIST = os.path.join(REPO, "tests", "e2e", "replay", "해본동작.json")
OUT = os.path.expanduser("~/Downloads/편집기재현")
WORK = os.path.expanduser("~/.cache/yone-replay")
SINCE = "2026-10-10 18:00"                    # 사람 조작 목록 고르기(.selmenu 항목 누르기)로 고정된 뒤


def kinds(st):
    """단계 하나 → 동작 이름들. 자리가 지면 좌표·화면 픽셀이면 「지면」으로 묶는다."""
    # 칸 자리에 든 이름(단락 스타일 「실전·발문」, 원고 자리 「문항번호」)은 값이다 — 같은 칸이면 같은 동작
    spot = lambda v: re.sub(r'(data-st="|data-cs="|slotfmt\.|slot_fmt\.)[^:."]+', r"\1*", v) if isinstance(v, str) else "지면"   # slot_fmt.<자리> — 인디자인 맞춤 뒤 칸 이름(2026-10-14)
    out = []
    for k in ("click", "dbl", "move"):
        if k in st:
            out.append(f"{k} {spot(st[k])}")
    if "clickif" in st:
        out.append(f"click {spot(st['clickif']['at'])}")
    if "drag" in st:
        out.append(f"drag {spot(st['drag']['from'])} → {spot(st['drag']['to'])}")
    if "draw" in st:
        out.append(f"draw {st['draw']['tool']}")
    if "type" in st:
        out.append("type")
    if "fill" in st:
        out.append(f"fill {spot(st['fill']['at'])}")
    if "write" in st:
        out.append("write 지면 글상자")
    if "key" in st:
        out.append(f"key {st['key']}")
    if "pick" in st:
        p = st["pick"]
        v = str(p.get("value") or "")
        out.append(f"pick {spot(p['at'])}" + (f" = {v}" if v.startswith("__") else ""))   # 「새 …」 같은 만드는 항목은 따로
    if "upload" in st:
        out.append(f"upload {st['upload']['at']}")
    if "answer" in st:
        out.append("answer 묻는 창")
    return out


def build():
    seen, used = {}, []
    for jp in sorted(glob.glob(os.path.join(OUT, "*", "판정.json"))):
        unit = os.path.basename(os.path.dirname(jp))
        j = json.load(open(jp, encoding="utf-8"))
        sp = os.path.join(WORK, unit, "work", "steps.json")
        if not j.get("통과") or j.get("바로넣기") or unit.endswith("~바로") or j.get("때", "") < SINCE or not os.path.exists(sp):
            continue
        used.append(unit)
        for st in json.load(open(sp, encoding="utf-8")):
            for k in kinds(st):
                e = seen.setdefault(k, {"횟수": 0, "처음": unit})
                e["횟수"] += 1
    old = json.load(open(LIST, encoding="utf-8")) if os.path.exists(LIST) else {"출처": [], "동작": {}}
    for k, v in old["동작"].items():                                   # 그 판을 바로 넣기로 다시 돌려 출처에서 빠져도 한 번 검증한 동작은 남긴다
        seen.setdefault(k, v)
    used = sorted(set(used) | set(old["출처"]))
    json.dump({"출처": used, "동작": dict(sorted(seen.items()))}, open(LIST, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"해 본 동작 {len(seen)}가지 — 통과한 판 {len(used)}개에서 → {os.path.relpath(LIST, REPO)}")


def split(paths):
    known = json.load(open(LIST, encoding="utf-8"))["동작"]
    for p in paths:
        new = {}
        for i, st in enumerate(json.load(open(p, encoding="utf-8"))):
            for k in kinds(st):
                if k not in known:
                    new.setdefault(k, i + 1)
        print(f"{p}: {'처음 보는 종류' if new else '검증한 종류'}")
        for k, i in new.items():
            print(f"  · {k}  ({i}번째 단계)")


if __name__ == "__main__":
    if sys.argv[1:2] == ["build"]:
        build()
    elif sys.argv[1:2] == ["split"] and sys.argv[2:]:
        split(sys.argv[2:])
    else:
        sys.exit(__doc__)
