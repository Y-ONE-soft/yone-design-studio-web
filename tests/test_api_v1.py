# -*- coding: utf-8 -*-
"""routes/api_v1 — 카탈로그 계약 · 렌더 잡 · 파일 · 웹훅 서명.

조판(Vivliostyle)은 돌리지 않는다 — `jobs.run_cmd` 를 가짜로 바꿔 PDF 를 흉내 낸다.
"""
import importlib
import json
import os
import time

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
    assert "pages" not in c.get("/api/v1/catalog/analysis/d1").get_json()      # PDF 등록 · 예전 디자인은 없다


def test_health_public(app):
    r = app.test_client().get("/api/v1/health")
    assert r.status_code == 200 and r.get_json()["ok"] is True and r.get_json()["auth"] == "off"


def test_render_validation(app):
    c = app.test_client()
    assert c.post("/api/v1/renders", json={"series": "nope"}).status_code == 400
    t, d = _first_design(c)
    r = c.post("/api/v1/renders", json={"series": t["series"], "design": d["id"], "book": {"name": "x"},
                                        "source": {"type": "data", "data": {}}})
    assert r.status_code == 400 and "period" in r.get_json()["error"]
    r = c.post("/api/v1/renders", json={"series": t["series"], "design": d["id"],
                                        "book": {"name": "x", "period": "27-1"}, "source": {"type": "wat"}})
    assert r.status_code == 400
    r = c.post("/api/v1/renders", json={"series": t["series"], "design": d["id"],
                                        "book": {"name": "x", "period": "27-1"}, "source": {"type": "yos"}})
    assert r.status_code == 400 and "YOS_CONTENTS_API" in r.get_json()["error"]
    r = c.post("/api/v1/renders", json={"series": t["series"], "design": d["id"],
                                        "book": {"name": "x", "period": "27-1"},
                                        "source": {"type": "plan", "plan": {}}})
    assert r.status_code == 400 and "워크북" in r.get_json()["error"]


def _fake_run_cmd(pdf_name, rc=0):
    def run(job, cmd, cwd=None, timeout=0, env=None, quiet=()):
        d = cmd[cmd.index("core.render_vivlio.book") + 1]
        job.add("■ 가짜 조판 " + " ".join(cmd[-3:]))
        # 진짜 PDF 한 장 — 면 그림(pages/1.png) 까지 확인하려고
        import fitz
        doc = fitz.open(); doc.new_page(width=420, height=595); doc.save(os.path.join(d, pdf_name))
        return rc
    return run


def _wait(c, jid, seconds=10):
    for _ in range(int(seconds * 10)):
        s = c.get(f"/api/v1/renders/{jid}").get_json()
        if s["status"] not in ("queued", "running"):
            return s
        time.sleep(0.1)
    raise AssertionError("잡이 끝나지 않았다")


def test_render_data_source_end_to_end(app, monkeypatch, tmp_path):
    from core import jobs
    c = app.test_client()
    t, d = _first_design(c)
    sent = []
    monkeypatch.setenv("YOS_WEBHOOK_URL", "https://contents.example/hook")
    monkeypatch.setenv("YOS_WEBHOOK_SECRET", "whsec")
    monkeypatch.setenv("YONE_PUBLIC_URL", "https://studio.example")

    class R:
        status_code = 200

    def fake_post(url, data=None, headers=None, timeout=0):
        sent.append((url, data, headers))
        return R()
    import requests
    monkeypatch.setattr(requests, "post", fake_post)

    body = {"series": t["series"], "design": d["id"],
            "book": {"name": "테스트책", "period": "27-1-중간", "school": "이의고"},
            "knobs": {"page.bleed": 3},
            "source": {"type": "data", "data": {"hello": "world"}},
            "callback": {"ref": "book-42"}}
    stem = "이의고_테스트책_내지"
    monkeypatch.setattr(jobs, "run_cmd", _fake_run_cmd(stem + ".pdf"))
    r = c.post("/api/v1/renders", json=body)
    assert r.status_code == 202, r.get_json()
    j = r.get_json()
    assert j["book"]["key"].endswith(os.path.join("테스트책", "27-1-중간"))
    book_dir = tmp_path / j["book"]["key"]
    cfg = json.load(open(book_dir / "config.json", encoding="utf-8"))
    assert cfg["_카탈로그"]["design"] == d["id"] and cfg["_카탈로그"]["design_version"] == d["version"]
    assert cfg["book"]["school"] == "이의고" and cfg["output"]["stem"] == stem
    assert json.load(open(book_dir / "data.json", encoding="utf-8")) == {"hello": "world"}

    s = _wait(c, j["job"])
    assert s["status"] == "done", s["log"]
    assert s["result"]["main_pdf"] == stem + ".pdf" and s["result"]["pages"] == 1
    assert s["meta"]["steps"][0] == "build" and s["meta"]["steps"][-1] == "verify"
    assert s["urls"][stem + ".pdf"].startswith("https://studio.example/api/v1/renders/")
    assert s["urls"]["studio"].endswith("/book-studio?b=" + j["book"]["bid"])
    # 파일·면 그림
    assert c.get(f"/api/v1/renders/{j['job']}/files/{stem}.pdf").status_code == 200
    assert c.get(f"/api/v1/renders/{j['job']}/files/조판_로그.txt").status_code == 200
    assert c.get(f"/api/v1/renders/{j['job']}/files/../config.json").status_code == 404
    png = c.get(f"/api/v1/renders/{j['job']}/pages/1.png")
    assert png.status_code == 200 and png.data[:4] == b"\x89PNG"
    assert c.get(f"/api/v1/renders/{j['job']}/pages/2.png").status_code == 404
    # 목록 · 로그 since
    assert any(x["id"] == j["job"] for x in c.get("/api/v1/renders").get_json()["renders"])
    assert c.get(f"/api/v1/renders/{j['job']}?since=999").get_json()["log"] == []
    # 같은 책 다시 → 409, replace 면 된다
    assert c.post("/api/v1/renders", json=body).status_code == 409
    assert c.post("/api/v1/renders", json=dict(body, replace=True)).status_code == 202
    # 웹훅: 서명이 맞고 callback 이 그대로 돌아온다
    for _ in range(50):
        if sent:
            break
        time.sleep(0.1)
    assert sent, "웹훅이 안 갔다"
    url, data, headers = sent[0]
    from core import yos_hooks
    assert url == "https://contents.example/hook" and headers["x-studio-event"] == "render.finished"
    # core 의 chat/link.ts verifySignature 와 같은 규칙: hex HMAC-SHA256(비밀, 본문)
    import hashlib, hmac
    assert headers["x-studio-signature"] == hmac.new(b"whsec", data, hashlib.sha256).hexdigest()
    assert headers["x-studio-signature"] == yos_hooks.sign(data, "whsec")
    payload = json.loads(data)
    assert payload["render"]["callback"] == {"ref": "book-42"} and payload["render"]["status"] == "done"
    assert payload["render"]["files"][stem + ".pdf"].startswith("https://studio.example/api/v1/renders/")
    # 디스크 기록 — 재시작 뒤에도 물을 수 있다
    assert os.path.exists(tmp_path / "_jobs" / (j["job"] + ".json"))


