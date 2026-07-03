"""(교재, STEP 단원, 단락종류) → InDesign 단락스타일 결정.

룩업 데이터: core/structure/style_map.json (docs/taxonomy/11 데이터화).
학교/교재 커스텀은 override dict를 병합해 해결 — 코드 수정 없이 데이터로.

사용:
    from core.structure.style_resolver import resolve_style
    style = resolve_style("workbook", "STEP3", "P", has_underline=True)
    # → "STEP 03 > 지문 밑줄 있음"    (없으면 None = 제거 대상 또는 미정의)
"""
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
_MAP_PATH = os.path.join(_DIR, "style_map.json")
_map_cache = None


def load_style_map():
    global _map_cache
    if _map_cache is None:
        with open(_MAP_PATH, encoding="utf-8") as f:
            _map_cache = json.load(f)
    return _map_cache


_MISSING = object()


def resolve_style(material, step_unit, kind, has_underline=None, overrides=None):
    """단락스타일 이름 반환. 명시적 null(제거 대상)은 None, 미정의는 KeyError.

    has_underline: kind가 P일 때 밑줄 변형 스타일(P@underline / P@no_underline)
        우선 적용. 변형 키가 없으면 기본 P로 폴백.
    overrides: {"P": "...", ...} — 학교/내지 커스텀 매핑 (데이터 주입).
    """
    smap = load_style_map()
    table = dict(smap.get(material, {}).get(step_unit) or {})
    if overrides:
        table.update(overrides)
    if not table:
        raise KeyError(f"스타일 매핑 없음: {material}/{step_unit}")

    if kind == "P" and has_underline is not None:
        variant = "P@underline" if has_underline else "P@no_underline"
        v = table.get(variant, _MISSING)
        if v is not _MISSING:
            return v

    v = table.get(kind, _MISSING)
    if v is not _MISSING:
        return v
    v = table.get("*", _MISSING)
    if v is not _MISSING:
        return v
    raise KeyError(f"스타일 미정의: {material}/{step_unit}/{kind}")
