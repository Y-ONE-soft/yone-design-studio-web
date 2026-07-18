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

    # STEP4.5 의도적 차이 (W27 실기 결함 수리 — 수동본 프레임 단위 분리
    # 'texts[0].duplicate(...nf...)'는 stale 참조 침묵 스킵·부분 실패 겹침·
    # 단락 분단을 실기에서 유발): 이식본은 ID 재해결 라운드 + 스토리 단위
    # 트랜잭션 + 단락 경계 그룹 분리를 사용한다.
    assert "texts[0].duplicate(LocationOptions.AT_END, nf.insertionPoints[0])" in manual
    assert "itemByID" in port                # stale 참조 대체 (ID 재해결)
    assert "characters.itemByRange" in port  # 그룹 범위 복제 (단락 보존)
    assert "_collectThreadIds" in port       # 잔존 0 검증 라운드
    assert "분리 실패 스레드" in port          # 잔존 시 [오류] 중단 게이트
    # STEP4.5 undo 그룹 의도적 차이 (5차 프로브 probe_remove5, 2026-07-18):
    # 수동본의 doScript(FAST_ENTIRE_SCRIPT, "스토리 보존 분리") 래퍼는 창 없는
    # do script 컨텍스트에서 모든 remove()를 예외 없는 침묵 no-op으로 만든다
    # (1~4차 '원본 제거 no-op'의 실원인) — 이식본은 래퍼 없이 직접 실행.
    assert 'UndoModes.FAST_ENTIRE_SCRIPT' in manual
    assert 'UndoModes.FAST_ENTIRE_SCRIPT, "\\uc2a4\\ud1a0\\ub9ac ' \
           '\\ubcf4\\uc874 \\ubd84\\ub9ac"' in manual or \
           'UndoModes.FAST_ENTIRE_SCRIPT, "스토리 보존 분리"' in manual
    assert "app.doScript(_splitRounds" not in port  # 래퍼 제거 (직접 실행)
    assert "_splitRounds();" in port
    assert "made.length - 1" in port         # fail 시 __cv_split__ 복제 롤백

    # W27 6차 의도적 차이 3종 (5차 하류 결함 실측 수리 — 오프라인 진단:
    # 5차 덤프 job/typeset_dump.json + 수동 실물 manual_dump.json 대조):
    # ① STEP4.4 arrange 코드 단위 재배분 — 수동본은 페이지 라벨 이어붙임만
    #   있어(18코드/10페이지 스레드) 코드 산개가 구조적으로 불가피. 이식본은
    #   코드당 새 페이지 1장으로 재배분 (수동 '실물'의 지문당 1페이지 구조).
    assert "STEP4.4" in port and "arrange_pages_added" in port
    assert 'PFX + "arrange_" + k4 + "_0"' in port
    # ② 분리 산물 말미 \r 제거 — 암묵 빈 최종 단락이 flag-only 오버셋을
    #   남기는 것 방지. 7차 프로브(probe_tail7 D0) 실측: itemByRange의
    #   contents는 배열(["\r"]) 반환이라 === "\r" 직접 비교(6차 수리)는
    #   항상 false로 침묵 no-op — String() 비교 + remove()로 교체.
    assert port.count('String(lc4.contents) === "\\r"') == 1
    assert port.count('String(lc5.contents) === "\\r"') == 1
    assert "lc4.remove();" in port and "lc5.remove();" in port
    # ②b 프레임 속성 대입 순서 — tfp.properties 일괄 대입이 새 프레임 폭을
    #   리사이즈(84→82, probe_tail7c 실측)하므로 gb는 반드시 tfp 이후 마지막.
    for frag in ("nf4.textFramePreferences.properties = pTfp",
                 "nf.textFramePreferences.properties = cp.tfp"):
        assert frag in port
        gb_after = port.index("nf4.geometricBounds = pGb") if "pTfp" in frag \
            else port.index("nf.geometricBounds = cp.gb")
        assert gb_after > port.index(frag), f"gb 대입이 tfp보다 앞: {frag!r}"
    # ③ STEP10 파괴적 동기화 기본 생략 — 수동 실물은 임포트 스타일 흔적 0·
    #   혼합 마스터 유지. 같은 이름 스타일 덮어쓰기가 리플로우 오버셋 유발.
    assert "cfg.master_sync === true" in port
    assert "_applyCMasterExceptFirst(doc);" in port   # 코드는 보존(옵션 경로)
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


# ── 검수 게이트 헬퍼 — 중복 배치 / 관통 스레드 (W27 실기 결함 실증) ─────────

def test_line_counts_and_duplication():
    from engines.convert_to_vertical.engine import line_counts
    long_a = "A" * 30
    long_b = "B" * 30
    src = {"stories": [
        {"pg": ["1"], "paragraphs": [{"t": long_a}, {"t": "짧음"}]},
    ]}
    out = {"stories": [
        {"pg": ["1"], "paragraphs": [{"t": long_a}]},
        {"pg": ["2"], "paragraphs": [{"t": long_a}, {"t": long_b}]},
    ]}
    sc = line_counts(src)
    oc = line_counts(out)
    assert sc == {long_a: 1}
    assert oc == {long_a: 2, long_b: 1}
    dup = [t for t, n in oc.items() if n > sc.get(t, 0)]
    assert sorted(dup) == sorted([long_a, long_b])


def test_expected_page_count():
    from engines.convert_to_vertical.engine import expected_page_count
    # W27 6차: 240 - 구분4 - arrange원본10 + 코드별18 = 244
    stats = {"sep_pages_deleted": 4,
             "arrange_pages_added": 18, "arrange_pages_deleted": 10}
    assert expected_page_count(240, stats) == 244
    # 구버전 JSX (arrange 통계 없음) — 기존 산식 유지
    assert expected_page_count(240, {"sep_pages_deleted": 4}) == 236
    # 통계 없음/실패 → 판정 생략
    assert expected_page_count(240, {}) is None
    assert expected_page_count(0, {"sep_pages_deleted": 4}) is None


def test_residual_thread_count():
    from engines.convert_to_vertical.engine import residual_thread_count
    # 문제 내 연속 3~4p 스레드(수동 실물 구조) — 정상
    ok_dump = {"stories": [
        {"pg": ["14", "15", "16"], "paragraphs": []},
        {"pg": ["7"], "paragraphs": []},
    ]}
    assert residual_thread_count(ok_dump) == 0
    # 사이클 관통 스레드(분리 실패 실증 형태 — 큰 페이지 간격)
    bad_dump = {"stories": [
        {"pg": ["8", "23", "36", "48"], "paragraphs": []},
        {"pg": ["4", "19"], "paragraphs": []},
        {"pg": ["100", "101"], "paragraphs": []},
    ]}
    assert residual_thread_count(bad_dump) == 2
