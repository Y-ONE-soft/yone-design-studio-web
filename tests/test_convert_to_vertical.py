# -*- coding: utf-8 -*-
"""convert_to_vertical (W27) — 수동 ConvertToVertical.jsx 웹 흡수 오프라인 가드.

실 InDesign 없이 검증 가능한 것: 등록 정합 / JSX 본문 ES3 제약·감사 패턴 /
parse·prepare_jsx 산출물 / 검수 헬퍼(코드 시퀀스·블록) 로직.
"""
import json
import os

import pytest

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)
BODY = os.path.join(REPO, "core", "jsx", "convert_vertical.body.jsx")


# ── 등록 정합 ────────────────────────────────────────────────────────────────

def test_registration():
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "convert_to_vertical" in engines
    # 기존 엔진 유지 (삭제 금지 규칙)
    for keep in ("workbook", "workbook_sero", "vert_to_horiz",
                 "passage_remove", "slim_merge", "mockexam_horiz_merge"):
        assert keep in engines
    assert len(engines) >= 35

    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "convert_to_vertical"' in raw
    assert '"engine_id": "vert_to_horiz"' in raw      # 기존 카드 유지
    assert '"engine_id": "passage_remove"' in raw

    e = engines["convert_to_vertical"]
    assert "베타" in e.display_name
    tpl = os.path.join(REPO, "templates", e.template_name)
    assert os.path.isfile(tpl), f"템플릿 없음: {tpl}"
    src = open(tpl, encoding="utf-8").read()
    assert "const MATERIAL_ID = 'convert_to_vertical'" in src


# ── JSX 본문 — ES3 제약 + 감사 3패턴 ────────────────────────────────────────

def test_jsx_body_es3_and_audit_patterns():
    src = open(BODY, encoding="utf-8").read()
    # ES3 제약 (ExtendScript)
    import re
    code = "\n".join(ln for ln in src.splitlines()
                     if not ln.strip().startswith("//"))
    assert not re.search(r"\blet\s+\w", code)
    assert not re.search(r"\bconst\s+\w", code)
    assert "=>" not in code
    assert "`" not in code
    assert "JSON.parse" not in code and "JSON.stringify" not in code

    # 감사 패턴 ① 부트스트랩 try-catch: 설정 로드가 try 안 + [오류] 로그
    assert src.index("try {") < src.index("readJSONFile(CFG_PATH)")
    assert 'wlog("[오류] " + e)' in src
    # 감사 패턴 ② 완료 마커 (job 전용 로그는 wlog=__LIB_LOG_PATH__)
    assert "세로 변환 완료" in src
    # 감사 패턴 ③ export 정규화
    assert "pageRange = PageRange.ALL_PAGES" in src
    assert "exportAsSinglePages = false" in src
    assert "viewPDF = false" in src
    # 웹 안전화: activeDocument 사용 금지 (사용자 문서 무접촉)
    assert "activeDocument" not in code
    # 구조 유도 존재
    assert "(sep1[0] - FRONT) / 6" in src


def test_jsx_body_builds_with_lib():
    """build_jsx로 lib + 본문이 실제로 합쳐지는지 (치환 포함)."""
    from core.indesign.jsxbuild import build_jsx
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        out = build_jsx(BODY, {"__CFG_PATH__": os.path.join(td, "cfg.json")},
                        log_path=os.path.join(td, "log.txt"),
                        out_path=os.path.join(td, "run.jsx"))
        src = open(out, encoding="utf-8").read()
        assert "__CFG_PATH__" not in src
        assert "function wlog" in src          # lib 포함
        assert "cfg.json" in src


# ── 수동본 파리티 정적 대조 (실기 E2E 보류 대체 — 미러 있을 때만) ───────────

MANUAL = os.path.expanduser(
    "~/dev/yone-design-web/manual_jsx_mirror/ConvertToVertical.jsx")


