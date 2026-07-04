"""스타일 룩업 테스트 — 코퍼스 전 단락이 KeyError 없이 해결되는지 포함."""
import json
import os

import pytest

from core.structure import classify_paragraphs
from core.structure.style_resolver import resolve_style

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))


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
                if s and s not in inventory:
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
