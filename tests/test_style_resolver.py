"""스타일 룩업 테스트 — 코퍼스 전 단락이 KeyError 없이 해결되는지 포함."""
import json
import os

import pytest

from core.structure import classify_paragraphs
from core.structure.style_resolver import resolve_style

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


def _resolved_with_fallback(table, kind, style, inventory):
    """인벤토리 가드의 fail-open 규칙 (W45).

    `<kind>@fallback` 키가 있는 매핑은 '아직 템플릿에 없을 수 있는 신설
    스타일'이다 (예: AnsL → S_답란). 본 스타일이 인벤토리에 없어도 폴백이
    있으면 통과 — 렌더가 s→s_fb 순으로 해석하기 때문(침묵 실패 아님:
    JSX가 [답란] 폴백 로그, 게이트 G44가 warning 지목).
    템플릿에 신설 스타일이 반영되면 자동으로 다시 엄격해진다."""
    if style in inventory:
        return True
    fb = table.get(kind + "@fallback")
    if fb is None:
        return False
    for f in (fb if isinstance(fb, list) else [fb]):
        if f and f not in inventory:
            return False
    return True


def test_step3_basics():
    assert resolve_style("workbook", "STEP3", "Q") \
        == "STEP 03 > S_실전문제 번호 수정 올림포스"
    assert resolve_style("workbook", "STEP3", "GH") is None       # 제거 대상
    # P 계열은 허용 스타일 배열 (JSX가 밑줄 변형을 상황별로 적용 — E2E 파일럿 반영)
    p_styles = resolve_style("workbook", "STEP3", "P")
    assert isinstance(p_styles, list)
    assert "STEP 03 > 실전 문제 지문 올림포스_" in p_styles
    assert "STEP 03 > 실전 문제 지문 올림포스_ 밑줄제거" in p_styles


def test_override():
    assert resolve_style("workbook", "STEP3", "Q",
                         overrides={"Q": "커스텀 > 발문"}) == "커스텀 > 발문"


def test_wildcard_and_missing():
    assert resolve_style("workbook", "STEP2B1", "P") == "STEP 02 > B1_어법 OX"
    with pytest.raises(KeyError):
        resolve_style("workbook", "STEP3", "존재안함")
    with pytest.raises(KeyError):
        resolve_style("없는교재", "STEP3", "Q")


def test_corpus_step3_full_coverage():
    """골든 코퍼스 workbook Step3의 모든 단락이 스타일 결정 가능해야 한다."""
    base = os.path.join(TESTS_DIR, "corpus", "workbook")
    n = 0
    for case in sorted(os.listdir(base)):
        g = os.path.join(base, case, "golden", "content.json")
        c = json.load(open(g, encoding="utf-8"))
        step3 = c.get("steps", {}).get("step3") or {}
        for group in ("normal", "short"):
            for item in step3.get(group, []) or []:
                for r in classify_paragraphs(item.get("paragraphs", [])):
                    if r["kind"] == "BLANK":
                        continue
                    resolve_style("workbook", "STEP3", r["kind"],
                                  has_underline=r.get("has_underline"))
                    n += 1
    assert n > 2000  # 커버리지 실효성 가드


def test_style_map_names_exist_in_template_inventory():
    """style_map의 모든 스타일명이 실물 템플릿 인벤토리에 존재해야 한다.

    (템플릿 스타일 개명/오타를 회귀로 잡는 장치 — 픽스처는
    core/template_spec.extract_template_spec으로 워크북C 원본에서 추출)
    """
    spec = json.load(open(os.path.join(TESTS_DIR, "fixtures",
                                       "template_spec_workbookC.json"),
                          encoding="utf-8"))
    inventory = set(spec["paragraph_styles"])
    smap = json.load(open(os.path.join(
        os.path.dirname(TESTS_DIR), "core", "structure", "style_map.json"),
        encoding="utf-8"))
    missing = []
    for step, table in smap["workbook"].items():
        for kind, style in table.items():
            for s in (style if isinstance(style, list) else [style]):
                if s and not _resolved_with_fallback(table, kind, s,
                                                     inventory):
                    missing.append(f"{step}/{kind}: {s}")
    assert not missing, f"템플릿에 없는 스타일 참조: {missing}"


def test_whitebook_style_map_exists_in_template_inventory():
    """whitebook v2: style_map의 단락/문자스타일이 실물 [원본] 템플릿
    인벤토리(tests/fixtures/template_spec_whitebook.json)에 전부 존재."""
    spec = json.load(open(os.path.join(TESTS_DIR, "fixtures",
                                       "template_spec_whitebook.json"),
                          encoding="utf-8"))
    para_inv = set(spec["paragraph_styles"])
    char_inv = set(spec["character_styles"])
    smap = json.load(open(os.path.join(
        os.path.dirname(TESTS_DIR), "core", "structure", "style_map.json"),
        encoding="utf-8"))["whitebook"]
    missing = []
    for table in ("AREAS", "PRAC"):
        for kind, style in smap[table].items():
            if style not in para_inv:
                missing.append(f"{table}/{kind}: {style}")
    for kind, style in smap["CHAR"].items():
        if style not in char_inv:
            missing.append(f"CHAR/{kind}: {style}")
    assert not missing, f"템플릿에 없는 스타일 참조: {missing}"


