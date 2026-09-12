"""W13 — 품질 루프 3라운드 결함 가드 (미학습 원고 3종 실증 결함의 재발 방지).

투입 원고 (docs/원고_구조_인벤토리.md 다양성 후보):
  후보⑬ 공통영어1 YBM(김) Project 1 워크북 (PROJECT N-본문N 헤더)
  후보⑮ 공통영어1 능률(민) SL2 워크북 ([본문 N]+정답해설 통합본 혼재 폴더)
  후보⑤  고1 25년 10월 모의고사 워크북 (STEP1~3 정답 hwpx 포함 전체 업로드)

결함→가드 매핑:
  D1 ANS_PATTERNS[1] 파국적 백트래킹 — 긴 밑줄 답란 run(90자+) 뒤 영문이
     이어지는 단락에서 classify가 수 분+ 소요 (c05 24번 실증, 파서 행처럼
     보임) → 비모호 선형 패턴으로 교체 (수용 언어 동일)
  D2 hwp 밑줄 추출 pos_ul dict가 단락마다 ~100만 엔트리 생성 — 파일당
     4~5초, 25파일 원고에서 침묵 지연 (c05 실증) → 구간 역순 스캔
     (동작 byte-identical — 실파일 8종 대조 완료)
  D3 정답/답지/해설 파일의 Step3 라우팅 차단 (c05 실증:
     "…STEP3_정답.hwpx" 교사용 정답이 Step3 원고 폴더로 들어감)
  D4 게이트 G9 [미사용원고] — 업로드 원고가 어느 스텝에도 소비되지 않고
     조용히 무시됨 (c15 실증: "…STEP 2_박소원 완료.hwpx" 통합본 3종)
  D5 textbook 완제품 op 확산 — 모의고사 잔재 지문번호 프레임 17종 +
     잔여 페이지 200개+ (c13/c15 실조판 게이트 warning 실증, v1 실물
     SL2는 78페이지 = v1 16.5가 삭제하던 것)
  D6 상하반전 pos 힌트 — 기본 STEP_MAP(본가+textbook) rank 선택이
     [원본]워크북_C에서 step2_a1(상단)/btm(하단)을 뒤바꿈 (c13/c15/c05
     실기 + v1 실물 SL2 기하(a1 top=31/btm=164) 실증)
"""
import json
import os
import re
import signal
import time

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus")


# ── D1: ANS_PATTERNS[1] 파국적 백트래킹 차단 ────────────────────────────────

def test_ans_pattern_linear_on_pathological_input():
    from core.structure import rules as R
    pat = R.ANS_PATTERNS[1]
    t = ("(1)" + "_" * 95
         + " the aggregation of dust and gas particles to proto-stars (2)"
         + "_" * 95)
    t0 = time.time()
    assert pat.search(t) is None
    assert time.time() - t0 < 0.5, "파국적 백트래킹 재발"
    # 밑줄 반복 + 비매칭 꼬리의 최악 케이스도 즉시 결정
    t2 = ("___ " * 40) + "x"
    t0 = time.time()
    assert pat.search(t2) is None
    assert time.time() - t0 < 0.5


def test_ans_pattern_language_unchanged():
    from core.structure import rules as R
    pat = R.ANS_PATTERNS[1]
    for good in ("(1) ___ → ___", "_____", "(1)______",
                 "   ______  ______  ", "(1) ______ → ______ "):
        assert pat.search(good), good
    # 옛 패턴도 비매칭이던 형태 (run 사이 구분자는 공백/화살표만)
    for bad in ("(1) ___ abc", "hello", "__", "___a___",
                "1. ______ : ______"):
        assert not pat.search(bad), bad


def test_ans_pattern_equivalent_to_legacy():
    """옛 패턴(짧은 입력에선 안전)과 수용 언어 동일 — 무작위 대조."""
    import random
    from core.structure import rules as R
    old = re.compile(
        "^[\\s\\d()（）\\u00a0:：→.\\-]*(?:_{3,}[\\s\\u00a0→]*)+$")
    new = R.ANS_PATTERNS[1]
    rng = random.Random(42)
    alpha = list("_()（）0129→:：.-aZ한 \t") + ["_"] * 6 + [" "] * 3 \
        + [" "] * 3
    # W39 결함 4: 새 패턴은 꼬리 구두점("____." — 6b66b750 실증)만 추가
    # 수용 — 옛 수용분 전부 수용(무회귀) + 추가분은 꼬리 [.,] 제거 시
    # 옛 패턴 수용 문자열뿐임을 대조.
    import re as _re
    strip_tail = _re.compile("[.,](?=[\\s\\u00a0]*$)")
    for _ in range(5000):
        s = "".join(rng.choice(alpha) for _ in range(rng.randint(0, 22)))
        if old.search(s):
            assert new.search(s), repr(s)
        elif new.search(s):
            assert old.search(strip_tail.sub("", s, count=1)), repr(s)


