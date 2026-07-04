"""suneungteukgang_workbook_v2 — 2단계 prepare/run/verify 구조 오프라인 검증."""
import json
import os

import pytest

import engines.suneungteukgang_workbook_v2.engine as eng_mod
from engines.suneungteukgang_workbook_v2.engine import (
    SuneungteukgangWorkbookV2Engine)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CASE = os.path.join(TESTS_DIR, "corpus", "suneungteukgang_workbook",
                    "65cf0265")


@pytest.fixture()
def engine():
    return SuneungteukgangWorkbookV2Engine()


def _prepare(engine, tmp_path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    out_dir = tmp_path / "out"
    t_a = tmp_path / "analysis.indd"
    t_p = tmp_path / "problem.indd"
    t_a.write_bytes(b"A")
    t_p.write_bytes(b"P")
    monkeypatch.setattr(eng_mod, "_load_v1_config", lambda: {
        "indd_output_dir": str(out_dir),
        "indd_original": {"analysis": str(t_a), "problem": str(t_p)},
    })
    with open(os.path.join(str(job), "lesson.txt"), "w",
              encoding="utf-8") as f:
        f.write(open(os.path.join(CASE, "meta", "lesson.txt"),
                     encoding="utf-8").read().strip())
    json_path = str(job / "content.json")
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(open(os.path.join(CASE, "golden", "content.json"),
                     encoding="utf-8").read())
    return engine.prepare_jsx(json_path, str(job), lambda m: None), str(job)


def test_prepare_jsx_two_stages(engine, tmp_path, monkeypatch):
    settings_path, job = _prepare(engine, tmp_path, monkeypatch)
    settings = json.load(open(settings_path, encoding="utf-8"))
    assert settings["engine"] == "suneungteukgang_workbook_v2"
    assert [s["label"] for s in settings["stages"]] \
        == ["analysis", "problem"]
    assert settings["unsupported"] == []

    names = [os.path.basename(s["indd_path"]) for s in settings["stages"]]
    assert names == ["EBS_수능특강_27강_분석_v2.indd",
                     "EBS_수능특강_27강_문제_v2.indd"]
    for st in settings["stages"]:
        assert os.path.exists(st["indd_path"]), st["label"]
        assert os.path.exists(st["jsx_path"]), st["label"]
        assert os.path.basename(st["log_path"]) \
            == f"조판_로그_{st['label']}.txt"     # 스테이지별 로그 분리
        plan = json.load(open(st["plan_path"], encoding="utf-8"))
        steps = [f["step"] for f in plan["flows"]]
        if st["label"] == "analysis":
            assert "step3" not in steps
            assert "step1_a1" in steps and "step2_c2" in steps
        else:
            assert steps == ["step3"]
            assert plan["flows"][0]["target"] == {"master": "D"}
        assert "divider" not in plan


def test_prepare_jsx_missing_template_raises(engine, tmp_path, monkeypatch):
    job = tmp_path / "job"
    job.mkdir()
    monkeypatch.setattr(eng_mod, "_load_v1_config", lambda: {
        "indd_output_dir": str(tmp_path / "out"),
        "indd_original": {"analysis": str(tmp_path / "없음.indd"),
                          "problem": str(tmp_path / "없음2.indd")},
    })
    json_path = str(job / "content.json")
    with open(json_path, "w", encoding="utf-8") as f:
        f.write(open(os.path.join(CASE, "golden", "content.json"),
                     encoding="utf-8").read())
    with pytest.raises(FileNotFoundError):
        engine.prepare_jsx(json_path, str(job), lambda m: None)


def test_run_indesign_two_sequential_runs(engine, tmp_path, monkeypatch):
    """run_indesign이 스테이지별 jsx를 순서대로, 각자 로그로 실행 + 이전
    poll 로그를 지운다 (stale 완료마커 함정 차단)."""
    settings_path, job = _prepare(engine, tmp_path, monkeypatch)
    settings = json.load(open(settings_path, encoding="utf-8"))
    # 이전 실행 로그 잔재 심기
    for st in settings["stages"]:
        with open(st["log_path"], "w", encoding="utf-8") as f:
            f.write("워크북 v2 조판 완료\n")

    calls = []

    def fake_run_jsx(jsx_path, log, poll_log_path=None, timeout=None,
                     completion_marker=None, stall_limit=None):
        assert not os.path.exists(poll_log_path), "stale 로그 미삭제"
        calls.append((os.path.basename(jsx_path),
                      os.path.basename(poll_log_path), stall_limit,
                      completion_marker))

    import core.indesign.runner as runner
    monkeypatch.setattr(runner, "run_jsx", fake_run_jsx)
    engine.run_indesign(job, lambda m: None)
    assert [c[0] for c in calls] == ["run_analysis.jsx", "run_problem.jsx"]
    assert [c[1] for c in calls] == ["조판_로그_analysis.txt",
                                     "조판_로그_problem.txt"]
    assert all(c[2] == 900 for c in calls)
    assert all(c[3] == "워크북 v2 조판 완료" for c in calls)


def test_workbook_type_fixed(engine, tmp_path):
    assert engine._workbook_type(str(tmp_path)) == "EBS"


def test_parse_delegates_to_v1(engine):
    import inspect
    src = inspect.getsource(engine.parse)
    assert "SuneungteukgangWorkbookEngine" in src
