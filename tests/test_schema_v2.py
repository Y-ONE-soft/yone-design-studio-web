"""content.json v2 스키마 검증기 테스트."""
import copy

from core.schema import validate_v2

VALID = {
    "version": 2,
    "meta": {"school": "한영고", "grade": 1, "category": "동형모의고사"},
    "items": [
        {
            "id": "q-001",
            "type": "OBJ-CTN-TITLE",
            "kind": "객관식",
            "label": "제목",
            "header": {"marker": "1.", "source": "[24년 10월 20번]", "score": 2,
                       "group_id": None},
            "question": "다음 글의 제목으로 가장 적절한 것은?",
            "stimulus": {
                "type": "passage",
                "blocks": [
                    {"kind": "text", "content": "A few million years after ...",
                     "marks": [{"type": "underline", "id": "①", "span": [12, 18]}]}
                ],
            },
            "given": None,
            "choices": {
                "format": "circled",
                "items": [{"label": "①", "content": "How Volcanoes Shaped Earth"}],
            },
            "constraints": [],
            "answer": None,
        },
        {
            "id": "q-002",
            "type": None,          # 미분류 허용 — 검수 게이트가 지목
            "question": "다음 빈칸에 들어갈 가장 알맞은 것은?",
        },
    ],
}


def test_valid_document():
    assert validate_v2(VALID) == []


def test_missing_required():
    doc = copy.deepcopy(VALID)
    del doc["items"][0]["question"]
    errors = validate_v2(doc)
    assert errors and any("question" in e for e in errors)


def test_bad_leaf_code():
    doc = copy.deepcopy(VALID)
    doc["items"][0]["type"] = "banana"
    assert validate_v2(doc)


def test_wrong_version():
    doc = copy.deepcopy(VALID)
    doc["version"] = 1
    assert validate_v2(doc)
