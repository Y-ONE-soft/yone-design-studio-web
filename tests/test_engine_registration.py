"""엔진 등록 정합성 — registry/subjects.json/템플릿 3자 일치 (CLAUDE.md 규칙)."""
import json
import os

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(TESTS_DIR)


def test_registry_subjects_template_consistency():
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "mockexam_v2" in engines
    assert "mockexam" in engines            # 기존 엔진 유지 (삭제 금지 규칙)
    assert len(engines) >= 22

    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "mockexam_v2"' in raw     # 카드 존재
    assert '"engine_id": "mockexam"' in raw        # 기존 카드 유지

    e = engines["mockexam_v2"]
    tpl = os.path.join(REPO, "templates", e.template_name)
    assert os.path.isfile(tpl), f"템플릿 없음: {tpl}"
    assert 'const MATERIAL_ID = "mockexam_v2"' in open(tpl, encoding="utf-8").read()
