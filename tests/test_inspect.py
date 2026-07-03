"""검수 비교기 단위 테스트 (InDesign 불필요 — 합성 덤프 사용)."""
from core.inspect import inspect_workbook_step3

CONTENT = {
    "steps": {
        "step3": {
            "normal": [
                {
                    "question_num": "20",
                    "paragraphs": [
                        {"text": "1. 다음 글의 제목으로 가장 적절한 것은?",
                         "runs": [], "kind": "Q", "q_code": "OBJ-CTN-TITLE"},
                        {"text": "Understanding ecosystems requires patience and careful observation.",
                         "runs": [{"t": "...", "ul": False}], "kind": "P"},
                        {"text": "① The Hidden Cost of Progress", "runs": [], "kind": "C"},
                    ],
                }
            ],
            "short": [],
        }
    }
}


def _dump(paras):
    return {"doc": "t.indd", "overflow_stories": 0,
            "stories": [{"idx": 0, "overflow": False, "paragraphs": paras}]}


GOOD_DUMP = _dump([
    {"t": "1. 다음 글의 제목으로 가장 적절한 것은?",
     "s": "STEP 03 > S_실전문제 번호 수정 올림포스"},
    {"t": "Understanding ecosystems requires patience and careful observation.",
     "s": "STEP 03 > 실전 문제 지문 올림포스_"},
    {"t": "① The Hidden Cost of Progress", "s": "STEP 03 > S_선지 올림포스"},
])


def test_clean_pass():
    r = inspect_workbook_step3(CONTENT, GOOD_DUMP)
    assert r["ok"], r
    assert r["stats"]["style_mismatched"] == 0
    assert r["stats"]["style_matched"] >= 3


def test_content_loss_is_critical():
    dump = _dump([{"t": "1. 다음 글의 제목으로 가장 적절한 것은?",
                   "s": "STEP 03 > S_실전문제 번호 수정 올림포스"}])
    r = inspect_workbook_step3(CONTENT, dump)
    assert not r["ok"]
    assert any("내용누락" in c for c in r["critical"])


def test_answer_leak_is_critical():
    paras = GOOD_DUMP["stories"][0]["paragraphs"] + [
        {"t": "②: making → make 가 옳다", "s": "STEP 03 > 실전 문제 지문 올림포스_"}
    ]
    r = inspect_workbook_step3(CONTENT, _dump(paras))
    assert not r["ok"]
    assert any("정답잔존" in c for c in r["critical"])


def test_style_mismatch_is_warning_not_critical():
    paras = [dict(p) for p in GOOD_DUMP["stories"][0]["paragraphs"]]
    paras[2]["s"] = "STEP 03 > 엉뚱한 스타일"
    r = inspect_workbook_step3(CONTENT, _dump(paras))
    assert r["ok"]                      # warning은 차단하지 않음 (A8 등급제)
    assert any("스타일" in w for w in r["warnings"])


def test_overflow_reported():
    dump = dict(GOOD_DUMP)
    dump["overflow_stories"] = 2
    r = inspect_workbook_step3(CONTENT, dump)
    assert any("오버플로우" in w for w in r["warnings"])
