# -*- coding: utf-8 -*-
"""배점 배분 — 학교 총점을 **원고 문항 수**에 나눠 준다.

사용자 결정(`_결정.json`): 머리표 문항 수는 항상 원고 기준이고, **총점은 학교
상수를 유지**한 채 원고 문항 수에 재배분한다.

문제는 프로파일마다 배점을 적어 둔 **키 이름이 다르다**는 것이다(`관측값`,
`정본_배점표_26-1-기말`, `배분규칙`, `선택형_배점분포_정본`, `관측_배점표` …).
16명이 따로 실측해 쓴 결과라 이름 규약이 없다. 그래서 이름이 아니라 **값의 모양**
으로 찾는다 — 배점처럼 생긴 숫자(0.3~10.0)와 총점처럼 생긴 숫자(20~100)를 구분한다.

배분 원칙:
  - 정본 문항 수 == 원고 문항 수  → 정본 배점 **그대로**
  - 다르면 → 정본 분포의 **모양을 유지한 채** 원고 문항 수로 다시 뽑고,
    마지막에 총점이 정확히 맞도록 잔차를 조정한다. 그리고 **재배분했다고 알린다**.
  - 총점을 못 찾으면 배점을 **아예 넣지 않는다**(0으로 채우지 않는다).

⚠ 유형→배점 매핑은 만들지 않는다. 명일3 실증 — 같은 어법 문항이 3.5와 3.2로
갈린다. 배점은 유형이 아니라 난이도로 배정된다.
"""
import re

_SCORE_RANGE = (0.2, 12.0)      # 문항 배점처럼 생긴 값
_TOTAL_RANGE = (15.0, 100.0)    # 총점처럼 생긴 값
_RE_NUM = re.compile(r"\d+(?:\.\d+)?")


def _nums_in(v):
    """dict/list/str 아무 데서나 숫자를 긁어낸다."""
    out = []
    if isinstance(v, (int, float)):
        out.append(float(v))
    elif isinstance(v, str):
        for m in _RE_NUM.finditer(v):
            out.append(float(m.group(0)))
    elif isinstance(v, list):
        for x in v:
            out += _nums_in(x)
    elif isinstance(v, dict):
        for k, x in v.items():
            if str(k).startswith("_"):
                continue
            out += _nums_in(x)
    return out


def _walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield path + "." + str(k), v
            for p2, v2 in _walk(v, path + "." + str(k)):
                yield p2, v2
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield f"{path}[{i}]", v


def totals(prof):
    """프로파일에서 선택형·서답형 총점을 찾는다. 못 찾으면 None."""
    sel = essay = None
    for path, v in _walk(prof.get("score") or {}):
        key = path.split(".")[-1]
        if not isinstance(v, (int, float)):
            continue
        f = float(v)
        if not (_TOTAL_RANGE[0] <= f <= _TOTAL_RANGE[1]):
            continue
        if any(w in key for w in ("선택형만점", "선택형_합", "선택형")) and sel is None:
            sel = f
        elif any(w in key for w in ("서답형만점", "서답형_합", "서답형",
                                    "서술형_합", "서술형")) and essay is None:
            essay = f
    # 산문에 적힌 "선택형 80 / 서답형 20" 형태도 건진다
    if sel is None or essay is None:
        blob = " ".join(str(v) for _p, v in _walk(prof.get("score") or {})
                        if isinstance(v, str))
        m = re.search(r"선택형[^0-9]{0,8}(\d{2}(?:\.\d+)?)[^0-9]{0,12}"
                      r"서[답술]형[^0-9]{0,8}(\d{1,3}(?:\.\d+)?)", blob)
        if m:
            sel = sel if sel is not None else float(m.group(1))
            essay = essay if essay is not None else float(m.group(2))
    return sel, essay


def observed(prof, kind):
    """정본에서 관측된 문항별 배점 목록. kind = '선택형' | '서답형'."""
    want = ("선택형", "객관식") if kind == "선택형" else ("서답형", "서술형", "서논술")
    best = []
    for path, v in _walk(prof.get("score") or {}):
        key = path.split(".")[-1]
        if not any(w in key for w in want):
            continue
        vals = [x for x in _nums_in(v)
                if _SCORE_RANGE[0] <= x <= _SCORE_RANGE[1]]
        if len(vals) > len(best):
            best = vals
    return sorted(best)


