"""W16 품질 루프 6라운드 가드 — 후보⑦(EBS 리딩파워 유형편(완성) Unit17
Step3.hwp, [REVIEW N강-N번]형) + 후보⑩(15개정 천재(이) 8과 서술형 hwpx —
후보⑨ 동형 파이널 문장배열은 파이널 v1 관할이라 대체).

결함 재현→수리 고정:
  D1 [서술형 N] 접두 + 해요체("쓰세요") 발문이 지문 스타일 (c07 실증)
     → 플랜 오버레이 _s3_effective_kind 확장 + 게이트 G13
  D2 WORD_DEF 과광폭 — 대화문 화자 라벨("Minji:"/"A: …")·영문 제목이
     영단어 스타일 (c10 실증 6건 + c04 안내문 필드 27건·80dd3fa2 잠복.
     v1 실물: 전부 지문 스타일) → WORD_DEF 한글 뜻 + 2+글자 머리 + G14
  D3 <조건> 블록 항목 스타일 공백 3경로 (c10 실증 + c04/c05/0a5da924
     잠복) — (a) 영어 어구 나열에서 propagation 중단 → v1 pass 15
     의미론(skip-계속), (b) ◦⦁ㆍ∙ 불릿 마커 미등록, (c) 조건 문구가
     taxonomy 발문으로 오매칭(Q) → 무힌트 + '것' 종결 강등 + G15
"""
import json
import os

from core.structure.paragraph_kind import classify_paragraphs
from engines.workbook_v2.gate import inspect_workbook_finish
from engines.workbook_v2.plan import build_step3

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)

_ST_P = "STEP 03 > 실전 문제 지문 올림포스_"
_ST_Q = "STEP 03 > S_실전문제 번호 수정 올림포스"
_ST_COND = "STEP 03 > 조건 올림포스"
_ST_WORD = "STEP 03 > 영단어"

_SEYO_Q = ("[서술형 2] 다음 글의 밑줄 친 without을 if로 시작하여 바꿔 쓸 때 "
           "빈칸에 들어갈 알맞은 표현을 쓰세요. [리딩파워, Chapter4 Review "
           "17강 3번]")


def _dump(paragraphs):
    return {"stories": [{"paragraphs": paragraphs, "pg": ["1"],
                         "b": [0, 0]}],
            "stale_pages": []}


def _plan_stub():
    return {"flows": [{"step": "step3", "units": [[{"t": "x"}]]}]}


# ── D1 수리: 플랜 오버레이 — [서술형 N] 접두 + 해요체 발문 ───────────────────

def test_s3_overlay_seyo_and_tag_question():
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind("UNKNOWN", _SEYO_Q) == "Q"
    assert _s3_effective_kind(
        "UNKNOWN", "[서술형 1] 윗글의 빈칸에 알맞은 단어를 쓰시오.") == "Q"
    # 해요체 + 발문 시작 신호 (숫자 접두 포함 — Q_START_HINT)
    assert _s3_effective_kind(
        "UNKNOWN", "15. 다음 지문 속에 밑줄 친 'it'의 용법과 같은 'it'을 "
        "가진 문장을 고르세요.") == "Q"
    # 시작 신호 없는 해요체(해석/대화 문장)는 미발동 — false positive 방지
    assert _s3_effective_kind("K", "매일 아침 운동하세요.") == "K"
    # 강한 kind는 오버레이 대상 아님
    assert _s3_effective_kind("P", "Some passage ending 하세요.") == "P"


def test_s3_overlay_word_demotion():
    from engines.workbook_v2.plan import _s3_effective_kind
    # 화자 라벨 / 영문 제목 / 안내문 필드 / 1글자 머리 → 지문(P) 강등
    assert _s3_effective_kind("Word", "Minji:") == "P"
    assert _s3_effective_kind(
        "Word", "Gijisi Juldarigi Festival: A Celebration of Tradition") \
        == "P"
    assert _s3_effective_kind("Word", "Dates: July 5-7, 2025") == "P"
    assert _s3_effective_kind(
        "Word", "A: 노란색 코트를 입고 있는 저 여자 아이는 누구야?") == "P"
    # 실제 어휘 항목은 유지
    assert _s3_effective_kind("Word", "inherit: 물려받다") == "Word"
    assert _s3_effective_kind("Word", "*extensively 널리, 광범위하게") \
        == "Word"


