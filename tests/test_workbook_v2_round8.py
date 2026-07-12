"""W18 품질 루프 8라운드 가드 — 신규 선정 2종:
c17 고1 23년 11월 모의고사 워크북 폴더 → workbook_sero_v2 (세로 첫 품질 루프)
c18 리딩파워(Reading power) 유형편 완성 기출문제(Step 3에 사용함).hwp
    → ebs_workbook_v2

결함 재현→수리 고정:
  D1 (c18) 선두 표제 블록의 날짜-only 메모("17. 11. 23")가 문항 번호 보호
     규칙에 오인 보호돼 본문 첫 단락으로 인쇄 → 파서
     _strip_step3_leading_junk 날짜 예외 + 게이트 G20 [선두잔재]
  D2 (c18/sero 잠복) 시작 신호 없는 해요체 발문("영어로 번역하세요
     [9강 1번]" / "11. (주관식) … 고르세요. [정답 2개]")이 지문 스타일로
     인쇄 → 플랜 오버레이 꼬리 [출처/태그]+세요-체 종결 → Q + 게이트 G13
     확장 (꼬리 태그 + 시오/세요 종결)
  D3 (c17) 정답/스텝1·2 파일의 Step3 오라우팅 — "고1 23년 11월 NN번_정답
     .hwp" 20종 + "…워크북step3_정답지.hwpx" + "Step1 A1 어휘선택(2단계
     34번).docx"가 Step3로 흘러 중복/정답 사이클 생성 → sero_v2 라우팅 가드
  D4 (c17) 정규 모의고사 워크북 마커 미인식 — 고N #NN / NN. / N. pN-no.NN /
     NN번 셰이프에서 q_num 분할 0 → 전 스텝 침묵 유실(빈 사이클 조판) →
     sero_v2 자체 분할 오케스트레이션 (v1 helpers 재사용)
  D5 (c17) sero verify 완제품 게이트 부재 — 위 침묵 유실이 verify ok=True로
     통과 → 게이트 통합 (pseudo-plan/steps 어댑터 + G9 uploads)
"""
import json
import os

from engines.workbook_v2.gate import inspect_workbook_finish

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)

_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"


def _fixture(name):
    path = os.path.join(TESTS_DIR, "fixtures", "w18_defect_dumps", name)
    return json.load(open(path, encoding="utf-8"))


def _dump(paragraphs):
    return {"stories": [{"paragraphs": paragraphs, "pg": ["1"],
                         "b": [0, 0]}],
            "stale_pages": []}


# ── D1 게이트: G20 선두 날짜-only 잔재 ──────────────────────────────────────