def _fit(dist, n, total, unit=0.1):
    """분포 dist 의 모양을 유지한 채 n 개를 뽑아 합이 total 이 되게 한다."""
    if n <= 0:
        return []
    if not dist:
        base = round(total / n / unit) * unit
        vals = [base] * n
    elif len(dist) == n:
        vals = list(dist)
    else:
        # 분포를 n 개 지점에서 균등 표집 — 낮은 값에서 높은 값으로(학교 관행 다수)
        vals = [dist[int(round(i * (len(dist) - 1) / max(n - 1, 1)))]
                for i in range(n)]
    # 잔차 보정: 합이 total 과 정확히 맞게 unit 단위로 나눠 얹는다
    vals = [round(v / unit) * unit for v in vals]
    cur = round(sum(vals), 6)
    steps = int(round((total - cur) / unit))
    i = 0
    guard = 0
    while steps != 0 and guard < 100000:
        j = i % n
        step = unit if steps > 0 else -unit
        nv = round(vals[j] + step, 6)
        if _SCORE_RANGE[0] <= nv <= _SCORE_RANGE[1]:
            vals[j] = nv
            steps += -1 if steps > 0 else 1
        i += 1
        guard += 1
    return [round(v, 2) for v in vals]


def from_allocation(prof):
    """프로파일의 정규화 블록(score.allocation)을 읽는다. 없으면 None.

    학교마다 배점을 적어 둔 키 이름이 제각각이라 값의 모양으로 더듬는 것보다
    이 블록이 훨씬 정확하다. 여기 값이 있으면 휴리스틱은 쓰지 않는다.
    """
    a = (prof.get("score") or {}).get("allocation")
    if not isinstance(a, dict):
        return None
    tot = a.get("총점") or {}
    sel = tot.get("선택형")
    ess = tot.get("서답형")
    if not isinstance(sel, (int, float)):
        return None
    obs_sel = [float(x) for x in (a.get("정본_선택형") or [])
               if isinstance(x, (int, float))]
    obs_ess = [float(x) for x in (a.get("정본_서답형") or [])
               if isinstance(x, (int, float))]
    return {
        "sel_total": float(sel),
        "essay_total": float(ess) if isinstance(ess, (int, float)) else None,
        "obs_sel": obs_sel, "obs_essay": obs_ess,
        "unit": float(a.get("단위") or 0.1),
        "confidence": a.get("확신도"),
        "basis": a.get("근거"),
    }


def allocate(prof, n_select, n_essay):
    """원고 문항 수에 배점을 배분한다.

    Returns:
        {"선택형": [...], "서답형": [...], "총점": (sel, essay), "notes": [...]}
        총점을 못 찾으면 목록이 비어 있고 notes 에 사유가 남는다.
    """
    notes = []
    unit = 0.1
    norm = from_allocation(prof)
    if norm:
        sel_total, essay_total = norm["sel_total"], norm["essay_total"]
        obs_sel, obs_essay = norm["obs_sel"], norm["obs_essay"]
        unit = norm["unit"]
        notes.append(f"배점 근거: {norm['basis']} ({norm['confidence']})")
    else:
        sel_total, essay_total = totals(prof)
        obs_sel = observed(prof, "선택형")
        obs_essay = observed(prof, "서답형")
        notes.append("score.allocation 블록이 없어 값의 모양으로 더듬었다 "
                     "— 정확도가 떨어진다. 프로파일에 블록을 채울 것.")

    out = {"선택형": [], "서답형": [],
           "총점": (sel_total, essay_total), "notes": notes}

    if sel_total is None:
        notes.append("선택형 총점을 프로파일에서 못 찾았다 — 배점을 넣지 않는다.")
    elif n_select:
        if len(obs_sel) == n_select:
            out["선택형"] = list(obs_sel)
            notes.append(f"선택형 {n_select}문항: 정본 배점 그대로(문항 수 일치).")
        else:
            out["선택형"] = _fit(obs_sel, n_select, sel_total, unit)
            notes.append(
                f"선택형 {n_select}문항: 정본은 {len(obs_sel)}문항이라 "
                f"분포 모양을 유지한 채 재배분했다(합 {sel_total}).")

    if essay_total is None and n_essay:
        notes.append("서답형 총점을 프로파일에서 못 찾았다 — 배점을 넣지 않는다.")
    elif n_essay:
        if len(obs_essay) == n_essay:
            out["서답형"] = list(obs_essay)
            notes.append(f"서답형 {n_essay}문항: 정본 배점 그대로(문항 수 일치).")
        else:
            out["서답형"] = _fit(obs_essay, n_essay, essay_total, unit)
            notes.append(
                f"서답형 {n_essay}문항: 정본은 {len(obs_essay)}문항이라 "
                f"분포 모양을 유지한 채 재배분했다(합 {essay_total}).")
    return out


if __name__ == "__main__":
    import sys
    from core.render_vivlio.series.mockexam import profile as P
    for key in (sys.argv[1:] or P.available()):
        prof = P.raw(key)
        s, e = totals(prof)
        os_, oe = observed(prof, "선택형"), observed(prof, "서답형")
        print(f"{key:6s} 총점 선택형={s} 서답형={e} | 관측 {len(os_)}·{len(oe)}문항"
              f" 합 {round(sum(os_),1)}·{round(sum(oe),1)}")
