"""W17 품질 루프 7라운드 가드 — 후보⑪ 대체(영어 독해와 작문 비상(김) 1과
15개정 구6스텝 워크북 폴더) + 신규 선정(올림포스 독해기본2 9강 스텝3.hwp).

결함 재현→수리 고정:
  D1 구6스텝 파일명 라우팅 공백 (c11 실증) — Step4 빈칸내용/Step5 영작배열/
     Step6 실전문제 침묵 미사용 + 'Step3 어법수정'이 실전문제(step3)로
     오라우팅 → textbook_workbook_v2 선라우팅 스테이징 + 게이트 G16/G19
  D2 문제모음 선두 표제/워터마크 블록 잔존 (c16 실증 7단락 + v1 골든
     0807ebd8/0e3844d2 APEX 블록 잠복) → 파서 _strip_step3_leading_junk
     + 게이트 G17
  D3 꼬리 '<표제> 정답' 섹션 표제 잔존 (c16 실증 + c04 실출력 잠복:
     정답표 88행 + 제작진 크레딧 29행 인쇄) → _strip_step3_answers 확장
     + G2(find_leaked_answers) 확장
  D4 Box 전파가 유형 구분 마커를 오염 (c16 실증: [ Type C (2) ]만 보기
     스타일) → 분류기 전파 차단 + 게이트 G18
"""
import json
import os

from core.structure.paragraph_kind import classify_paragraphs
from engines.workbook_v2.gate import inspect_workbook_finish

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)

_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"
_ST_BOX = "STEP 03 > 보기 올림포스"


def _fixture(name):
    path = os.path.join(TESTS_DIR, "fixtures", "w17_defect_dumps", name)
    return json.load(open(path, encoding="utf-8"))


def _dump(paragraphs):
    return {"stories": [{"paragraphs": paragraphs, "pg": ["1"],
                         "b": [0, 0]}],
            "stale_pages": []}


# ── D1 게이트: G16 미사용 스텝 원고 critical 승격 ────────────────────────────

def _touch(d, names):
    os.makedirs(d, exist_ok=True)
    for n in names:
        open(os.path.join(d, n), "w").close()


def test_gate_g16_detects_unused_step_manuscripts(tmp_path):
    """수리 전 c11 상태 재현: 실전문제/영작배열/빈칸내용 침묵 미사용 →
    critical [스텝원고미사용]."""
    up = str(tmp_path / "uploads")
    _touch(up, ["Step1 A1 어휘선택.docx", "Step2 문장배열.docx",
                "Step4 빈칸내용.docx", "Step5 영작배열.docx",
                "Step6 실전문제.hwp"])
    content = {"workbook_type": "교과서", "steps": {
        "step1_a1": {"filename": "Step1 A1 어휘선택.docx"},
        "step1_c1": {"filename": "Step2 문장배열.docx"},
    }}
    rep = inspect_workbook_finish(content, {"flows": []}, _dump([]),
                                  uploads_dir=up)
    hits = [c for c in rep["critical"] if "스텝원고미사용" in c]
    assert hits and "실전문제" in hits[0]
    assert len(rep["stats"]["unused_step_manuscripts"]) == 3


def test_gate_g16_unmapped_stays_warning(tmp_path):
    """수리 후 c11 상태: 어법수정(구6스텝 미대응)은 경고만 (교과서 계열은
    어법수정 소화 스텝이 없다 — 운영 판단 위임)."""
    up = str(tmp_path / "uploads")
    _touch(up, ["어법수정 (구6스텝 미대응).docx"])
    content = {"workbook_type": "교과서", "steps": {}}
    rep = inspect_workbook_finish(content, {"flows": []}, _dump([]),
                                  uploads_dir=up)
    assert not [c for c in rep["critical"] if "스텝원고미사용" in c]
    assert [w for w in rep["warnings"] if "미사용원고" in w]


def test_gate_g16_ebs_counts_grammar_fix(tmp_path):
    """EBS 계열은 어법수정이 스텝 원고(file_map step2_a1) — critical."""
    up = str(tmp_path / "uploads")
    _touch(up, ["Step2 어법수정.docx"])
    content = {"workbook_type": "EBS", "steps": {}}
    rep = inspect_workbook_finish(content, {"flows": []}, _dump([]),
                                  uploads_dir=up)
    assert [c for c in rep["critical"] if "스텝원고미사용" in c]


# ── D1 게이트: G19 어법수정 step3 혼입 ───────────────────────────────────────

def _plan_for(dump):
    """덤프 스토리를 그대로 유닛으로 갖는 step3 플랜 스텁 (probe 일치)."""
    paras = dump["stories"][0]["paragraphs"]
    return {"flows": [{"step": "step3",
                       "units": [[{"t": p["t"]} for p in paras]]}]}


def test_gate_g19_detects_grammar_fix_in_step3():
    d = _fixture("c11_pre_fix.json")
    rep = inspect_workbook_finish(None, _plan_for(d), d)
    assert [c for c in rep["critical"] if "어법수정혼입" in c]
    assert rep["stats"]["grammar_fix_sig_hits"] >= 45


