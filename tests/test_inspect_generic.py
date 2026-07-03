"""범용 검수(harvest) 단위 테스트 — 스키마 무관 수확 + 누락 판정."""
from core.inspect import harvest_content_words


def test_harvest_any_schema():
    content = {
        "school": "성덕고",
        "steps": {"step3": {"normal": [
            {"question_num": "20", "kind": "Q",          # kind는 스킵 키
             "paragraphs": [
                 {"text": "Understanding ecosystems requires patience.",
                  "pstyle": "무시될 스타일명"},
             ]}]}},
        "indd_path": "/Users/x/조판/something.indd",       # 경로 스킵
        "_warnings": ["ignored english words here"],        # _키 스킵
    }
    words = harvest_content_words(content)
    assert "understanding" in words and "patience" in words
    assert "ignored" not in words          # _warnings 제외
    assert not any(w in words for w in ("indd", "path"))


def test_missing_detection_semantics():
    want = harvest_content_words({"t": "alpha bravo charlie delta"})
    got = harvest_content_words({"t": "alpha bravo charlie"})
    assert want - got == {"delta"}
