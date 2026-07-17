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


def test_whitebook_v2_registration():
    """whitebook_v2 — registry(27번째)/카드/공용 템플릿 정합."""
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "whitebook_v2" in engines
    assert "whitebook" in engines           # 기존 엔진 유지 (삭제 금지 규칙)
    assert len(engines) >= 27

    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "whitebook_v2"' in raw
    assert '"engine_id": "whitebook"' in raw       # 기존 카드 유지

    # v1이 공용 typeset.html 사용 — v2도 동일 (template_name 미정의 = 공용)
    e = engines["whitebook_v2"]
    assert getattr(e, "template_name", "typeset.html") == "typeset.html"
    assert os.path.isfile(os.path.join(REPO, "templates", "typeset.html"))
    # 공용 폼은 upload_spec으로 자동 생성 — v1과 동일 슬롯이어야 UI 동작 동일
    assert e.upload_spec == engines["whitebook"].upload_spec


def test_seseospecial_v2_registration():
    """seseospecial_v2 — registry(28번째)/카드/공용 템플릿 정합."""
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "seseospecial_v2" in engines
    assert "seseospecial" in engines        # 기존 엔진 유지 (삭제 금지 규칙)
    assert len(engines) >= 28

    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "seseospecial_v2"' in raw
    assert '"engine_id": "seseospecial"' in raw     # 기존 카드 유지

    # v1이 공용 typeset.html 사용 — v2도 동일 (template_name 미정의 = 공용)
    e = engines["seseospecial_v2"]
    assert getattr(e, "template_name", "typeset.html") == "typeset.html"
    # 공용 폼은 upload_spec으로 자동 생성 — v1과 동일 슬롯이어야 UI 동작 동일
    assert e.upload_spec == engines["seseospecial"].upload_spec


def test_gdrive_workbook_family_v2_registration():
    """GDrive 의존 워크북 3종 v2 — registry/카드/전용 템플릿 정합.

    (textbook_workbook_v2 → ebs_workbook_v2 → suneungteukgang_workbook_v2
    순차 전환 — 전환 완료된 엔진만 검사 목록에 추가한다)
    """
    converted = ["textbook_workbook_v2", "ebs_workbook_v2",
                 "suneungteukgang_workbook_v2"]
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    raw = open(os.path.join(REPO, "data", "subjects.json"),
               encoding="utf-8").read()
    for mid in converted:
        v1_id = mid[:-3]
        assert mid in engines, mid
        assert v1_id in engines, v1_id      # 기존 엔진 유지 (삭제 금지 규칙)
        assert f'"engine_id": "{mid}"' in raw
        assert f'"engine_id": "{v1_id}"' in raw     # 기존 카드 유지

        e = engines[mid]
        assert e.template_name == f"typeset_{v1_id}_v2.html"
        tpl = os.path.join(REPO, "templates", e.template_name)
        assert os.path.isfile(tpl), f"템플릿 없음: {tpl}"
        src = open(tpl, encoding="utf-8").read()
        assert 'data-material="{{ engine.material_id }}"' in src
        # 폴더 탐색 UI는 v1 공용 API 재사용 + 업로드 슬롯 v1 동일
        assert e.upload_spec == engines[v1_id].upload_spec

    from engines.workbook_v2.engine import WorkbookV2Engine
    assert isinstance(engines["textbook_workbook_v2"], WorkbookV2Engine)


def test_processing_tools_registration():
    """W25: 수동 결합 2종 흡수 + 카테고리 재편 — registry/카드/템플릿 정합."""
    from engines import registry
    engines = {e.material_id: e for e in registry.all_engines()}
    assert "slim_merge" in engines
    assert "mockexam_horiz_merge" in engines
    assert "mockexam_sero_merge" in engines   # 기존 엔진 유지 (삭제 금지 규칙)
    assert "vert_to_horiz" in engines

    # 가로판 결합은 sero 엔진의 입력 파이프 상속 (코드 파싱/GDrive 매칭 재사용)
    from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine
    assert isinstance(engines["mockexam_horiz_merge"], MockexamSeroMergeEngine)

    for mid in ("slim_merge", "mockexam_horiz_merge"):
        e = engines[mid]
        tpl = os.path.join(REPO, "templates", e.template_name)
        assert os.path.isfile(tpl), f"템플릿 없음: {tpl}"
        assert f'const MATERIAL_ID = "{mid}"' in open(tpl, encoding="utf-8").read()
        jsx = os.path.join(REPO, "engines", mid, "jsx", "run.jsx")
        assert os.path.isfile(jsx), f"JSX 없음: {jsx}"
        src = open(jsx, encoding="utf-8").read()
        assert "__SETTINGS_PATH__" in src              # 토큰 치환 계약
        assert "settings 로드 실패" in src              # 부트스트랩 try-catch

    # 카테고리 재편: [가공] 섹션 = 결합/변환/편집 3그룹, 이동 카드 URL 보존
    subjects = json.load(open(os.path.join(REPO, "data", "subjects.json"),
                              encoding="utf-8"))
    proc = [b for b in subjects if b.get("section") == "가공"]
    assert [b["category"] for b in proc] == ["결합", "변환", "편집"]
    typeset_cats = {b["category"] for b in subjects if b.get("section") == "조판"}
    assert "결합 도구" not in typeset_cats             # [조판]에서 도구 제거
    items = {i["engine_id"]: i for b in proc for i in b["items"]}
    for mid in ("mockexam_sero_merge", "analysis_merge",
                "mothertongue_merge", "vert_to_horiz",
                "slim_merge", "mockexam_horiz_merge"):
        assert items[mid]["url"] == f"/typeset/{mid}"  # 라우트 무변경 (이동만)
    assert "workbook_edit" in items                    # 기존 가공 카드 유지