def test_s3_overlay_speaker_line_not_question():
    """대화 화자 라벨 행은 물음표가 있어도 발문 승격 금지 (c10 실증 —
    Word 오분류 수리 후 KORQ 오버레이가 대화행을 발문으로 승격하던 것)."""
    from engines.workbook_v2.plan import _s3_effective_kind
    assert _s3_effective_kind(
        "UNKNOWN", "A: 노란색 코트를 입고 있는 저 여자 아이는 누구야?") \
        == "UNKNOWN"
    assert _s3_effective_kind(
        "UNKNOWN", "Minji: 이건 무슨 뜻이야? 대답해 보시오.") == "UNKNOWN"


def test_cond_propagation_v1_semantics():
    """D3 — <조건> 블록 전파 + 번호/불릿 항목 조건화 + 발문 오매칭(Q)
    강등 + 답란 종료 (c10 실증). W39 결함 3: 블록 안 단어 나열은 조건
    내용물 — v1 '지문 유지' 관행은 사용자 확정으로 폐기."""
    out = classify_paragraphs([
        {"text": "<조건>"},
        {"text": "team, teams, their, even though,"},        # 어구 = 조건
        {"text": "both, tried, won, best, my"},              # 어구 = 조건
        {"text": "1. 위 단어들을 어형변화 없이 모두, 한 번씩만 사용할 것"},
        {"text": "2. 위 단어들 외에 3개의 단어를 추가하여 '나의 팀'을 "
                 "강조하는 문장으로 완성할 것"},
        {"text": "정답: ___________________"},               # 답란 = 종료
        {"text": "다음은 글의 내용을 바탕으로 재구성한 문장이다."},
    ])
    kinds = [o["kind"] for o in out]
    assert kinds[0] == "Cond"
    assert kinds[1] == "Cond" and kinds[2] == "Cond", \
        "블록 안 단어 나열은 조건 (W39 결함 3)"
    assert kinds[3] == "Cond" and kinds[4] == "Cond", "번호 조건 항목"
    assert kinds[6] != "Cond", "답란 이후는 전파 금지"


def test_cond_propagation_bullets_and_q_demotion():
    out = classify_paragraphs([
        {"text": "<조건>"},
        {"text": "◦ It(가주어), that(진주어)를 활용할 것"},
        {"text": "◦ Gijisi juldarigi, couples, a child를 활용할 것"},
        {"text": "◦ 12단어 내외의 완전한 문장으로 작성할 것"},
        {"text": "<조건>"},
        # taxonomy 발문 리프(SRV-WRD-START-LETTER) 오매칭 → 강등
        {"text": "반드시 빈칸은 주어진 철자로 시작하는 한 단어로 쓸 것"},
    ])
    kinds = [o["kind"] for o in out]
    assert kinds[1:4] == ["Cond", "Cond", "Cond"]
    assert kinds[5] == "Cond", "조건 문구의 발문 오매칭은 조건으로 강등"


def test_cond_block_numbered_sio_items_are_cond():
    """W38 블록 문맥 우선 — 조건 블록 안 번호 항목은 종결어미(시오-체)
    무관 조건 항목 (W16 D3 "발문 유지(v1 관행)" 사용자 확정으로 폐기).
    진짜 발문(발문 어휘 선두 / 번호 시퀀스 이탈)만 블록을 종료한다."""
    out = classify_paragraphs([
        {"text": "<조건>"},
        {"text": "1.(A)는 본문에서 찾아 변형하여 한단어로 쓰시오."},
        {"text": "2.(B)는 본문에서 찾아 한 단어로 쓰시오"},
        # 번호 시퀀스 이탈 + 발문 어휘 선두 = 진짜 발문 (블록 종료)
        {"text": "22. 다음 글의 내용을 한 문장으로 요약하고자 한다. "
                 "빈칸 (A)에 들어갈 말로 가장 적절한 것은?"},
    ])
    kinds = [o["kind"] for o in out]
    assert kinds[1] == "Cond" and kinds[2] == "Cond"
    assert kinds[3] == "Q", "진짜 발문은 블록 종료"


