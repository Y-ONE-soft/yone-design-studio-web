"""배치 A (W33) — 파일명 라우팅 침묵 금지 (docs/인식지점_전수감사.md §9).

감사 리스크 1·2위 전환 검증:
  · 공용 라우터 route_step3 — 토큰 정규화('STEP 03'/'177 문제'/'변형 문항')
    + 기존 코퍼스 라우팅 파리티 (차이는 W18 D3 스텝1/2 가드 확산뿐)
  · canonical_step3_filename — '20번 (수정).docx'/'41-42번' 규격명 스테이징
    (감사 실증 #1: 완전 침묵 누락·textbook 폴백 오라우팅)
  · reconcile_step3 — 입력 파일 전수 ↔ 라우팅 결과 쌍방 대조, 미소비 [오류]
  · analysis_merge 월 폴더 숫자 토큰 매칭 (감사 실증 #6: 언더스코어 침묵 None)
"""
import json
import os
import re
import shutil
import unicodedata

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
CORPUS = os.path.join(TESTS_DIR, "corpus")


def _nfc(s):
    return unicodedata.normalize("NFC", s)


# ── 공용 라우터: 새 인식 (감사 실증 #4) ─────────────────────────────────────

def test_router_new_recognitions():
    from engines.workbook_v2.routing import route_step3
    # 감사 실증 #4 — 기존 라우터가 놓치던 토씨 변형
    for f in ("리딩파워 유형완성 기출문제-16강 CR-4(177 문제).hwp",  # 띄어쓴 문항수
              "고1_모의고사_STEP 03.hwpx",                        # 0패딩 스텝 토큰
              "고2 변형 문항 모음.hwp",                            # 변형 '문항'
              "STEP_03 실전.docx"):
        assert route_step3(f), f


def test_router_rejections_kept():
    from engines.workbook_v2.routing import route_step3
    # 기존 차단 관행 유지 (W13 정답류 / W14 비문항수 / W18 D3 스텝1/2 접두)
    for f in ("고1_모의고사_25년_10월_STEP3_정답.hwpx",
              "변형문제 정답지.hwp",
              "배재고 어휘 DAY23~25 문제.hwpx",
              "24년 3월 고2 문제.hwpx",
              "Step1 A1 어휘선택(2단계 34번).docx",
              "Step2 C2 영작배열(서술형).hwp"):
        assert not route_step3(f), f


def test_router_parity_on_corpus_filenames():
    """기존 코퍼스 전체 라우팅 diff 0 — 유일한 허용 차이는 스텝1/2 접두 가드
    (W18 D3 세로 가드의 전 계열 확산: 구 라우터의 'NN번' 오인 라우팅 차단)."""
    from engines.workbook_v2.routing import route_step3, _RE_STEP12_PREFIX, \
        _collapsed
    _pool = re.compile(r"변형\s*문제|\d문제")
    _ans = re.compile(r"정답|해설|답지|답안")

    def old(f):
        return (bool(re.search(r"(?:스텝|step)[\s_-]*3(?!\d)", f, re.I))
                or bool(re.search(r"\d+(?:\s*~\s*\d+)?\s*번", f))
                or (bool(_pool.search(f)) and not _ans.search(f))) \
            and not _ans.search(f)

    checked = 0
    for root, dirs, files in os.walk(CORPUS):
        if os.path.basename(root) != "inputs":
            continue
        for f in files:
            fn = _nfc(f)
            if fn.startswith("manuscripts_"):
                fn = fn[len("manuscripts_"):]
            fn = fn.strip()
            if not fn or fn.startswith("."):
                continue
            checked += 1
            new, prev = route_step3(fn), old(fn)
            if new != prev:
                # 허용된 개선: 스텝1/2 접두 가드 (True→False)
                assert prev and not new and \
                    _RE_STEP12_PREFIX.match(_collapsed(fn)), \
                    f"라우팅 파리티 위반: {fn} old={prev} new={new}"
    assert checked > 300


# ── 규격명 스테이징 (감사 실증 #1) ──────────────────────────────────────────

