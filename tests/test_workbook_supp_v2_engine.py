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
