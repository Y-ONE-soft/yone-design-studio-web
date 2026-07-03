"""blackbook_v2 엔진 parse 스모크 (InDesign 불필요 — 코퍼스 재현)."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))
import _replay

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def test_engine_parse_reproduces_counts(tmp_path):
    from engines import registry
    engine = registry.get("blackbook_v2")
    case_dir = os.path.join(TESTS_DIR, "corpus", "blackbook", "027d750a")

    job = str(tmp_path / "job")
    _replay.build_job(case_dir, job)
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded.get("manuscript"), "업로드 재구성 실패"

    logs = []
    json_path = engine.parse(uploaded, job, logs.append)
    content = json.load(open(json_path, encoding="utf-8"))
    sec = content["sections"]
    assert len(sec["problems_p1"]["items"]) == 107
    assert len(sec["problems_p2"]["items"]) == 43
    assert len(sec["vocab"]) == 8
    assert len(sec["answers_p1"]) == 107
    assert len(sec["answers_p2"]) == 43

    # prepare 단계의 플랜 빌드도 검증 (InDesign 전 단계까지)
    from engines.blackbook_v2.render import sections_to_plan
    plan = sections_to_plan(sec)
    assert {f["area"]: len(f["units"]) for f in plan["flows"]} == {
        "module_p1": 107, "large": 8, "module_p2": 43,
        "narrow_1": 1, "narrow_2": 1}