def test_canonical_step3_filename():
    from engines.workbook_v2.routing import canonical_step3_filename as canon
    # 괄호 주석 → 규격명 재구성
    assert canon("고1 25년 9월 20번 (수정).docx") == "고1 25년 9월 20번.docx"
    # 하이픈 범위 → 물결 정규화 (r9c20 코퍼스 실증: 41-42번 침묵 누락 회복)
    assert canon("2025년 고2 3월 변형문제 41-42번.hwpx") \
        == "2025년 고2 3월 변형문제 41~42번.hwpx"
    # 언더스코어 꼬리
    got = canon("20번_수정.hwpx")
    assert got and got.endswith("20번.hwpx")
    # 이미 규격 — 무변경 (diff 0)
    assert canon("고1 25년 9월 20번.docx") is None
    assert canon("고1 25년 9월 41~42번.docx") is None
    # 마더텅형 — v1 폴백이 소비, 무변경
    assert canon("15강 3번 250920.docx") is None
    # 번호 토큰 없음 / 비원고 확장자
    assert canon("리딩파워 유형완성 기출문제-11강(133문제).hwp") is None
    assert canon("고1 25년 9월 20번.pdf") is None


# ── 쌍방 대조 reconcile_step3 ───────────────────────────────────────────────

def _mk_step3(tmp_path, names):
    d = tmp_path / "Step3"
    d.mkdir(exist_ok=True)
    for n in names:
        (d / n).write_bytes(b"x")
    return str(d)


def _logs():
    lines = []
    return lines, lines.append


def test_reconcile_numbered_ok(tmp_path):
    from engines.workbook_v2.routing import reconcile_step3
    d = _mk_step3(tmp_path, ["고1 25년 9월 20번.hwp", "고1 25년 9월 41~42번.docx",
                             "step3_정답지.hwpx"])
    st3 = {"normal": [{"question_num": "20"}, {"question_num": "41~42"}],
           "short": []}
    lines, log = _logs()
    stats = reconcile_step3(d, st3, log, number_matching=True)
    assert stats["unrouted"] == []
    assert stats["excluded"] == ["step3_정답지.hwpx"]


def test_reconcile_unconsumed_raises(tmp_path):
    """감사 실증 #1 혼재 케이스 — 소비되지 않은 원고가 남으면 [오류]."""
    from engines.workbook_v2.routing import reconcile_step3
    d = _mk_step3(tmp_path, ["고1 25년 9월 20번.hwp",
                             "고1 25년 9월 21번 (수정).docx"])
    st3 = {"normal": [{"question_num": "20"}], "short": []}
    lines, log = _logs()
    with pytest.raises(ValueError) as ei:
        reconcile_step3(d, st3, log, number_matching=True)
    assert "[오류]" in str(ei.value) and "21" in str(ei.value)
    assert any("[오류]" in l for l in lines)      # 로그에도 남김 (침묵 금지)


def test_reconcile_duplicate_variant_raises(tmp_path):
    """규격명 충돌(같은 문항 2벌) — 침묵 대신 [오류]로 판정 위임."""
    from engines.workbook_v2.routing import reconcile_step3
    d = _mk_step3(tmp_path, ["고1 25년 9월 20번.hwp",
                             "고1 25년 9월 20번 (수정).hwp"])
    st3 = {"normal": [{"question_num": "20"}], "short": []}
    lines, log = _logs()
    with pytest.raises(ValueError) as ei:
        reconcile_step3(d, st3, log, number_matching=True)
    assert "중복 후보" in str(ei.value)


def test_reconcile_textbook_mode(tmp_path):
    from engines.workbook_v2.routing import reconcile_step3
    # 비정답 후보 전부 통합 소비 (수능특강/EBS 관행) — number_matching=False
    d = _mk_step3(tmp_path, ["2027 수능특강 13강.docx", "37번.hwpx",
                             "정답해설.hwpx"])
    st3 = {"normal": [{"question_num": "textbook"}], "short": []}
    lines, log = _logs()
    stats = reconcile_step3(d, st3, log, number_matching=False)
    assert stats["unrouted"] == []


def test_reconcile_textbook_number_matching_leftover(tmp_path):
    """모의고사 번호 매칭이 수행됐는데 'N번' 파일이 textbook 후보에서
    제외돼 침묵 누락되는 v1 관행(파서 1710행) — [오류]로 승격."""
    from engines.workbook_v2.routing import reconcile_step3
    d = _mk_step3(tmp_path, ["문제모음 MIXED.hwpx", "고1 25년 9월 20번.hwp"])
    st3 = {"normal": [{"question_num": "textbook"}], "short": []}
    lines, log = _logs()
    with pytest.raises(ValueError):
        reconcile_step3(d, st3, log, number_matching=True)


