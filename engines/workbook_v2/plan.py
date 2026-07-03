"""워크북 v2 렌더 플랜 빌더 — v1 파서 산출(steps)을 플랜으로 변환.

스텝별 빌더 레지스트리 방식(단계 전환): 빌더가 있는 스텝만 v2가 렌더하고,
없는 스텝은 플랜에서 제외되며 커버리지 리포트에 '미지원'으로 남는다.
스타일 결정 = core/structure/style_map.json "workbook" 섹션 (실물 인벤토리 가드).

Step3는 Phase 2에서 심은 단락 kind 주석을 그대로 사용 — 스타일 결정이
데이터 룩업 한 줄이다 (v1 processStep3 480줄의 휴리스틱을 대체).
"""
import json
import os

from core.structure.style_resolver import resolve_style

_DIR = os.path.dirname(os.path.abspath(__file__))
STEP_MAP = json.load(open(os.path.join(_DIR, "step_map.json"),
                          encoding="utf-8"))


def _style(step_unit, kind, default_kind="P"):
    try:
        v = resolve_style("workbook", step_unit, kind)
    except KeyError:
        try:
            v = resolve_style("workbook", step_unit, default_kind)
        except KeyError:
            return None
    if isinstance(v, list):
        return v[0]
    return v


# ── Step3: kind 주석 기반 (질문/지문/선지/보기/조건/답란 전부 데이터 룩업) ──

def build_step3(step_data):
    """step3 데이터 {normal:[{question_num, paragraphs}], short:[...]} → 유닛."""
    units = []
    warnings = []
    for group in ("normal", "short"):
        for item in step_data.get(group, []) or []:
            unit = []
            for p in item.get("paragraphs", []):
                text = p.get("text", "")
                kind = p.get("kind") or "UNKNOWN"
                if kind in ("GH", "A", "BLANK"):
                    continue          # 제거 대상 (style_map에서 null)
                style = _style("STEP3", kind)
                if style is None:
                    continue
                unit.append({"t": text, "s": style,
                             "runs": p.get("runs") or []})
            if unit:
                units.append(unit)
    return {"units": units, "warnings": warnings}


# ── 스텝 빌더 레지스트리 (단계 전환: 지원 스텝을 여기서 늘려간다) ────────────

STEP_BUILDERS = {
    "step3": build_step3,
}


def steps_to_plan(steps, exclude=None):
    """v1 content steps → {"format": "wb-flows-v1", "flows": [...],
    "unsupported": [스텝키]} — 미지원 스텝은 커버리지 리포트용으로 기록."""
    exclude = set(exclude or [])
    flows = []
    unsupported = []
    for step_key, step_data in steps.items():
        if step_key in exclude:
            continue
        builder = STEP_BUILDERS.get(step_key)
        if builder is None:
            unsupported.append(step_key)
            continue
        built = builder(step_data)
        target = dict(STEP_MAP.get(step_key, {}))
        flows.append({"step": step_key, "target": target,
                      "break_per_unit": True, "units": built["units"]})
    return {"format": "wb-flows-v1", "flows": flows,
            "unsupported": sorted(unsupported)}
