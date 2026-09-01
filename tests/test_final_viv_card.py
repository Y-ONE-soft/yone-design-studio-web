# -*- coding: utf-8 -*-
"""파이널 Vivliostyle 카드 — 등록과 무회귀 계약.

지키려는 것: 새 카드가 **기존 파이널을 건드리지 않는다**. 백엔드 분기는
`render_backend` 한 값으로만 일어나고, 기존 `final` 은 InDesign 그대로다.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import engines.registry as registry            # noqa: E402
from engines.final_viv.engine import book_config  # noqa: E402


def test_card_is_registered():
    e = registry.get("final_viv")
    assert e.display_name == "파이널 직전보충 (Vivliostyle)"
    assert e.template_name == "typeset_final_viv.html"


def test_existing_final_card_is_untouched():
    """새 카드는 opt-in — 기존 파이널은 InDesign 경로 그대로."""
    assert registry.get("final").render_backend == "indesign"
    assert registry.get("final_viv").render_backend == "vivliostyle"


def test_card_appears_on_the_index():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    raw = open(os.path.join(root, "data", "subjects.json"),
               encoding="utf-8").read()
    assert '"engine_id": "final_viv"' in raw
    assert '"engine_id": "final"' in raw        # 기존 카드도 그대로


def test_template_exists_and_points_at_the_new_card():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(root, "templates", "typeset_final_viv.html")
    body = open(p, encoding="utf-8").read()
    assert 'MATERIAL_ID = "final_viv"' in body


def test_book_config_is_a_complete_book():
    """책 폴더엔 config.json + 원고만 둔다 — 그 config 가 온전해야 한다."""
    c = book_config("광문2", "고2", "26-1-기말", 1)
    assert c["series"] == "final"
    assert c["options"]["vol"] == 1
    assert c["manuscript"]["dir"] == "../원고"
    assert c["page"]["bleed"] == 3
    assert c["print"]["gray_map"]["#ffffff"] == 0.0
    assert {f["family"] for f in c["fonts"]} == {"Noto", "Neolli", "Jalnan"}
    json.dumps(c)                              # 파일로 나갈 수 있어야 한다


def test_card_builds_without_workbook_uploads(monkeypatch, tmp_path):
    """카드는 워크북 업로드 없이 선다 — 학교·학년·시험기간 세 값뿐.

    범위를 못 읽으면 **부모의 되수확 경로로 물러난다**(멈추지 않는다).
    """
    from engines.final_viv.engine import FinalVivEngine
    e = FinalVivEngine()
    for name, val in (("school", "광문2"), ("grade", "고2"),
                      ("exam_period", "26-1-기말")):
        (tmp_path / (name + ".txt")).write_text(val, encoding="utf-8")

    made = {}
    monkeypatch.setattr(e, "_scratch",
                        lambda s, g, p, log: {"vol1": {"문장배열": [{"header": "x"}]},
                                              "vol2": {}, "school": s})
    out = e.parse({}, str(tmp_path), lambda m: made.setdefault("log", []) or
                  made["log"].append(m))
    assert out.endswith("content.json") and os.path.exists(out)

    # 범위를 못 읽으면 부모 경로 — 여기서는 부모를 세워 두고 호출만 확인한다
    monkeypatch.setattr(e, "_scratch", lambda *a, **k: None)
    from engines.final.engine import FinalEngine
    monkeypatch.setattr(FinalEngine, "parse",
                        lambda self, u, j, log: "FELLBACK")
    assert e.parse({}, str(tmp_path), lambda m: None) == "FELLBACK"