def test_reconcile_mixed_shadow_excluded(tmp_path):
    from engines.workbook_v2.routing import reconcile_step3
    d = _mk_step3(tmp_path, ["문제모음 MIXED.hwpx", "문제모음 구본.hwpx"])
    st3 = {"normal": [{"question_num": "textbook"}], "short": []}
    lines, log = _logs()
    stats = reconcile_step3(d, st3, log, number_matching=False)
    assert stats["unrouted"] == []
    assert "문제모음 구본.hwpx" in stats["excluded"]


def test_reconcile_sero_filename_based(tmp_path):
    from engines.workbook_v2.routing import reconcile_step3
    d = _mk_step3(tmp_path, ["15강 3번 250920.docx", "미인식 원고.hwp"])
    st3 = {"normal": [{"question_num": "3", "filename": "15강 3번 250920.docx"}],
           "short": []}
    lines, log = _logs()
    with pytest.raises(ValueError) as ei:
        reconcile_step3(d, st3, log)
    assert "미인식 원고.hwp" in str(ei.value)


def test_reconcile_missing_dir_noop(tmp_path):
    from engines.workbook_v2.routing import reconcile_step3
    stats = reconcile_step3(str(tmp_path / "없음"), None, lambda s: None)
    assert stats["files"] == 0


# ── 통합: v2 스테이징 → v1 파서 소비 (감사 실증 #1 재현) ────────────────────

def test_workbook_v2_variant_filename_consumed(tmp_path):
    """'21번 (수정).hwp'가 규격명 스테이징을 거쳐 문항 21로 소비된다
    (수정 전: 완전 침묵 누락 — 로그 0줄)."""
    import sys
    sys.path.insert(0, TESTS_DIR)
    import _replay
    from engines import registry

    src = os.path.join(CORPUS, "workbook_v2", "r10c22mock2503g1")
    case = tmp_path / "case"
    shutil.copytree(src, case)
    inputs = case / "inputs"
    old = inputs / "manuscripts_고1 25년 3월 21번.hwp"
    assert old.exists()
    old.rename(inputs / "manuscripts_고1 25년 3월 21번 (수정).hwp")

    engine = registry.get("workbook_v2")
    job = str(tmp_path / "job")
    produced = _replay.replay(engine, str(case), job)
    st3 = produced["steps"]["step3"]
    nums = {it["question_num"] for it in st3["normal"] + st3["short"]}
    assert "21" in nums, "규격명 스테이징 후에도 21번 미소비 — 침묵 누락"


# ── 월 폴더 숫자 토큰 매칭 (감사 실증 #6) ───────────────────────────────────

@pytest.mark.parametrize("folder", ["고1 25년 10월",      # 규정 (1차 경로)
                                    "고1_25년 10월",      # 언더스코어 (실증 #6)
                                    "고1 2025년 10월",    # 4자리 연도
                                    "고1-25년-10월 모의고사"])
def test_find_month_folder_variants(tmp_path, folder, monkeypatch):
    from engines.analysis_merge.engine import AnalysisMergeEngine
    base = tmp_path / "모의고사 작업"
    (base / "고1" / folder).mkdir(parents=True)
    (base / "고1" / "고1 24년 10월").mkdir(parents=True)   # 다른 연도 오탐 가드
    import engines.final.extractor as ext
    monkeypatch.setattr(
        ext, "list_manuscript_entries",
        lambda d, log=None: [(_nfc(n), os.path.join(d, n))
                             for n in sorted(os.listdir(d))]
        if os.path.isdir(d) else [])
    got = AnalysisMergeEngine._find_month_folder(str(base), 1, "25", "10")
    assert got and os.path.basename(got) == folder


def test_find_month_folder_absent_returns_none(tmp_path, monkeypatch):
    from engines.analysis_merge.engine import AnalysisMergeEngine
    base = tmp_path / "모의고사 작업"
    (base / "고1" / "고1 24년 10월").mkdir(parents=True)
    import engines.final.extractor as ext
    monkeypatch.setattr(
        ext, "list_manuscript_entries",
        lambda d, log=None: [(_nfc(n), os.path.join(d, n))
                             for n in sorted(os.listdir(d))]
        if os.path.isdir(d) else [])
    assert AnalysisMergeEngine._find_month_folder(
        str(base), 1, "25", "10") is None
