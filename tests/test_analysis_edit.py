# -*- coding: utf-8 -*-
"""분석본 지면 위 고치기(routes/analysis_edit) — 그리기 · 되돌리기 경로"""
import json
import os

import pytest

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "analysis_docs.json")
DESIGN = "x009d5556"                                                      # 광문 스텝업 분석본 (편집기 제작)


@pytest.fixture
def client():
    from studio_server import create_app
    app = create_app()
    app.testing = True
    return app.test_client()


def test_render_and_doc_roundtrip(client):
    doc = json.load(open(FIX, encoding="utf-8"))[0]["doc"]
    assert client.get(f"/analysis-edit?design={DESIGN}").status_code == 200
    assert client.get("/analysis-edit?design=nope").status_code == 400
    r = client.post("/analysis-edit/render", json={"design": DESIGN, "doc": doc}).get_json()
    assert len(r["svgs"]) == 2 and r["rec"]["문장+해석"]
    rec = r["rec"]
    d = client.post("/analysis-edit/doc", json={"rec": rec, "base": doc}).get_json()
    assert d == {"doc": doc, "changed": []}
    rec["문장+해석"][0]["해석"] = "고친 해석"
    d = client.post("/analysis-edit/doc", json={"rec": rec, "base": doc}).get_json()
    assert d["changed"] == [f"해석 {doc['sentences'][0]['no']}"] and d["doc"]["sentences"][0]["ko"] == "고친 해석"