# ── D2: hwp 밑줄 추출 pos_ul 의미론 (dict 대체) ────────────────────────────

def _payload(text):
    return text.encode("utf-16-le")


def test_hwp_underline_lookup_semantics():
    """charshape 구간 lookup이 옛 dict(나중 쓰기 우선 + 미커버 기본값)와
    동일 — 비정렬/중첩 pair 포함."""
    import random
    from core.extract.extractors import _hwp_text_with_underline
    rng = random.Random(7)
    for _ in range(200):
        n = rng.randint(0, 5)
        pairs = [(rng.randint(0, 12), rng.randint(0, 4)) for _ in range(n)]
        ul_map = {i: bool(rng.getrandbits(1)) for i in range(5)}
        text = "abcdefghijklmn"[:rng.randint(1, 14)]
        got_t, got_runs = _hwp_text_with_underline(_payload(text), pairs,
                                                   ul_map)
        # 옛 dict 의미론 재현 (범위 캡 — 테스트에서만)
        pos_ul = {}
        for k in range(len(pairs)):
            e = pairs[k + 1][0] if k + 1 < len(pairs) else 40
            for p in range(pairs[k][0], e):
                pos_ul[p] = ul_map.get(pairs[k][1], False)
        assert got_t == text
        # run 재구성으로 위치별 ul 검증
        pos = 0
        cur_ul = False
        expect = []
        for ch in text:
            cur_ul = pos_ul.get(pos, cur_ul)
            expect.append(cur_ul)
            pos += 1
        got = []
        for r in got_runs:
            got.extend([r["ul"]] * len(r["t"]))
        assert got == expect, (pairs, ul_map, text)


def test_hwp_underline_fast_on_large_end():
    """마지막 pair end=999999가 더 이상 ~100만 엔트리를 만들지 않는다."""
    from core.extract.extractors import _hwp_text_with_underline
    text = "x" * 2000
    pairs = [(0, 1), (1000, 2)]
    t0 = time.time()
    for _ in range(50):
        _hwp_text_with_underline(_payload(text), pairs, {1: True, 2: False})
    assert time.time() - t0 < 2.0, "밑줄 추출 성능 회귀 (단락당 수십 ms)"


# ── D3: 정답/답지 파일 Step3 라우팅 차단 ────────────────────────────────────

def test_routes_to_step3_answer_guard():
    from engines.workbook_v2.engine import _routes_to_step3
    # 정답/답지/해설류 — 문항 패턴이 겹쳐도 라우팅 금지 (c05 실증)
    for f in ("고1_모의고사_25년_10월_STEP3_정답.hwpx",
              "Step3 해설.hwpx", "고1 25년 9월 20번 정답.hwp",
              "변형문제 답지.hwp"):
        assert not _routes_to_step3(f), f
    # 기존 라우팅 무회귀 (코퍼스 실명 포함)
    for f in ("Step3.hwpx", "Step3 실전문제.hwpx",
              "고1 25년 9월 41~42번.hwp", "1. 10-A 분석 스텝3.hwpx",
              "리딩파워 유형 (기본)-Unit 15- 123문제 [변형문제]-.hwp"):
        assert _routes_to_step3(f), f
    # 일반 스텝 파일은 루트
    assert not _routes_to_step3("Step2 A1 어법선택.docx")


# ── D4: 게이트 G9 미사용 업로드 원고 ────────────────────────────────────────

def _mk_uploads(tmp_path, names):
    up = tmp_path / "uploads"
    (up / "Step3").mkdir(parents=True)
    for n in names:
        p = up / n
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(b"x")
    return str(up)


