# -*- coding: utf-8 -*-
"""배치 G (W37) — 잔여 침묵 지점 가시화 테스트.

원칙 (docs/인식지점_전수감사.md §9 G):
  - 인식 실패·강등·건너뜀은 [경고] + 무엇을 못 읽었는지 + 후보/근거를 로그에 남긴다.
  - 동작은 무변경 (로그는 fail-open) — [오류] 승격은 운영 판단 기록 없이는 금지.
  - 정상 입력(골든 코퍼스)에서는 새 경고가 발생하지 않는다 (소음 0 — 본 배치에서
    코퍼스 42케이스 재파스 실측).
"""
import io
import os
import re
import sys
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ── final: classify_scope unknown 후보 리포트 ───────────────────────────────

class TestScopeCandidates:
    def test_unknown_scope_gets_hints(self):
        from engines.final.scope_parser import classify_scope, classify_scope_candidates
        # 공백 변형: 정규화 재분류 후보를 제시해야 한다
        scope = "올 림포스3강"
        assert classify_scope(scope) == "unknown"
        hints = classify_scope_candidates(scope)
        assert any("ebs_olympos" in h for h in hints)

    def test_empty_scope_hint(self):
        from engines.final.scope_parser import classify_scope_candidates
        hints = classify_scope_candidates("")
        assert hints and "비어" in hints[0]

    def test_partial_signals(self):
        from engines.final.scope_parser import classify_scope, classify_scope_candidates
        scope = "신교재9강"  # 강 표기는 있으나 교재명 미등재
        assert classify_scope(scope) == "unknown"
        hints = classify_scope_candidates(scope)
        assert any("N강" in h for h in hints)

    def test_known_scope_unchanged(self):
        # 분류 로직 무변경 가드
        from engines.final.scope_parser import classify_scope
        assert classify_scope("교과서1,2과,SL") == "textbook"
        assert classify_scope("25년10월") == "mockexam"
        assert classify_scope("올포1-4강") == "ebs_olympos"


# ── final: _canonical_order_key tier 기타 강등 수집기 ───────────────────────

class TestCanonUnknownCollector:
    def test_unknown_header_collected_and_reported(self):
        from engines.final import parser as FP
        FP._canon_unknown_reset()
        key = FP._canonical_order_key("완전히 새로운 형식 헤더")
        assert key[:2] == (3, 9999)  # 동작 무변경 (종전 tier 그대로)
        logs = []
        FP._canon_unknown_report(logs.append)
        joined = "\n".join(logs)
        assert "[경고]" in joined and "완전히 새로운 형식 헤더" in joined

    def test_recognized_header_not_collected(self):
        from engines.final import parser as FP
        FP._canon_unknown_reset()
        FP._canonical_order_key("교과서2과 본문1")
        FP._canonical_order_key("리딩파워 3강 01")
        FP._canonical_order_key("251020")
        logs = []
        FP._canon_unknown_report(logs.append)
        assert logs == []  # 인식 헤더는 무경고

    def test_reset_clears(self):
        from engines.final import parser as FP
        FP._canon_unknown_reset()
        FP._canonical_order_key("이상한 헤더 A")
        FP._canon_unknown_reset()
        logs = []
        FP._canon_unknown_report(logs.append)
        assert logs == []


# ── workbook v1 공유 파서: 정답부/짤지문/헤더 폴백 가시화 (로그만) ──────────

def _paras(*texts):
    return [{"text": t, "runs": []} for t in texts]