def test_seseospecial_style_map_exists_in_template_inventory():
    """세서특필 v2: style_map의 모든 단락스타일이 광문2/광문3 실물 [원본]
    템플릿 인벤토리에 전부 존재. (주의: [원본]광문1은 구세대 템플릿 —
    C ver 트리, 새형식 스타일 부재 — 이라 대상에서 제외. style_map _doc 참조.)"""
    smap = json.load(open(os.path.join(
        os.path.dirname(TESTS_DIR), "core", "structure", "style_map.json"),
        encoding="utf-8"))["seseospecial"]
    for fx in ("template_spec_seseospecial_광문2.json",
               "template_spec_seseospecial_광문3.json"):
        inv = set(json.load(open(os.path.join(TESTS_DIR, "fixtures", fx),
                                 encoding="utf-8"))["paragraph_styles"])
        missing = []
        for table in ("PART1", "PART2", "ANS"):
            for kind, style in smap[table].items():
                if style not in inv:
                    missing.append(f"{table}/{kind}: {style}")
        assert not missing, f"{fx}에 없는 스타일 참조: {missing}"


def test_mockexam_v2_school_overrides_exist_in_inventory():
    """동형 v2: 기본 FLOW + 학교 overrides 적용 결과가 각 학교 실물 템플릿
    인벤토리에 전부 존재해야 한다 (새 학교 추가 시 스펙 픽스처도 추가할 것)."""
    smap = json.load(open(os.path.join(
        os.path.dirname(TESTS_DIR), "core", "structure", "style_map.json"),
        encoding="utf-8"))["mockexam_v2"]
    flow = smap["FLOW"]
    school_fixtures = {
        "한영3": "template_spec_dh_hanyoung3.json",
        "상일2": "template_spec_dh_상일2.json",
        "성덕1": "template_spec_dh_성덕1.json",
        "명일3": "template_spec_dh_명일3.json",
        "강동3": "template_spec_dh_강동3.json",
    }
    problems = []
    for school, fx in school_fixtures.items():
        inv = set(json.load(open(os.path.join(TESTS_DIR, "fixtures", fx),
                                 encoding="utf-8"))["paragraph_styles"])
        table = dict(flow)
        table.update(smap.get("overrides", {}).get(school, {}))
        for kind, style in table.items():
            if kind.startswith("_"):
                continue
            for s in (style if isinstance(style, list) else [style]):
                if s and s not in inv:
                    problems.append(f"{school}/{kind}: {s}")
    assert not problems, f"학교 템플릿에 없는 스타일: {problems}"


def test_gdrive_workbook_v2_templates_inventory():
    """GDrive 워크북 3종 v2 템플릿 실물 인벤토리 가드.

    각 내지가 해당 엔진 스텝의 style_map 스타일(플랜이 실제 방출하는 것 —
    리스트 값은 첫 요소)·아이콘 라벨·마커 프레임·스토리 탐색 마스터를
    실제로 갖고 있는지 고정한다. 픽스처는 core.template_spec으로
    [원본] 로컬 사본에서 추출 (2026-07-04).
    """
    def missing_styles(smap, steps, inv):
        """플랜이 실제 방출하는 스타일 중 인벤토리에 없는 것 (W45 폴백 허용)."""
        out = set()
        for st in steps:
            table = smap[st]
            for kind, v in table.items():
                s = v[0] if isinstance(v, list) else v
                if s and not _resolved_with_fallback(table, kind, s, inv):
                    out.add(s)
        return out

    smap = json.load(open(os.path.join(
        os.path.dirname(TESTS_DIR), "core", "structure", "style_map.json"),
        encoding="utf-8"))["workbook"]
    ebs_steps = ["STEP1A1", "STEP1A2", "STEP1C1", "STEP1C2", "STEP2A1",
                 "STEP2A1Practice", "STEP2C2", "STEP3"]
    cases = [
        # (픽스처, 스텝 유닛, 필요 마스터 prefix, 마커 텍스트)
        ("template_spec_ebs_readingpower.json", ebs_steps, {"O", "M"},
         ["어휘 선택", "본문 O/X", "문장 배열", "빈칸 어휘", "어법 수정",
          "영작 배열"]),
        ("template_spec_suneungteukgang_analysis.json", ebs_steps[:-1],
         set(),
         ["어휘선택", "본문 O/X", "문장배열", "빈칸어휘", "어법선택",
          "영작배열"]),
        ("template_spec_suneungteukgang_problem.json", ["STEP3"], {"D"},
         []),
    ]
    icon_labels = {"TF 버튼", "STEP1 문제아이콘", "STEP2 영작 답지",
                   "화살표 답지"}
    for fixture, steps, masters, markers in cases:
        spec = json.load(open(os.path.join(TESTS_DIR, "fixtures", fixture),
                              encoding="utf-8"))
        inv = set(spec["paragraph_styles"])
        missing = missing_styles(smap, steps, inv)
        assert not missing, (fixture, missing)
        assert masters <= {m["prefix"] for m in spec["masters"]}, fixture
        labels = {li["label"] for li in spec["labeled_items"]}
        assert icon_labels <= labels, (fixture, icon_labels - labels)
        heads = " | ".join(f.get("head", "") for p in spec["page_map"]
                           for f in p["frames"])
        for mk in markers:
            assert mk in heads, (fixture, mk)
        # 밑줄 문자스타일 폴백 체인(문제_밑줄→밑줄) 중 하나는 존재
        assert any(c in spec["character_styles"]
                   for c in ("문제_밑줄", "밑줄")), fixture
