"""workbook_sero_v2 엔진 parse 스모크 (InDesign 불필요 — 코퍼스 재현).

parse는 v1 세로 파서(engines/workbook_sero/parser)를 그대로 재사용하므로,
코퍼스 e79f8af9의 사이클 수/스텝 단락 수가 v1 골든과 동일해야 한다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "tests"))
import _replay

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def test_engine_parse_reproduces_cycles(tmp_path):
    from engines import registry
    engine = registry.get("workbook_sero_v2")
    case_dir = os.path.join(TESTS_DIR, "corpus", "workbook_sero", "e79f8af9")

    job = str(tmp_path / "job")
    _replay.build_job(case_dir, job)
    uploaded = _replay.build_uploaded(engine, job)
    assert uploaded.get("manuscripts"), "업로드 재구성 실패"

    logs = []
    json_path = engine.parse(uploaded, job, logs.append)
    content = json.load(open(json_path, encoding="utf-8"))
    golden = json.load(open(os.path.join(case_dir, "golden", "content.json"),
                            encoding="utf-8"))
    assert len(content["cycles"]) == len(golden["cycles"]) == 7
    for got, want in zip(content["cycles"], golden["cycles"]):
        assert got["q_num"] == want["q_num"]
        assert got["code"] == want["code"]
        for sk, paras in want["steps"].items():
            assert len(got["steps"][sk]) == len(paras), (want["q_num"], sk)

    # prepare 단계의 플랜 빌드 (InDesign 전 단계까지) — 13슬롯 전부 채움
    from engines.workbook_sero_v2.plan import content_to_plan
    plan = content_to_plan(content)
    assert plan["cycle_count"] == 7
    assert plan["unsupported"] == []
    for cyc in plan["cycles"]:
        assert len(cyc["slots"]) == 13
        assert not any(s.get("clear") for s in cyc["slots"])
