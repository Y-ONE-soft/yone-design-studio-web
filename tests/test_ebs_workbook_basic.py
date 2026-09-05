"""리딩파워(기본) 워크북 — 시리즈 연동/내지/파일명 계약 가드.

기본 시리즈는 완성과 원고 구조도 내지도 다르다 (엔진 docstring 참조).
여기서는 GDrive 없이도 고정되는 계약만 검증한다:
  1. 단원 폴더 구조   — 단원 아래 '워크북' 폴더가 원고 폴더
  2. 원고 이름 방언   — 변형문제 모음 Step3 인식 · 대체 파일명(공백 무시)
  3. 내지/파일명      — 세종 워크북 내지 + 세종1_워크북{stem}_내지_v2.indd
  4. 완성 시리즈 무회귀 — 이름/훅 기본값이 그대로
"""
import json
import os

import pytest

from engines.ebs_workbook.engine import EbsWorkbookEngine
from engines.ebs_workbook_basic.engine import EbsWorkbookBasicEngine
from engines.ebs_workbook_basic_v2.engine import EbsWorkbookBasicV2Engine


@pytest.fixture()
def engine():
    return EbsWorkbookBasicV2Engine()


# ── 1. 단원 폴더 구조 ───────────────────────────────────────────────────────

def test_workbook_subdir_is_manuscript_dir(tmp_path):
    """단원 폴더 → 그 아래 '워크북' 폴더 (두 표기 모두)."""
    u1 = tmp_path / "Unit 10 Practice 3, 4"
    (u1 / "워크북").mkdir(parents=True)
    (u1 / "리뷰테스트").mkdir()
    assert EbsWorkbookBasicEngine._resolve_workbook_dir(str(u1)) \
        == str(u1 / "워크북")

    u2 = tmp_path / "Unit 20 Example, 1, 2"
    (u2 / "Unit 20 Example, 1, 2 워크북").mkdir(parents=True)
    assert EbsWorkbookBasicEngine._resolve_workbook_dir(str(u2)) \
        == str(u2 / "Unit 20 Example, 1, 2 워크북")


def test_workbook_dir_is_gdrive_not_mirror(tmp_path, monkeypatch):
    """워크북 폴더 경로는 **항상 GDrive(정본)** — 미러를 돌려주면 안 된다.

    2026-09-05 실사고: 미러 동기화가 도중이라 미러의 'Unit 10 …/워크북'에
    Step3와 .rsync-partial만 들어와 있었고, 그 경로를 목록 열거에 쓰는 바람에
    원고 19개가 통째로 '단원 폴더에 원고 파일이 없습니다'로 보였다.
    """
    unit = tmp_path / "gdrive" / "Unit 10 Practice 3, 4"
    (unit / "워크북").mkdir(parents=True)
    (unit / "워크북" / "Step1 A1 어휘선택.docx").write_bytes(b"x")
    mirror_wb = tmp_path / "mirror" / "Unit 10 Practice 3, 4" / "워크북"
    mirror_wb.mkdir(parents=True)          # 미러는 동기화 도중 = 비어 있음

    import engines.final.extractor as ex
    monkeypatch.setattr(ex, "list_manuscript_entries",
                        lambda folder, log=None: [("워크북", str(mirror_wb))])
    got = EbsWorkbookBasicEngine._resolve_workbook_dir(str(unit))
    assert got == str(unit / "워크북")


def test_workbook_dir_falls_back_to_mirror_when_gdrive_gone(tmp_path,
                                                            monkeypatch):
    """GDrive를 못 읽는 상황(좀비 Drive)에서는 미러 폴백은 유지한다."""
    unit = tmp_path / "gdrive" / "Unit 10 Practice 3, 4"
    unit.mkdir(parents=True)               # 워크북 폴더가 GDrive에 안 보임
    mirror_wb = tmp_path / "mirror" / "Unit 10 Practice 3, 4" / "워크북"
    mirror_wb.mkdir(parents=True)

    import engines.final.extractor as ex
    monkeypatch.setattr(ex, "list_manuscript_entries",
                        lambda folder, log=None: [("워크북", str(mirror_wb))])
    assert EbsWorkbookBasicEngine._resolve_workbook_dir(str(unit)) \
        == str(mirror_wb)


def test_unit_without_workbook_dir_is_not_a_unit(tmp_path):
    """워크북 폴더가 없으면 원고 미작업 단원 — 목록에서 제외된다."""
    u = tmp_path / "Unit 7 Practice 1, 2"
    (u / "리뷰테스트").mkdir(parents=True)
    assert EbsWorkbookBasicEngine._resolve_workbook_dir(str(u)) == str(u)


def test_completed_series_dir_hook_unchanged(tmp_path):
    """완성 시리즈는 단원 폴더 자신이 원고 폴더 (무회귀)."""
    u = tmp_path / "Unit 15 워크북"
    u.mkdir()
    assert EbsWorkbookEngine._resolve_workbook_dir(str(u)) == str(u)


@pytest.mark.parametrize("label,expected", [
    ("Unit 20 Example, 1, 2", "20"),
    ("Unit 21 Example, 1~2", "21"),
    ("Chapter1 Unit1 Practice 3,4", "1"),
    ("Unit 10 Practice 3, 4", "10"),
])
def test_unit_number(label, expected):
    assert EbsWorkbookBasicEngine.unit_number(label) == expected


# ── 2. 원고 이름 방언 ───────────────────────────────────────────────────────

