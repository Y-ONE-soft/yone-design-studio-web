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


# ── D1 수리: 구6스텝 선라우팅 매핑 ───────────────────────────────────────────

def test_legacy_dest_name_mapping():
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    f = TextbookWorkbookV2Engine._legacy_dest_name
    names = set()
    assert f("Step2 문장배열.docx", names) == "Step1 C1 문장배열.docx"
    assert (f("Step2 문장배열 정답지.docx", names)
            == "Step1 C1 문장배열 정답지.docx")
    assert f("Step4 빈칸내용.docx", names) == "Step1 C2 빈칸어휘.docx"
    assert (f("Step4 빈칸내용 정답지.docx", names)
            == "Step1 C2 빈칸어휘 정답지.docx")
    assert (f("Step5 영작배열.docx", names)
            == "Step2 C2 영작배열(서술형).docx")
    assert f("Step6 실전문제.hwp", names) == "Step3 실전문제.hwp"
    # 미대응 토큰: StepN 접두 제거 (step3 오라우팅 차단) + 미대응 표기
    assert (f("Step3 어법수정.docx", names)
            == "어법수정 (구6스텝 미대응).docx")
    assert (f("Step3 어법수정 정답지.docx", names)
            == "어법수정 (구6스텝 미대응) 정답지.docx")
    # 현행 규격명(스텝 문자코드 포함)은 무변경
    assert f("Step1 A1 어휘선택.docx", names) is None
    assert f("Step2 C2 영작배열(서술형).hwpx", names) is None
    assert f("Step3.hwpx", names) is None
    # 충돌 방지: 현행 규격명이 폴더에 실재하면 rename하지 않음
    assert f("Step2 문장배열.docx", {"Step1 C1 문장배열.docx"}) is None


# ── D2 수리: 선두 표제/워터마크 블록 제거 ────────────────────────────────────

def _p(texts):
    return [{"text": t, "runs": []} for t in texts]


def test_strip_step3_leading_junk_c16_block():
    from engines.workbook.parser import _strip_step3_leading_junk
    paras = _p(["EBS 변형문제", " ", "EBS 올림포스", "영어독해 기본 02",
                "Chapter 03", "Unit 09", "  ",
                "http://cafe.naver.com/isaacenglishacademy",
                "※ 본 자료는 무단도용 및 타 사이트에 게시를 금합니다.",
                "[ Type A ]",
                "다음 글의 제목으로 가장 적절한 것은?"])
    out = [p["text"] for p in _strip_step3_leading_junk(paras)]
    assert out == [" ", "  ", "[ Type A ]",
                   "다음 글의 제목으로 가장 적절한 것은?"]


def test_strip_step3_leading_junk_apex_block():
    """v1 골든 0807ebd8/0e3844d2의 APEX 권리 블록 (긴 문장이라 표제 기준
    밖이지만 권리 어휘로 제거)."""
    from engines.workbook.parser import _strip_step3_leading_junk
    paras = _p(["리딩파워 유형편 [기본]", "CH5 17강 변형문제",
                "본 자료는 APEX에서 제작하였으며, 도서로의 모든 출판권과 "
                "파일 전송권 등은 APEX에 있습니다.",
                "본 자료의 레이아웃 및 편집 등에 대한 저작권 침해나 타 "
                "사이트 게시 및 무단복제/무단전송/무단도용을 금합니다.",
                "다음 글에 드러난 'Captain Zietem'의 심경으로 가장 적절한 "
                "것은? [pr2]"])
    out = [p["text"] for p in _strip_step3_leading_junk(paras)]
    assert len(out) == 1 and out[0].startswith("다음 글에")


def test_strip_step3_leading_junk_conservative():
    from engines.workbook.parser import _strip_step3_leading_junk
    # 40자+ 문서 타이틀(수능특강)은 표제 기준 밖 — 즉시 중단, 무변경
    stg = _p(["2027년 수능특강 영어                          더변형문제",
              "[Gateway]", "짧은 표제처럼 보이는 줄"])
    assert [p["text"] for p in _strip_step3_leading_junk(stg)] \
        == [p["text"] for p in stg]
    # 발문/지시문 시작 신호는 보호 — 첫 줄부터 실질 내용이면 무변경
    q = _p(["서술형 1. 다음 조건에 맞게 쓰시오", "본문..."])
    assert [p["text"] for p in _strip_step3_leading_junk(q)] \
        == [p["text"] for p in q]
    # 문서 중간(첫 실질 라인 이후)은 절대 무접촉
    mid = _p(["다음 글의 제목으로 가장 적절한 것은?", "기출┃2023┃",
              "passage"])
    assert [p["text"] for p in _strip_step3_leading_junk(mid)] \
        == [p["text"] for p in mid]