def test_cond_block_paren_numbered_sio_items_are_cond():
    """W38 (6b66b750 실증): '1) 9단어로 빈칸을 완성하시오.' 괄호형 번호
    항목 — 발문 스타일+자동 번호로 인쇄되던 결함의 파서 계층 가드."""
    out = classify_paragraphs([
        {"text": "11. 다음 글을 읽고, 주제문을 주어진 조건에 맞게 완성하시오."},
        {"text": "The passage body sentence is long enough to be a passage "
                 "paragraph for the classifier here."},
        {"text": "[조건]"},
        {"text": "1) 9단어로 빈칸을 완성하시오."},
        {"text": "2) 다음 단어를 한 번씩 사용하여 배열하시오."},
    ])
    kinds = [o["kind"] for o in out]
    assert kinds[2] == "Cond"
    assert kinds[3] == "Cond" and kinds[4] == "Cond"
    assert kinds[0] == "Q"


def test_cond_item_with_inline_blank_not_block_end():
    """본문 중간 빈칸 표기는 답란이 아님 — 조건 항목 유지 (c06 실증)."""
    out = classify_paragraphs([
        {"text": "<조건>"},
        {"text": "보기의 [_______]에서 적절한 단어 하나만 고르고 나머지 "
                 "단어는 모두 한 번씩 사용할 것"},
        {"text": "주어진 단어들의 형태를 바꾸지 말 것"},
    ])
    assert out[1]["kind"] == "Cond"
    assert out[2]["kind"] == "Cond"


def test_word_def_tightened():
    """D2 분류기 — 화자 라벨/영문 제목/안내문 필드는 Word가 아님."""
    out = classify_paragraphs([
        {"text": "Minji:"},
        {"text": "Gijisi Juldarigi Festival: A Celebration of Tradition"},
        {"text": "Dates: July 5-7, 2025"},
        {"text": "A: 노란색 코트를 입고 있는 저 여자 아이는 누구야?"},
        {"text": "inherit: 물려받다"},
        {"text": "*extensively 널리, 광범위하게"},
    ])
    kinds = [o["kind"] for o in out]
    assert "Word" not in kinds[:4]
    assert kinds[4] == "Word" and kinds[5] == "Word"


# ── D1 게이트 G13: 발문 스타일 누락 — 수리 전 상태 재현으로 검출 실증 ─────────

def test_gate_g13_detects_seyo_question_as_passage():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": _SEYO_Q, "s": _ST_P},                     # 수리 전: 지문 스타일
    ]))
    assert any("[발문스타일]" in c for c in rep["critical"])
    assert rep["stats"]["q_style_miss"] == 1


def test_gate_g13_clean_when_question_styled():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": _SEYO_Q, "s": _ST_Q},
        # 시오-체 발문 (기존 정상 경로)
        {"t": "다음 글의 주제로 가장 적절한 것을 고르시오.", "s": _ST_Q},
        # 지문/선지/조건 단락은 시그니처 미해당 — false positive 방지
        {"t": "다음 주어진 예시처럼 강조 구문을 만들어 보자.", "s": _ST_P},
        {"t": "주어진 표현으로 시작할 것", "s": _ST_COND},
        {"t": "[REVIEW 17강-2번]", "s": _ST_P},          # 단독 마커 무해
    ]))
    assert rep["stats"]["q_style_miss"] == 0


# ── D2 게이트 G14: 영단어 오분류 — 수리 전 상태 재현으로 검출 실증 ────────────

def test_gate_g14_detects_non_vocab_word_style():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "Minji:", "s": _ST_WORD},                       # 화자 라벨
        {"t": "Gijisi Juldarigi Festival: A Celebration of Tradition",
         "s": _ST_WORD},                                      # 영문 제목
        {"t": "A: 노란색 코트를 입고 있는 저 여자 아이는 누구야?",
         "s": _ST_WORD},                                      # 1글자 머리
        {"t": "Dates: July 5-7, 2025", "s": _ST_WORD},        # 안내문 필드
    ]))
    assert any("[영단어오분류]" in c for c in rep["critical"])
    assert rep["stats"]["word_style_bad"] == 4


def test_gate_g14_clean_for_real_vocab():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "inherit: 물려받다", "s": _ST_WORD},
        {"t": "*extensively 널리, 광범위하게", "s": _ST_WORD},
        {"t": "Minji: Now, what does juldarigi mean to you?",
         "s": _ST_P},                                    # 지문 스타일이면 무관
    ]))
    assert rep["stats"]["word_style_bad"] == 0


# ── D3 게이트 G15: 조건 항목 스타일 — 수리 전 상태 재현으로 검출 실증 ─────────

