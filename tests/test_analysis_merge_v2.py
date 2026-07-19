# -*- coding: utf-8 -*-
"""분석본 결합 v2 오프라인 테스트 — 등록 정합 + 범위 파싱 + relink 맵 +
GDrive 복사 규칙 + verify 게이트 (InDesign 비의존, 합성 리포트)."""
import json
import os
import sys

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
sys.path.insert(0, REPO)

from engines.analysis_merge_v2.engine import AnalysisMergeV2Engine  # noqa: E402


@pytest.fixture
def engine():
    return AnalysisMergeV2Engine()


# ── 등록 정합 (registry / subjects / 템플릿 / JSX 계약) ──────────────────────

def test_registration_consistency():
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "analysis_merge_v2" in engines
    assert "analysis_merge" in engines          # v1 유지 (삭제 금지 규칙)

    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "analysis_merge_v2"' in raw
    assert '"engine_id": "analysis_merge"' in raw

    e = engines["analysis_merge_v2"]
    tpl = os.path.join(REPO, "templates", e.template_name)
    assert os.path.isfile(tpl)
    assert 'const MATERIAL_ID = "analysis_merge_v2"' in open(tpl, encoding="utf-8").read()

    jsx = os.path.join(REPO, "engines", "analysis_merge_v2", "jsx", "run.jsx")
    src = open(jsx, encoding="utf-8").read()
    assert "__SETTINGS_PATH__" in src           # 토큰 치환 계약
    assert "settings 로드 실패" in src           # 부트스트랩 try-catch
    assert "exportFile" not in src              # PDF export 제거 (스펙1·3)
    # 2026-07-19 배재1 실사고 봉합 계약:
    assert "overset_frames" in src              # 간지 기재 프레임 오버셋 게이트
    assert '"master:" + mkey' in src            # 마스터 프레임 오버플로우 스캔
    assert "keepSize" in src                    # 로컬 서식 캡처→복원 (오버셋 원인)


def test_upload_spec_slots(engine):
    keys = [s["key"] for s in engine.upload_spec["slots"]]
    assert keys == ["codes", "ranges", "ganji_school", "result_name"]


# ── 범위 파싱 (스펙5 입력) ───────────────────────────────────────────────────

def test_parse_ranges_json(engine):
    out = engine.parse_ranges(
        '[{"title":"고1 25년 3월 모의고사","detail":"39번, 40번"},'
        '{"title":"외부지문","detail":""}]')
    assert out == [
        {"title": "고1 25년 3월 모의고사", "detail": "39번, 40번"},
        {"title": "외부지문", "detail": ""},
    ]


def test_parse_ranges_lines(engine):
    out = engine.parse_ranges("영어I YBM(박) 2과 | Smart Economic\n고2 26년 6월")
    assert out == [
        {"title": "영어I YBM(박) 2과", "detail": "Smart Economic"},
        {"title": "고2 26년 6월", "detail": ""},
    ]


def test_parse_ranges_empty_and_error(engine):
    assert engine.parse_ranges("") == []
    with pytest.raises(ValueError):
        engine.parse_ranges("[{broken")


def test_default_result_name(engine):
    name = engine.default_result_name(
        "강동2", "3", [{"title": "26년6월", "detail": ""},
                       {"title": "YBM박2과", "detail": ""}])
    assert name == "강동2_분석본03(26년6월,YBM박2과)_내지"
    # 파일명 부적합 문자 제거 + 순번 폴백
    name2 = engine.default_result_name("명일1", "x", [{"title": "a/b:c", "detail": ""}])
    assert name2.startswith("명일1_분석본01(")
    assert "/" not in name2.split("_", 1)[1] and ":" not in name2


# ── 파일명 축약 규칙 (사용자 피드백 2026-07-19) ──────────────────────────────

def test_default_result_name_abbreviates_year_month(engine):
    """범위 제목 전체("고1 25년 3월 모의고사")가 아니라 "25년3월"만 —
    공백 없는 파일명."""
    name = engine.default_result_name(
        "배재1", "1",
        [{"title": "고1 25년 3월 모의고사", "detail": "39~40번"},
         {"title": "고1 22년 9월 모의고사", "detail": "20번"}])
    assert name == "배재1_분석본01(25년3월,22년9월)_내지"
    assert " " not in name


def test_summarize_range_title_variants(engine):
    # 년·월 추출 (선행 0 제거)
    assert engine.summarize_range_title("고1 25년 3월 모의고사") == "25년3월"
    assert engine.summarize_range_title("고2 22년 09월") == "22년9월"
    # 이미 축약된 기존 형식 하위호환
    assert engine.summarize_range_title("26년6월") == "26년6월"
    # 년·월 없는 제목(교과서 단원 등)은 공백만 제거
    assert engine.summarize_range_title("영어I YBM(박) 2과") == "영어IYBM(박)2과"
    assert engine.summarize_range_title("") == ""


