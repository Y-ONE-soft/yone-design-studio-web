"""suneungteukgang_workbook_v2 다중 강 통합(merge) — 오프라인 검증.

InDesign 없이: 라벨/소스 해석, 머지 설정·JSX 생성, stale 로그 제거,
검수 게이트(_gate_merge) 판정을 검증한다. 실기 머지는
scripts/e2e_engine_suneungteukgang_workbook_v2_merge.py.
"""
import json
import os
import time

import pytest

import engines.suneungteukgang_workbook_v2.engine as eng_mod
from engines.suneungteukgang_workbook_v2.engine import (
    SuneungteukgangWorkbookV2Engine, _MERGE_MARKER, _dedupe_path,
    _gate_merge, _latest_lesson_indd, _merged_label)


# ── 라벨 규칙 (v1 merge_lessons 파리티) ──────────────────────────────────────

def test_merged_label_rules():
    assert _merged_label(["21강", "22강"]) == "21강-22강"
    assert _merged_label(["21강", "22강", "23강", "24강"]) \
        == "21강-22강-23강-24강"
    # 5개 이상 → 처음-끝
    assert _merged_label(["21강", "22강", "23강", "24강", "25강"]) \
        == "21강-25강"
    # 동일 라벨 → 단일
    assert _merged_label(["27강", "27강"]) == "27강"
    # 공백 제거 ("Test 2" → "Test2")
    assert _merged_label(["27강", "Test 2"]) == "27강-Test2"


# ── 소스/출력 경로 해석 ──────────────────────────────────────────────────────

def test_latest_lesson_indd_prefers_recent(tmp_path):
    out = str(tmp_path)
    exact = os.path.join(out, "EBS_수능특강_27강_분석_v2.indd")
    copy2 = os.path.join(out, "EBS_수능특강_27강_분석_v2_2.indd")
    for p in (exact, copy2):
        with open(p, "wb") as f:
            f.write(b"x")
    old = time.time() - 1000
    os.utime(exact, (old, old))           # exact가 더 오래됨 → _2 선택
    assert _latest_lesson_indd(out, "27강", "분석") == copy2
    os.utime(exact, None)                 # exact가 최신 → exact 선택
    assert _latest_lesson_indd(out, "27강", "분석") == exact
    assert _latest_lesson_indd(out, "없는강", "분석") is None


def test_dedupe_path(tmp_path):
    p = str(tmp_path / "EBS_수능특강_21강-22강_분석_v2.indd")
    assert _dedupe_path(p) == p
    with open(p, "wb") as f:
        f.write(b"x")
    assert _dedupe_path(p).endswith("_v2_2.indd")


# ── 검수 게이트 (_gate_merge 순수 함수) ──────────────────────────────────────

def _mk_stats(paras_by_src, spreads_by_src, merged_spreads, dup_fail=0):
    return {
        "sources": [{"path": f"/x/src{i}.indd", "spreads": sp,
                     "pages": sp * 2, "paras": paras}
                    for i, (paras, sp)
                    in enumerate(zip(paras_by_src, spreads_by_src))],
        "merged": {"path": "/x/merged.indd",
                   "spreads": merged_spreads,
                   "pages": merged_spreads * 2},
        "dup_fail": dup_fail,
    }


def _mk_dump(texts, overflow=0):
    stories = [{"idx": i, "overflow": i < overflow,
                "paragraphs": [{"t": t, "s": "본문"}]}
               for i, t in enumerate(texts)]
    return {"stories": stories, "overflow_stories": overflow}


def test_gate_merge_ok_with_overflow_warning_only():
    stats = _mk_stats([["alpha bravo charlie"], ["delta echo foxtrot"]],
                      [6, 6], 12)
    dump = _mk_dump(["alpha bravo charlie", "delta echo foxtrot"],
                    overflow=1)
    ok, warnings, info = _gate_merge(stats, dump,
                                     ["/x/src0.indd", "/x/src1.indd"])
    assert ok is True                      # 오버플로우는 경고일 뿐
    assert any("오버플로우" in w for w in warnings)
    assert info == {"spreads": 12, "pages": 24, "overflow": 1, "lessons": 2}


def test_gate_merge_detects_missing_words():
    stats = _mk_stats([["alpha bravo charlie"], ["delta echo foxtrot"]],
                      [6, 6], 12)
    dump = _mk_dump(["alpha bravo charlie"])   # 두 번째 강 내용 증발
    ok, warnings, _ = _gate_merge(stats, dump,
                                  ["/x/src0.indd", "/x/src1.indd"])
    assert ok is False
    assert any("내용누락" in w and "src1.indd" in w for w in warnings)


