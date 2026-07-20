"""화이트북 v2 엔진 래퍼 오프라인 테스트 — parse 스모크(골든 파리티) + 플랜.

parse 는 W35 배치 C부터 v1 위임이 아니라 인-리포 파서
(engines/whitebook/external 스냅샷 + wb_parser 구조 섹션 인식)다 —
골든 파리티 계약은 동일하게 유지된다.

InDesign 필요 단계(prepare_jsx 템플릿 복사/run_indesign/verify)는
scripts/e2e_engine_whitebook_v2.py 로 검증한다.
"""
import json
import os

import _replay
from engines.whitebook_v2.engine import (
    WhitebookV2Engine, EXPECTED_STORIES, _load_v1_config)

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def test_parse_smoke_matches_golden(tmp_path):
    """v2 parse(인-리포 파서)가 코퍼스 골든과 동일한 content.json을 산출."""
    case_dir = os.path.join(TESTS_DIR, "corpus", "whitebook", "3b3ddc5a")
    engine = WhitebookV2Engine()
    job_dir = str(tmp_path / "job")
    produced = _replay.replay(engine, case_dir, job_dir)
    golden = json.load(open(os.path.join(case_dir, "golden", "content.json"),
                            encoding="utf-8"))
    produced = _replay.canonicalize(produced, [job_dir])
    golden = _replay.canonicalize(golden, [])
    diff = _replay.first_diff(produced, golden)
    assert diff is None, f"v2 parse가 골든과 다름: {diff}"


def test_parse_output_builds_plan(tmp_path):
    """parse 산출물 → 플랜 빌드 전 구간 스모크 (연습문제 포함 케이스)."""
    from engines.whitebook_v2.plan import content_to_plan, unit_paras
    case_dir = os.path.join(TESTS_DIR, "corpus", "whitebook", "e41f1c70")
    engine = WhitebookV2Engine()
    job_dir = str(tmp_path / "job")
    content = _replay.replay(engine, case_dir, job_dir)
    plan = content_to_plan(content, issue_num="1")
    assert len(plan["flows"]) == 9
    ans_units = next(f for f in plan["flows"]
                     if f["area"] == "ans")["units"]
    assert len(unit_paras(ans_units[0])) == 136   # v1 실행 로그 파리티
    prac = next(f for f in plan["flows"] if f["area"] == "prac_main")["units"]
    assert all(not u.get("skip") for u in prac)


def test_upload_spec_is_v1():
    from engines.whitebook.engine import WhitebookEngine
    assert WhitebookV2Engine().upload_spec == WhitebookEngine().upload_spec


def test_expected_stories_inherits_v1_config():
    """v1 config verify.expected_stories 계승 확인.

    예외: D항목(D단어new)은 v1 config가 8(구버전 템플릿 기준)로 stale —
    현행 [원본] 템플릿 실측 10 (2026-05-13 v1 실행 로그). v2는 10으로 보정."""
    v1_expected = _load_v1_config()["verify"]["expected_stories"]
    v2_by_label = {label: exp for label, exp in EXPECTED_STORIES.values()}
    for key, exp in v1_expected.items():
        assert key in v2_by_label, f"v1 검수 항목 누락: {key}"
        if key == "D항목(D단어new)":
            assert v2_by_label[key] == 10
        else:
            assert v2_by_label[key] == exp, key
    # 연습문제 스토리 검수 강화 (v1 config에는 없던 항목)
    assert v2_by_label["연습문제본문"] == 3
    assert v2_by_label["연습문제답지"] == 3
