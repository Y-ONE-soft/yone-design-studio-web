"""조판 완료/실패 macOS 알림 (리스크분석 C1-4).

osascript `display notification`으로 잡 종료 시 알림을 띄운다.
"돌려놓고 잊기"용 — 사용자가 로그 화면을 계속 보지 않아도 결과를 알 수 있다.

설계 원칙 (fail-open):
- 알림 실패가 조판 파이프라인에 절대 영향을 주면 안 된다 — 모든 예외를
  삼키고 stdout 로그만 남긴다.
- 환경변수 YONE_NOTIFY=0 으로 끌 수 있다 (기본 켬).
"""
import os
import subprocess


def _enabled() -> bool:
    return os.environ.get("YONE_NOTIFY", "1") != "0"


def _esc(s: str) -> str:
    """AppleScript 문자열 리터럴 이스케이프 (역슬래시 → 따옴표 순서)."""
    return s.replace("\\", "\\\\").replace('"', '\\"')


def send(title: str, message: str, subtitle: str = "") -> bool:
    """macOS 알림 표시. 성공 여부 반환 (실패해도 예외는 던지지 않음)."""
    if not _enabled():
        return False
    try:
        script = (f'display notification "{_esc(message)}" '
                  f'with title "{_esc(title)}"')
        if subtitle:
            script += f' subtitle "{_esc(subtitle)}"'
        subprocess.run(["osascript", "-e", script],
                       capture_output=True, timeout=10)
        return True
    except Exception as e:
        # fail-open: 알림 실패는 로그만 남기고 무시
        try:
            print(f"[notify] 알림 실패 (무시): {e}", flush=True)
        except Exception:
            pass
        return False


def notify_job_finished(material_name: str, job_id: str, ok: bool,
                        error: str = "") -> bool:
    """잡 종료 알림 — 교재명 + job_id 앞 8자 + 성공/실패 (+실패 요약 1줄)."""
    short_id = (job_id or "")[:8]
    if ok:
        title = f"조판 완료 ✅ {material_name}"
        message = f"job {short_id} 성공"
    else:
        title = f"조판 실패 ❌ {material_name}"
        summary = (error or "").strip().splitlines()[0] if (error or "").strip() else "원인 미상"
        if len(summary) > 120:
            summary = summary[:120] + "…"
        message = f"job {short_id} 실패: {summary}"
    return send(title, message)
