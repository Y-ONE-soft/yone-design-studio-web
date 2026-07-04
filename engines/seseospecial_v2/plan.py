"""세서특필 v2 렌더 플랜 빌더 — content.json(v1 파서 출력) → ss-flows 플랜.

플랜 포맷 (core/jsx/seseospecial_flow.body.jsx가 실행):
{
  "format": "ss-flows-v1",
  "part1_page": 6,                 # v1 config part1_story_page (1-기준)
  "flows": [
    {"area": "part1",   "break_per_unit": false, "units": [{"paras": [...]}]},
    {"area": "part2",   "break_per_unit": true,  "units": [{"paras": [...]}, ...]},
    {"area": "answers", "break_per_unit": false, "units": [{"paras": [...]}]}
  ]
}

배치 의미론 = v1 engines/seseospecial/jsx/run.jsx와 동일:
  - part1: 6페이지 최대 스토리에 전체 흘리기 (오버플로우 시 스프레드 추가)
  - part2: intro+main을 한 스토리에 흘리고 출처(0)/소제목(7) 앞 프레임 분리.
    v1은 FRAME_BREAK 문자 삽입(단락 수 +N) — v2는 유닛 경계 startParagraph
    NEXT_FRAME(텍스트 무변형, 검수 1:1 대조 가능). 분리 지점은 동일.
  - answers: 정답 스토리(해설_번호 사본/정답 사본 시그니처)에 흘리기.
    v1과 동일하게 정답 데이터가 없으면 flow 자체를 생략(기존 스토리 보존).

스타일 결정은 여기(데이터) — core/structure/style_map.json "seseospecial".
v1의 밑줄 ul_ranges(구형식 원고)는 runs로 변환해 이식 (실행기가 underline
속성 직접 적용 — v1 파리티, 문자스타일 아님).
"""
from core.structure.style_resolver import load_style_map

# v1 run.jsx: 프레임 브레이크 트리거 = p2 스타일 0(출처) / 7(소제목)
_P2_BREAK_CODES = (0, 7)


def _tables():
    smap = load_style_map()["seseospecial"]
    return smap["PART1"], smap["PART2"], smap["ANS"]


def _runs_from_ul_ranges(text, ul_ranges):
    """v1 ul_ranges("s:e,s:e") → runs [{t, ul}] (구형식 원고 밑줄 이식)."""
    if not ul_ranges:
        return []
    spans = []
    for part in str(ul_ranges).split(","):
        se = part.split(":")
        if len(se) != 2:
            continue
        try:
            s, e = int(se[0]), int(se[1])
        except ValueError:
            continue
        if 0 <= s < e:
            spans.append((s, min(e, len(text))))
    if not spans:
        return []
    spans.sort()
    runs = []
    pos = 0
    for s, e in spans:
        if s > pos:
            runs.append({"t": text[pos:s], "ul": False})
        if e > max(s, pos):
            runs.append({"t": text[max(s, pos):e], "ul": True})
        pos = max(pos, e)
    if pos < len(text):
        runs.append({"t": text[pos:], "ul": False})
    return runs


def _part1_flow(part1):
    P1, _, _ = _tables()
    # v1 파리티: 범위 밖 코드는 스타일 미적용(None — 실행기가 건너뜀)
    paras = [{"t": p.get("text", ""), "s": P1.get(str(p.get("style"))),
              "runs": []}
             for p in (part1 or {}).get("paragraphs", [])]
    return {"area": "part1", "break_per_unit": False,
            "units": [{"paras": paras}]}


def _part2_flow(part2):
    _, P2, _ = _tables()
    entries = list((part2 or {}).get("intro") or []) \
        + list((part2 or {}).get("main") or [])
    units = []
    cur = []
    for i, e in enumerate(entries):
        text = e.get("text", "")
        # v1 파리티: 미정의 코드는 선지(fb)로 폴백
        para = {"t": text, "s": P2.get(str(e.get("style"))) or P2["3"],
                "runs": _runs_from_ul_ranges(text, e.get("ul_ranges"))}
        # v1 브레이크: 첫 단락 제외, 출처(0)/소제목(7) 단락 앞에서 프레임 분리
        if i > 0 and e.get("style") in _P2_BREAK_CODES:
            units.append({"paras": cur})
            cur = []
        cur.append(para)
    if cur:
        units.append({"paras": cur})
    return {"area": "part2", "break_per_unit": True, "units": units}


def _answers_flow(answers):
    _, _, ANS = _tables()
    if not answers:
        return None    # v1: 정답 입력 없음 — 기존 정답 스토리 보존(스킵)
    paras = []
    for a in answers:
        code = a.get("style")
        if code is None or str(code) not in ANS:
            code = 1   # v1 파리티: 범위 밖 코드는 '정답 사본'
        paras.append({"t": a.get("text", ""),
                      "s": ANS[str(code)], "runs": []})
    return {"area": "answers", "break_per_unit": False,
            "units": [{"paras": paras}]}


def content_to_plan(content, part1_page=6):
    part2 = content.get("part2") or {}
    flows = [
        _part1_flow(content.get("part1")),
        _part2_flow(part2),
    ]
    ans = _answers_flow(part2.get("answers"))
    if ans:
        flows.append(ans)
    return {"format": "ss-flows-v1", "part1_page": int(part1_page),
            "flows": flows}


def unit_paras(unit):
    """검수/테스트용 — 유닛의 단락 목록."""
    if not unit or unit.get("skip"):
        return []
    return unit.get("paras") or []


def flow_paras(flow):
    """검수/테스트용 — 플로우 전체 단락(유닛 순서 평탄화)."""
    out = []
    for u in flow.get("units", []):
        out.extend(unit_paras(u))
    return out