class TestAnswerSectionVisibility:
    def test_uncut_but_rules_eye_sees_warns(self):
        # 구 눈은 못 자르지만 rules.A_SECTION_HEADER 는 아는 표기 → [경고]+무절단
        from engines.workbook.parser import _remove_answer_section
        paras = _paras("1. p2-no.18", "본문...", "[정답 및 해설]", "1. ②")
        logs = []
        out = _remove_answer_section(paras, log=logs.append)
        assert out == paras  # 동작 무변경 (침묵 통과 그대로)
        assert any("[경고]" in l and "정답부 헤더 후보 미절단" in l for l in logs)

    def test_cut_case_no_warning(self):
        from engines.workbook.parser import _remove_answer_section
        paras = _paras("1. p2-no.18", "본문...", "정답 및 해설", "1. ②")
        logs = []
        out = _remove_answer_section(paras, log=logs.append)
        assert len(out) == 2  # 종전과 동일 절단
        assert not any("[경고]" in l for l in logs)

    def test_no_log_no_side_effect(self):
        from engines.workbook.parser import _remove_answer_section
        paras = _paras("본문", "[정답 및 해설]")
        assert _remove_answer_section(paras) == paras


class TestShortQuestionVisibility:
    def test_unmatched_header_shape_warns(self):
        # 짤지문 18이 새 형식 헤더로 잔존 → 필터 미제거 + [경고]
        from engines.workbook.parser import _filter_short_questions
        paras = _paras("지문 1 - no.18 빈칸추론", "English body ...")
        logs = []
        out = _filter_short_questions(paras, [18], log=logs.append)
        assert out == paras  # 동작 무변경
        assert any("[경고]" in l and "18" in l for l in logs)

    def test_matched_header_removed_no_warning(self):
        from engines.workbook.parser import _filter_short_questions
        paras = _paras("1. p2-no.18", "removed body", "2. p3-no.20", "kept body")
        logs = []
        out = _filter_short_questions(paras, [18], log=logs.append)
        assert [p["text"] for p in out] == ["2. p3-no.20", "kept body"]
        assert not any("[경고]" in l for l in logs)

    def test_body_number_no_false_positive(self):
        # 본문 속 우연한 숫자 (헤더 표기 아님) 는 경고하지 않는다
        from engines.workbook.parser import _filter_short_questions
        paras = _paras("There were 18 people in the piano room.")
        logs = []
        _filter_short_questions(paras, [18], log=logs.append)
        assert not any("[경고]" in l for l in logs)


class TestStripHeaderFallbackVisibility:
    def test_label_fallback_drop_warns(self):
        from engines.workbook.parser import _strip_manuscript_headers
        # 본문 마커 0 + 선두 라벨('어휘선택(문제지)')이 실제로 제거되는 경우
        paras = _paras("어휘선택(문제지)", "그냥 본문 같은 한글 라인",
                       "다음 한글 라인")
        logs = []
        out = _strip_manuscript_headers(paras, log=logs.append)
        assert len(out) < len(paras)
        assert any("[경고]" in l and "본문 마커" in l for l in logs)

    def test_noop_fallback_silent(self):
        # 세로 C2 'NN번' 원고 (코퍼스 실측 소음 케이스) — 아무것도 안 버리면 무경고
        from engines.workbook.parser import _strip_manuscript_headers
        paras = _paras("20번", "Some English sentence here.")
        logs = []
        out = _strip_manuscript_headers(paras, log=logs.append)
        assert out == paras
        assert not any("[경고]" in l for l in logs)


# ── whitebook: 연습문제/실전문제 docx 헤더 침묵 유실 가시화 ──────────────────

_DOCX_XML_TMPL = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/'
    '2006/main"><w:body>{body}</w:body></w:document>'
)


def _make_docx(tmp_path, name, lines):
    body = "".join(
        f"<w:p><w:r><w:t>{l}</w:t></w:r></w:p>" for l in lines)
    path = os.path.join(str(tmp_path), name)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("word/document.xml", _DOCX_XML_TMPL.format(body=body))
    return path


