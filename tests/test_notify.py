"""core/notify.py — 조판 완료/실패 macOS 알림 (C1-4). osascript는 모킹."""
import subprocess
from unittest import mock

from core import notify


def _run_capture(calls):
    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, b"", b"")
    return fake_run


def test_send_invokes_osascript(monkeypatch):
    monkeypatch.delenv("YONE_NOTIFY", raising=False)
    calls = []
    with mock.patch.object(notify.subprocess, "run", _run_capture(calls)):
        ok = notify.send("제목", "본문")
    assert ok
    assert len(calls) == 1
    assert calls[0][0] == "osascript"
    script = calls[0][2]
    assert 'display notification "본문"' in script
    assert 'with title "제목"' in script


def test_send_escapes_quotes_and_backslashes(monkeypatch):
    monkeypatch.delenv("YONE_NOTIFY", raising=False)
    calls = []
    with mock.patch.object(notify.subprocess, "run", _run_capture(calls)):
        notify.send('t"x', 'a\\b"c')
    script = calls[0][2]
    assert '\\"' in script          # 따옴표 이스케이프
    assert "a\\\\b" in script       # 역슬래시 이스케이프


def test_disabled_by_env(monkeypatch):
    monkeypatch.setenv("YONE_NOTIFY", "0")
    calls = []
    with mock.patch.object(notify.subprocess, "run", _run_capture(calls)):
        ok = notify.send("제목", "본문")
    assert not ok
    assert calls == []              # osascript 호출 자체가 없어야 함


def test_fail_open_on_exception(monkeypatch):
    """osascript가 죽어도 예외가 밖으로 던져지면 안 됨 (파이프라인 보호)."""
    monkeypatch.delenv("YONE_NOTIFY", raising=False)
    def boom(*a, **k):
        raise OSError("osascript not found")
    with mock.patch.object(notify.subprocess, "run", boom):
        ok = notify.send("제목", "본문")   # 예외 없이 False만
    assert ok is False


def test_job_finished_success_message(monkeypatch):
    monkeypatch.delenv("YONE_NOTIFY", raising=False)
    calls = []
    with mock.patch.object(notify.subprocess, "run", _run_capture(calls)):
        notify.notify_job_finished("워크북(모의고사)", "abcdef1234567890", ok=True)
    script = calls[0][2]
    assert "워크북(모의고사)" in script
    assert "abcdef12" in script          # job_id 앞 8자
    assert "1234567890" not in script    # 전체 id는 아님
    assert "성공" in script
    assert "조판 완료" in script


def test_job_finished_failure_message_with_summary(monkeypatch):
    monkeypatch.delenv("YONE_NOTIFY", raising=False)
    calls = []
    with mock.patch.object(notify.subprocess, "run", _run_capture(calls)):
        notify.notify_job_finished(
            "화이트북", "deadbeefcafe", ok=False,
            error="파싱 실패: 지문 번호 없음\n(traceback...)")
    script = calls[0][2]
    assert "화이트북" in script
    assert "deadbeef" in script
    assert "실패" in script
    assert "파싱 실패: 지문 번호 없음" in script   # 첫 줄만
    assert "traceback" not in script


def test_job_finished_failure_without_error():
    calls = []
    with mock.patch.object(notify.subprocess, "run", _run_capture(calls)):
        notify.notify_job_finished("교재", "12345678", ok=False, error="")
    assert "원인 미상" in calls[0][2]


def test_job_finished_failure_long_error_truncated(monkeypatch):
    monkeypatch.delenv("YONE_NOTIFY", raising=False)
    calls = []
    with mock.patch.object(notify.subprocess, "run", _run_capture(calls)):
        notify.notify_job_finished("교재", "12345678", ok=False,
                                   error="x" * 500)
    script = calls[0][2]
    assert "x" * 121 not in script
    assert "…" in script