def test_step3_variant_pool_is_recognized():
    """Step3 토큰이 없는 변형문제 모음도 Step3 원고 (Unit 9 실측)."""
    name = "리딩파워 변형문제 발췌 Unit 09 (Practice 3·4).docx"
    assert EbsWorkbookBasicEngine._is_step3_manuscript(name)
    assert EbsWorkbookBasicEngine._is_step3_manuscript("Step3.hwpx")
    assert not EbsWorkbookBasicEngine._is_step3_manuscript(
        "Step1 A1 어휘선택.docx")
    # 완성 시리즈는 종전 그대로 (Step3 토큰만)
    assert not EbsWorkbookEngine._is_step3_manuscript(name)


def test_alt_target_ignores_spacing():
    """대체 파일명은 공백/대소문자 차이를 무시하고 찾는다."""
    alts = {"Step2 A1 어법선택(문법 기본 문제).docx":
            "Step2 A1 어법선택(객관식).docx"}
    assert EbsWorkbookEngine._alt_target(
        alts, " Step2 A1 어법선택(문법 기본 문제).docx") \
        == "Step2 A1 어법선택(객관식).docx"
    assert EbsWorkbookEngine._alt_target(alts, "Step2 A1 어법선택.docx") is None


def test_basic_config_covers_measured_dialects():
    cfg = json.load(open(EbsWorkbookBasicEngine.CONFIG_PATH,
                         encoding="utf-8"))
    assert cfg["fixed_series"] == "Reading Power 유형편(기본)"
    alts = cfg["manuscript_file_alternatives"]
    for dialect, target in [
            ("Step1 C2 빈칸어휘 해설지.docx", "Step1 C2 빈칸어휘 정답지.docx"),
            ("Step1 C2 빈칸어휘 정답.docx", "Step1 C2 빈칸어휘 정답지.docx"),
            ("Step2 C1 빈칸어법 정답.docx", "Step2 C1 빈칸어법 정답지.docx"),
            ("Step2 A1 어법 객관식.docx", "Step2 A1 어법선택(객관식).docx")]:
        assert alts.get(dialect) == target
    # 표준 워크북 12스텝 구성 (완성의 7스텝이 아니다)
    assert "step1_b1" in cfg["manuscript_file_map"]
    assert "step2_b1" in cfg["manuscript_file_map"]


# ── 3. 내지 / 출력 파일명 ───────────────────────────────────────────────────

def test_template_is_sejong_workbook_indd(engine):
    cfg = engine._load_cfg()
    assert "워크북(세종)" in os.path.basename(cfg["indd_original"])


def test_select_template_and_step_catalog(engine, tmp_path):
    src = tmp_path / "[원본]워크북(세종)_내지.indd"
    src.write_bytes(b"x")
    cfg = {"indd_original": str(src)}
    assert engine._select_template(cfg, "모의고사", "", print) == str(src)

    engine._plan_ctx = {"cfg": cfg, "school": "", "workbook_type": "모의고사"}
    assert engine._template_token() == "세종"
    # 세종 내지에는 '내용 종합' 섹션이 없다 (W19)
    assert "step1_b2" not in engine._step_map()


def test_plan_branch_is_standard_not_ebs(engine, tmp_path):
    """EBS 분기(완성 내지 전용 프레임 분리)를 타면 안 된다."""
    assert engine._workbook_type(str(tmp_path)) == "모의고사"


def test_output_name_from_unit(engine, tmp_path):
    job = str(tmp_path)
    open(os.path.join(job, "lesson.txt"), "w", encoding="utf-8").write(
        "Unit 20 Example, 1, 2")
    assert engine._output_name(job, 1, 0, 0, "모의고사", "") \
        == "세종1_워크북(리딩파워20강)_내지_v2.indd"


def test_output_name_uses_manual_stem(engine, tmp_path):
    job = str(tmp_path)
    open(os.path.join(job, "lesson.txt"), "w", encoding="utf-8").write(
        "Unit 13 Example, 1, 2")
    open(os.path.join(job, "filename_stem.txt"), "w",
         encoding="utf-8").write("01(리딩파워13,14,15강)")
    assert engine._output_name(job, 1, 0, 0, "모의고사", "") \
        == "세종1_워크북01(리딩파워13,14,15강)_내지_v2.indd"


def test_divider_defaults_to_readingpower(engine, tmp_path):
    job = str(tmp_path)
    open(os.path.join(job, "lesson.txt"), "w", encoding="utf-8").write(
        "Unit 21 Example, 1~2")
    assert engine._divider_deco(job, {})["divider"] == {
        "line1": "리딩파워", "line2": "21강", "source": "type"}


def test_divider_user_input_wins(engine, tmp_path):
    job = str(tmp_path)
    open(os.path.join(job, "lesson.txt"), "w", encoding="utf-8").write(
        "Unit 21 Example, 1~2")
    open(os.path.join(job, "divider_line1.txt"), "w",
         encoding="utf-8").write("외부지문")
    d = engine._divider_deco(job, {})["divider"]
    assert d["line1"] == "외부지문" and d["source"] == "user"


# ── 4. 등록 / UI 배선 ───────────────────────────────────────────────────────

def test_engine_registered_and_page_wired():
    import engines.registry as registry
    e = registry.get("ebs_workbook_basic_v2")
    assert e.display_name == "리딩파워(기본) 워크북 v2 (베타)"

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    html = open(os.path.join(root, "templates", e.template_name),
                encoding="utf-8").read()
    # 완성 시리즈 API를 그대로 물고 있으면 다른 교재 원고가 올라온다
    assert "/api/ebs-workbook-basic/units" in html
    assert "/api/ebs-workbook/units" not in html
    assert "세종1_워크북" in html

    subjects = json.load(open(os.path.join(root, "data", "subjects.json"),
                              encoding="utf-8"))
    ids = [it.get("engine_id") for cat in subjects
           for it in cat.get("items", [])]
    assert "ebs_workbook_basic_v2" in ids