def test_gate_g9_unused_uploads_classification(tmp_path):
    """c15 수리 전 상태 재현: 통합본 hwpx 3종이 어느 스텝에도 소비되지
    않는데 아무 보고가 없던 침묵 무시 → suspicious 경고."""
    from engines.workbook_v2.gate import (find_unused_uploads,
                                          inspect_workbook_finish)
    uploads = _mk_uploads(tmp_path, [
        "Step1 A1 어휘선택.docx",                      # 사용됨
        "Step1 C2 빈칸어휘 정답지.docx",               # 사용됨 (정답지 본)
        "Step1 C2 빈칸어휘.docx",                      # 짝 파일 → expected
        "Step2 C2 영작배열(서술형).hwpx",              # 사용됨
        "Step2 C2 영작배열.docx",                      # 짝 파일 → expected
        "공통영어1_YBM_STEP1_답지.hwpx",               # 답지 → expected
        "공통영어1_능률(민)_SL 2_본문1~5_STEP 2_박소원 완료.hwpx",  # 의심
        os.path.join("Step3", "고1 25년 9월 20번.hwp"),  # 번호 매칭 소비
    ])
    content = {"steps": {
        "step1_a1": {"filename": "Step1 A1 어휘선택.docx"},
        "step1_c2": {"filename": "Step1 C2 빈칸어휘 정답지.docx"},
        "step2_c2": {"filename": "Step2 C2 영작배열(서술형).hwpx"},
        "step3": {"normal": [{"question_num": "20"}], "short": []},
    }}
    expected, suspicious = find_unused_uploads(content, uploads)
    assert suspicious == ["공통영어1_능률(민)_SL 2_본문1~5_STEP 2_박소원 완료.hwpx"]
    assert "Step1 C2 빈칸어휘.docx" in expected
    assert "Step2 C2 영작배열.docx" in expected
    assert "공통영어1_YBM_STEP1_답지.hwpx" in expected

    plan = {"flows": [{"step": "step1_a1", "target": {},
                       "units": [[{"t": "x", "s": "P"}]]}]}
    dump = {"stories": [{"idx": 0, "overflow": False,
                         "paragraphs": [{"t": "x", "s": ""}]}]}
    rep = inspect_workbook_finish(content, plan, dump, uploads_dir=uploads)
    # 배치 A (W33): G9 suspicious는 critical 승격 — 반침묵(경고 무시) 금지
    assert any(c.startswith("[미사용원고]") for c in rep["critical"])
    assert not rep["ok"], "배치 A: G9 미사용원고는 critical (침묵 유실 금지)"


def test_gate_g9_silent_without_uploads_dir():
    """오프라인 플랜 테스트 호환 — uploads_dir 미지정이면 G9 미검사."""
    from engines.workbook_v2.gate import inspect_workbook_finish
    plan = {"flows": [{"step": "step1_a1", "target": {},
                       "units": [[{"t": "x", "s": "P"}]]}]}
    dump = {"stories": [{"idx": 0, "overflow": False,
                         "paragraphs": [{"t": "x", "s": ""}]}]}
    rep = inspect_workbook_finish({"steps": {}}, plan, dump)
    assert not any(w.startswith("[미사용원고]") for w in rep["warnings"])


def test_gate_g9_textbook_step3_route(tmp_path):
    """교과서 step3(textbook 항목) — 비정답 후보는 소비로 간주하고
    Step3 폴더의 정답류만 expected."""
    from engines.workbook_v2.gate import find_unused_uploads
    uploads = _mk_uploads(tmp_path, [
        os.path.join("Step3", "공통영어1 YBM(김은형) Project 1 Step 3.docx"),
        os.path.join("Step3", "Step3 정답해설.hwpx"),
    ])
    content = {"steps": {
        "step3": {"normal": [{"question_num": "textbook"}], "short": []},
    }}
    expected, suspicious = find_unused_uploads(content, uploads)
    assert suspicious == []
    assert expected == ["Step3 정답해설.hwpx"]


# ── D5: textbook 완제품 op 확산 ────────────────────────────────────────────

def test_textbook_plan_decorations_finish_ops(tmp_path):
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    job = tmp_path / "job"
    job.mkdir()
    (job / "subject.txt").write_text("공통영어1", encoding="utf-8")
    (job / "publisher.txt").write_text("공통영어1 YBM(김)", encoding="utf-8")
    (job / "lesson.txt").write_text("Project 1", encoding="utf-8")
    content = {"steps": {"step1_a1": {"paragraphs": [
        {"text": "[1]"}, {"text": "body"}, {"text": "[2]"},
        {"text": "body"}]}}}
    (job / "content.json").write_text(json.dumps(content, ensure_ascii=False),
                                      encoding="utf-8")
    deco = TextbookWorkbookV2Engine()._plan_decorations(str(job), {})
    # W24 r14 의미론 갱신: 교과서도 delete 모드 확산 (r14 c13 실기 검증)
    assert deco["page_cleanup"] == {"empty": "delete"}
    assert deco["passage_numbers"]["labels"] == ["1", "2"]
    assert deco["passage_numbers"]["steps"] == ["step1_c2", "step2_b1",
                                                "step2_c1"]
    # 기존 W8-1 데코 무회귀
    assert deco["divider"] == {"line1": "공통영어1 YBM(김)",
                               "line2": "Project 1"}
    assert deco["textbook_postprocess"] is True


