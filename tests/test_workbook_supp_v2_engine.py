"""workbook_supp_v2 — 훅 오버라이드(내지 lookup/출력명) 오프라인 검증.

supp v2는 WorkbookV2Engine 100% 상속 (파서/플랜/렌더/검수 공유 — 그쪽은
test_workbook_v2_*가 가드). 여기서는 v1 supp와의 차이 2가지만 검증:
  1. _select_template: 학교명 키 lookup → "_default" 폴백
  2. _output_name: {학교}_워크북{stem}_내지_v2.indd (filename_stem 필수)
"""
import os

import pytest

from engines.workbook_supp_v2.engine import WorkbookSuppV2Engine


@pytest.fixture()
def engine():
    return WorkbookSuppV2Engine()


def _cfg(tmp_path):
    school_indd = tmp_path / "세종_내지.indd"
    default_indd = tmp_path / "기본_내지.indd"
    school_indd.write_bytes(b"x")
    default_indd.write_bytes(b"x")
    return {"indd_original": {"세종1": str(school_indd),
                              "_default": str(default_indd)}}


def test_select_template_school_lookup(engine, tmp_path):
    cfg = _cfg(tmp_path)
    logs = []
    src = engine._select_template(cfg, "모의고사", "세종1", logs.append)
    assert src == cfg["indd_original"]["세종1"]
    assert any("학교 전용" in m for m in logs)


def test_select_template_default_fallback(engine, tmp_path):
    cfg = _cfg(tmp_path)
    src = engine._select_template(cfg, "모의고사", "미등록고", print)
    assert src == cfg["indd_original"]["_default"]
    src2 = engine._select_template(cfg, "모의고사", "", print)
    assert src2 == cfg["indd_original"]["_default"]


def test_select_template_missing_raises(engine):
    with pytest.raises(FileNotFoundError):
        engine._select_template({"indd_original": {}}, "모의고사", "", print)


def test_output_name(engine, tmp_path):
    job = str(tmp_path)
    with open(os.path.join(job, "filename_stem.txt"), "w",
              encoding="utf-8") as f:
        f.write("1학기기말")
    name = engine._output_name(job, 1, 25, 10, "모의고사", "세종1")
    assert name == "세종1_워크북1학기기말_내지_v2.indd"
    name2 = engine._output_name(job, 1, 25, 10, "모의고사", "")
    assert name2 == "워크북1학기기말_내지_v2.indd"


def test_output_name_requires_stem(engine, tmp_path):
    with pytest.raises(ValueError):
        engine._output_name(str(tmp_path), 1, 25, 10, "모의고사", "")


def test_output_name_sanitizes_slash(engine, tmp_path):
    job = str(tmp_path)
    with open(os.path.join(job, "filename_stem.txt"), "w",
              encoding="utf-8") as f:
        f.write("중간/기말")
    assert engine._output_name(job, 1, 25, 10, "모의고사", "") \
        == "워크북중간_기말_내지_v2.indd"


def test_v1_workbook_v2_output_name_unchanged(tmp_path):
    """리팩터링 회귀 가드 — workbook_v2 기본 훅은 기존 파일명 그대로."""
    from engines.workbook_v2.engine import WorkbookV2Engine
    base = WorkbookV2Engine()
    assert base._output_name(str(tmp_path), 1, 25, 10, "모의고사", "") \
        == "고1_25년_10월_전체_v2.indd"


# ── 세종고 전용 내지 ────────────────────────────────────────────────────────

def test_config_has_sejong_school_key():
    """'세종고' 학교 키 → 세종 전용 내지 (부교재 supp는 학교명 bare 키 lookup).

    UI(typeset_workbook_supp_v2.html)의 옵션 값과 config 키가 어긋나면
    조용히 기본(모의고사) 내지로 조판된다 — 그 정합을 고정한다.
    """
    from engines.workbook.engine import _load_config
    indd_map = _load_config()["indd_original"]
    assert "세종고" in indd_map
    assert "워크북(세종)" in os.path.basename(indd_map["세종고"])


def test_sejong_school_selects_sejong_template(engine, tmp_path):
    sejong = tmp_path / "[원본]워크북(세종)_내지.indd"
    default = tmp_path / "[원본]워크북(모의고사)_내지.indd"
    sejong.write_bytes(b"x")
    default.write_bytes(b"x")
    cfg = {"indd_original": {"세종고": str(sejong), "_default": str(default)}}

    assert engine._select_template(cfg, "모의고사", "세종고", print) == str(sejong)

    # 세종 내지는 '내용 종합'(step1_b2)이 실물에 없다 (W19) — 학교 토큰
    # 판정이 step_map까지 이어지는지 확인
    engine._plan_ctx = {"cfg": cfg, "school": "세종고",
                        "workbook_type": "모의고사"}
    assert engine._template_token() == "세종"
    assert "step1_b2" not in engine._step_map()


def test_supp_v2_template_offers_sejong_option():
    """UI 드롭다운에 '세종고'가 있어야 학교 키가 조판까지 전달된다."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "templates",
                             "typeset_workbook_supp_v2.html"),
                encoding="utf-8").read()
    assert "'세종고'" in html