def test_gate_g19_clean_for_real_siljeon():
    """수리 후 step3(실전문제 pool ⓐ~ⓔ 형식)는 시그니처 0."""
    paras = [{"t": "다음 글의 밑줄 친 ⓐ~ⓔ 중, 어법상 어색한 것은?", "s": _ST_Q},
             {"t": "If we were asked which one we prefer.", "s": _ST_P},
             {"t": "① ⓐ ② ⓑ ③ ⓒ ④ ⓓ ⑤ ⓔ", "s": _ST_P}]
    d = _dump(paras)
    rep = inspect_workbook_finish(None, _plan_for(d), d)
    assert not [c for c in rep["critical"] if "어법수정혼입" in c]


# ── D2 게이트: G17 워터마크 잔존 ─────────────────────────────────────────────

def test_gate_g17_detects_watermark():
    d = _fixture("c16_pre_fix.json")
    rep = inspect_workbook_finish(None, None, d)
    hits = [c for c in rep["critical"] if "워터마크잔존" in c]
    assert hits and rep["stats"]["watermark_leaks"] >= 2


def test_gate_g17_ignores_vocab_definition():
    """어휘 정의('pirate : … 불법 복제하다')는 워터마크가 아니다
    (화이트북 실덤프 실증 false-positive 셰이프)."""
    d = _dump([{"t": "14. pirate : n. 1. 해적 2. 저작권 침해자 "
                     "v. 1. 해적 행위를 하다 2. 불법 복제하다", "s": "영단어"}])
    rep = inspect_workbook_finish(None, None, d)
    assert not [c for c in rep["critical"] if "워터마크잔존" in c]


# ── D3 게이트: G2 확장 — 꼬리 '<표제> 정답' ──────────────────────────────────

def test_gate_g2_detects_answer_tail_title():
    d = _fixture("c16_pre_fix.json")
    rep = inspect_workbook_finish(None, None, d)
    hits = [c for c in rep["critical"] if "정답잔존" in c]
    assert hits and "정답" in hits[0]


def test_gate_g2_ignores_per_question_answer_line():
    """'■ 정답: …' 문항별 정답(수능특강 Test2 형식)과 발문('…정답은?')은
    표제가 아니다."""
    d = _dump([{"t": "■ 정답: He was taken on tour by his enslaver.",
                "s": _ST_P},
               {"t": "다음 중 이 문제의 정답은?", "s": _ST_Q}])
    rep = inspect_workbook_finish(None, None, d)
    assert not [c for c in rep["critical"] if "정답잔존" in c]


# ── D4 게이트: G18 유형 마커 스타일 일관성 ───────────────────────────────────

def test_gate_g18_detects_type_marker_style_split():
    d = _fixture("c16_pre_fix.json")
    rep = inspect_workbook_finish(None, None, d)
    hits = [c for c in rep["critical"] if "유형마커스타일" in c]
    assert hits and _ST_BOX in hits[0]
    assert rep["stats"]["type_markers"] == 6
    assert rep["stats"]["type_marker_styles"] == 2


def test_gate_g18_clean_when_uniform():
    d = _dump([{"t": "[ Type A ]", "s": _ST_P},
               {"t": "[ Type B ]", "s": _ST_P},
               {"t": "[ Type C (1) ]", "s": _ST_P}])
    rep = inspect_workbook_finish(None, None, d)
    assert not [c for c in rep["critical"] if "유형마커스타일" in c]


# ── 기존 양품 덤프 false-critical 0 (신규 게이트 sweep) ──────────────────────

def test_new_gates_false_positive_free_on_known_good_dumps():
    good = [
        "data_corpus/round2/c12_wb2/out/job/typeset_dump.json",
        "data_corpus/round3/c13_ybm/out/job/typeset_dump.json",
        "data_corpus/round4/c03_tb_essay/out/job/typeset_dump.json",
        "data_corpus/round4/c06_rp_cr/out/job/typeset_dump.json",
        "data_corpus/tbwb_engine_e2e/20a3838b/job/typeset_dump.json",
        "data_corpus/wb_sero_e2e/e79f8af9/job/typeset_dump.json",
        "data_corpus/wbwt_engine_e2e/e41f1c70/job/typeset_dump.json",
    ]
    for rel in good:
        path = os.path.join(REPO, rel)
        if not os.path.isfile(path):
            continue
        d = json.load(open(path, encoding="utf-8"))
        rep = inspect_workbook_finish(None, None, d)
        for key in ("워터마크잔존", "유형마커스타일", "어법수정혼입",
                    "스텝원고미사용"):
            assert not [c for c in rep["critical"] if key in c], (rel, key)


def test_g2_extension_catches_c04_latent_dump():
    """W16까지 critical 0이던 c04 실출력의 잠복 결함(정답표+크레딧 블록)을
    G2 확장이 잡는다 — 존재 시에만 (재조판 후 새 덤프는 통과해야 하므로
    이 테스트는 수리 전 덤프를 고정 픽스처가 아닌 이력 검증으로만 본다)."""
    path = os.path.join(REPO, "tests", "fixtures", "w17_defect_dumps",
                        "c04_tail_pre_fix.json")
    d = json.load(open(path, encoding="utf-8"))
    rep = inspect_workbook_finish(None, None, d)
    assert [c for c in rep["critical"] if "정답잔존" in c]