def test_strip_step3_leading_junk_doc_label():
    """c11 Step6 실전문제.hwp 선두 '기출┃2023┃' 문서 라벨 제거."""
    from engines.workbook.parser import _strip_step3_leading_junk
    paras = _p(["기출┃2023┃", "다음 글의 밑줄 친 ⓐ~ⓔ 중, 어법상 어색한 "
                "것은?", "If we were asked..."])
    out = [p["text"] for p in _strip_step3_leading_junk(paras)]
    assert out[0].startswith("다음 글의")


# ── D3 수리: 꼬리 '<표제> 정답' 섹션 절단 ────────────────────────────────────

def test_strip_step3_answers_tail_title_cut():
    from engines.workbook.parser import _strip_step3_answers
    paras = _p(["마지막 문제 지문입니다.",
                "2025년 06월 모의고사 <고2> 정답",
                "★ 객관식 빠른 정답", "1", "2",
                "규림재희아빠 선생님", "최종 감수\tIsaac 매니저님"])
    out = [p["text"] for p in _strip_step3_answers(paras)]
    assert out == ["마지막 문제 지문입니다."]


def test_strip_step3_answers_keeps_per_question_lines():
    from engines.workbook.parser import _strip_step3_answers
    paras = _p(["■ 정답: He was taken on tour by his enslaver.",
                "다음 중 이 문제의 정답은?"])
    out = [p["text"] for p in _strip_step3_answers(paras)]
    assert out == [p["text"] for p in paras]


# ── D4 수리: Box 전파가 유형 마커에서 중단 ───────────────────────────────────

def test_box_propagation_breaks_at_type_marker():
    res = classify_paragraphs([
        {"text": "<보기>"},
        {"text": "they / is / exist / that / understand"},
        {"text": ""},
        {"text": ""},
        {"text": "[ Type C (2) ]"},
        {"text": "※ 다음 글을 읽고 물음에 답하시오."},
    ])
    kinds = [r["kind"] for r in res]
    assert kinds[1] == "Box"          # 어구 나열은 유지
    assert kinds[4] != "Box"          # 유형 마커는 전파 차단
    # 어구 나열 대괄호(구분자 포함)는 여전히 Box 전파
    res2 = classify_paragraphs([
        {"text": "<보기>"},
        {"text": "[ pleased / pleasing ]"},
    ])
    assert res2[1]["kind"] == "Box"


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

# ── 코퍼스 r7 — c11 커스텀 리플레이 + 플랜 앵커 ─────────────────────────────

CORPUS = os.path.join(TESTS_DIR, "corpus")


def test_round7_c11_parse_replay(tmp_path):
    """r7c11oldwb 커스텀 리플레이 — 구6스텝 폴더가 선라우팅 스테이징을
    거쳐 6스텝으로 파싱된다 (r6c10cheonjae와 동일 방식)."""
    import sys
    sys.path.insert(0, TESTS_DIR)
    import _replay
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    case_dir = os.path.join(CORPUS, "textbook_workbook", "r7c11oldwb")
    job = str(tmp_path / "job")
    os.makedirs(job)
    for n in os.listdir(os.path.join(case_dir, "meta")):
        with open(os.path.join(case_dir, "meta", n)) as f:
            val = f.read()
        with open(os.path.join(job, n), "w") as f:
            f.write(val)
    with open(os.path.join(job, "manuscript_folder.txt"), "w") as f:
        f.write(os.path.join(case_dir, "inputs_folder"))
    logs = []
    json_path = TextbookWorkbookV2Engine().parse({"manuscripts": []}, job,
                                                 logs.append)
    produced = _replay.canonicalize(
        json.load(open(json_path, encoding="utf-8")), [job])
    golden = _replay.canonicalize(
        json.load(open(os.path.join(case_dir, "golden", "content.json"),
                       encoding="utf-8")), [])
    diff = _replay.first_diff(produced, golden)
    assert diff is None, diff
    assert any("[구6스텝]" in m for m in logs)


