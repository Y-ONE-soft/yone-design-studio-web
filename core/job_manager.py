import queue
import uuid
import os
import shutil
from config import JOBS_DIR

# {job_id: {"status": str, "q": Queue, "result": dict|None, "material_id": str}}
_jobs: dict = {}


def create_job(material_id: str) -> str:
    job_id = str(uuid.uuid4())[:8]
    job_dir = os.path.join(JOBS_DIR, job_id)
    os.makedirs(os.path.join(job_dir, "uploads"), exist_ok=True)
    _jobs[job_id] = {
        "status": "pending",
        "q": queue.Queue(),
        "result": None,
        "material_id": material_id,
        "dir": job_dir,
    }
    return job_id


def get_job(job_id: str):
    return _jobs.get(job_id)


def put_log(job_id: str, msg: str):
    job = _jobs.get(job_id)
    if job:
        job["q"].put(msg)


def done(job_id: str, result: dict):
    job = _jobs.get(job_id)
    if job:
        job["status"] = "done"
        job["result"] = result
        job["q"].put("__DONE__")


def fail(job_id: str, error: str):
    job = _jobs.get(job_id)
    if job:
        job["status"] = "error"
        job["result"] = {"ok": False, "error": error}
        job["q"].put("__DONE__")


def cancel_job(job_id: str):
    job = _jobs.get(job_id)
    if job and job["status"] in ("pending", "running"):
        job["cancelled"] = True
        job["status"] = "cancelled"
        job["result"] = {"ok": False, "error": "사용자가 취소했습니다."}
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
