"""지문 배지 표기 통일(사용자 지시 2026-09-14).

  · 모의고사: `고1 23년 11월 모의고사 36번` — 예전엔 `…모의고사 231136` 처럼
    회차와 지문번호를 겹쳐 적었다.
  · 교과서: **교재명**(`능률(오) 1과 본문1`) — 예전엔 책마다 `교과서 1과`·
    `능률(민) SL2` 로 달랐다. 교재명은 분석본 파일 괄호 `(능률오1,2과)` 에서 읽는다.
"""
from core.render_vivlio.series.pocketbook import render as R


def _tb(label, unit, file):
    return {"label": label, "unit": unit, "source": {"file": file}}


def test_mock_is_round_plus_number():
    p = {"label": "231136", "unit": "모의고사", "category": "고1 23년 11월 모의고사"}
    assert R._badge_text(p) == "고1 23년 11월 모의고사 36번"
    assert R._badge_parts(p) == ("고1 23년 11월 모의고사", "36번")


def test_mock_range_keeps_range():
    p = {"label": "231141~42", "unit": "모의고사", "category": "고1 23년 11월 모의고사"}
    assert R._badge_text(p) == "고1 23년 11월 모의고사 41~42번"


def test_mock_without_category_builds_round_from_number():
    p = {"label": "240920", "unit": "모의고사", "grade": "고2"}
    assert R._badge_text(p) == "고2 24년 9월 모의고사 20번"


def test_textbook_gets_book_name():
    assert R._badge_text(_tb("1과 본문1", "교과서 1과",
                             "배재1_분석본01(능률오1,2과)_내지.idml")) == "능률(오) 1과 본문1"
    assert R._badge_text(_tb("2과 본문 1", "교과서 2과",
                             "배재2_분석본01(YBM박1,2,3과)_내지.idml")) == "YBM(박) 2과 본문 1"
    assert R._badge_parts(_tb("3과 MR1 Brain Insights", "교과서 3과",
                              "광문2_분석본04(비상황3과)_내지.idml")) == ("비상(황)", "3과 MR1 Brain Insights")


def test_publisher_without_author_is_not_split():
    # 목록 없이 자르면 `천재3과` 가 `천(재)` 가 된다
    assert R._textbook_of({"source": {"file": "X_분석본01(천재3과)_내지.idml"}}) == "천재"


def test_nfd_filename():
    import unicodedata
    f = unicodedata.normalize("NFD", "배재1_분석본01(능률오1,2과)_내지.idml")
    assert R._textbook_of({"source": {"file": f}}) == "능률(오)"


def test_unknown_textbook_falls_back_to_gyogwaseo():
    assert R._badge_text(_tb("추가 읽기 자료 (1)", "교과서 추가 읽기 자료",
                             "명일여고2_분석본05(추가 읽기자료).pdf")) == "교과서 추가 읽기 자료 (1)"


def test_supplementary_unchanged():
    assert R._badge_text({"label": "1강 01", "unit": "올림포스 1강"}) == "올림포스 1강 01"
    assert R._badge_text({"label": "1강 02", "unit": "수능특강 1강"}) == "수특 1강 02"
