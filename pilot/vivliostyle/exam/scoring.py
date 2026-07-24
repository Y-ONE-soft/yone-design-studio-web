"""문항 배점 분배 — 합이 총점(기본 100)과 정확히 일치하도록.

규칙 출처: 조판/.claude/skills/baejeom-typeset/references/distribution.md
  - 유형을 3티어(낮음/중간/높음)로 나누고 값은 0.1점 단위, vLow < vMid < vHigh
  - 중심값 ~= 총점/문항수, 초안 c-0.2 / c / c+0.2
  - 이 원고는 전원 선택형(서답형 없음)

**티어 값만으로 총점을 정확히 맞추려 하면 안 된다.** 문항 수 조합에 따라 0.1점
단위 해가 없거나(8·27 분포), 있어도 2.4/2.5/3.2 처럼 평균에서 크게 벌어진다.
그래서 티어는 촘촘한 사다리(c-0.2/c/c+0.2)로 고정하고, 남는 잔여를 문항 몇 개에
±0.1 씩 얹어 흡수한다 — 실제 시험지도 이 방식이다.

난이도 신호:
  - 1차: 유형 티어표 (이해형 < 핵심형 < 구조조작형)
  - 2차: 원고의 원 [3점] 표시 — 잔여 +0.1 을 받을 우선순위로만 쓴다.
    선별 원고는 [3점] 문항 비중이 과반(35문항 중 19)이라 티어로는 못 쓴다.
"""

TIER_LOW = {           # 이해형 — 글 전체를 한 번 읽으면 풀린다
    "OBJ-CTN-TOPIC", "OBJ-CTN-TITLE", "OBJ-CTN-GIST", "OBJ-CTN-CLAIM",
    "OBJ-CTN-MATCH", "OBJ-CTN-PURPOSE", "OBJ-CTN-TONE",
}
TIER_HIGH = {          # 재배열·삽입·장문 — 구조 조작이 필요하다
    "OBJ-FLW-ORDER", "OBJ-FLW-INSERT", "OBJ-LNG-HEADER",
}


def _tier(item):
    t = item.get("type")
    if t in TIER_HIGH:
        return 2
    if t in TIER_LOW:
        return 0
    return 1


def assign(items, total=100, step=0.1):
    """items 에 최종 배점을 매긴다 (합 == total 보장). 반환: 분배 요약."""
    n = len(items)
    if not n:
        return {"total": 0}
    unit = round(total / step)                  # 0.1점 단위 정수 총점
    c = round(unit / n)                         # 중심값(0.1 단위)
    ladder = (c - 2, c, c + 2)                  # 초안 c-0.2 / c / c+0.2

    tiers = [_tier(it) for it in items]
    vals = [ladder[t] for t in tiers]
    diff = unit - sum(vals)                     # 남거나 모자란 0.1 스텝 수

    # 보정 우선순위: 올릴 땐 어려운 쪽부터, 내릴 땐 쉬운 쪽부터.
    # 같은 조건이면 원고 [3점] 문항을 먼저, 그 다음 문항 번호 순 (결정론적).
    order = sorted(range(n), key=lambda i: (
        -tiers[i] if diff > 0 else tiers[i],
        0 if items[i].get("score") == 3 else 1,
        i))
    bump = 1 if diff > 0 else -1
    for k in range(abs(diff)):
        if k >= n:                              # 한 바퀴로 안 되면 두 바퀴째
            pass
        vals[order[k % n]] += bump

    for it, v in zip(items, vals):
        it["score"] = round(v * step, 2)

    got = round(sum(it["score"] for it in items), 6)
    if abs(got - total) > 1e-9:
        raise ValueError(f"배점 합 불일치: {got} != {total}")

    dist = {}
    for it in items:
        dist[it["score"]] = dist.get(it["score"], 0) + 1
    return {
        "tier_counts": {"낮음": tiers.count(0), "중간": tiers.count(1),
                        "높음": tiers.count(2)},
        "ladder": [round(v * step, 2) for v in ladder],
        "distribution": dict(sorted(dist.items())),
        "total": got,
    }
