"""배N제 v2 렌더 플랜 빌더 — content.json → bj-flows-v1 플랜.

플랜 포맷 (core/jsx/baenje_flow.body.jsx가 실행):
{
  "format": "bj-flows-v1",
  "flows": [
    {"area": "body",    "break_per_unit": true,
     "units": [{"paras":[{t,s,runs,align}], "page_break": bool,
                "unit_label": str|null, "no": int}]},
    {"area": "answers", "break_per_unit": false, "units": [...]}
  ],
  "ops": {
    "unit_masters": {"body":    {"left":"L0","right":"L2","cont":"L1"},
                     "answers": {"left":"C0","right":"C2","cont":"C1"}},
    "unit_char_style": "유닛",       # 러닝헤드 텍스트 변수가 찾는 문자스타일
    "label_style": "[기본 단락]",     # 라벨 단락(자동번호 없는 중립 스타일)
    "wide_space_style": "한글",       # 전각 공백 .notdef 방지
    "memo_master": "B",              # 뒤쪽 빈 페이지
    "keep_block_in_spread": "answers" # 한 문항 블록이 펼침면을 넘지 않게
  },
  "warnings": [...]
}

배치 의미론 = v1(engines/baenje/jsx/run.jsx)과 동일하되 차이 두 가지:
  - v1은 JSX 상태머신이 단락 종류를 판정 → v2는 파서가 판정하고 플랜에 스타일
    이름을 실어 보낸다 (JSX는 이름으로 스타일을 찾아 적용만).
  - v1은 프레임 브레이크를 JSX가 재탐색해 걸었다 → v2는 유닛 경계가 곧
    프레임 브레이크(문항 1개 = 유닛 1개). 텍스트 무변형이라 검수 1:1 대조 가능.
"""
import os
import re

from core.structure.style_resolver import load_style_map

_ASSETS = os.path.join(os.path.dirname(os.path.dirname(
    os.path.dirname(os.path.abspath(__file__)))), "core", "assets")

_MATERIAL = "baenje"

# (A)  (B) 2단 선지 머리행 — 아래 선지의 두 칸 위치에 맞춰 정렬해야 한다
_RE_AB_HEADER = re.compile(r"^\(A\)[\s\u3000]+\(B\)\s*$")
# 조합형 짧은 선지(① (a), (b) …) — 3열로 묶어 배치
_SHORT_CHOICE_MAX = 22
_PACK_MIN_CHOICES = 4


def _tables():
    smap = load_style_map()[_MATERIAL]
    return smap["BODY"], smap["ANS"]


def _para(text, style, runs=None, align=None):
    p = {"t": text, "s": style}
    if runs:
        p["runs"] = runs
    if align:
        p["align"] = align
    return p


def _has_long_blank(text):
    """긴 밑줄 답란 — 양끝정렬 시 자간이 벌어지므로 왼쪽 정렬."""
    if len(text) > 200:
        return False
    run = 0
    for ch in text:
        if ch in ("＿", "_"):
            run += 1
            if run >= 5:
                return True
        else:
            run = 0
    return False


def _choice_layout(paras):
    """유닛 안의 선지 배치 힌트 — (머리행 인덱스, 3열 묶음 인덱스들)."""
    ab_header = None
    choice_idx = []
    for i, p in enumerate(paras):
        if p["kind"] != "choice":
            continue
        if _RE_AB_HEADER.match(p["t"]):
            ab_header = i
            continue
        choice_idx.append(i)
    pack = (len(choice_idx) >= _PACK_MIN_CHOICES
            and all(len(paras[i]["t"]) <= _SHORT_CHOICE_MAX for i in choice_idx))
    return ab_header, (choice_idx if pack else [])