class TestWhitebookPracticeVisibility:
    def test_no_question_header_warns(self, tmp_path):
        from engines.whitebook.practice_parser import parse_practice_docx
        p = _make_docx(tmp_path, "prac.docx",
                       ["제목", "1) 잘못된 형식 발문", "선지 하나"])
        logs = []
        out = parse_practice_docx(p, log=logs.append)
        assert out == []  # 동작 무변경
        assert any("[경고]" in l and "(N)" in l for l in logs)

    def test_normal_format_silent(self, tmp_path):
        from engines.whitebook.practice_parser import parse_practice_docx
        p = _make_docx(tmp_path, "prac2.docx",
                       ["제목", "(1) 정상 발문입니다", "선지"])
        logs = []
        out = parse_practice_docx(p, log=logs.append)
        assert len(out) == 1
        assert not any("[경고]" in l for l in logs)

    def test_answer_no_haeseol_header_warns(self, tmp_path):
        from engines.whitebook.practice_parser import parse_practice_answer_docx
        p = _make_docx(tmp_path, "ans.docx",
                       ["제목", "(1) ④ 답인데 헤더가 없음"])
        logs = []
        out = parse_practice_answer_docx(p, log=logs.append)
        assert out == []
        assert any("[경고]" in l and "해설" in l for l in logs)

    def test_answer_normal_silent(self, tmp_path):
        from engines.whitebook.practice_parser import parse_practice_answer_docx
        p = _make_docx(tmp_path, "ans2.docx",
                       ["제목", "■ 해설", "(1) ④ 유형"])
        logs = []
        out = parse_practice_answer_docx(p, log=logs.append)
        assert len(out) == 1
        assert not any("[경고]" in l for l in logs)


class TestWhitebookProblemVisibility:
    def test_no_day_header_warns(self, tmp_path):
        from engines.whitebook_problem.parser import parse_problem_docx
        p = _make_docx(tmp_path, "prob.docx",
                       ["표지", "첫날 1", "(1) 발문", "① 선지"])
        logs = []
        out = parse_problem_docx(p, log=logs.append)
        assert out == []
        assert any("[경고]" in l and "Day" in l for l in logs)

    def test_day_recognized_silent(self, tmp_path):
        from engines.whitebook_problem.parser import parse_problem_docx
        p = _make_docx(tmp_path, "prob2.docx",
                       ["표지", "Day 1", "(1) 발문", "① 선지"])
        logs = []
        out = parse_problem_docx(p, log=logs.append)
        assert len(out) == 1 and out[0]["day"] == 1
        assert not any("[경고]" in l for l in logs)

    def test_answer_no_day_header_warns(self, tmp_path):
        from engines.whitebook_problem.parser import parse_answer_docx
        p = _make_docx(tmp_path, "ans.docx", ["표지", "(1) ④ 해설"])
        logs = []
        out = parse_answer_docx(p, log=logs.append)
        assert out == []
        assert any("[경고]" in l for l in logs)


# ── whitebook v2: 정답 hwpx 섹션 마커('▶ X') / Day 분할 침묵 가시화 ─────────