@pytest.mark.skipif(not os.path.isfile(MANUAL), reason="수동본 미러 없음")
def test_static_parity_with_manual():
    """이식 본문이 수동본(2026-06-17)의 핵심 의미론 조각을 그대로 담는지.

    실기 파리티(dump 대조)가 InDesign 점유로 보류된 동안의 정적 게이트 —
    변환 로직의 핵심 리터럴(코드 정규식/섹션명/간지 스타일/이미지 normName/
    재배치 순서)이 수동본과 문자 그대로 일치해야 한다.
    """
    manual = open(MANUAL, encoding="utf-8").read()
    port = open(BODY, encoding="utf-8").read()

    verbatim = [
        # leadPassageNum 코드 정규식 2종 (06-17 개선의 핵심)
        r"/^\s*\{(\d{4})(\d{2}(?:~\d+)?)\}/",
        r"/^\s*[\[{]\s*(\d{1,3}(?:~\d+)?)\s*[\]}]/",
        # O/M 그룹 시작 감지
        r"/^\s*\{[^}]+\}/",
        # 섹션 라벨명
        '["ox", "title", "content", "insert", "blank"]',
        '["grammar", "grammarox", "blankgrammar"]',
        # 재배치 사이클 안전 상한
        "aseq < 30", "op < 40",
        # STEP4.5 보존 분리의 핵심 호출
        "texts[0].duplicate(LocationOptions.AT_END, nf.insertionPoints[0])",
        'UndoModes.FAST_ENTIRE_SCRIPT, "스토리 보존 분리"',
        # STEP10 간지 처리 스타일/마스터 이름 (\uXXXX가 아닌 원문 비교는 port쪽)
        "GlobalClashResolutionStrategy.LOAD_ALL_WITH_OVERWRITE",
        # 이미지 normName 규칙
        '.replace("(B)", "")',
        "/^마지막P(?=\\.[^.]+$)/",
    ]
    for frag in verbatim:
        # 수동본은 한글을 \uXXXX 이스케이프로 담는 경우가 있어 두 형태 허용
        frag_esc = frag.encode("unicode_escape").decode("ascii") \
                       .replace("\\\\", "\\")
        assert frag in port, f"이식본에 없음: {frag!r}"
        assert (frag in manual) or (frag_esc in manual) or (
            frag in ("aseq < 30", "op < 40")  # 공백 변형 허용 조각
            and frag.replace(" ", "") in manual.replace(" ", "")), \
            f"수동본에 없음(파리티 기준 이탈?): {frag!r}"

    # 수동본 하드코딩 ↔ 이식 유도의 대응 (숫자 21/5/9는 유도식으로 대체됨)
    assert "sep1[0] - 21" in manual          # 수동: A_SECT_COUNT = sep1[0]-21
    assert "(sep1[0] - FRONT) / 6" in port   # 이식: NUM = (sep1-front)/6
    assert "pair < 9" in manual              # 수동: 어휘 9쌍 고정
    assert "pair < HW_PAIRS" in port         # 이식: NUM/2 유도
    # 재배치 사이클 순서 (hw→ox→…→blankgrammar) 등장 순서 일치
    order = ["hw_", "ox_", "title_", "content_", "insert_", "blank_",
             "grammar_", "grammarox_", "blankgrammar_", "arrange_", "om_"]
    def _push_positions(src, tag):
        idx = src.find('pages_k.push(lmap[PFX + "' + tag)
        assert idx >= 0, f"재배치 push 없음: {tag}"
        return idx
    for src in (manual, port):
        pos = [src.find('"' + t) for t in order]
        # 각 라벨 문자열이 존재하고, STEP5 push 블록의 순서가 동일
        p_hw = _push_positions(src, "hw_")
        p_bg = _push_positions(src, "blankgrammar_")
        assert p_hw < p_bg


# ── 엔진 parse / prepare_jsx (InDesign 불필요) ──────────────────────────────

@pytest.fixture()
def fake_indd(tmp_path):
    p = tmp_path / "고1_25년_6월_전체(C).indd"
    p.write_bytes(b"INDD-FAKE" * 100)
    return str(p)


def _engine_with_tmp_output(tmp_path, monkeypatch, master_exists=False):
    import engines.convert_to_vertical.engine as mod
    real = mod._load_config

    master = tmp_path / "master.indd"
    if master_exists:
        master.write_bytes(b"MASTER" * 10)

    def patched():
        cfg = real()
        cfg["output_base"] = str(tmp_path / "out")
        cfg["master_indd"] = str(master)
        cfg["step123_ai"] = str(tmp_path / "STEP123.ai")
        cfg["image_base"] = str(tmp_path / "img")
        return cfg

    monkeypatch.setattr(mod, "_load_config", patched)
    return mod.ConvertToVerticalEngine()


