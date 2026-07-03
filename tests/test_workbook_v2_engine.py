"""workbook_v2 엔진 parse 스모크 (InDesign 불필요 — 코퍼스 재현).

parse는 v1 파서(parse_manuscript_folder)를 그대로 재사용하므로,
코퍼스 0a5da924의 스텝 수/지문 수가 v1 골든과 동일해야 한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))
import _replay

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def test_engine_parse_reproduces_steps(tmp_path):
    from engines import registry
    engine = registry.get("workbook_v2")
    case_dir = os.path.join(TESTS_DIR, "corpus", "workbook", "0a5da924")

    job = str(tmp_path / "job")
    _replay.build_job(case_dir, job)
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded.get("manuscripts"), "업로드 재구성 실패"

    logs = []
    json_path = engine.parse(uploaded, job, logs.append)
    content = json.load(open(json_path, encoding="utf-8"))
    golden = json.load(open(os.path.join(case_dir, "golden", "content.json"),
                            encoding="utf-8"))
    # v1 파서 재사용 → 스텝 구성이 골든과 동일 (13스텝)
    assert set(content["steps"]) == set(golden["steps"])
    assert len(content["steps"]) == 13
    # 대표 스텝 단락 수 재현
    for key in ("step1_c1", "step1_a1", "step2_c2"):
        assert (len(content["steps"][key]["paragraphs"])
                == len(golden["steps"][key]["paragraphs"])), key

    # prepare 단계의 플랜 빌드 (InDesign 전 단계까지) — 미지원 스텝 0
    from engines.workbook_v2.plan import steps_to_plan
    plan = steps_to_plan(content["steps"])
    assert plan["unsupported"] == []
    assert len(plan["flows"]) == 13
