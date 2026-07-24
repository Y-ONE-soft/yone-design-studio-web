"""문항 배점 분배 — 합이 총점(기본 100)과 정확히 일치하도록.

규칙 출처: 조판/.claude/skills/baejeom-typeset/references/distribution.md
  - 유형을 3티어(낮음/중간/높음)로 나누고 값은 0.1점 단위, vLow < vMid < vHigh
  - 중심값 ~= 총점/문항수, 초안 c-0.2 / c / c+0.2 에서 시작해 정확히 맞춘다
  - 이 원고는 전원 선택형(서답형 없음)

난이도 신호 우선순위:
  1) 원고에 [3점]이 박혀 있으면 원 출제기관이 고난도로 매긴 것 -> 높음
  2) 그 외에는 유형 티어표
"""

TIER_LOW = {           # 이해형 — 글 전체를 한 번 읽으면 풀린다
    "OBJ-CTN-TOPIC", "OBJ-CTN-TITLE", "OBJ-CTN-GIST", "OBJ-CTN-CLAIM",
    "OBJ-CTN-MATCH", "OBJ-CTN-PURPOSE", "OBJ-CTN-TONE",
}
TIER_HIGH = {          # 재배열·삽입·장문 — 구조 조작이 필요하다
    "OBJ-FLW-ORDER", "OBJ-FLW-INSERT", "OBJ-LNG-HEADER",
}


def _tier(item):
    if item.get("type") in TIER_HIGH:
        return 2
    if item.get("score") == 3:          # 원고의 원 배점 = 출제기관 난이도 표시
        return 2
    if item.get("type") in TIER_LOW:
        return 0
    return 1


def solve(counts, total, step=0.1):
    """(nLow, nMid, nHigh) -> (vLow, vMid, vHigh) 합이 정확히 total.

    0.1점 단위 · vLow < vMid < vHigh · 중심값 근처를 우선 탐색.
    해가 없으면 None.
    """
    n = sum(counts)
    if n == 0:
        return None
    c = round(total / n / step)
    best = None
    for dl in range(-8, 1):             # vLow <= c
        for dh in range(0, 9):          # vHigh >= c
            for dm in range(dl + 1, dh):
                v = (c + dl, c + dm, c + dh)
                if not (0 < v[0] < v[1] < v[2]):
                    continue
                s = sum(cnt * val for cnt, val in zip(counts, v))
                if abs(s * step - total) < 1e-9:
                    spread = (dh - dl, abs(dm))
                    if best is None or spread < best[0]:
                        best = (spread, tuple(round(x * step, 2) for x in v))
    return best[1] if best else None


def assign(items, total=100):
    """items 에 최종 배점을 매긴다. 반환: 분배 요약 dict."""
    tiers = [_tier(it) for it in items]
    # 높음 티어가 비면 2티어로 축약 (해가 없어지는 것을 막는다)
    counts = [tiers.count(0), tiers.count(1), tiers.count(2)]
    vals = solve(counts, total)
    if vals is None:
        raise ValueError(f"배점 해 없음: counts={counts} total={total}")
    for it, t in zip(items, tiers):
        it["score"] = vals[t]
    got = round(sum(it["score"] for it in items), 6)
    if abs(got - total) > 1e-9:
        raise ValueError(f"배점 합 불일치: {got} != {total}")
    return {"tier_counts": {"낮음": counts[0], "중간": counts[1], "높음": counts[2]},
            "tier_values": {"낮음": vals[0], "중간": vals[1], "높음": vals[2]},
            "total": got}