def test_round7_c11_plan_anchor():
    """c11 골든 재플랜 — 구6스텝 라우팅 후 6스텝 플랜 (실전문제=step3,
    어법수정 시그니처 0)."""
    import re
    from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds
    golden = os.path.join(CORPUS, "textbook_workbook", "r7c11oldwb",
                          "golden", "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    ensure_step3_kinds(c["steps"]["step3"])
    plan = steps_to_plan(c["steps"], workbook_type="교과서")
    shape = {f["step"]: (len(f["units"]),
                         sum(len(u["paras"] if isinstance(u, dict) else u)
                             for u in f["units"]))
             for f in plan["flows"]}
    assert shape == {"step1_a1": (6, 12), "step1_a1_2": (6, 12),
                     "step1_c1": (6, 75), "step1_c2": (6, 110),
                     "step2_c2": (1, 33), "step3": (1, 560)}
    # D5: step2_c2 헤더("1. L1-본문1") 플랜 제거 / D6: 꼬리 라이센스 제거
    c2 = [f for f in plan["flows"] if f["step"] == "step2_c2"][0]
    c2_paras = [p for u in c2["units"]
                for p in (u["paras"] if isinstance(u, dict) else u)]
    from engines.workbook_v2.plan import is_header_line, _norm_header
    assert not [p for p in c2_paras
                if is_header_line(_norm_header(p["t"]))]
    assert plan["unsupported"] == []
    sig = re.compile(r"\d\s*\[\s*[A-Za-z]")
    st3 = [f for f in plan["flows"] if f["step"] == "step3"][0]
    paras = [p for u in st3["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    assert sum(len(sig.findall(p["t"])) for p in paras) == 0


def test_round7_c16_plan_anchor():
    """c16 골든 재플랜 — 워터마크/꼬리 정답 표제 0 + 유형 마커 6개
    지문 스타일 일관 (D2/D3/D4 수리 고정)."""
    import re
    from collections import Counter
    from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds
    golden = os.path.join(CORPUS, "ebs_workbook_v2", "r7c16olympos",
                          "golden", "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    ensure_step3_kinds(c["steps"]["step3"])
    plan = steps_to_plan(c["steps"], workbook_type="EBS")
    fl = [f for f in plan["flows"] if f["step"] == "step3"][0]
    paras = [p for u in fl["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    assert len(paras) == 301
    junk = re.compile(r"^(https?://|※ 본|EBS |영어독해)")
    assert not [p for p in paras if junk.match(p["t"].strip())]
    assert not [p for p in paras if p["t"].strip().endswith(" 정답")]
    tm = [p for p in paras if p["t"].strip().startswith("[ Type")]
    assert len(tm) == 6 and len({p["s"] for p in tm}) == 1
    tally = Counter(p["s"].split(">")[-1].strip() for p in paras)
    assert tally["조건 올림포스"] == 7
    assert tally["배경 올림포스"] == 1      # PUA 화살표 → 삭제+배경 (W14 D2)


# ── D5/D6 수리 (c11 실조판 게이트 검출분 — G1 헤더잔존 / G17 워터마크) ───────

def test_strip_step3_trailing_junk():
    from engines.workbook.parser import _strip_step3_trailing_junk
    paras = _p(["마지막 문제 지문입니다.", "",
                "본 콘텐츠는 해당 출판사로부터 교과서 라이센스를 획득하여 "
                "이그잼포유에서 제작하였습니다. 본 콘텐츠에 대한 저작권은 "
                "이그잼포유가 소유하고 있으며, 콘텐츠의 전부 또는 일부를 "
                "무단 전재하거나 배포하는 것은 저작권법에 의한 법적 책임을 "
                "물을 수 있습니다."])
    out = [p["text"] for p in _strip_step3_trailing_junk(paras)]
    assert out == ["마지막 문제 지문입니다.", ""]
    # 문서 중간 권리 문구는 무접촉 (꼬리에 실질 라인이 있으면 중단)
    mid = _p(["지문", "저작권 관련 지문 문장입니다.", "실질 마지막 지문."])
    assert [p["text"] for p in _strip_step3_trailing_junk(mid)] \
        == [p["text"] for p in mid]


def test_build_step2_c2_strips_headers():
    """D5: 한글 포함 지문 헤더("1. L1-본문1")가 v1 eng_only 삭제 룰을
    비껴가 문항번호 스타일로 인쇄되던 것 — 플랜에서 제거."""
    from engines.workbook_v2.plan import build_step2_c2
    step = {"paragraphs": [
        {"text": "1. L1-본문1", "runs": []},
        {"text": "만약 우리가 실패와 성공 중 어느 것을 선호하냐는 질문을 "
                 "받는다면, 우리는 모두 성공을 선택할 것이다.", "runs": []},
        {"text": "(prefer / and / would / one / choose / success)",
         "runs": []},
    ]}
    res = build_step2_c2(step)
    paras = [p for u in res["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    assert not [p for p in paras if p["t"].startswith("1. L1")]
    assert [p for p in paras if p["t"].startswith("만약")]