class TestWhitebookV2AnswerSections:
    def _run(self, monkeypatch, content_lines, answer_lines):
        from engines.whitebook_v2 import wb_parser
        snap = wb_parser._snap

        def fake_extract(path):
            return content_lines if "main" in path else answer_lines

        monkeypatch.setattr(snap, "extract_lines_from_hwpx", fake_extract)
        logs = []
        data = wb_parser.parse_workbook_files(
            ["main.hwpx"], ["ans.hwpx"], log=logs.append)
        return data, logs

    _CONTENT = [
        "Day 1",
        "A. 주어진 단어에 해당하는 뜻을 쓰시오.", "1. significant",
        "B. 다음 우리말 해석에 맞는 단어를 쓰시오.", "1. 중요한",
        "C. 다음 단어들을 알맞게 배열하시오.", "[문제 1]",
        "D. 다음 단어에 맞는 뜻을 고르시오.", "1. significant",
        "E. 다음 문장을 해석하시오.", "1. The boat is big.",
    ]

    def test_missing_answer_section_warns_with_candidates(self, monkeypatch):
        # '▶ B' 마커가 변형('▶B정답')이라 미매치 → B 빈 섹션 + [경고]+후보
        answers = ["Day 1", "▶ A", "1. significant : 중요한",
                   "▶B정답", "1. significant",
                   "▶ C", "▶ D", "▶ E"]
        data, logs = self._run(monkeypatch, self._CONTENT, answers)
        warn = [l for l in logs if "[경고]" in l and "섹션" in l]
        assert warn, logs
        assert any("B" in l for l in warn)
        assert any("▶" in l and "후보" in l for l in logs)

    def test_all_sections_present_silent(self, monkeypatch):
        answers = ["Day 1",
                   "▶ A", "1. significant : 중요한",
                   "▶ B", "1. significant",
                   "▶ C", "[문제 1]", "1. word, word2",
                   "▶ D", "1. significant : ⑬",
                   "▶ E", "1. The boat is big."]
        data, logs = self._run(monkeypatch, self._CONTENT, answers)
        assert not any("[경고]" in l and "섹션" in l for l in logs), logs

    def test_no_day_header_in_answers_warns(self, monkeypatch):
        answers = ["정답지 제목", "▶ A", "1. significant : 중요한"]
        data, logs = self._run(monkeypatch, self._CONTENT, answers)
        assert any("[경고]" in l and "Day" in l and "정답" in l for l in logs)


# ── blackbook: classify_filename 실패 근거 ──────────────────────────────────

class TestBlackbookReason:
    def test_reason_string(self):
        from engines.blackbook.kind_parser import (
            classify_filename, classify_filename_reason)
        assert classify_filename("이상한원고.hwpx") is None
        reason = classify_filename_reason("이상한원고.hwpx")
        assert "Part번호=미검출" in reason and "미대응" in reason

    def test_reason_partial_signal(self):
        from engines.blackbook.kind_parser import classify_filename_reason
        reason = classify_filename_reason("Part3 문제.hwpx")  # 미지원 part 번호
        assert "Part번호=3" in reason and "문제" in reason

    def test_classify_unchanged(self):
        from engines.blackbook.kind_parser import classify_filename
        assert classify_filename("Part1 문제.hwpx") == "part1_problem"
        assert classify_filename("1부 어휘.docx") == "part1_vocab"
        assert classify_filename("Part2 해설.hwpx") == "part2_answer"


# ── seseospecial: part2 프로필 데이터화 + 침묵 강등 가시화 ──────────────────