def test_default_result_name_dedups_same_month(engine):
    name = engine.default_result_name(
        "명일1", "2",
        [{"title": "고1 25년 3월 모의고사", "detail": "1번"},
         {"title": "25년 3월", "detail": "2번"}])
    assert name == "명일1_분석본02(25년3월)_내지"


def test_sanitize_filename_strips_spaces(engine):
    assert engine.sanitize_filename("배재1_분석본01(고1 25년 3월)_내지") == \
        "배재1_분석본01(고125년3월)_내지"
    assert engine.sanitize_filename('a/b:c*d?e"f<g>h|i j') == "abcdefghij"
    assert engine.sanitize_filename("") == ""


# ── relink 맵 (스펙4) ────────────────────────────────────────────────────────

def test_build_relink_map_prunes_hidden_and_adds_nfd(engine, tmp_path):
    img = tmp_path / "이미지"
    (img / ".rsync-partial").mkdir(parents=True)
    (img / ".rsync-partial" / "깨진1P.ai").write_bytes(b"x")   # dot-dir — 제외
    (img / "1P.ai").write_bytes(b"ok")
    (img / "내지배경.jpg").write_bytes(b"ok")
    (img / "노트.txt").write_bytes(b"skip")                     # 확장자 제외
    mapping = engine.build_relink_map({"image_dirs": [str(img)]}, [])
    assert mapping.get("1P.ai", "").endswith("1P.ai")
    assert "깨진1P.ai" not in mapping
    assert "노트.txt" not in mapping
    # NFC 키 + NFD 키 동시 제공 (JSX link.name 정규화 대응)
    import unicodedata
    nfc = unicodedata.normalize("NFC", "내지배경.jpg")
    nfd = unicodedata.normalize("NFD", "내지배경.jpg")
    assert nfc in mapping and nfd in mapping


# ── GDrive 복사 규칙 (스펙3) ─────────────────────────────────────────────────

def test_copy_to_gdrive_creates_folders_and_never_overwrites(engine, tmp_path):
    local = tmp_path / "결과.indd"
    local.write_bytes(b"INDD" * 100)
    base = tmp_path / "분석본베이스"
    base.mkdir()

    dst1, err = engine._copy_to_gdrive(str(local), str(base), "26-2-중간",
                                       "명일1", None)
    assert err is None
    assert dst1 == str(base / "26-2-중간" / "명일1" / "결과.indd")
    assert os.path.isfile(dst1)

    # 동명 존재 → 덮어쓰지 않고 _2 접미 신규 생성
    dst2, err2 = engine._copy_to_gdrive(str(local), str(base), "26-2-중간",
                                        "명일1", None)
    assert err2 is None
    assert dst2 == str(base / "26-2-중간" / "명일1" / "결과_2.indd")
    assert os.path.isfile(dst1) and os.path.isfile(dst2)


def test_copy_to_gdrive_missing_base(engine, tmp_path):
    local = tmp_path / "결과.indd"
    local.write_bytes(b"x")
    dst, err = engine._copy_to_gdrive(str(local), str(tmp_path / "없음"),
                                      "26-2-중간", "명일1", None)
    assert dst is None and "기준 폴더 없음" in err


# ── verify 게이트 (스펙2·4·5·6) — 합성 job_dir ──────────────────────────────

GOOD_REPORT = {
    "unresolved": [],
    "geometry": {"max_drift_before_mm": 4.0, "max_residual_mm": 0.0,
                 "count_mismatch_pages": [], "pages": []},
    "links": {"total": 4, "missing_before": 1, "relinked": 1, "embedded": 1,
              "missing_after": 0, "unembedded_after": 0, "detail": []},
    "ganji": {"ok": True, "school": "2026 검증고2", "issue_num": "1",
              "range_pairs": 1},
    "overflow_pages": [],
}


def _make_job(tmp_path, report, with_indd=True):
    job = tmp_path / "job"
    out = job / "out"
    out.mkdir(parents=True)
    indd = out / "검증_분석본01(테스트)_내지.indd"
    if with_indd:
        indd.write_bytes(b"INDD" * 64)
    gbase = tmp_path / "gdrive"
    gbase.mkdir()
    settings = {
        "output_indd": str(indd),
        "output_dir": str(out),
        "report_path": str(job / "v2_report.json"),
        "log_path": str(job / "merge_log.txt"),
        "gdrive_save": {"base": str(gbase), "exam_period": "테스트기간",
                        "school_dir": "검증1"},
    }
    (job / ".settings.json").write_text(
        json.dumps(settings, ensure_ascii=False), encoding="utf-8")
    if report is not None:
        (job / "v2_report.json").write_text(
            json.dumps(report, ensure_ascii=False), encoding="utf-8")
    return str(job), str(gbase)


