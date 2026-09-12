"""개발용 자동 재시작(Flask/Werkzeug reloader)이 진행 중인 잡을 죽이지 않게 미룬다.

배경 — app.py 는 `debug=True, use_reloader=True` 로 뜬다. 저장소 안 .py 를
하나라도 고치면(다른 작업 세션의 편집, autosync 의 git pull, tests 수정 포함)
Werkzeug 가 프로세스를 통째로 다시 띄운다. 그러면
  * 인메모리 `_jobs` 가 사라져 브라우저가 "작업 결과를 찾을 수 없습니다" 를 받고,
  * 조판 파이프라인의 파이썬 쪽(폴러·후처리·검수)이 그 자리에서 끊긴다.
InDesign JSX 는 별도 프로세스라 계속 돌지만, 끝나도 검수/PDF/결과 화면이 없다.
(2026-09-12 실증: 14:26 시작한 workbook_v2 잡 f7960153 이 14:35
 engines/convert_to_vertical/engine.py 저장으로 끊김.)

수리 — 재시작 자체를 막지 않고 **미룬다**. 진행 중인 잡이 하나도 없을 때까지
기다렸다가 그때 재시작하므로, 개발 중 코드 반영 편의는 그대로 유지된다.
"""
import sys
import time

# 잡이 끝나기를 기다리는 최대 시간. 이보다 오래 걸리는 조판은 없다고 보고,
# 만에 하나 상태가 꼬여도 재시작이 영영 막히지 않게 하는 안전판.
MAX_DEFER_SEC = 3 * 3600
POLL_SEC = 5


def _say(msg: str):
    print(f" * [재시작보류] {msg}", file=sys.stderr, flush=True)


def install(max_defer_sec: int = MAX_DEFER_SEC, poll_sec: int = POLL_SEC):
    """Werkzeug 리로더의 trigger_reload 를 감싼다. 실패해도 서버 기동은 막지 않는다."""
    try:
        from werkzeug import _reloader
    except Exception as e:      # werkzeug 내부 구조가 바뀐 경우 — 조용히 포기
        print(f" * [재시작보류] 설치 실패(무시): {e}", file=sys.stderr, flush=True)
        return False

    import core.job_manager as jm

    orig_trigger = _reloader.ReloaderLoop.trigger_reload

    def guarded_trigger(self, filename):
        waited = 0
        announced = False
        while waited < max_defer_sec:
            active = jm.active_job_ids()
            if not active:
                break
            if not announced:
                _say(f"조판 {len(active)}개 진행 중({', '.join(active)}) — "
                     f"끝나면 재시작합니다. 바뀐 파일: {filename}")
                announced = True
            elif waited % 300 == 0:
                _say(f"{waited // 60}분째 대기 중 (잡 {len(active)}개)")
            time.sleep(poll_sec)
            waited += poll_sec
        if announced:
            _say(f"{waited // 60}분 {waited % 60}초 대기 후 재시작")
        return orig_trigger(self, filename)

    _reloader.ReloaderLoop.trigger_reload = guarded_trigger
    _say("설치됨 — 조판 진행 중에는 코드 변경 자동 재시작을 미룹니다")
    return True
