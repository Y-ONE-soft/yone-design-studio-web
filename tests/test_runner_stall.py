"""core/indesign/runner.py — 스톨 처리 '킬 루프 금지' 가드 (2026-07-13).

배경: 2026-07-04 W4 사건 — 자동 SIGKILL 누적으로 InDesign 복구 데이터가
비가시 모달 30486을 만들어 스크립팅이 영구 차단됨. W15에서 runner 내장
스톨 처리가 여전히 pkill하는 경로가 실증돼(c04 2700초 비결정 스톨 →
자동 강제 종료 → 재제출은 1분 내 통과) 킬 경로를 제거하고
'알림 + 작업 보류 + 실패 반환'으로 전환했다. 이 테스트는 그 전환을 고정한다.
"""
import os
import tempfile
from unittest import mock

import pytest

from core import notify
from core.indesign import runner


def test_kill_helper_removed():
    """자동 강제 종료 헬퍼가 다시 생기면 즉시 실패."""
    assert not hasattr(runner, "_kill_indesign")


def _spy_subprocess(calls):
    real_run = runner.subprocess.run

    def spy(cmd, *a, **k):
        calls.append(cmd)
        return real_run(cmd, *a, **k)

    return spy


def test_stall_holds_notifies_and_never_kills():
    """스톨 감지 시: macOS 알림 + '작업 보류' RuntimeError, pkill 절대 금지."""
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False)
    tmp.write("조판 시작\n진행 중...\n")
    tmp.close()
    notify_calls = []
    subprocess_calls = []
    logs = []
    try:
        with mock.patch.object(runner.time, "sleep"), \
             mock.patch.object(notify, "send",
                               lambda *a, **k: notify_calls.append(a) or True), \
             mock.patch.object(runner.subprocess, "run",
                               _spy_subprocess(subprocess_calls)):
            with pytest.raises(RuntimeError) as exc:
                runner._wait_for_completion(tmp.name, logs.append,
                                            timeout=60, stall_limit=6)
    finally:
        os.unlink(tmp.name)

    msg = str(exc.value)
    assert "작업 보류" in msg
    assert "종료하지 않았습니다" in msg
    assert notify_calls and "스톨" in notify_calls[0][0]
    assert any("스톨 감지" in l for l in logs)
    assert not any("pkill" in str(c) for c in subprocess_calls)


def test_transient_retry_resubmits_without_kill():
    """일시적 실패 재시도는 '제출 재시도'만 — InDesign 프로세스 무접촉."""
    attempts = []
    subprocess_calls = []
    logs = []

    def fake_once(*a, **k):
        attempts.append(1)
        if len(attempts) == 1:
            raise RuntimeError("InDesign 스크립트 전달 실패: -609")

    with mock.patch.object(runner, "_run_jsx_once", fake_once), \
         mock.patch.object(runner.time, "sleep"), \
         mock.patch.object(runner.subprocess, "run",
                           _spy_subprocess(subprocess_calls)):
        runner.run_jsx("/tmp/fake.jsx", logs.append)

    assert len(attempts) == 2
    assert not any("pkill" in str(c) for c in subprocess_calls)


def test_non_transient_failure_no_retry():
    """hang/JSX 오류 등 비일시적 실패는 재시도 없이 그대로 실패 (기존 의미론 유지)."""
    attempts = []

    def fake_once(*a, **k):
        attempts.append(1)
        raise RuntimeError("InDesign 스톨 (로그 999초간 미갱신) — 작업 보류.")

    with mock.patch.object(runner, "_run_jsx_once", fake_once), \
         mock.patch.object(runner.time, "sleep"):
        with pytest.raises(RuntimeError):
            runner.run_jsx("/tmp/fake.jsx", lambda m: None)

    assert len(attempts) == 1