def test_verify_all_gates_pass_copies_to_gdrive(engine, tmp_path):
    job, gbase = _make_job(tmp_path, GOOD_REPORT)
    res = engine.verify(job, lambda m: None)
    assert res["gates"] == {"codes_ok": True, "geometry_ok": True,
                            "links_ok": True, "ganji_ok": True,
                            "overflow_ok": True}
    assert res["ok"] is True
    assert res["gdrive_path"] and os.path.isfile(res["gdrive_path"])
    assert res["gdrive_path"].startswith(gbase)
    # 스펙1: 목업 핸드오프 차단 — pdf_path/pdf_paths 미반환
    assert "pdf_path" not in res and "pdf_paths" not in res


def test_verify_geometry_gate_blocks_gdrive(engine, tmp_path):
    bad = json.loads(json.dumps(GOOD_REPORT))
    bad["geometry"]["max_residual_mm"] = 2.0
    job, gbase = _make_job(tmp_path, bad)
    res = engine.verify(job, lambda m: None)
    assert res["gates"]["geometry_ok"] is False
    assert res["ok"] is False
    assert res["gdrive_path"] is None
    assert not os.listdir(gbase)                     # GDrive 미기록 (로컬 보존)
    assert any("드리프트" in w for w in res["warnings"])
    assert any("로컬 보존" in w for w in res["warnings"])


def test_verify_links_gate(engine, tmp_path):
    bad = json.loads(json.dumps(GOOD_REPORT))
    bad["links"]["unembedded_after"] = 2
    job, _ = _make_job(tmp_path, bad)
    res = engine.verify(job, lambda m: None)
    assert res["gates"]["links_ok"] is False and res["ok"] is False


def test_verify_ganji_gate(engine, tmp_path):
    bad = json.loads(json.dumps(GOOD_REPORT))
    bad["ganji"] = {"ok": False, "error": "간지 마스터를 찾지 못함"}
    job, _ = _make_job(tmp_path, bad)
    res = engine.verify(job, lambda m: None)
    assert res["gates"]["ganji_ok"] is False and res["ok"] is False


def test_verify_ganji_overset_blocks_gdrive(engine, tmp_path):
    """간지 기재 프레임 오버셋(2026-07-19 배재1 실사고)이 게이트에 잡혀
    GDrive 저장이 보류되는지 — JSX가 남기는 리포트 형태 그대로 검증."""
    bad = json.loads(json.dumps(GOOD_REPORT))
    bad["ganji"] = {"ok": False,
                    "error": "기재 프레임 오버셋: 간지 학교명(챕터_숫자)",
                    "overset_frames": ["간지 학교명(챕터_숫자)"]}
    job, gbase = _make_job(tmp_path, bad)
    res = engine.verify(job, lambda m: None)
    assert res["gates"]["ganji_ok"] is False and res["ok"] is False
    assert res["gdrive_path"] is None and not os.listdir(gbase)
    assert any("오버셋" in w for w in res["warnings"])


def test_verify_master_overflow_blocks(engine, tmp_path):
    """마스터 프레임 오버플로우("master:간지-마스터")도 오버플로우 게이트가
    잡는지 — 스캔 확장 계약."""
    bad = json.loads(json.dumps(GOOD_REPORT))
    bad["overflow_pages"] = ["master:간지-마스터"]
    job, _ = _make_job(tmp_path, bad)
    res = engine.verify(job, lambda m: None)
    assert res["gates"]["overflow_ok"] is False and res["ok"] is False


def test_verify_overflow_and_unresolved_gates(engine, tmp_path):
    bad = json.loads(json.dumps(GOOD_REPORT))
    bad["overflow_pages"] = ["3"]
    bad["unresolved"] = ["250633"]
    job, _ = _make_job(tmp_path, bad)
    res = engine.verify(job, lambda m: None)
    assert res["gates"]["overflow_ok"] is False
    assert res["gates"]["codes_ok"] is False
    assert res["ok"] is False
    assert res["overflow"] == 1


def test_verify_missing_report(engine, tmp_path):
    job, _ = _make_job(tmp_path, None)
    res = engine.verify(job, lambda m: None)
    assert res["ok"] is False
    assert any("리포트" in w for w in res["warnings"])


def test_verify_visual_hook_off_by_default(engine, tmp_path, monkeypatch):
    """시각 검수는 opt-in — 환경변수 없으면 visual=None, 게이트 불변."""
    monkeypatch.delenv("YONE_VISUAL_INSPECT", raising=False)
    job, _ = _make_job(tmp_path, GOOD_REPORT)
    res = engine.verify(job, lambda m: None)
    assert res["visual"] is None and res["ok"] is True


def test_verify_visual_hook_fail_open(engine, tmp_path, monkeypatch):
    """시각 검수 예외는 fail-open — 게이트/저장에 영향 없음 (W29 판정 철학)."""
    monkeypatch.setenv("YONE_VISUAL_INSPECT", "1")
    import core.visual_inspect as vi

    def _boom(*a, **k):
        raise RuntimeError("렌더 백엔드 없음")

    monkeypatch.setattr(vi, "inspect_job_visual", _boom)
    job, _ = _make_job(tmp_path, GOOD_REPORT)
    res = engine.verify(job, lambda m: None)
    assert res["ok"] is True and res["visual"] is None