def test_gate_merge_detects_spread_mismatch_and_dup_fail():
    stats = _mk_stats([["alpha bravo"], ["delta echo"]], [6, 6], 11,
                      dup_fail=1)
    dump = _mk_dump(["alpha bravo", "delta echo"])
    ok, warnings, _ = _gate_merge(stats, dump,
                                  ["/x/src0.indd", "/x/src1.indd"])
    assert ok is False
    assert any("스프레드 수 불일치" in w for w in warnings)
    assert any("duplicate 실패" in w for w in warnings)


def test_gate_merge_detects_source_count_mismatch():
    stats = _mk_stats([["alpha bravo"]], [6], 6)   # 소스 1개만 기록됨
    dump = _mk_dump(["alpha bravo"])
    ok, warnings, _ = _gate_merge(stats, dump,
                                  ["/x/src0.indd", "/x/src1.indd"])
    assert ok is False
    assert any("소스 수 불일치" in w for w in warnings)


def test_gate_merge_typo_normalization():
    """곡선따옴표 등 타이포 정규화 후 대조 (_norm_typo 필수 — 핸드북)."""
    stats = _mk_stats([["it’s a “curly” test-word"]], [3], 3)
    dump = _mk_dump(["it's a \"curly\" test-word"])
    ok, warnings, _ = _gate_merge(stats, dump, ["/x/src0.indd"])
    assert ok is True
    assert not any("내용누락" in w for w in warnings)


# ── merge_lessons 흐름 (run_jsx/dump_indd 모킹) ─────────────────────────────

def _touch(path, content=b"INDD"):
    with open(path, "wb") as f:
        f.write(content)


@pytest.fixture()
def out_dir(tmp_path, monkeypatch):
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(eng_mod, "_load_v1_config",
                        lambda: {"indd_output_dir": str(out)})
    return str(out)


def test_merge_lessons_rejects_single_lesson(out_dir):
    res = SuneungteukgangWorkbookV2Engine.merge_lessons(["21강"],
                                                        lambda m: None)
    assert res["analysis"] is None and res["problem"] is None
    assert any("2개 미만" in e for e in res["errors"])


def test_merge_lessons_missing_sources_error(out_dir, monkeypatch):
    called = []
    import core.indesign.runner as runner
    monkeypatch.setattr(runner, "run_jsx",
                        lambda *a, **k: called.append(a))
    res = SuneungteukgangWorkbookV2Engine.merge_lessons(
        ["21강", "22강"], lambda m: None)
    assert res["analysis"] is None and res["problem"] is None
    assert len(res["errors"]) == 2          # 분석/문제 각각 누락 보고
    assert all("원본 indd 누락" in e for e in res["errors"])
    assert not called                       # InDesign 실행 자체를 안 함


