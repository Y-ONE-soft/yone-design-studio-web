"""검수 에이전트 2층 자동화 (W41) — core/review_agent + 파이프라인 훅 + rerun.

InDesign/실 claude 호출 없이 전부 오프라인 (invoke_claude·subprocess는 mock).
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("YONE_SECRET_KEY", "test-secret-key")

from core import review_agent as ra  # noqa: E402


# ── 픽스처 헬퍼 ──────────────────────────────────────────────────────────────

def _mk_report(tmp_path, n=20, crit_pages=(4,), review_pages=(7, 9),
               with_pngs=True):
    pages = []
    for p in range(1, n + 1):
        png = str(tmp_path / "visual_pages" / f"page-{p:04d}.png")
        if with_pngs:
            os.makedirs(os.path.dirname(png), exist_ok=True)
            with open(png, "wb") as f:
                f.write(b"\x89PNG fake")
        flags = []
        if p in crit_pages:
            flags.append({"code": "OVERSET", "level": "critical",
                          "detail": "오버셋 스토리 8"})
        if p in review_pages:
            flags.append({"code": "NEAR_BLANK", "level": "review",
                          "detail": "잉크 0.1%"})
        pages.append({"page": p, "png": png, "flags": flags})
    return {
        "page_count": n,
        "pages": pages,
        "doc_flags": [],
        "summary": {"critical": len(crit_pages), "review": len(review_pages),
                    "flagged_pages": sorted(list(crit_pages) + list(review_pages))},
        "source": "/nonexistent/out.indd",   # PDF 아님 → 1층 PNG 재사용 경로
    }


def _structured(findings=None, verdict="pass"):
    return {
        "verdict": verdict,
        "pages_reviewed": [1, 4, 7],
        "findings": findings or [],
        "notes": "테스트 소견",
    }


# ── build_queue ──────────────────────────────────────────────────────────────

def test_queue_priority_and_cap():
    """critical > review > 고정 표본 > 무작위, max_pages 절단."""
    report = _mk_report_dictonly(n=50, crit=[40, 3], review=[10, 20, 30])
    q = ra.build_queue(report, max_pages=4)
    pages = [x["page"] for x in q]
    assert set(pages[:0] or pages) >= {3, 40}          # critical 전부 포함
    assert len(pages) == 4
    assert 10 in pages and 20 in pages                  # review 순서대로
    # critical 페이지 사유가 플래그 상세를 담는다
    rec = next(x for x in q if x["page"] == 40)
    assert any("OVERSET" in r for r in rec["reasons"])


def _mk_report_dictonly(n, crit, review):
    pages = []
    for p in range(1, n + 1):
        flags = []
        if p in crit:
            flags.append({"code": "OVERSET", "level": "critical", "detail": "x"})
        if p in review:
            flags.append({"code": "NEAR_BLANK", "level": "review", "detail": "y"})
        pages.append({"page": p, "png": f"/x/page-{p:04d}.png", "flags": flags})
    return {"page_count": n, "pages": pages, "doc_flags": [],
            "summary": {"critical": len(crit), "review": len(review),
                        "flagged_pages": sorted(crit + review)}}


def test_queue_includes_fixed_samples_when_clean():
    """플래그 없으면 고정 표본(첫/가운데/끝) + 무작위."""
    report = _mk_report_dictonly(n=30, crit=[], review=[])
    q = ra.build_queue(report, max_pages=10)
    pages = {x["page"] for x in q}
    assert {1, 15, 30} <= pages
    assert len(q) <= 10


def test_queue_empty_report():
    assert ra.build_queue({"page_count": 0, "pages": []}) == []


# ── 프롬프트/스키마 ──────────────────────────────────────────────────────────

def test_prompt_contains_checklist_and_judgements():
    p = ra.build_prompt()
    assert "C1" in p and "C8" in p                  # 체크리스트 재사용
    assert "auto_fixable" in p and "manuscript_error" in p
    assert "operator_judgment" in p
    assert ra.INPUT_FILENAME in p


def test_schema_judgement_enum():
    j = REVIEW_ITEM = ra.REVIEW_SCHEMA["properties"]["findings"]["items"]
    assert set(j["properties"]["judgement"]["enum"]) == {
        "auto_fixable", "manuscript_error", "operator_judgment"}
    assert set(ra.REVIEW_SCHEMA["properties"]["verdict"]["enum"]) == {
        "pass", "suspect", "fail"}


def test_find_claude_bin_env_override(tmp_path, monkeypatch):
    fake = tmp_path / "claude"
    fake.write_text("#!/bin/sh\n")
    monkeypatch.setenv("YONE_CLAUDE_BIN", str(fake))
    assert ra.find_claude_bin() == str(fake)


# ── invoke_claude (subprocess mock) ──────────────────────────────────────────

class _CP:
    def __init__(self, code, stdout="", stderr=""):
        self.returncode = code
        self.stdout = stdout
        self.stderr = stderr


def test_invoke_claude_structured_output(tmp_path, monkeypatch):
    out = {"structured_output": _structured(), "total_cost_usd": 0.5,
           "duration_ms": 1000, "num_turns": 3}
    captured = {}

    def fake_run(cmd, **kw):
        captured["cmd"] = cmd
        captured["kw"] = kw
        return _CP(0, stdout=json.dumps(out))

    monkeypatch.setattr(ra.subprocess, "run", fake_run)
    monkeypatch.setattr(ra, "find_claude_bin", lambda: "/fake/claude")
    structured, meta = ra.invoke_claude("prompt", str(tmp_path), None)
    assert structured["verdict"] == "pass"
    assert meta["cost_usd"] == 0.5
    cmd = captured["cmd"]
    # 읽기 전용 도구 제한 + 예산 상한이 항상 걸려 있어야 한다
    assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == "Read,Glob,Grep"
    assert "--max-budget-usd" in cmd
    assert "--json-schema" in cmd
    assert captured["kw"]["cwd"] == str(tmp_path)


def test_invoke_claude_fenced_fallback(tmp_path, monkeypatch):
    """structured_output 없으면 result 텍스트에서 JSON 추출."""
    txt = "```json\n" + json.dumps(_structured(verdict="suspect")) + "\n```"
    out = {"result": txt}
    monkeypatch.setattr(ra.subprocess, "run",
                        lambda cmd, **kw: _CP(0, stdout=json.dumps(out)))
    monkeypatch.setattr(ra, "find_claude_bin", lambda: "/fake/claude")
    structured, _ = ra.invoke_claude("p", str(tmp_path), None)
    assert structured["verdict"] == "suspect"


def test_invoke_claude_nonzero_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ra.subprocess, "run",
                        lambda cmd, **kw: _CP(1, stderr="boom"))
    monkeypatch.setattr(ra, "find_claude_bin", lambda: "/fake/claude")
    with pytest.raises(RuntimeError):
        ra.invoke_claude("p", str(tmp_path), None)


def test_invoke_claude_no_bin_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ra, "find_claude_bin", lambda: None)
    with pytest.raises(RuntimeError):
        ra.invoke_claude("p", str(tmp_path), None)


# ── run_review_agent (오프라인 E2E) ─────────────────────────────────────────

def test_run_review_agent_writes_report(tmp_path, monkeypatch):
    report = _mk_report(tmp_path)
    with open(tmp_path / "visual_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f)
    findings = [
        {"type": "잔존 템플릿", "check": "C5", "page": 4, "grade": "fail",
         "detail": "빈 STEP 페이지", "judgement": "auto_fixable",
         "suggestion": "재조판"},
        {"type": "번호 소실", "check": "C3", "page": 7, "grade": "suspect",
         "detail": "40-41 사이 무번호 문항", "judgement": "manuscript_error"},
    ]
    monkeypatch.setattr(
        ra, "invoke_claude",
        lambda prompt, job_dir, log, **kw:
            (_structured(findings, verdict="fail"),
             {"wall_s": 12.3, "cost_usd": 0.4, "duration_ms": 1, "num_turns": 2,
              "model": "sonnet", "is_error": False}))
    logs = []
    out = ra.run_review_agent(str(tmp_path), logs.append, result={"ok": True})
    assert out["verdict"] == "fail"
    assert out["counts"] == {"auto_fixable": 1, "manuscript_error": 1,
                             "operator_judgment": 0}
    # 리포트 + 입력 파일이 job_dir에 남는다
    with open(tmp_path / ra.REPORT_FILENAME, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved["reviewer"] == "claude-review-agent"
    assert saved["counts"]["auto_fixable"] == 1
    with open(tmp_path / ra.INPUT_FILENAME, encoding="utf-8") as f:
        rin = json.load(f)
    assert rin["layer1"]["critical"] == 1
    assert all(os.path.isfile(os.path.join(str(tmp_path), q["png"]))
               for q in rin["queue"])


def test_run_review_agent_skips_without_report(tmp_path, monkeypatch):
    """visual_report도 PDF도 없으면 None (fail-open 스킵)."""
    monkeypatch.setattr("core.visual_inspect.inspect_job_visual",
                        lambda *a, **kw: None)
    assert ra.run_review_agent(str(tmp_path), None, result={}) is None


def test_run_review_agent_skips_when_no_pngs(tmp_path, monkeypatch):
    """소스가 PDF도 아니고 1층 PNG도 없으면 스킵 (예외 없이)."""
    report = _mk_report(tmp_path, with_pngs=False)
    with open(tmp_path / "visual_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f)
    assert ra.run_review_agent(str(tmp_path), None, result={}) is None


# ── 파이프라인 훅 (opt-in + fail-open + warnings 합류) ───────────────────────

class _StubEngine:
    material_id = "stub"
    display_name = "스텁"
    skip_indesign = True

    def parse(self, uploaded, job_dir, log):
        return os.path.join(job_dir, "content.json")

    def verify(self, job_dir, log):
        return {"ok": True, "overflow": 0, "warnings": []}


def _run_pipeline_in(tmp_path, monkeypatch, optin, ra_impl):
    import core.job_manager as jm
    from core import pipeline
    monkeypatch.setattr(ra, "run_review_agent", ra_impl)
    monkeypatch.setenv("YONE_NOTIFY", "0")
    monkeypatch.delenv("YONE_REVIEW_AGENT", raising=False)
    monkeypatch.delenv("YONE_INSPECT", raising=False)
    monkeypatch.delenv("YONE_VISUAL_INSPECT", raising=False)
    monkeypatch.setattr("core.notify.notify_job_finished",
                        lambda *a, **kw: None)
    job_id = jm.create_job("stub")
    job_dir = jm.get_job(job_id)["dir"]
    if optin:
        open(os.path.join(job_dir, "review_agent.txt"), "w").write("1")
    pipeline.run_pipeline(_StubEngine(), job_id, job_dir, {})
    return jm.get_job(job_id)


def test_pipeline_hook_not_called_without_optin(tmp_path, monkeypatch):
    called = []
    job = _run_pipeline_in(tmp_path, monkeypatch, optin=False,
                           ra_impl=lambda *a, **kw: called.append(1))
    assert job["status"] == "done" and not called


def test_pipeline_hook_optin_appends_warnings(tmp_path, monkeypatch):
    summary = {
        "verdict": "fail",
        "counts": {"auto_fixable": 1, "manuscript_error": 1,
                   "operator_judgment": 1},
        "findings": [
            {"page": 4, "detail": "빈 페이지", "judgement": "auto_fixable"},
            {"page": 7, "detail": "번호 소실", "judgement": "manuscript_error"},
            {"page": 9, "detail": "단 구성 확인", "judgement": "operator_judgment"},
        ],
        "pages_reviewed": [4, 7, 9], "notes": "", "report_path": "/x",
        "cost_usd": 0.4, "wall_s": 10,
    }
    job = _run_pipeline_in(tmp_path, monkeypatch, optin=True,
                           ra_impl=lambda job_dir, log, result=None: summary)
    res = job["result"]
    assert res["ok"] is True                       # advisory — ok 무변경
    assert res["review_agent"]["verdict"] == "fail"
    warns = res.get("warnings", [])
    assert any("원고 오류" in w and "p7" in w for w in warns)
    assert any("확인 필요" in w and "p9" in w for w in warns)
    # auto_fixable은 warnings가 아니라 버튼 제안(review_agent.counts)으로만
    assert not any("p4" in w for w in warns)


def test_pipeline_hook_fail_open(tmp_path, monkeypatch):
    def boom(*a, **kw):
        raise RuntimeError("agent down")
    job = _run_pipeline_in(tmp_path, monkeypatch, optin=True, ra_impl=boom)
    assert job["status"] == "done" and job["result"]["ok"] is True
    assert "review_agent" not in job["result"]


# ── /api/run 영속화 + /api/rerun ─────────────────────────────────────────────

@pytest.fixture()
def client():
    import app as app_module
    with app_module.app.test_client() as c:
        with c.session_transaction() as s:
            s["authenticated"] = True
            s["role"] = "admin"
        yield c


def test_api_rerun_bad_id(client):
    r = client.post("/api/rerun/../etc")
    assert r.status_code == 404   # Flask 라우팅 자체가 슬래시 차단
    r = client.post("/api/rerun/ZZZZZZZZ")
    assert r.status_code == 400


def test_api_rerun_missing_job(client):
    r = client.post("/api/rerun/deadbeef")
    assert r.status_code == 404


def test_api_rerun_spawns_new_job(client, monkeypatch, tmp_path):
    import config
    import routes.typeset as tp
    import core.job_manager as jm
    # 옛 job 재료 구성
    old_id = "abc12345"
    old_dir = os.path.join(config.JOBS_DIR, old_id)
    os.makedirs(os.path.join(old_dir, "uploads"), exist_ok=True)
    up = os.path.join(old_dir, "uploads", "step1_원고.docx")
    open(up, "w").write("x")
    open(os.path.join(old_dir, "material_id.txt"), "w").write("stub_rerun")
    open(os.path.join(old_dir, "school.txt"), "w").write("테스트고")
    open(os.path.join(old_dir, "review_agent.txt"), "w").write("1")
    with open(os.path.join(old_dir, "uploaded.json"), "w",
              encoding="utf-8") as f:
        json.dump({"step1": [up], "memo": "텍스트값"}, f)

    stub = _StubEngine()
    monkeypatch.setattr(tp.registry, "get",
                        lambda mid: stub if mid == "stub_rerun"
                        else (_ for _ in ()).throw(KeyError(mid)))
    ran = {}

    def fake_pipeline(engine, job_id, job_dir, uploaded):
        ran.update(job_id=job_id, job_dir=job_dir, uploaded=uploaded)

    monkeypatch.setattr(tp, "run_pipeline", fake_pipeline)
    try:
        r = client.post(f"/api/rerun/{old_id}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["rerun_of"] == old_id
        new_dir = jm.get_job(data["job_id"])["dir"]
        # 스레드 완료 대기 (fake_pipeline은 즉시 반환)
        import time
        for _ in range(50):
            if ran:
                break
            time.sleep(0.1)
        assert ran["job_id"] == data["job_id"]
        # 업로드 파일이 새 job으로 복사되고 매핑 경로가 재작성됨
        new_up = ran["uploaded"]["step1"][0]
        assert new_up.startswith(new_dir) and os.path.isfile(new_up)
        assert ran["uploaded"]["memo"] == "텍스트값"
        # 메타 .txt 승계 (review_agent 포함 — 재조판도 재검수)
        assert open(os.path.join(new_dir, "school.txt")).read() == "테스트고"
        assert os.path.isfile(os.path.join(new_dir, "review_agent.txt"))
    finally:
        import shutil as _sh
        _sh.rmtree(old_dir, ignore_errors=True)
        if ran.get("job_dir"):
            _sh.rmtree(ran["job_dir"], ignore_errors=True)


def test_api_run_persists_rerun_material(client, monkeypatch):
    """api_run이 uploaded.json + material_id.txt + review_agent.txt를 남긴다."""
    import routes.typeset as tp
    import core.job_manager as jm
    stub = _StubEngine()
    stub.upload_spec = {"slots": [
        {"key": "step1", "label": "원고", "accept": ".docx", "required": False},
    ]}
    monkeypatch.setattr(tp.registry, "get",
                        lambda mid: stub if mid == "stub_run" else
                        (_ for _ in ()).throw(KeyError(mid)))
    monkeypatch.setattr(tp, "run_pipeline", lambda *a, **kw: None)
    import io
    r = client.post("/api/run/stub_run", data={
        "review_agent": "1",
        "step1": (io.BytesIO(b"docx"), "원고.docx"),
    }, content_type="multipart/form-data")
    assert r.status_code == 200
    job_id = r.get_json()["job_id"]
    job_dir = jm.get_job(job_id)["dir"]
    try:
        assert open(os.path.join(job_dir, "material_id.txt")).read() == "stub_run"
        assert os.path.isfile(os.path.join(job_dir, "review_agent.txt"))
        with open(os.path.join(job_dir, "uploaded.json"), encoding="utf-8") as f:
            up = json.load(f)
        assert up["step1"].endswith("step1_원고.docx")
    finally:
        import shutil as _sh
        _sh.rmtree(job_dir, ignore_errors=True)
