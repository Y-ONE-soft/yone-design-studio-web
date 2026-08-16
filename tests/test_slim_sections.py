# -*- coding: utf-8 -*-
"""워크북 슬림 변환 — 섹션 액션/마커 교체/조판 시점 후처리 계약 테스트.

수동 Slim_Ver / Slim_Merge / Slim_Merge2 3종을 한 엔진으로 통합하면서
새로 생긴 계약을 고정한다:
  - 섹션 액션 3종(delete/merge_half/merge_stack) 해석 규칙
  - 구 2모드(ox/arrange) 하위호환
  - 단원 마커 교체(어법 선택 → 어법 수정)
  - 조판 시점 후처리(core/slim_post)는 요청이 없으면 완전 no-op
  - JSX 계약 (ES3 + 판권 페이지 가드 + 삽입 방식)
"""

import json
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from core import slim_post                                    # noqa: E402
from engines.slim_merge.engine import SlimMergeEngine          # noqa: E402


@pytest.fixture()
def cfg():
    with open(os.path.join(REPO, "engines", "slim_merge", "config.json"),
              encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture()
def eng():
    return SlimMergeEngine()


# ── 섹션 액션 해석 ──────────────────────────────────────────────────────

def test_preset_expands_to_three_actions(eng, cfg):
    """광문고 프리셋 = 삭제 5 + 반쪽 1 + 적층 1."""
    acts = eng._resolve_actions({"preset": "gwangmun"}, cfg, lambda m: None)
    assert acts["delete"] == ["어휘 선택 2", "본문 정리", "내용 종합",
                              "어법 O/X", "빈칸 어법"]
    assert acts["merge_half"] == ["본문 O/X"]
    assert acts["merge_stack"] == ["문장 배열"]


def test_manual_sections_union_with_preset(eng, cfg):
    """개별 지정은 프리셋을 덮어쓰지 않고 합집합 — 중복은 한 번만."""
    acts = eng._resolve_actions(
        {"preset": "gwangmun", "delete_sections": "영작 배열, 본문 정리"},
        cfg, lambda m: None)
    assert acts["delete"].count("본문 정리") == 1
    assert "영작 배열" in acts["delete"]


def test_legacy_modes_still_work(eng, cfg):
    """구 2모드(ox/arrange)는 액션으로 합류 — 기존 호출자 무영향."""
    ox = eng._resolve_actions({"merge_mode": "ox"}, cfg, lambda m: None)
    assert ox["merge_half"] == ["본문 O/X"] and not ox["delete"]
    arr = eng._resolve_actions({"merge_mode": "arrange"}, cfg, lambda m: None)
    assert arr["merge_stack"] == ["문장 배열"] and not arr["merge_half"]


def test_unknown_preset_and_mode_raise(eng, cfg):
    with pytest.raises(ValueError):
        eng._resolve_actions({"preset": "없는학교"}, cfg, lambda m: None)
    with pytest.raises(ValueError):
        eng._resolve_actions({"merge_mode": "없는모드"}, cfg, lambda m: None)


# ── 마커 교체 ───────────────────────────────────────────────────────────

def test_rename_markers_parsing(eng):
    assert eng._parse_renames("어법 선택>어법 수정") == {"어법 선택": "어법 수정"}
    assert eng._parse_renames("A>B, C>D") == {"A": "B", "C": "D"}
    assert eng._parse_renames("") == {}
    assert eng._parse_renames("구분자없음") == {}


def test_slim_post_rename_parsing_matches_engine(eng):
    """조판 시점 경로와 후처리 경로가 같은 규칙을 써야 한다."""
    raw = "어법 선택>어법 수정, A>B"
    assert slim_post.parse_renames(raw) == eng._parse_renames(raw)


# ── 조판 시점 후처리 (no-op 보장) ───────────────────────────────────────

def test_postprocess_is_noop_without_request(tmp_path):
    """slim_*.txt 가 없으면 아무 것도 하지 않는다 (전 엔진 무영향)."""
    assert slim_post.wanted(str(tmp_path)) is False
    calls = []
    assert slim_post.run_slim_postprocess(
        None, str(tmp_path), calls.append) is None
    assert calls == []


def test_postprocess_wanted_on_rename_only(tmp_path):
    """마커 교체만 요청해도 후처리가 돌아야 한다 (섹션 액션 0개)."""
    (tmp_path / "slim_rename.txt").write_text("어법 선택>어법 수정",
                                              encoding="utf-8")
    assert slim_post.wanted(str(tmp_path)) is True


def test_postprocess_missing_indd_warns_not_raises(tmp_path):
    """대상 .indd 를 못 찾아도 조판 결과를 망치지 않고 경고만."""
    (tmp_path / "slim_preset.txt").write_text("gwangmun", encoding="utf-8")
    logs = []
    assert slim_post.run_slim_postprocess(
        None, str(tmp_path), logs.append) is None
    assert any("대상 .indd" in m for m in logs)


def test_form_keys_are_saved_by_route():
    """routes/typeset.py 가 slim_* 폼 키를 job_dir 에 저장해야 한다."""
    src = open(os.path.join(REPO, "routes", "typeset.py"),
               encoding="utf-8").read()
    assert "FORM_KEYS as _SLIM_KEYS" in src
    assert "core.slim_post" in src


def test_pipeline_calls_postprocess_after_typeset():
    """조판 완료 직후에 후처리 훅이 있어야 한다 (verify 이전)."""
    src = open(os.path.join(REPO, "core", "pipeline.py"),
               encoding="utf-8").read()
    assert "run_slim_postprocess" in src
    assert src.index("run_slim_postprocess") < src.index('stage = "verify"')


# ── JSX 계약 ────────────────────────────────────────────────────────────

@pytest.fixture()
def jsx():
    return open(os.path.join(REPO, "engines", "slim_merge", "jsx", "run.jsx"),
                encoding="utf-8").read()


def _code_only(src):
    """주석(//)을 뗀 코드만 — 금지 패턴 검사가 설명 주석에 걸리지 않도록."""
    return "\n".join(line.split("//")[0] for line in src.split("\n"))


def test_jsx_is_es3(jsx):
    """ExtendScript ES3 — let/const/화살표/템플릿 리터럴 금지."""
    body = jsx.split("\n")
    for i, line in enumerate(body, 1):
        code = line.split("//")[0]
        assert " let " not in code, f"let at line {i}"
        assert " const " not in code, f"const at line {i}"
        assert "=>" not in code, f"arrow at line {i}"
        assert "`" not in code, f"template literal at line {i}"


def test_jsx_reads_action_settings(jsx):
    for key in ("delete_sections", "merge_half_sections",
                "merge_stack_sections", "rename_markers",
                "fix_divider_spreads", "memo_master"):
        assert key in jsx, f"settings.{key} 미사용"


def test_jsx_divider_guard_excludes_credit_page(jsx):
    """판권(크레딧) 페이지는 [없음] 마스터지만 왼쪽이 정상 —
    간지로 오인해 메모를 끼우면 파리티가 되레 깨진다."""
    assert "function isDividerRun" in jsx
    body = jsx.split("function isDividerRun")[1].split("\n    }")[0]
    assert "textFrames.length > 0" in body
    # 런 선택과 검증 양쪽에서 가드를 써야 한다
    assert jsx.count("isDividerRun(") >= 3


def test_jsx_inserts_memo_by_move_not_add_before(jsx):
    """pages.add(BEFORE, ...)는 facing pages 셔플로 한 칸 앞(콘텐츠 사이)에
    끼어든다 — AT_END 추가 후 move(BEFORE)가 페이지 단위로 정확하다."""
    body = jsx.split("function fixDividerSpreads")[1]
    assert "LocationOptions.AT_END" in body
    assert "move(LocationOptions.BEFORE" in body
    assert "LocationOptions.BEFORE, refPage)" not in body.split("add(")[1][:80]


def test_jsx_thread_split_uses_duplicate_not_null(jsx):
    """스레드 해제는 Adobe SplitStory 방식 — nextTextFrame=null 금지
    (뒤 프레임 텍스트를 앞 프레임 오버셋으로 빨아들인다)."""
    code = _code_only(jsx)
    assert "nextTextFrame" not in code
    assert "duplicate()" in code


def test_jsx_opens_by_path_not_active_document(jsx):
    """사용자가 창을 전환해도 대상이 바뀌면 안 된다."""
    code = _code_only(jsx)
    assert "activeDocument" not in code
    assert "app.open(srcFile" in code


def test_config_sections_cover_preset_markers(cfg):
    """프리셋이 가리키는 마커는 UI 섹션 목록에 전부 있어야 한다."""
    known = {s["marker"] for s in cfg["sections"]}
    for key, preset in cfg["presets"].items():
        for act in ("delete", "merge_half", "merge_stack"):
            for marker in preset.get(act, []):
                assert marker in known, f"{key}.{act}: {marker} 미등재"


def test_slim_opt_included_in_workbook_templates():
    """워크북 계열 조판 페이지에 슬림 옵션이 노출돼야 한다."""
    tpl_dir = os.path.join(REPO, "templates")
    for name in ("typeset_workbook_v2.html", "typeset_ebs_workbook_v2.html",
                 "typeset_suneungteukgang_workbook_v2.html",
                 "typeset_textbook_workbook_v2.html"):
        src = open(os.path.join(tpl_dir, name), encoding="utf-8").read()
        assert "_slim_opt.html" in src, f"{name} 에 슬림 옵션 include 없음"