def test_merge_lessons_full_flow_mocked(out_dir, monkeypatch):
    """정상 흐름: 설정/JSX 생성 → run_jsx(마커/로그) → stats/dump 게이트."""
    # 강별 v2 산출물 심기 (v2 파일명 규칙 — _N 사본 포함)
    for short in ("21강", "22강"):
        for tok in ("분석", "문제"):
            _touch(os.path.join(out_dir,
                                f"EBS_수능특강_{short}_{tok}_v2.indd"))
    _touch(os.path.join(out_dir, "EBS_수능특강_21강_분석_v2_2.indd"))
    _old = time.time() - 1000               # mtime 동률 방지 — _2가 확실히 최신
    os.utime(os.path.join(out_dir, "EBS_수능특강_21강_분석_v2.indd"),
             (_old, _old))

    # stale 로그/스탯 심기 (제거 검증 — stale 완료마커 함정)
    stale_log = os.path.join(out_dir, "_merge_분석_v2_로그.txt")
    stale_stats = os.path.join(out_dir, "_merge_분석_v2_stats.json")
    with open(stale_log, "w", encoding="utf-8") as f:
        f.write(_MERGE_MARKER + "\n")
    with open(stale_stats, "w", encoding="utf-8") as f:
        f.write("{}")

    runs = []

    def fake_run_jsx(jsx_path, log, poll_log_path=None, timeout=None,
                     completion_marker=None, stall_limit=None):
        assert not os.path.exists(poll_log_path), "stale 머지 로그 미삭제"
        jsx_src = open(jsx_path, encoding="utf-8").read()
        assert "function wlog" in jsx_src            # lib.jsxinc concat
        assert _MERGE_MARKER in jsx_src
        # 설정 JSON 경로가 치환돼 있고 내용이 절대경로
        settings_path = jsx_path.replace(".jsx", ".settings.json")
        assert os.path.basename(settings_path) in jsx_src
        m_settings = json.load(open(settings_path, encoding="utf-8"))
        assert all(os.path.isabs(p) for p in m_settings["sources"])
        assert os.path.isabs(m_settings["merged"])
        assert m_settings["merged"].endswith("_v2.indd")
        if "분석" in os.path.basename(jsx_path):
            # 최신 사본(_2) 선택 확인 (21강 분석은 _2가 최신)
            assert m_settings["sources"][0].endswith("_v2_2.indd")
        # JSX 효과 시뮬레이션: 통합본 + stats 생성
        _touch(m_settings["merged"])
        stats = _mk_stats([["alpha bravo"], ["delta echo"]], [6, 6], 12)
        with open(m_settings["stats"], "w", encoding="utf-8") as f:
            json.dump(stats, f)
        runs.append({"jsx": jsx_path, "marker": completion_marker,
                     "stall": stall_limit, "poll": poll_log_path})

    def fake_dump(indd_path, out_json, log, timeout=600):
        assert os.path.isabs(indd_path) and indd_path.endswith("_v2.indd")
        return _mk_dump(["alpha bravo", "delta echo"])

    import core.indesign.runner as runner
    import core.inspect as inspect_mod
    monkeypatch.setattr(runner, "run_jsx", fake_run_jsx)
    monkeypatch.setattr(inspect_mod, "dump_indd", fake_dump)

    logs = []
    res = SuneungteukgangWorkbookV2Engine.merge_lessons(
        ["21강", "22강"], logs.append)

    assert res["errors"] == []
    assert os.path.basename(res["analysis"]) \
        == "EBS_수능특강_21강-22강_분석_v2.indd"
    assert os.path.basename(res["problem"]) \
        == "EBS_수능특강_21강-22강_문제_v2.indd"
    assert res["verify"]["analysis"]["ok"] is True
    assert res["verify"]["problem"]["ok"] is True
    assert res["verify"]["analysis"]["spreads"] == 12
    assert len(runs) == 2
    assert all(r["marker"] == _MERGE_MARKER for r in runs)
    assert all(r["stall"] == 900 for r in runs)
    assert all(r["poll"] and os.path.isabs(r["poll"]) for r in runs)


def test_merge_lessons_gate_failure_reported(out_dir, monkeypatch):
    """게이트 실패(내용 누락) 시 결과 경로 대신 오류로 보고."""
    for short in ("21강", "22강"):
        for tok in ("분석", "문제"):
            _touch(os.path.join(out_dir,
                                f"EBS_수능특강_{short}_{tok}_v2.indd"))

    def fake_run_jsx(jsx_path, log, poll_log_path=None, timeout=None,
                     completion_marker=None, stall_limit=None):
        m_settings = json.load(open(
            jsx_path.replace(".jsx", ".settings.json"), encoding="utf-8"))
        _touch(m_settings["merged"])
        stats = _mk_stats([["alpha bravo"], ["delta echo"]], [6, 6], 12)
        with open(m_settings["stats"], "w", encoding="utf-8") as f:
            json.dump(stats, f)

    import core.indesign.runner as runner
    import core.inspect as inspect_mod
    monkeypatch.setattr(runner, "run_jsx", fake_run_jsx)
    monkeypatch.setattr(inspect_mod, "dump_indd",
                        lambda *a, **k: _mk_dump(["alpha bravo"]))  # 누락

    res = SuneungteukgangWorkbookV2Engine.merge_lessons(
        ["21강", "22강"], lambda m: None)
    assert res["analysis"] is None and res["problem"] is None
    assert all("검수 게이트 실패" in e for e in res["errors"])
    assert res["verify"]["analysis"]["ok"] is False


# ── merge JSX 본문 자체 가드 (ES3/철칙) ─────────────────────────────────────

def test_merge_body_jsx_es3_and_conventions(tmp_path):
    from core.indesign.jsxbuild import build_jsx
    body = eng_mod._MERGE_BODY
    assert os.path.isfile(body)
    out = build_jsx(body, {"__MERGE_SETTINGS_PATH__": "/tmp/한글 경로.json"},
                    log_path="/tmp/merge.log",
                    out_path=str(tmp_path / "built.jsx"))
    src = open(out, encoding="utf-8").read()
    for banned in ("=>", "let ", "const ", "`"):
        assert banned not in src, f"ES3 금지 문법 발견: {banned}"
    assert "__MERGE_SETTINGS_PATH__" not in src        # 치환 완료
    assert "everyItem().getElements()" in src          # 컬렉션 캐시 패턴
    assert "LocationOptions.AT_END" in src             # v1 의미론
    assert _MERGE_MARKER in src
    assert 'var settingsPath = "/tmp/merge.log"' in src  # 러너 호환 헤더