def content_to_plan(content, log=None):
    body_tbl, ans_tbl = _tables()
    warnings = list(content.get("warnings") or [])
    units = content.get("units") or []
    unit_by_q = {u["start_q"]: u["label"] for u in units}

    body_units = []
    for prob in content.get("problems") or []:
        paras = []
        for p in prob["paras"]:
            style = body_tbl.get(p["kind"])
            if style is None:
                style = body_tbl.get("passage")
                warnings.append(
                    f"[플랜] 스타일 미정의 종류 '{p['kind']}' → 지문으로 대체 "
                    f"({prob['no']}번)")
            paras.append(_para(p["t"], style, p.get("runs"),
                               "left" if _has_long_blank(p["t"]) else None))
        label = unit_by_q.get(prob["no"])
        ab_header, pack_idx = _choice_layout(prob["paras"])
        unit = {
            "no": prob["no"],
            "paras": paras,
            # 유닛 시작 문항은 새 페이지에서 (머리말이 그 페이지에 걸린다)
            "page_break": bool(label) and prob["no"] != (
                units[0]["start_q"] if units else None),
            "unit_label": label,
        }
        if ab_header is not None:
            unit["ab_header"] = ab_header          # 머리행 단락 인덱스
        if pack_idx:
            unit["choice_pack"] = {"columns": 3, "idx": pack_idx}
        body_units.append(unit)

    ans_units = []
    for blk in content.get("answers") or []:
        paras = []
        for p in blk["paras"]:
            style = ans_tbl.get(p["kind"])
            if style is None:
                style = ans_tbl.get("cont")
                warnings.append(
                    f"[플랜] 정답지 스타일 미정의 종류 '{p['kind']}' "
                    f"({blk['no']}번)")
            paras.append(_para(p["t"], style, p.get("runs")))
        label = unit_by_q.get(blk["no"])
        ans_units.append({
            "no": blk["no"],
            "paras": paras,
            "page_break": bool(label) and blk["no"] != (
                units[0]["start_q"] if units else None),
            "unit_label": label,
        })

    plan = {
        "format": "bj-flows-v1",
        "flows": [
            # 본문: 문항 1개 = 프레임 1개 (v1 파리티)
            {"area": "body", "break_per_unit": True, "units": body_units},
            # 정답지: 이어 흘리고, 유닛(과) 시작만 새 페이지
            {"area": "answers", "break_per_unit": False, "units": ans_units},
        ],
        "ops": {
            "unit_masters": {
                "body": {"left": "L0", "right": "L2", "cont": "L1"},
                "answers": {"left": "C0", "right": "C2", "cont": "C1"},
            },
            "unit_char_style": "유닛",
            "label_style": "[기본 단락]",
            "wide_space_style": "한글",
            "memo_master": "B",
            "keep_block_in_spread": "answers",
            # 마지막 페이지 크레딧 (배재보카 크레딧 스니펫 — 서식 그대로)
            "credit": {
                # 크레딧 면 배경 = 배N제 뒷면 디자인(큰 N·회색 밴드·연구소 로고).
                # 텍스트만 제거한 벡터 아트라 판형·색이 완성본과 1:1로 맞는다.
                "background": {
                    "file": os.path.join(_ASSETS, "baenje_credit_bg.pdf"),
                    "x": -3.0, "y": -3.0, "w": 216.0, "h": 303.0,   # 도련 포함 전면
                },
                "items": [
                    {"file": os.path.join(_ASSETS, "credit_yone.idms"),
                     "x": 23.0, "y": 96.0},
                    # 저작권 줄은 로고(왼쪽 20mm)와 왼쪽을 맞춰 바로 아래
                    {"file": os.path.join(_ASSETS, "copyright_yone.idms"),
                     "x": 20.0, "y": 270.0},
                ],
                # 라벨은 본문 포인트 색(청록) + 고딕 볼드 9pt
                "label_color": "c99m29y42k28",
                "label_font": {"family": "Gmarket Sans", "style": "Bold",
                               "size": 9.0, "space_after_add": 1.7},
                "labels": ["Writer", "Assistant", "Design", "Production",
                           "Marketer"],
            },
        },
        "warnings": warnings,
    }
    if log:
        log(f"[플랜] 본문 {len(body_units)}유닛 / 정답지 {len(ans_units)}유닛 "
            f"/ 경고 {len(warnings)}")
    return plan


def flow_paras(plan, area):
    """검수용 — 영역의 모든 단락 (텍스트, 스타일) 시퀀스."""
    for flow in plan.get("flows") or []:
        if flow["area"] != area:
            continue
        out = []
        for unit in flow["units"]:
            if unit.get("unit_label"):
                out.append((unit["unit_label"], None))    # 보이지 않는 라벨 단락
            for p in unit["paras"]:
                out.append((p["t"], p["s"]))
        return out
    return []
