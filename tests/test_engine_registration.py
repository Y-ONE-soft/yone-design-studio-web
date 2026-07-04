"""엔진 등록 정합성 — registry/subjects.json/템플릿 3자 일치 (CLAUDE.md 규칙)."""
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)


def test_registry_subjects_template_consistency():
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "mockexam_v2" in engines
    assert "blackbook_v2" in engines
    assert "workbook_v2" in engines
    assert "mockexam" in engines            # 기존 엔진 유지 (삭제 금지 규칙)
    assert "blackbook" in engines
    assert "workbook" in engines
    assert len(engines) >= 24

    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "mockexam_v2"' in raw     # 카드 존재
    assert '"engine_id": "blackbook_v2"' in raw
    assert '"engine_id": "workbook_v2"' in raw
    assert '"engine_id": "mockexam"' in raw        # 기존 카드 유지
    assert '"engine_id": "blackbook"' in raw
    assert '"engine_id": "workbook"' in raw

    e = engines["mockexam_v2"]
    tpl = os.path.join(REPO, "templates", e.template_name)
    assert os.path.isfile(tpl), f"템플릿 없음: {tpl}"
    assert 'const MATERIAL_ID = "mockexam_v2"' in open(tpl, encoding="utf-8").read()

    # workbook_v2: v1 typeset_workbook.html 클론 — material id는
    # data-material="{{ engine.material_id }}"로 동적 주입 (상수 없음)
    w = engines["workbook_v2"]
    wtpl = os.path.join(REPO, "templates", w.template_name)
    assert w.template_name == "typeset_workbook_v2.html"
    assert os.path.isfile(wtpl), f"템플릿 없음: {wtpl}"
    wsrc = open(wtpl, encoding="utf-8").read()
    assert 'data-material="{{ engine.material_id }}"' in wsrc
    assert "workbook_sero" not in wsrc      # v2 페이지에 v1 세로 버튼 없음


def test_workbook_family_v2_registration():
    """workbook_supp_v2 / workbook_sero_v2 — registry/카드/템플릿 정합."""
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "workbook_supp_v2" in engines
    assert "workbook_sero_v2" in engines
    assert "workbook_supp" in engines       # 기존 엔진 유지 (삭제 금지 규칙)
    assert "workbook_sero" in engines

    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "workbook_supp_v2"' in raw
    assert '"engine_id": "workbook_sero_v2"' in raw
    assert '"engine_id": "workbook_supp"' in raw   # 기존 카드 유지

    for mid in ("workbook_supp_v2", "workbook_sero_v2"):
        e = engines[mid]
        tpl = os.path.join(REPO, "templates", e.template_name)
        assert e.template_name.endswith("_v2.html"), mid
        assert os.path.isfile(tpl), f"템플릿 없음: {tpl}"
        src = open(tpl, encoding="utf-8").read()
        assert 'data-material="{{ engine.material_id }}"' in src

    # supp v2는 workbook_v2 상속 — 파서/플랜/검수 로직 공유 확인
    from engines.workbook_v2.engine import WorkbookV2Engine
    assert isinstance(engines["workbook_supp_v2"], WorkbookV2Engine)
