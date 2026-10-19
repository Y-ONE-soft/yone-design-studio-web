# -*- coding: utf-8 -*-
"""routes/api_v1 — 카탈로그 계약 · 렌더 잡 · 파일 · 웹훅 서명.

조판(Vivliostyle)은 돌리지 않는다 — `jobs.run_cmd` 를 가짜로 바꿔 PDF 를 흉내 낸다.
"""
import importlib
import json
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def app(monkeypatch, tmp_path):
    for k in ("YONE_AUTH", "YOS_LINK_SECRET", "SERVICE_TOKEN", "YOS_SERVICE_TOKENS", "YOS_WEBHOOK_URL",
              "YOS_WEBHOOK_SECRET", "YOS_CONTENTS_API", "YONE_PUBLIC_URL", "BLOB_READ_WRITE_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("YONE_STUDIO_ROOT", str(tmp_path))
    (tmp_path / "조판" / "교재").mkdir(parents=True)
    import studio_server
    importlib.reload(studio_server)
    a = studio_server.create_app()
    a.config["TESTING"] = True
    return a


def _first_design(client):
    cat = client.get("/api/v1/catalog").get_json()
    for d in cat["dirs"]:
        for t in d["templates"]:
            if t["designs"] and t.get("pipeline") != "workbook_v2" and t.get("ready") != "manual":
                return t, t["designs"][0]
    pytest.skip("카탈로그에 디자인이 없다")


def test_catalog_contract(app):
    c = app.test_client()
    r = c.get("/api/v1/catalog")
    assert r.status_code == 200
    body = r.get_json()
    assert "dirs" in body and body["dirs"]
    t, d = _first_design(c)
    for k in ("series", "name", "ready", "designs", "slots", "dir"):
        assert k in t
    for k in ("id", "name", "version", "masters", "previews"):
        assert k in d
    assert "intake" not in d                       # PDF 판정 원문은 계약이 아니다
    assert len(d["version"]) == 10
    for m in d["masters"] + d["previews"]:
        assert m["url"].startswith("http://localhost/api/v1/catalog/")
        assert c.get(m["url"].replace("http://localhost", "")).status_code == 200
    one = c.get(f"/api/v1/catalog/{t['series']}/{d['id']}").get_json()
    assert one["template"]["series"] == t["series"] and "config" in one and "page" in one["config"]
    assert c.get(f"/api/v1/catalog/{t['series']}/nope").status_code == 404
    assert c.get(f"/api/v1/catalog/{t['series']}/{d['id']}/image/../config.json").status_code == 404


def test_editor_design_fields(app):
    # 편집기 제작 디자인은 상위 페이지마다 데이터 필드 자리(mm)를 낸다 — contents 간지 지면 위 고치기
    c = app.test_client()
    one = c.get("/api/v1/catalog/analysis/x009d5556").get_json()
    gan = next(p for p in one["pages"] if p["name"] == "간지")
    assert (gan["w"], gan["h"]) == (210, 297)
    assert [f["bind"] for f in gan["fields"]] == ["학교", "권번호", "교재명+강제목"]
    assert all(f["w"] and f["h"] for f in gan["fields"])
    assert "pages" not in c.get("/api/v1/catalog/analysis/x9d242bf3").get_json()      # PDF 등록 디자인은 없다


def test_health_public(app):
    r = app.test_client().get("/api/v1/health")
    assert r.status_code == 200 and r.get_json()["ok"] is True and r.get_json()["auth"] == "off"
    assert "vivliostyle" in r.get_json()                  # 계약 칸 — 나중에 뽑을 때 쓰는 Vivliostyle 이 깔렸나


def test_render_validation(app):
    # 찍기는 편집기 제작 디자인만 — 예전 조판 디자인 · 모르는 틀 · 원고 꼴이 틀리면 400 (2026-10-19 예전 엔진 지움)
    c = app.test_client()
    assert c.post("/api/v1/renders", json={"series": "nope"}).status_code == 400
    r = c.post("/api/v1/renders", json={"series": "analysis", "design": "x9d242bf3", "book": {"title": "x"},
                                        "source": {"type": "data", "data": {}}})
    assert r.status_code == 400 and "편집기 제작" in r.get_json()["error"]
    r = c.post("/api/v1/renders", json={"series": "analysis", "design": "x009d5556", "book": {"title": "x"},
                                        "source": {"type": "data", "data": {"format": "wat"}}})
    assert r.status_code == 400 and "yos-analysis-v1" in r.get_json()["error"]
    assert c.get("/api/v1/books").status_code == 404 and c.post("/api/v1/embed-token", json={}).status_code == 404


def test_jobs_lost_on_boot(tmp_path, monkeypatch):
    monkeypatch.setenv("YONE_STUDIO_ROOT", str(tmp_path))
    from core import jobs
    d = tmp_path / "_jobs"; d.mkdir()
    (d / "abc123abc123.json").write_text(json.dumps({"id": "abc123abc123", "status": "running", "log": []}),
                                         encoding="utf-8")
    jobs.mark_lost_on_boot()
    j = jobs.get("abc123abc123")
    assert j.status == "lost" and "재시작" in j.to_dict()["log"][-1]


def test_blob_upload_of_pdfs_and_catalog_images(app, monkeypatch, tmp_path):
    """BLOB_READ_WRITE_TOKEN 이 있으면 카탈로그 이미지는 public 으로 올린다(찍은 PDF 는 편집기 찍기 시험에서)."""
    import shutil
    from routes import catalog as catmod, intake as intakemod
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_STORE123_secretpart")
    # blob.json 캐시가 리포의 catalog/ 에 남지 않게 사본에서 돈다
    tmp_cat = tmp_path / "catalog"
    shutil.copytree(os.path.join(REPO, "catalog"), tmp_cat)
    monkeypatch.setattr(catmod, "CATALOG", str(tmp_cat))
    monkeypatch.setattr(intakemod, "CATALOG", str(tmp_cat))
    c = app.test_client()
    calls = []

    class R:
        status_code = 200
        text = ""

        def __init__(self, path):
            self._p = path

        def json(self):
            return {"url": "https://store123.public.blob.vercel-storage.com/" + self._p + "-abc",
                    "downloadUrl": "…", "pathname": self._p, "contentType": "x", "contentDisposition": "x", "etag": "e"}

    def fake_put(url, data=None, headers=None, timeout=0):
        import urllib.parse
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        calls.append((q["pathname"][0], headers, len(data)))
        return R(q["pathname"][0])
    import requests
    monkeypatch.setattr(requests, "put", fake_put)

    cat = c.get("/api/v1/catalog").get_json()
    imgs = [m for dd in cat["dirs"] for tt in dd["templates"] for ds in tt["designs"] for m in ds["masters"]]
    if imgs:
        assert imgs[0]["url"].startswith("https://store123.public.blob.vercel-storage.com/studio/catalog/")
        first = [x for x in calls if x[0].startswith("studio/catalog/")][0]
        assert first[1]["x-vercel-blob-access"] == "public" and first[1]["x-api-version"] == "12"
        assert first[1]["x-vercel-blob-store-id"] == "STORE123"
        n = len(calls)
        c.get("/api/v1/catalog")                          # 두 번째는 캐시(blob.json) — 다시 안 올린다
        assert len(calls) == n