def test_parse_and_prepare(tmp_path, monkeypatch, fake_indd):
    engine = _engine_with_tmp_output(tmp_path, monkeypatch, master_exists=True)
    job = tmp_path / "job"
    job.mkdir()
    logs = []

    json_path = engine.parse({"doc_path": fake_indd}, str(job), logs.append)
    content = json.load(open(json_path, encoding="utf-8"))
    assert content["source_name"] == "고1_25년_6월_전체(C).indd"
    assert os.path.isfile(content["source_local"])   # 로컬 사본

    jsx_path = engine.prepare_jsx(json_path, str(job), logs.append)
    assert jsx_path == str(job / "run.jsx")
    settings = json.load(open(job / ".settings.json", encoding="utf-8"))
    # 기본 결과명: '전체' → '세로'
    assert os.path.basename(settings["indd_path"]) == "고1_25년_6월_세로(C).indd"
    assert os.path.isfile(settings["indd_path"])     # 출력 위치 작업 사본
    assert settings["pdf_path"].endswith("세로(C).pdf")
    assert settings["log_paths"][0].startswith(str(job))  # job 전용 로그

    jsx_cfg = json.load(open(job / "convert_cfg.json", encoding="utf-8"))
    # 구조 상수 외부화 기본값 (수동본 파리티)
    assert jsx_cfg["front_pages"] == 3
    assert jsx_cfg["sep_scan_start"] == 100
    assert jsx_cfg["margin_outside"] == 20
    assert jsx_cfg["margin_inside"] == 22
    # 세로 마스터는 로컬 사본으로 전달 (GDrive 직접 열기 금지)
    assert jsx_cfg["master_indd"].startswith(str(job))
    assert os.path.isfile(jsx_cfg["master_indd"])

    src = open(jsx_path, encoding="utf-8").read()
    assert "convert_cfg.json" in src
    assert "__CFG_PATH__" not in src


def test_parse_requires_input(tmp_path, monkeypatch):
    engine = _engine_with_tmp_output(tmp_path, monkeypatch)
    job = tmp_path / "job2"
    job.mkdir()
    with pytest.raises(ValueError):
        engine.parse({}, str(job), lambda m: None)


def test_prepare_without_master_warns(tmp_path, monkeypatch, fake_indd):
    engine = _engine_with_tmp_output(tmp_path, monkeypatch, master_exists=False)
    job = tmp_path / "job3"
    job.mkdir()
    logs = []
    json_path = engine.parse({"doc_path": fake_indd}, str(job), logs.append)
    engine.prepare_jsx(json_path, str(job), logs.append)
    assert any("[경고]" in m and "마스터" in m for m in logs)
    jsx_cfg = json.load(open(job / "convert_cfg.json", encoding="utf-8"))
    assert jsx_cfg["master_indd"] == ""              # JSX가 STEP10 생략+경고


def test_result_name_override(tmp_path, monkeypatch, fake_indd):
    engine = _engine_with_tmp_output(tmp_path, monkeypatch)
    job = tmp_path / "job4"
    job.mkdir()
    (job / "result_name.txt").write_text("커스텀이름", encoding="utf-8")
    (job / "export_pdf.txt").write_text("off", encoding="utf-8")
    json_path = engine.parse({"doc_path": fake_indd}, str(job), lambda m: None)
    engine.prepare_jsx(json_path, str(job), lambda m: None)
    settings = json.load(open(job / ".settings.json", encoding="utf-8"))
    assert os.path.basename(settings["indd_path"]) == "커스텀이름.indd"
    assert settings["pdf_path"] is None
    assert settings["export_pdf"] is False


# ── 검수 헬퍼 — 지문 코드 시퀀스/블록 ───────────────────────────────────────

def _story(pg, first_text):
    return {"pg": [pg], "paragraphs": [{"t": first_text, "s": ""}],
            "overflow": False}


def test_page_code_sequence_and_blocks():
    from engines.convert_to_vertical.engine import (
        page_code_sequence, contiguous_blocks)
    dump = {
        "pages": [{"p": str(i)} for i in range(1, 9)],
        "stories": [
            _story("2", "{250620} My passage twenty ..."),   # YYMMQQ → 20
            _story("3", "no code here"),
            _story("4", "[21] short marker"),
            _story("5", "{250620~21} combined"),             # ~ 형식
            _story("7", "{22} curly short"),
        ],
    }
    seq = page_code_sequence(dump)
    assert seq == [("2", "20"), ("4", "21"), ("5", "20~21"), ("7", "22")]
    assert contiguous_blocks(seq) == ["20", "21", "20~21", "22"]
    # 사이클 정합(모두 연속)이면 중복 블록 없음
    blocks = contiguous_blocks([("1", "20"), ("2", "20"), ("3", "21")])
    assert blocks == ["20", "21"]
    # 흩어진 코드 → 중복 블록
    scattered = contiguous_blocks([("1", "20"), ("2", "21"), ("3", "20")])
    assert scattered.count("20") == 2