class TestSeseoProfiles:
    def test_profiles_match_legacy_literals(self):
        # 데이터화 파리티 가드 — json 프로필 == 종전 하드코딩
        from engines.seseospecial import parser as P
        k1, p1 = P._part2_profile("광문1")
        k2, p2 = P._part2_profile("광문2")
        assert (k1, p1["has_jogeon"]) == ("gm1", False)
        assert (k2, p2["has_jogeon"]) == ("gm2", True)
        assert p1["header_re"].pattern == P._HEADER_RE_GM1.pattern
        assert p2["header_re"].pattern == P._HEADER_RE_GM2.pattern
        # 종전 `'2' in school` 의미론 유지
        assert P._part2_profile("")[0] == "gm1"
        assert P._part2_profile("어느학교2")[0] == "gm2"

    def test_loader_fallback_on_missing_file(self, monkeypatch):
        from engines.seseospecial import parser as P
        monkeypatch.setattr(P, "_PROFILES_PATH", "/nonexistent/x.json")
        prof = P._load_part2_profiles()
        assert prof["profiles"]["gm1"]["header_re"] is P._HEADER_RE_GM1
        assert prof["profiles"]["gm2"]["has_jogeon"] is True

    def test_demoted_source_header_warns(self):
        from engines.seseospecial import parser as P
        paras = [
            {"text": "영어1 미래엔(김) 3과 본문", "runs": [], "has_ul": False},
            {"text": "1. 다음 글을 읽으시오", "runs": [], "has_ul": False},
        ]
        logs = []
        out = P.classify_part2(paras, school="광문1", log=logs.append)
        # 동작 무변경: 여전히 선지(3) 강등
        assert out["main"][0]["style"] == P.P2_SEONJI
        assert any("[경고]" in l and "출처 헤더 후보" in l for l in logs)

    def test_matching_source_no_warning(self):
        from engines.seseospecial import parser as P
        paras = [
            {"text": "공통영어1 2025년", "runs": [], "has_ul": False},
            {"text": "1. 다음 글을 읽으시오", "runs": [], "has_ul": False},
        ]
        logs = []
        out = P.classify_part2(paras, school="광문1", log=logs.append)
        assert out["main"][0]["style"] == P.P2_CHULCHEO
        assert not any("[경고]" in l for l in logs)

    def test_part1_zero_header_warns(self):
        from engines.seseospecial import parser as P
        paras = [{"text": "실용영어 1과", "runs": [], "has_ul": False},
                 {"text": "{A sentence.}", "runs": [], "has_ul": False}]
        logs = []
        P.classify_part1(paras, logs.append)
        assert any("[경고]" in l and "대분류 헤더" in l for l in logs)

    def test_part1_with_header_silent(self):
        from engines.seseospecial import parser as P
        paras = [{"text": "공통영어1 5과", "runs": [], "has_ul": False},
                 {"text": "{A sentence.}", "runs": [], "has_ul": False}]
        logs = []
        P.classify_part1(paras, logs.append)
        assert not any("[경고]" in l for l in logs)


# ── pocketbook: 리뷰테스트 트리 탐색 침묵 가시화 ────────────────────────────

class TestPocketbookDiscoveryVisibility:
    def _engine(self, monkeypatch, rt_base):
        import engines.pocketbook.engine as PE
        monkeypatch.setattr(PE, "_load_config",
                            lambda: {"review_test_base": rt_base})
        return PE.PocketbookEngine()

    def test_rt_base_missing_warns(self, monkeypatch, tmp_path):
        eng = self._engine(monkeypatch, str(tmp_path / "없는폴더"))
        logs = []
        rt_map, missing = eng._discover_review_tests(
            ["동아박1과"], ["textbook"], "고1", str(tmp_path), logs.append)
        assert rt_map == {} and missing == ["동아박1과"]  # 동작 무변경
        assert any("[경고]" in l and "기준 폴더" in l for l in logs)

    def test_folder_match_zero_warns_with_candidates(self, monkeypatch, tmp_path):
        rt_base = tmp_path / "base"
        tb = rt_base / "교과서 작업" / "공통영어1" / "YBM(박)"
        tb.mkdir(parents=True)
        (rt_base / "교과서 작업" / "공통영어1" / "YBM(박)" / "1과").mkdir()
        eng = self._engine(monkeypatch, str(rt_base))
        logs = []
        # 출판사 토큰이 전혀 다른 카테고리 → search_dirs 0건 (종전 완전 침묵)
        rt_map, missing = eng._discover_review_tests(
            ["없는출판사9과"], ["textbook"], "고1", str(tmp_path), logs.append,
            semester="1")
        assert not any(v.get("passages") for v in rt_map.values())
        assert missing == []  # 동작 무변경 (missing 미추가 유지 — 승격 금지)
        assert any("[경고]" in l and "폴더 매칭 0건" in l for l in logs)
        assert any("후보 폴더" in l for l in logs)

    def test_ebs_no_gang_number_warns(self, monkeypatch, tmp_path):
        rt_base = tmp_path / "base"
        (rt_base / "EBS 작업").mkdir(parents=True)
        eng = self._engine(monkeypatch, str(rt_base))
        logs = []
        eng._discover_review_tests(
            ["올포강없음"], ["ebs"], "고1", str(tmp_path), logs.append)
        assert any("[경고]" in l and "강 번호" in l for l in logs)

    def test_mockexam_no_date_warns(self, monkeypatch, tmp_path):
        rt_base = tmp_path / "base"
        rt_base.mkdir()
        eng = self._engine(monkeypatch, str(rt_base))
        logs = []
        eng._discover_review_tests(
            ["날짜없는모의"], ["mockexam"], "고1", str(tmp_path), logs.append)
        assert any("[경고]" in l and "YY년M월" in l for l in logs)