def test_gate_g15_detects_condition_items_styled_as_passage():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "<조건>", "s": _ST_COND},
        {"t": "team, teams, their, even though,", "s": _ST_P},   # 어구 (skip)
        {"t": "both, tried, won, best, my", "s": _ST_P},         # 어구 (skip)
        {"t": "1. 위 단어들을 어형변화 없이 모두, 한 번씩만 사용할 것",
         "s": _ST_P},                                    # 수리 전: 지문
        {"t": "2. 위 단어들 외에 3개의 단어를 추가하여 '나의 팀'을 강조하는 "
              "문장으로 완성할 것", "s": _ST_P},
        {"t": "정답: ___________________", "s": _ST_P},   # 답란 = 블록 종료
    ]))
    assert any("[조건항목]" in c for c in rep["critical"])
    assert rep["stats"]["cond_item_miss"] == 2


def test_gate_g15_detects_bullet_items():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "<조건>", "s": _ST_COND},
        {"t": "◦ It(가주어), that(진주어)를 활용할 것", "s": _ST_COND},
        {"t": "◦ Gijisi juldarigi, couples, a child를 활용할 것",
         "s": _ST_P},                                    # 수리 전 (c10 실증)
        {"t": "⦁(1)은 Only later로 시작할 것", "s": _ST_P},  # c05 잠복 셰이프
    ]))
    assert rep["stats"]["cond_item_miss"] == 2


def test_gate_g15_clean_paths():
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "<조건>", "s": _ST_COND},
        {"t": "- 관계대명사 활용", "s": _ST_COND},
        {"t": "정답: ___________________", "s": _ST_P},
        # 별도 블록 (W38): 시오-체 번호 항목도 조건 스타일이 정상
        {"t": "<조건>", "s": _ST_COND},
        {"t": "1.(A)는 본문에서 찾아 변형하여 한단어로 쓰시오.", "s": _ST_COND},
        {"t": "2.(B)는 본문에서 찾아 한 단어로 쓰시오", "s": _ST_COND},
        # 별도 블록: 발문 시작 신호 발문 = 블록 종료
        {"t": "<조건>", "s": _ST_COND},
        {"t": "다음 글의 주제로 가장 적절한 것은?", "s": _ST_Q},
        # 별도 블록: 번호 시퀀스 이탈 + 발문 어휘 선두 = 진짜 발문 (종료)
        {"t": "<조건>", "s": _ST_COND},
        {"t": "· 우리말과 같은 의미가 되도록 영작하시오.", "s": _ST_COND},
        {"t": "22. 다음 글의 내용을 한 문장으로 요약하고자 한다.", "s": _ST_Q},
        # 별도 블록: 단어 나열도 조건 내용물 (W39 결함 3 — 지문 유지
        # 관행 폐기. 조건 스타일이면 G34 무지목)
        {"t": "<조건>", "s": _ST_COND},
        {"t": "end / plot / have / it / a / me / keep / from",
         "s": _ST_COND},
        {"t": "→ ____________________", "s": _ST_P},
    ]))
    assert rep["stats"]["cond_item_miss"] == 0
    assert rep["stats"]["cond_content_miss"] == 0


def test_gate_g15_detects_sio_numbered_items_styled_as_question():
    """W38 확장 (6b66b750 실증): 조건 블록 안 번호 항목이 발문 스타일로
    인쇄되면 검출 — "시오-체 번호 항목 발문 유지" W16 D3 계약의 폐기."""
    rep = inspect_workbook_finish({}, _plan_stub(), _dump([
        {"t": "<조건>", "s": _ST_COND},
        {"t": "1) 9단어로 빈칸을 완성하시오.", "s": _ST_Q},     # 수리 전
        {"t": "2) 다음 단어를 한 번씩 사용하여 배열하시오.", "s": _ST_Q},
    ]))
    assert any("[조건항목]" in c for c in rep["critical"])
    assert rep["stats"]["cond_item_miss"] == 2


# ── 코퍼스 r6 — c10 커스텀 리플레이 + 플랜 앵커 ─────────────────────────────

CORPUS = os.path.join(TESTS_DIR, "corpus")


def test_round6_c10_parse_replay(tmp_path):
    """r6c10cheonjae 커스텀 리플레이 — manuscript_folder 메타 경로
    (r4c03essay와 동일 방식). 15개정 천재(이) 8과 서술형 hwpx."""
    import sys
    sys.path.insert(0, TESTS_DIR)
    import _replay
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    case_dir = os.path.join(CORPUS, "textbook_workbook", "r6c10cheonjae")
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