def test_render_failed_when_no_pdf(app, monkeypatch):
    from core import jobs
    c = app.test_client()
    t, d = _first_design(c)

    def run(job, cmd, **kw):
        job.add("[오류] 가짜 실패")
        return 1
    monkeypatch.setattr(jobs, "run_cmd", run)
    r = c.post("/api/v1/renders", json={"series": t["series"], "design": d["id"],
                                        "book": {"name": "실패책", "period": "27-1"},
                                        "source": {"type": "data", "data": {}}})
    assert r.status_code == 202
    s = _wait(c, r.get_json()["job"])
    assert s["status"] == "failed" and s["rc"] == 1
    assert c.get(f"/api/v1/renders/{r.get_json()['job']}/pages/1.png").status_code == 404


def test_export_is_a_job(app, monkeypatch):
    """작업대 내보내기 — 요청은 바로 돌아오고 잡으로 진행된다."""
    from core import jobs
    from routes import book_studio
    c = app.test_client()
    monkeypatch.setattr(book_studio, "_book_dir", lambda k: ("/tmp/nope", {"key": "k", "bid": "b"}))
    monkeypatch.setattr(book_studio, "_last_pdf", lambda cfg, d: "/tmp/nope/x.pdf")
    monkeypatch.setattr(jobs, "run_cmd", lambda job, cmd, **kw: 0)
    import core.render_vivlio.book as bookmod
    monkeypatch.setattr(bookmod, "load", lambda d: None)
    r = c.post("/api/book-studio/export", json={"b": "k", "kind": "pdf"})
    assert r.status_code == 202 and r.get_json()["job"]
    jid = r.get_json()["job"]
    for _ in range(50):
        s = c.get(f"/api/book-studio/export/{jid}").get_json()
        if s["status"] not in ("queued", "running"):
            break
        time.sleep(0.1)
    assert s["status"] == "done" and s["result"]["pdf"] == "x.pdf"
    assert c.get("/api/book-studio/export/zzz").status_code == 404


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
    """BLOB_READ_WRITE_TOKEN 이 있으면 PDF 는 private, 카탈로그 이미지는 public 으로 같은 스토어에 올린다."""
    import shutil
    from core import jobs
    from routes import catalog as catmod, intake as intakemod
    monkeypatch.setenv("BLOB_READ_WRITE_TOKEN", "vercel_blob_rw_STORE123_secretpart")
    # blob.json 캐시가 리포의 catalog/ 에 남지 않게 사본에서 돈다
    tmp_cat = tmp_path / "catalog"
    shutil.copytree(os.path.join(REPO, "catalog"), tmp_cat)
    monkeypatch.setattr(catmod, "CATALOG", str(tmp_cat))
    monkeypatch.setattr(intakemod, "CATALOG", str(tmp_cat))
    c = app.test_client()
    t, d = _first_design(c)
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

    stem = "블롭책_내지"
    monkeypatch.setattr(jobs, "run_cmd", _fake_run_cmd(stem + ".pdf"))
    r = c.post("/api/v1/renders", json={"series": t["series"], "design": d["id"],
                                        "book": {"name": "블롭책", "period": "27-1"},
                                        "source": {"type": "data", "data": {}}})
    s = _wait(c, r.get_json()["job"])
    assert s["status"] == "done"
    b = s["result"]["blob"][stem + ".pdf"]
    assert b["pathname"] == f"studio/renders/{s['id']}/{stem}.pdf" and b["access"] == "private"
    pdf_call = [x for x in calls if x[0].endswith(stem + ".pdf")][0]
    assert pdf_call[1]["x-vercel-blob-access"] == "private" and pdf_call[1]["x-content-type"] == "application/pdf"
