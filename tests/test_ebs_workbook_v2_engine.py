"""ebs_workbook_v2 — 훅 오버라이드 + prepare_jsx 오프라인 검증."""
import json
import os

import pytest

import engines.ebs_workbook_v2.engine as eng_mod
from engines.ebs_workbook_v2.engine import EbsWorkbookV2Engine

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CASE = os.path.join(TESTS_DIR, "corpus", "ebs_workbook", "4ed24266")


@pytest.fixture()
def engine():
    return EbsWorkbookV2Engine()


def _write_meta(job, **kw):
    for k, v in kw.items():
        with open(os.path.join(job, f"{k}.txt"), "w", encoding="utf-8") as f:
            f.write(v)


def test_output_name(engine, tmp_path):
    job = str(tmp_path)
    _write_meta(job, lesson="Unit 15")
    assert engine._output_name(job, 0, 0, 0, "EBS", "") \
        == "EBS_리딩파워_Unit15_전체_v2.indd"
    # lesson 미지정 폴백
    job2 = str(tmp_path / "j2")
    os.makedirs(job2)
    assert engine._output_name(job2, 0, 0, 0, "EBS", "") \
        == "EBS_리딩파워_단원_전체_v2.indd"


def test_select_template(engine, tmp_path):
    t = tmp_path / "t.indd"
    t.write_bytes(b"x")
    assert engine._select_template({"indd_original": str(t)}, "EBS", "",
                                   print) == str(t)
    # 구버전 dict config 호환 (v1 동일)
    assert engine._select_template({"indd_original": {"모의고사": str(t)}},
                                   "EBS", "", print) == str(t)
    with pytest.raises(FileNotFoundError):
        engine._select_template({"indd_original": ""}, "EBS", "", print)


def test_workbook_type_and_step_map(engine, tmp_path):
    assert engine._workbook_type(str(tmp_path)) == "EBS"
    smap = engine._step_map()
    assert smap["step3"] == {"master": "O"}
    assert "_doc" not in smap
    assert "step1_b1" not in smap       # 리딩파워 내지에 없는 스텝


def test_prepare_jsx_offline(engine, tmp_path, monkeypatch):
    """코퍼스 content.json → prepare_jsx 전체 경로 (tmp 템플릿/출력)."""
    job = tmp_path / "job"
    job.mkdir()
    out_dir = tmp_path / "out"
    tmpl = tmp_path / "template.indd"
    tmpl.write_bytes(b"INDD")
    monkeypatch.setattr(eng_mod, "_load_v1_config", lambda: {
        "indd_output_dir": str(out_dir),
        "indd_original": str(tmpl),
    })
    _write_meta(str(job), lesson=open(os.path.join(CASE, "meta",
                                                   "lesson.txt"),
                                      encoding="utf-8").read().strip())
    json_path = str(job / "content.json")
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(open(os.path.join(CASE, "golden", "content.json"),
                     encoding="utf-8").read())

    settings_path = engine.prepare_jsx(json_path, str(job), lambda m: None)
    settings = json.load(open(settings_path, encoding="utf-8"))
    assert settings["engine"] == "ebs_workbook_v2"
    assert settings["workbook_type"] == "EBS"
    assert os.path.basename(settings["indd_path"]) \
        == "EBS_리딩파워_Unit15_전체_v2.indd"
    assert os.path.exists(settings["indd_path"])

    plan = json.load(open(settings["plan_path"], encoding="utf-8"))
    assert "divider" not in plan            # 간지 op는 교과서 전용
    assert "textbook_postprocess" not in plan
    assert len(plan["flows"]) == 8
    assert plan["unsupported"] == []
    targets = {f["step"]: f["target"] for f in plan["flows"]}
    assert targets["step2_a1_btm"]["rank"] == 2
    assert targets["step3"] == {"master": "O"}


def test_parse_delegates_to_v1(engine):
    import inspect
    src = inspect.getsource(engine.parse)
    assert "EbsWorkbookEngine" in src