# ── final: parse_grammar_word 헤더 변형 의심 병합 가시화 ────────────────────

class TestGrammarWordHeaderVariant:
    def _docx(self, tmp_path, rows):
        docx = pytest.importorskip("docx")
        d = docx.Document()
        t = d.add_table(rows=0, cols=2)
        for left in rows:
            cells = t.add_row().cells
            cells[0].text = left
            cells[1].text = ""
        p = os.path.join(str(tmp_path), "gw.docx")
        d.save(p)
        return p

    def test_variant_header_merged_warns(self, tmp_path):
        from engines.final.grammar_word_parser import parse_grammar_word
        # "1. L2 본문1" (하이픈 누락 변형) → is_header 미인식 → 본문 병합
        p = self._docx(tmp_path, ["1. L2-본문1", "First body line.",
                                  "2. L2 본문2", "Second body line."])
        logs = []
        blocks = parse_grammar_word(p, log=logs.append)
        assert len(blocks) == 1  # 동작 무변경 — 병합 그대로
        assert any("[경고]" in l and "헤더 변형 의심" in l for l in logs)

    def test_normal_headers_silent(self, tmp_path):
        from engines.final.grammar_word_parser import parse_grammar_word
        p = self._docx(tmp_path, ["1. L2-본문1", "Body one.",
                                  "2. L2-본문2", "Body two."])
        logs = []
        blocks = parse_grammar_word(p, log=logs.append)
        assert len(blocks) == 2
        assert not any("[경고]" in l for l in logs)


# ── hanyoung: 열 역할 미검출 → 위치 기본 매핑 폴백 가시화 ───────────────────

class TestHanyoungColumnVisibility:
    def test_csv_without_header_warns(self, tmp_path):
        from engines.hanyoung.parser import _parse_csv
        p = tmp_path / "v.csv"
        p.write_text("apple,사과,fruit,none\nbanana,바나나,fruit,none\n",
                     encoding="utf-8-sig")
        logs = []
        entries, _ = _parse_csv(str(p), "1장", logs.append)
        assert entries  # 동작 무변경 — 위치 매핑으로 계속 파싱
        assert any("[경고]" in l and "기본 매핑" in l for l in logs)

    def test_csv_with_header_silent(self, tmp_path):
        from engines.hanyoung.parser import _parse_csv
        p = tmp_path / "v2.csv"
        p.write_text("단어,뜻,유의어,반의어\napple,사과,-,-\n",
                     encoding="utf-8-sig")
        logs = []
        entries, _ = _parse_csv(str(p), "1장", logs.append)
        assert entries
        assert not any("[경고]" in l for l in logs)

    def test_word_at_col0_nondefault_order_preserved(self, tmp_path):
        # word가 0열(falsy 인덱스)에 감지돼도 감지 결과를 버리지 않는다 —
        # `not col_map.get('word')` falsy-0 버그 회귀 방지 (열 순서 뒤바뀐 파일).
        from engines.hanyoung.parser import _parse_csv
        p = tmp_path / "v3.csv"
        p.write_text("단어,반의어,뜻,유의어\napple,opp,사과,syn\n",
                     encoding="utf-8-sig")
        logs = []
        sections, _ = _parse_csv(str(p), "1장", logs.append)
        e = sections[0]["entries"][0]
        assert e == {"word": "apple", "meaning": "사과",
                     "synonym": "syn", "antonym": "opp"}
        assert not any("[경고]" in l for l in logs)
