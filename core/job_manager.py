import json
import queue
import time
import uuid
import os
import shutil
from config import JOBS_DIR

# {job_id: {"status": str, "q": Queue, "result": dict|None, "material_id": str}}
_jobs: dict = {}

# 잡을 "진행 중"으로 볼 최대 나이. 스레드가 예외로 죽어 done/fail을 못 부른
# 좀비 잡이 영원히 개발 자동 재시작을 막는 일을 방지 (reload_guard가 참조).
_ACTIVE_MAX_AGE = 6 * 3600


def create_job(material_id: str) -> str:
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(os.path.join(job_dir, "uploads"), exist_ok=True)
    _jobs[job_id] = {
        "status": "pending",
        "created": time.time(),
        "q": queue.Queue(),
        "result": None,
        "material_id": material_id,
        "dir": job_dir,
    }
    return job_id


def get_job(job_id: str):
    return _jobs.get(job_id)


def active_job_ids() -> list:
    """아직 끝나지 않은 잡 id 목록 (좀비 방지로 6시간 넘은 것은 제외)."""
    now = time.time()
    return [jid for jid, j in _jobs.items()
            if j["status"] in ("pending", "running")
            and now - j.get("created", now) < _ACTIVE_MAX_AGE]


def _persist_result(job_id: str, job: dict):
    """결과를 잡 폴더에 남긴다 — 서버가 재시작돼도 결과 화면을 되살리기 위함.
    인메모리 _jobs 는 프로세스와 함께 사라진다 (2026-09-12 실증: 개발 자동
    재시작이 조판 중인 잡을 지워 '작업 결과를 찾을 수 없습니다'). 저장 실패가
    조판 결과를 망치면 안 되므로 전부 fail-open."""
    try:
        path = os.path.join(job.get("dir") or os.path.join(JOBS_DIR, job_id),
                            "result.json")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"status": job["status"], "result": job["result"],
                       "material_id": job.get("material_id"),
                       "saved_at": time.time()},
                      f, ensure_ascii=False, default=str)
    except Exception:
        pass


def load_result(job_id: str):
    """디스크에 남은 결과 (인메모리 잡이 사라진 뒤 조회용). 없으면 None."""
    path = os.path.join(JOBS_DIR, job_id, "result.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def put_log(job_id: str, msg: str):
    job = _jobs.get(job_id)
    if job:
        job["q"].put(msg)


def done(job_id: str, result: dict):
    job = _jobs.get(job_id)
    if job:
        job["status"] = "done"
        job["result"] = result
        _persist_result(job_id, job)
        job["q"].put("__DONE__")


def fail(job_id: str, error: str):
    job = _jobs.get(job_id)
    if job:
        job["status"] = "error"
        job["result"] = {"ok": False, "error": error}
        _persist_result(job_id, job)
        job["q"].put("__DONE__")


def cancel_job(job_id: str):
    job = _jobs.get(job_id)
    if job and job["status"] in ("pending", "running"):
        job["cancelled"] = True
        job["status"] = "cancelled"
        job["result"] = {"ok": False, "error": "사용자가 취소했습니다."}
        _persist_result(job_id, job)
        job["q"].put("__DONE__")


def is_cancelled(job_id: str) -> bool:
    job = _jobs.get(job_id)
    return bool(job and job.get("cancelled"))


def stream(job_id: str):
    """SSE 제너레이터. 큐에서 메시지를 꺼내 text/event-stream 형식으로 yield."""
    job = _jobs.get(job_id)
    if not job:
        yield "data: [ERROR] job not found\n\n"
        return
    while True:
        try:
            msg = job["q"].get(timeout=30)
            if msg == "__DONE__":
                yield "data: [DONE]\n\n"
                break
            # 줄바꿈을 이스케이프해서 SSE 포맷 유지
            safe = msg.replace("\n", " ")
            yield f"data: {safe}\n\n"
        except queue.Empty:
            yield "data: [PING]\n\n"
