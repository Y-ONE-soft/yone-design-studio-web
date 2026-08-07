"""textbook_workbook_v2 — 훅 오버라이드 + prepare_jsx 오프라인 검증.

플랜/렌더/검수 공통 로직은 test_workbook_v2_* 가드. 여기서는 v1 textbook과의
차이(교과서 메타 출력명/학교 템플릿 lookup/간지·후처리 데코레이션)와
prepare_jsx 전체 경로(tmp 템플릿 + config 패치)를 검증한다.
"""
import json
import os

import pytest

import engines.textbook_workbook_v2.engine as eng_mod
from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CASE = os.path.join(TESTS_DIR, "corpus", "textbook_workbook", "80dd3fa2")


@pytest.fixture()
def engine():
    return TextbookWorkbookV2Engine()


def _write_meta(job, **kw):
    for k, v in kw.items():
        with open(os.path.join(job, f"{k}.txt"), "w", encoding="utf-8") as f:
            f.write(v)


def test_output_name(engine, tmp_path):
    job = str(tmp_path)
    _write_meta(job, subject="공통영어1", publisher="공통영어1 능률(오)",
                lesson="2과")
    assert engine._output_name(job, 1, 0, 0, "교과서", "") \
        == "공통영어1_능률(오)_2과_전체_v2.indd"
    assert engine._output_name(job, 1, 0, 0, "교과서", "세종") \
        == "공통영어1_능률(오)_2과_전체(세종)_v2.indd"


def test_select_template(engine, tmp_path):
    d = tmp_path / "d.indd"
    s = tmp_path / "s.indd"
    d.write_bytes(b"x")
    s.write_bytes(b"x")
    cfg = {"indd_original": {"_default": str(d), "세종": str(s)}}
    assert engine._select_template(cfg, "교과서", "", print) == str(d)
    assert engine._select_template(cfg, "교과서", "세종", print) == str(s)
    assert engine._select_template(cfg, "교과서", "미등록고", print) == str(d)
    # 구버전 문자열 config 호환
    assert engine._select_template({"indd_original": str(d)}, "교과서", "",
                                   print) == str(d)
    with pytest.raises(FileNotFoundError):
        engine._select_template({"indd_original": {}}, "교과서", "", print)


def test_plan_decorations(engine, tmp_path):
    job = str(tmp_path)
    _write_meta(job, subject="공통영어1", publisher="공통영어1 능률(오)",
                lesson="2과")
    deco = engine._plan_decorations(job, {})
    assert deco["divider"] == {"line1": "공통영어1 능률(오)", "line2": "2과"}
    assert deco["textbook_postprocess"] is True


def test_workbook_type_fixed(engine, tmp_path):
    assert engine._workbook_type(str(tmp_path)) == "교과서"


def test_prepare_jsx_offline(engine, tmp_path, monkeypatch):
    """코퍼스 content.json → prepare_jsx 전체 경로 (tmp 템플릿/출력)."""
    job = tmp_path / "job"
    job.mkdir()
    out_dir = tmp_path / "out"
    tmpl = tmp_path / "template.indd"
    tmpl.write_bytes(b"INDD")
    monkeypatch.setattr(eng_mod, "_load_v1_config", lambda: {
        "indd_output_dir": str(out_dir),
        "indd_original": {"_default": str(tmpl)},
    })
    for k in ("subject", "publisher", "lesson"):
        src = open(os.path.join(CASE, "meta", f"{k}.txt"),
                   encoding="utf-8").read().strip()
        _write_meta(str(job), **{k: src})
    json_path = str(job / "content.json")
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(open(os.path.join(CASE, "golden", "content.json"),
                     encoding="utf-8").read())

    settings_path = engine.prepare_jsx(json_path, str(job), lambda m: None)
    settings = json.load(open(settings_path, encoding="utf-8"))
    assert settings["engine"] == "textbook_workbook_v2"
    assert settings["workbook_type"] == "교과서"
    assert os.path.basename(settings["indd_path"]) \
        == "공통영어1_능률(오)_2과_전체_v2.indd"
    assert os.path.exists(settings["indd_path"])
    assert os.path.exists(os.path.join(str(job), "run.jsx"))

    plan = json.load(open(settings["plan_path"], encoding="utf-8"))
    assert plan["divider"] == {"line1": "공통영어1 능률(오)", "line2": "2과"}
    assert plan["textbook_postprocess"] is True
    assert len(plan["flows"]) == 13
    assert plan["unsupported"] == []


def test_parse_delegates_to_v1(engine):
    """parse는 v1 TextbookWorkbookEngine 완전 위임 (GDrive 로직 재사용)."""
    import inspect
    src = inspect.getsource(engine.parse)
    assert "TextbookWorkbookEngine" in src
