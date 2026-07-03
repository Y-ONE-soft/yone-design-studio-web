"""Phase 0 — parse-only 스냅샷 회귀 테스트.

tests/corpus/<engine>/<job_id>/ 케이스마다 engine.parse()를 재실행해
golden/content.json 과 비교한다 (InDesign 불필요).

골든은 pre-overhaul 시점 현행 코드의 출력이다 (scripts/regen_golden.py 로 생성).
의도된 개선으로 달라지면 tests/README.md 의 승격 절차를 따른다.
"""
import json
import os

import pytest

import _replay

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus")


def _discover():
    cases = []
    if not os.path.isdir(CORPUS):
        return cases
    for engine_id in sorted(os.listdir(CORPUS)):
        edir = os.path.join(CORPUS, engine_id)
        if not os.path.isdir(edir):
            continue
        for job_id in sorted(os.listdir(edir)):
            cdir = os.path.join(edir, job_id)
            if os.path.isfile(os.path.join(cdir, "manifest.json")):
                cases.append((engine_id, job_id, cdir))
    return cases


CASES = _discover()


@pytest.mark.parametrize(
    "engine_id,job_id,case_dir",
    CASES,
    ids=[f"{e}/{j}" for e, j, _ in CASES],
)
def test_parse_snapshot(engine_id, job_id, case_dir, tmp_path):
    from engines import registry
    engine = registry.get(engine_id)

    job_dir = str(tmp_path / "job")
    produced = _replay.replay(engine, case_dir, job_dir)

    golden_path = os.path.join(case_dir, "golden", "content.json")
    golden = json.load(open(golden_path, encoding="utf-8"))

    produced = _replay.canonicalize(produced, [job_dir])
    golden = _replay.canonicalize(golden, [])

    diff = _replay.first_diff(produced, golden)
    assert diff is None, (
        f"content.json이 골든과 다름 (첫 불일치: {diff})\n"
        f"의도된 개선이면 tests/README.md 승격 절차로 골든을 갱신할 것."
    )