def test_gate_g5_critical_when_pos_used():
    """G5 상하반전 — pos 힌트 사용 플랜에서 critical 승격 (W11 게이트의
    W13 확산 전제 재확인: c13/c15/c05 실기 + v1 실물 SL2 기하 실증)."""
    from engines.workbook_v2.gate import inspect_workbook_finish
    plan = {"flows": [
        {"step": "step2_a1", "target": {"pos": "top"},
         "units": [[{"t": "TOP-PROBE-A1", "s": "P"}]]},
        {"step": "step2_a1_btm", "target": {"pos": "bottom", "rank": 2},
         "units": [[{"t": "BTM-PROBE", "s": "P"}]]},
    ]}
    dump = {"stories": [
        {"idx": 0, "overflow": False, "pg": ["114"], "b": [164, 20],
         "paragraphs": [{"t": "TOP-PROBE-A1", "s": ""}]},
        {"idx": 1, "overflow": False, "pg": ["114"], "b": [31, 20],
         "paragraphs": [{"t": "BTM-PROBE", "s": ""}]},
    ], "stale_pages": []}
    rep = inspect_workbook_finish({"steps": {}}, plan, dump)
    assert any(c.startswith("[상하반전]") for c in rep["critical"])


# ── 코퍼스 레벨: 라운드3 케이스 ─────────────────────────────────────────────
# c05(모의고사 본가)는 tests/corpus/workbook_v2/r3c05mock의 manifest로
# test_parse_snapshot이 자동 리플레이한다. 교과서 2종은 parse가
# manuscript_folder 메타(GDrive 워크북 폴더의 로컬 재현)를 읽는 경로라
# 커스텀 리플레이로 골든 대조한다.

@pytest.mark.parametrize("case", ["r3c13ybm", "r3c15sl2"])
def test_round3_textbook_parse_snapshot(case, tmp_path):
    import _replay
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    case_dir = os.path.join(CORPUS, "textbook_workbook", case)
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
    assert diff is None, f"{case}: {diff}"


@pytest.mark.parametrize("case,expect_passages", [
    ("r3c13ybm", 2), ("r3c15sl2", 5)])
def test_round3_textbook_plan_counts(case, expect_passages):
    from engines.workbook_v2.plan import (steps_to_plan, ensure_step3_kinds,
                                          passage_labels)
    golden = os.path.join(CORPUS, "textbook_workbook", case, "golden",
                          "content.json")
    steps = json.load(open(golden, encoding="utf-8"))["steps"]
    ensure_step3_kinds(steps.get("step3"))
    plan = steps_to_plan(steps, workbook_type="교과서")
    by_step = {fl["step"]: len(fl["units"]) for fl in plan["flows"]}
    for key in ("step1_a1", "step1_a2", "step1_b2", "step1_c2",
                "step2_a1", "step2_a1_btm", "step2_b1", "step2_c1"):
        assert by_step[key] == expect_passages, (case, key, by_step)
    assert plan.get("warnings") == []
    assert len(passage_labels(steps)) == expect_passages


def test_round3_c05_golden_g9_and_step3():
    """c05 골든: STEP 정답 hwpx 3종이 스텝에 소비되지 않았고(step3 25문항
    = N번 파일만), G9가 이들을 expected-unused로 분류한다."""
    golden = os.path.join(CORPUS, "workbook_v2", "r3c05mock", "golden",
                          "content.json")
    c = json.load(open(golden, encoding="utf-8"))
    st3 = c["steps"]["step3"]
    assert st3["normal_count"] == 18 and st3["short_count"] == 7
    all_words = json.dumps(st3, ensure_ascii=False)
    from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds
    ensure_step3_kinds(st3)
    plan = steps_to_plan(c["steps"], workbook_type="모의고사")
    assert not plan["unsupported"]
    by_step = {fl["step"]: len(fl["units"]) for fl in plan["flows"]}
    # 2026-09-12: 짤지문 7묶음은 step3_short(별도 스토리)로 간다
    assert by_step["step3"] == 18 and by_step["step3_short"] == 7
    assert by_step["step2_a1"] == 18 and by_step["step2_a1_btm"] == 18


def test_textbook_plan_decorations_no_labels(tmp_path):
    """라벨을 못 뽑아도 passage_numbers는 clear-only 모드로 포함 (W14 D3:
    교과서 step3 페이지의 모의고사 문항번호 잔재 프레임 삭제 — 갱신은
    labels가 비면 실행기가 생략)."""
    from engines.textbook_workbook_v2.engine import TextbookWorkbookV2Engine
    job = tmp_path / "job"
    job.mkdir()
    for k in ("subject", "publisher", "lesson"):
        (job / f"{k}.txt").write_text("x", encoding="utf-8")
    deco = TextbookWorkbookV2Engine()._plan_decorations(str(job), {})
    # W24 r14 의미론 갱신: 교과서도 delete 모드 확산 (r14 c13 실기 검증)
    assert deco["page_cleanup"] == {"empty": "delete"}
    assert deco["passage_numbers"]["labels"] == []
    assert deco["passage_numbers"]["clear_steps"] == ["step3"]