def test_gate_g20_detects_leading_date():
    d = _dump([
        {"t": "17. 11. 23", "s": _ST_P},
        {"t": "다음 글의 내용과 일치하는 것은? [1강-E2]", "s": _ST_Q},
        {"t": "Anne Mangen at the University of Oslo studied.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert any("선두잔재" in c for c in rep["critical"])


def test_gate_g20_ignores_mid_story_date():
    """본문 중간의 날짜-only 단락은 검사하지 않는다 (스토리 선두 한정)."""
    d = _dump([
        {"t": "다음 글의 내용과 일치하는 것은?", "s": _ST_Q},
        {"t": "2017. 11. 23", "s": _ST_P},
        {"t": "Some passage text here.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert not any("선두잔재" in c for c in rep["critical"])


def test_gate_g20_ignores_question_number_lead():
    """선두 문항 번호("1. 다음 …")는 날짜가 아니다."""
    d = _dump([
        {"t": "1. 다음 글을 읽고 물음에 답하시오.", "s": _ST_Q},
        {"t": "Passage body.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert not any("선두잔재" in c for c in rep["critical"])


# ── D2 게이트: G13 확장 (꼬리 태그 + 시오/세요 종결) ────────────────────────

def test_gate_g13_ext_detects_tail_tag_seyo():
    d = _dump([
        {"t": "영어로 번역하세요 [9강 1번]", "s": _ST_P},
        {"t": "Passage body sentence.", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert any("발문스타일" in c for c in rep["critical"])


def test_gate_g13_ext_catches_sero_latent_dump():
    """세로 e79f8af9 기출력(W5, 게이트 이전)의 잠복 결함 — "11. (주관식)
    어법상 틀린 곳을 고르세요. [정답 2개]"가 지문 스타일 (수리 전 실덤프
    발췌 픽스처 — 재조판 후에도 검출 근거 유지)."""
    rep = inspect_workbook_finish(None, None,
                                  _fixture("e79f8af9_qstyle_pre_fix.json"))
    assert any("발문스타일" in c for c in rep["critical"])


def test_gate_g13_ext_clean_when_q_styled():
    d = _dump([
        {"t": "영어로 번역하세요 [9강 1번]", "s": _ST_Q},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert not any("발문스타일" in c for c in rep["critical"])


def test_gate_g13_ext_ignores_plain_tail_tag():
    """시오/세요 종결이 아닌 꼬리 태그 라인(출처 마커 인쇄 관행)은 무관."""
    d = _dump([
        {"t": "이것은 해설 문장이다 [3점]", "s": _ST_P},
    ])
    rep = inspect_workbook_finish(None, None, d)
    assert not any("발문스타일" in c for c in rep["critical"])


# ── D1 파서: _strip_step3_leading_junk 날짜 예외 ────────────────────────────

def _paras(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def test_strip_leading_junk_drops_date_in_title_block():
    from engines.workbook.parser import _strip_step3_leading_junk
    out = _strip_step3_leading_junk(_paras(
        "영어는 언어다",
        "Readign Power 유형편 완성 기출문제",
        "17. 11. 23",
        "다음 글의 내용과 일치하는 것은? [1강-E2]",
        "Anne Mangen at the University of Oslo studied the performance.",
    ))
    texts = [p["text"] for p in out]
    assert texts[0].startswith("다음 글의 내용과")
    assert "17. 11. 23" not in texts


def test_strip_leading_junk_keeps_mid_document_date():
    from engines.workbook.parser import _strip_step3_leading_junk
    out = _strip_step3_leading_junk(_paras(
        "다음 글의 내용과 일치하는 것은?",
        "17. 11. 23",
        "Passage body.",
    ))
    assert [p["text"] for p in out] == [
        "다음 글의 내용과 일치하는 것은?", "17. 11. 23", "Passage body."]


def test_strip_leading_junk_keeps_question_number():
    from engines.workbook.parser import _strip_step3_leading_junk
    out = _strip_step3_leading_junk(_paras(
        "1. 다음 글을 읽고 물음에 답하시오.", "Passage body."))
    assert len(out) == 2


# ── D2 플랜: 해요체 + 꼬리 태그 발문 오버레이 ───────────────────────────────

def test_s3_effective_kind_tail_tag_seyo():
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind("UNKNOWN", "영어로 번역하세요 [9강 1번]") == "Q"
    assert _s3_effective_kind(
        "UNKNOWN",
        "11. (주관식) 어법상 틀린 곳을 고르세요. [정답 2개]") == "Q"


def test_s3_effective_kind_seyo_without_tag_unchanged():
    """시작 신호도 꼬리 태그도 없는 해요체는 기존 규칙 유지 (해석 문장
    오탐 방지 — W16 AND 결합 설계 보존)."""
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind("UNKNOWN", "영어로 번역하세요") == "UNKNOWN"


def test_s3_effective_kind_strong_kind_not_overridden():
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind("P", "영어로 번역하세요 [9강 1번]") == "P"


def test_s3_effective_kind_tag_but_not_seyo_end_unchanged():
    """꼬리 태그가 있어도 몸통이 세요-체 종결이 아니면 무변경 (지문 속
    출처 표기 문장 보호)."""
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind(
        "UNKNOWN", "그는 학교에 갔다 [3점]") == "UNKNOWN"


# ── D3 세로 라우팅 가드 ─────────────────────────────────────────────────────

def _sero_engine():
    from engines import registry
    return registry.get("workbook_sero_v2")


def test_sero_routing_step12_prefix_not_step3(tmp_path):
    """'Step1 A1 어휘선택(2단계 34번).docx'의 '34번'이 Step3로 오라우팅되지
    않는다 (c17 실증 — Q34 중복 사이클)."""
    eng = _sero_engine()
    src = tmp_path / "Step1 A1 어휘선택(2단계 34번).docx"
    src.write_bytes(b"x")
    job = tmp_path / "job"
    job.mkdir()
    try:
        eng.parse({"manuscripts": [str(src)]}, str(job), lambda m: None)
    except Exception:
        pass    # 파싱 실패는 무관 — 라우팅 결과만 본다
    assert (job / "uploads" / "Step1 A1 어휘선택(2단계 34번).docx").exists()
    assert not (job / "uploads" / "Step3"
                / "Step1 A1 어휘선택(2단계 34번).docx").exists()


def test_sero_routing_answer_files_not_step3(tmp_path):
    """'고1 23년 11월 20번_정답.hwp'(스텝3 정답 폴더)와 '…워크북step3_정답지
    .hwpx'가 Step3(문제)로 오라우팅되지 않는다 (c17 실증 — 정답 사이클
    20개 중복 생성)."""
    eng = _sero_engine()
    files = ["고1 23년 11월 20번_정답.hwp", "고1 23년 11월_워크북step3_정답지.hwpx"]
    paths = []
    for n in files:
        p = tmp_path / n
        p.write_bytes(b"x")
        paths.append(str(p))
    job = tmp_path / "job"
    job.mkdir()
    try:
        eng.parse({"manuscripts": paths}, str(job), lambda m: None)
    except Exception:
        pass
    for n in files:
        assert (job / "uploads" / n).exists(), n
        assert not (job / "uploads" / "Step3" / n).exists(), n


def test_sero_routing_v1_step3_names_unchanged(tmp_path):
    """v1 코퍼스 명명('Step3 15강 14번 171140.docx' / '고1 25년 9월
    18번.hwp')은 여전히 Step3로 라우팅된다 (파리티)."""
    eng = _sero_engine()
    files = ["Step3 15강 14번 171140.docx", "고1 25년 9월 18번.hwp"]
    paths = []
    for n in files:
        p = tmp_path / n
        p.write_bytes(b"x")
        paths.append(str(p))
    job = tmp_path / "job"
    job.mkdir()
    try:
        eng.parse({"manuscripts": paths}, str(job), lambda m: None)
    except Exception:
        pass
    for n in files:
        assert (job / "uploads" / "Step3" / n).exists(), n


def test_sero_stage_rename_grammar_basic():
    """'Step2 B2 문법 기본 문제 정답.docx' → step2_a1_btm 기대명 rename
    (D6). 이미 어법선택 명명이거나 정답 아닌 문제지는 무변경."""
    eng = _sero_engine()
    logs = []
    assert eng._stage_fname("Step2 B2 문법 기본 문제 정답.docx",
                            logs.append) == "Step2 A1 어법선택(객관식).docx"
    assert eng._stage_fname("Step2 B2 문법 기본 문제.docx",
                            logs.append) == "Step2 B2 문법 기본 문제.docx"
    assert eng._stage_fname("Step2 A1 어법선택(문법 기본 문제) 정답지.docx",
                            logs.append) \
        == "Step2 A1 어법선택(문법 기본 문제) 정답지.docx"


# ── D4 세로 분할 마커 확장 ──────────────────────────────────────────────────

def _p(*texts):
    return [{"text": t, "runs": [{"t": t, "ul": False}]} for t in texts]


def test_sero_split_pnno_headers():
    from engines.workbook_sero_v2.parser_ext import (
        _split_paragraphs_by_qnum_v2)
    secs = _split_paragraphs_by_qnum_v2(_p(
        "1. p2-no.20", "Body A.", "2. p3-no.21  (정답 1개)", "Body B.",
        "18. p11-no.41~42", "Body C."), {"20", "21", "41", "42"})
    assert [(s["q_num"], s["q_num_end"]) for s in secs] == [
        ("20", None), ("21", None), ("41", "42")]
    assert [p["text"] for p in secs[0]["paragraphs"]] == ["Body A."]


def test_sero_split_hash_and_bare_markers():
    from engines.workbook_sero_v2.parser_ext import (
        _split_paragraphs_by_qnum_v2)
    known = {"20", "21"}
    secs = _split_paragraphs_by_qnum_v2(_p(
        "고1 #20", "Body A.", "21.", "Body B.", "21번", "Body B2.",
        "1. 어휘1단계", "item"), known)
    # "1. 어휘1단계"는 마커 아님 (bare 아님) / "21번"은 21에 병합
    assert [s["q_num"] for s in secs] == ["20", "21"]
    assert [p["text"] for p in secs[1]["paragraphs"]] == [
        "Body B.", "Body B2.", "1. 어휘1단계", "item"]


def test_sero_split_bare_requires_known_qnum():
    from engines.workbook_sero_v2.parser_ext import (
        _split_paragraphs_by_qnum_v2)
    secs = _split_paragraphs_by_qnum_v2(_p(
        "고1 #20", "1.", "item one", "2.", "item two"), {"20"})
    assert len(secs) == 1
    assert len(secs[0]["paragraphs"]) == 4


def test_sero_split_inclusive_stem_tail():
    """b1 순서삽입 문제 모음 — 발문 꼬리 [24] 표기가 포함형 마커 (c17
    실증: 파일 꼬리 모음이 마지막 지문 섹션에 통째로 붙던 것)."""
    from engines.workbook_sero_v2.parser_ext import (
        _split_paragraphs_by_qnum_v2)
    stem = "글의 흐름으로 보아, 주어진 문장이 들어가기에 가장 적절한 곳은? [24] ③"
    secs = _split_paragraphs_by_qnum_v2(_p(
        "24.", "Passage.", "주제", "Topic line.",
        "41.", "Passage41.",
        stem, "Given sentence.", "Body."), {"24", "41"})
    by = {s["q_num"]: [p["text"] for p in s["paragraphs"]] for s in secs}
    assert by["24"] == ["Passage.", "주제", "Topic line.",
                        stem, "Given sentence.", "Body."]
    assert by["41"] == ["Passage41."]


def test_sero_cut_answer_parts():
    """a2 '내용일치 정답' 이하 정답 파트("고1 #21 ③" 원문자 마커 포함)가
    사이클에 실리지 않는다 (c17 실증: 마지막 섹션에 234단락 부착)."""
    from engines.workbook_sero_v2.parser_ext import _cut_answer_parts
    out = _cut_answer_parts(_p(
        "고1 #20", "Problem body.", "내용일치 정답",
        "고1 #20 ⑤", "(1) T", "(2) F"), {"20"})
    assert [p["text"] for p in out] == ["고1 #20", "Problem body."]


def test_sero_cut_answer_parts_resumes_at_marker():
    from engines.workbook_sero_v2.parser_ext import _cut_answer_parts
    out = _cut_answer_parts(_p(
        "고1 #20", "Part1.", "어휘1단계 정답", "junk",
        "고1 #21", "Part2."), {"20", "21"})
    assert [p["text"] for p in out] == ["고1 #20", "Part1.",
                                        "고1 #21", "Part2."]


def test_sero_corpus_parity_deep():
    """v2 오케스트레이션이 세로 코퍼스 3건의 골든 cycles를 그대로 재현
    (마커 확장·정답 파트 컷·병합이 v1 증강 원고에 무영향)."""
    import _replay
    eng = _sero_engine()
    for case in ("e79f8af9", "b74f395f", "b9e0f1a4"):
        case_dir = os.path.join(TESTS_DIR, "corpus", "workbook_sero", case)
        if not os.path.isdir(case_dir):
            continue
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            job = os.path.join(td, "job")
            _replay.build_job(case_dir, job)
            uploaded = _replay.build_uploaded(eng, job)
            json_path = eng.parse(uploaded, job, lambda m: None)
            content = json.load(open(json_path, encoding="utf-8"))
            golden = json.load(open(
                os.path.join(case_dir, "golden", "content.json"),
                encoding="utf-8"))
            assert content["cycles"] == golden["cycles"], case


# ── D5 세로 verify 게이트 통합 (G7 — 빈 플랜 검출) ──────────────────────────

def test_sero_gate_empty_plan_critical():
    """전 스텝 0분할 침묵 유실 셰이프 — 유닛 0 플랜이면 G7 critical
    (수리 전 c17이 verify ok=True로 통과하던 구멍)."""
    rep = inspect_workbook_finish({}, {"flows": []}, {"stories": [],
                                                      "stale_pages": []})
    assert any("빈플랜" in c for c in rep["critical"])


def _touch(d, names):
    os.makedirs(d, exist_ok=True)
    for n in names:
        open(os.path.join(d, n), "w").close()


def test_gate_g16_family_consumed_not_critical(tmp_path):
    """소비된 스텝 가족의 변형본('빈칸어휘(개정)' 병존)은 G16 critical이
    아니라 G9 warning (c17 실증). 가족이 아예 미소비면 여전히 critical."""
    up = tmp_path / "uploads"
    _touch(str(up), ["Step1 C2 빈칸어휘(개정).docx",
                     "Step1 C1 문장배열.docx"])
    content = {"steps": {
        "step1_c2": {"filename": "Step1 C2 빈칸어휘 정답지.docx"},
    }}
    plan = {"flows": [{"step": "x",
                       "units": [[{"t": "unit text", "s": "st"}]]}]}
    rep = inspect_workbook_finish(content, plan,
                                  {"stories": [], "stale_pages": []},
                                  uploads_dir=str(up))
    crit = [c for c in rep["critical"] if "스텝원고미사용" in c]
    assert crit and "문장배열" in crit[0]
    assert "빈칸어휘(개정)" not in crit[0]
