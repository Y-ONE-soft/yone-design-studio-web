"""content.json v2 스키마 검증 (Phase 2).

사용:
    from core.schema import validate_v2
    errors = validate_v2(doc)      # [] 이면 유효
"""
import json
import os

_DIR = os.path.dirname(os.path.abspath(__file__))
_SCHEMA_PATH = os.path.join(_DIR, "content_v2.schema.json")
_schema_cache = None


def load_schema():
    global _schema_cache
    if _schema_cache is None:
        with open(_SCHEMA_PATH, encoding="utf-8") as f:
            _schema_cache = json.load(f)
    return _schema_cache


def validate_v2(doc):
    """v2 문서 검증. 반환: 오류 메시지 리스트 (빈 리스트 = 유효).

    jsonschema가 있으면 전체 스키마 검증, 없으면 필수 골격만 검사하는
    폴백 (운영 파이썬 3.9에 jsonschema 미설치여도 동작하도록).
    """
    try:
        import jsonschema
    except ImportError:
        return _validate_minimal(doc)
    errors = []
    validator = jsonschema.Draft7Validator(load_schema())
    for err in validator.iter_errors(doc):
        path = "$" + "".join(
            f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path
        )
        errors.append(f"{path}: {err.message[:160]}")
    return errors


def _validate_minimal(doc):
    """jsonschema 부재 시 골격 검사 폴백."""
    errors = []
    if not isinstance(doc, dict):
        return ["문서가 객체가 아님"]
    if doc.get("version") != 2:
        errors.append("$.version: 2가 아님")
    items = doc.get("items")
    if not isinstance(items, list):
        return errors + ["$.items: 배열이 아님"]
    for i, item in enumerate(items):
        if not isinstance(item, dict):
            errors.append(f"$.items[{i}]: 객체가 아님")
            continue
        if not item.get("id"):
            errors.append(f"$.items[{i}].id: 없음")
        if "question" not in item:
            errors.append(f"$.items[{i}].question: 없음")
        t = item.get("type")
        if t is not None and not (isinstance(t, str)
                                  and t.startswith(("OBJ-", "SRV-"))):
            errors.append(f"$.items[{i}].type: leaf 코드 형식 아님: {t!r}")
    return errors
