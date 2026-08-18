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

    # 과 단위 그룹핑 (Part 표기 원고 → 과 미표기 1개 + PART2)
    labels = [l["label"] for l in sec["lessons"]]
    assert labels == ["PART1", "PART2"], labels

    # prepare 단계의 플랜 빌드도 검증 (InDesign 전 단계까지)
    from engines.blackbook_v2.render import sections_to_plan
    plan = sections_to_plan(sec)
    assert plan["format"] == "bb-lessons-v1"
    got = [(l["label"], len(l["vocab"]), len(l["problems"]), len(l["answers"]) > 0)
           for l in plan["lessons"]]
    assert got == [("PART1", 8, 107, True), ("PART2", 0, 43, True)], got


def test_lesson_grouping_without_part_tokens(tmp_path):
    """`블랙북01_문제_교과서_1과.docx` 처럼 Part 표기가 없는 원고도
    구조로 분류되고 과 오름차순으로 묶인다 (W38)."""
    from engines.blackbook.kind_parser import classify_filename, classify_content

    # 파일명만으로는 판정 불가 — 구조 폴백이 살려야 한다
    assert classify_filename("블랙북01_문제_교과서_1과.docx") is None
    assert classify_content(
        "", texts=["1. 다음 글의 내용과 일치하지 않는 것은?", "본문", "① a", "② b",
                   "2. 다음 글의 요지로 가장 적절한 것은?", "① c", "② d"]
    ) == "part1_problem"
    assert classify_content(
        "", texts=["<1과 본문1>", "본문", "〈연관 어휘〉", "impressive  인상적인"]
    ) == "part1_vocab"
    assert classify_content(
        "", texts=["1", "[정답] ③", "[해설] ...", "2", "[정답] ④"]
    ) == "part1_answer"