def test_round6_c10_plan_anchor():
    """후보⑩ 골든 재플랜 — 조건 항목/화자 라벨/영단어 강등이 스타일에
    반영되고 전 단락 보존 (GH 1 제거 제외)."""
    from collections import Counter
    from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds
    golden = os.path.join(CORPUS, "textbook_workbook", "r6c10cheonjae",
                          "golden", "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    st3 = c["steps"]["step3"]
    ensure_step3_kinds(st3)
    plan = steps_to_plan(c["steps"], workbook_type="교과서")
    fl = [f for f in plan["flows"] if f["step"] == "step3"][0]
    paras = [p for u in fl["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    n_src = sum(len(it["paragraphs"])
                for it in (st3.get("normal") or []) + (st3.get("short") or []))
    assert len(paras) == n_src - 1 == 852       # GH 1 제거 외 전 단락 보존
    tally = Counter(p["s"].split(">")[-1].strip() for p in paras)
    assert tally["조건 올림포스"] >= 115        # D3 — 조건 항목 구제
    assert tally["영단어"] == 1                 # D2 — 각주 어휘(*extensively)만
    def style_of(prefix):
        for p in paras:
            if p["t"].strip().startswith(prefix):
                return p["s"]
        raise AssertionError(f"단락 없음: {prefix}")
    assert "지문" in style_of("Minji:")
    assert "지문" in style_of("A: 노란색 코트")
    assert "조건" in style_of("1. 위 단어들을 어형변화")
    assert "조건" in style_of("반드시 빈칸은 주어진 철자로")


def test_round6_c07_plan_anchor():
    """후보⑦ 골든 재플랜 — [서술형 2] 해요체 발문이 번호 스타일 (D1)."""
    from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds
    golden = os.path.join(CORPUS, "ebs_workbook_v2", "r6c07rp17",
                          "golden", "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    ensure_step3_kinds(c["steps"]["step3"])
    plan = steps_to_plan(c["steps"], workbook_type="EBS")
    fl = [f for f in plan["flows"] if f["step"] == "step3"][0]
    paras = [p for u in fl["units"]
             for p in (u["paras"] if isinstance(u, dict) else u)]
    seyo = [p for p in paras if p["t"].startswith("[서술형 2]")]
    assert seyo and all("번호" in p["s"] for p in seyo)
    assert len(paras) == 376


def test_gates_false_positive_free_on_known_good_dumps():
    """기존 양품 덤프에 새 게이트 false-critical 0 (파일 존재 시)."""
    good = [
        "data_corpus/round2/c12_wb2/out/job/typeset_dump.json",
        "data_corpus/round3/c13_ybm/out/job/typeset_dump.json",
        "data_corpus/round4/c03_tb_essay/out/job/typeset_dump.json",
        "data_corpus/round4/c06_rp_cr/out/job/typeset_dump.json",
        "data_corpus/tbwb_engine_e2e/20a3838b/job/typeset_dump.json",
        "data_corpus/wb_sero_e2e/e79f8af9/job/typeset_dump.json",
    ]
    for rel in good:
        path = os.path.join(REPO, rel)
        if not os.path.isfile(path):
            continue
        d = json.load(open(path, encoding="utf-8"))
        rep = inspect_workbook_finish(None, None, d)
        for key in ("발문스타일", "영단어오분류", "조건항목"):
            assert not [c for c in rep["critical"] if key in c], (rel, key)


def test_gates_catch_latent_defects_in_prior_outputs():
    """W16 게이트가 이전 라운드 실출력의 잠복 결함을 잡는다 (검출 실증 —
    c04 안내문 필드 영단어 27 + c05 ⦁조건 5. 수리 전 실덤프에서 추출한
    보존 픽스처 — 재조판 후에도 검출 근거 유지)."""
    cases = {
        "fixtures/w16_defect_dumps/c04_pre_fix.json": ("word_style_bad", 27),
        "fixtures/w16_defect_dumps/c05_pre_fix.json": ("cond_item_miss", 5),
    }
    for rel, (key, expected) in cases.items():
        path = os.path.join(TESTS_DIR, rel)
        d = json.load(open(path, encoding="utf-8"))
        rep = inspect_workbook_finish(None, None, d)
        assert rep["stats"][key] >= expected, (rel, key, rep["stats"][key])
