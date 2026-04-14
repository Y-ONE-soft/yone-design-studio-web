"""InDesign 실행 락 — 동시 실행 방지.

파일 기반 락으로, 웹사이트·Claude CLI 등 어디서 실행하든
InDesign 스크립트가 한 번에 하나만 돌도록 보장.
"""

import os
import time
import json

LOCK_FILE = "/tmp/indesign_exec.lock"
LOCK_TIMEOUT = 600  # 10분 이상 된 락은 자동 해제 (좀비 방지)


def acquire(job_name="unknown", timeout=300):
    """락 획득. 다른 작업이 끝날 때까지 대기. timeout(초) 초과 시 강제 획득."""
    waited = 0
    while os.path.exists(LOCK_FILE):
        try:
            with open(LOCK_FILE) as f:
                info = json.load(f)
            age = time.time() - info.get("time", 0)
            # 좀비 락 제거
            if age > LOCK_TIMEOUT:
                release()
                break
            if waited == 0:
                print(f"[InDesign 큐] '{info.get('job', '?')}' 작업 완료 대기 중...")
        except (json.JSONDecodeError, IOError):
            release()
            break

        time.sleep(3)
        waited += 3
        if waited >= timeout:
            print(f"[InDesign 큐] {timeout}초 대기 초과 — 강제 진행")
            release()
            break

    # 락 생성
    with open(LOCK_FILE, "w") as f:
        json.dump({"job": job_name, "time": time.time(), "pid": os.getpid()}, f)


def release():
    """락 해제."""
    try:
        os.remove(LOCK_FILE)
    except FileNotFoundError:
        pass


def is_locked():
    """현재 락 상태 확인."""
    if not os.path.exists(LOCK_FILE):
        return False, None
    try:
        with open(LOCK_FILE) as f:
            info = json.load(f)
        age = time.time() - info.get("time", 0)
        if age > LOCK_TIMEOUT:
            release()
            return False, None
        return True, info
    except (json.JSONDecodeError, IOError):
        return False, None
