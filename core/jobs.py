# -*- coding: utf-8 -*-
"""오래 걸리는 일(조판·내보내기)을 **요청 밖에서** 돌리는 실행기.

웹으로 나가면 요청 하나가 100초를 넘기지 못한다(Cloudflare·대부분의 프록시).
전권 조판은 20초~수 분, 인쇄 원고까지는 그보다 길다. 그래서 요청은 잡을 만들고
바로 돌아가고, 화면(또는 contents)은 `id` 로 폴링한다.

    job = jobs.start("export", meta={"book": key}, fn=lambda job, log: ...)
    jobs.get(job.id)  →  {"status": "running", "log": [...], ...}

- 프로세스 하나 안의 인메모리 등록부 + 스레드. gunicorn 워커를 **1개**로 두는 이유.
- 상태는 `<스튜디오 루트>/_jobs/<id>.json` 에도 남긴다 — 재시작 뒤에도 결과를 물을 수 있고,
  돌던 잡은 `lost` 로 표시된다(다시 돌리는 건 사람이 결정).
- `run_cmd` 는 자식 프로세스 출력을 한 줄씩 로그에 넣는다(카탈로그 `_run` 과 같은 방식).
"""
import json
import os
import subprocess
import threading
import time
import uuid

_LOCK = threading.Lock()
_JOBS = {}
_LISTENERS = []          # fn(job) — 끝났을 때 (웹훅 등)
KEEP = 200               # 메모리에 남길 최근 잡 수


def _dir():
    from core.studio import studio_root
    d = os.path.join(studio_root(), "_jobs")
    os.makedirs(d, exist_ok=True)
    return d


class Job(object):
    def __init__(self, kind, meta=None):
        self.id = uuid.uuid4().hex[:12]
        self.kind = kind
        self.meta = dict(meta or {})
        self.status = "queued"          # queued | running | done | done_warn | failed | lost
        self.log = []
        self.result = {}
        self.rc = None
        self.error = None
        self.started = time.time()
        self.finished = None
        self.created_by = self.meta.pop("created_by", None)

    def add(self, line):
        line = str(line).rstrip()
        if line:
            self.log.append(line)

    def to_dict(self, since=0, full=False):
        d = {"id": self.id, "kind": self.kind, "status": self.status, "meta": self.meta,
             "result": self.result, "rc": self.rc, "error": self.error,
             "started": self.started, "finished": self.finished,
             "elapsed": round((self.finished or time.time()) - self.started),
             "created_by": self.created_by, "n": len(self.log)}
        d["log"] = self.log if full else self.log[since:]
        return d

    def save(self):
        try:
            p = os.path.join(_dir(), self.id + ".json")
            tmp = p + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.to_dict(full=True), f, ensure_ascii=False, indent=1)
            os.replace(tmp, p)
        except Exception:
            pass                        # 기록 실패가 조판을 막아선 안 된다


def start(kind, fn, meta=None):
    """`fn(job, log)` 를 스레드로 돌린다. 결과 dict 를 돌려주면 `job.result` 가 된다.

    `fn` 이 예외를 던지면 failed, `job.rc` 가 0 이 아니면 done_warn(산출은 있으나 검수 경고),
    그 외 done.
    """
    job = Job(kind, meta)
    with _LOCK:
        _JOBS[job.id] = job
        if len(_JOBS) > KEEP:
            for old in sorted(_JOBS.values(), key=lambda j: j.started)[:len(_JOBS) - KEEP]:
                if old.status not in ("queued", "running"):
                    _JOBS.pop(old.id, None)

    def _go():
        job.status = "running"
        job.save()
        try:
            r = fn(job, job.add)
            if isinstance(r, dict):
                job.result.update(r)
            if job.status == "running":
                job.status = "done" if (job.rc in (None, 0)) else "done_warn"
        except Exception as e:                          # noqa: BLE001
            job.error = str(e)
            job.add(f"[오류] {e}")
            job.status = "failed"
        job.finished = time.time()
        job.save()
        for cb in list(_LISTENERS):
            try:
                cb(job)
            except Exception as e:                      # noqa: BLE001
                job.add(f"[알림 실패] {e}")
        job.save()

    threading.Thread(target=_go, daemon=True, name=f"job-{kind}-{job.id}").start()
    return job


def get(jid):
    j = _JOBS.get(jid)
    if j:
        return j
    p = os.path.join(_dir(), str(jid) + ".json")
    if os.path.exists(p) and "/" not in str(jid) and ".." not in str(jid):
        try:
            return _Stored(json.load(open(p, encoding="utf-8")))
        except Exception:
            return None
    return None


def recent(kind=None, limit=50):
    js = [j for j in _JOBS.values() if kind is None or j.kind == kind]
    return sorted(js, key=lambda j: j.started, reverse=True)[:limit]


def on_finish(cb):
    """끝난 잡을 받을 콜백 등록. 같은 함수는 한 번만."""
    if cb not in _LISTENERS:
        _LISTENERS.append(cb)


def mark_lost_on_boot():
    """재시작 뒤: 디스크에 running 으로 남은 잡은 lost 로. 실제로 돌던 스레드는 죽었다."""
    try:
        for fn in os.listdir(_dir()):
            if not fn.endswith(".json"):
                continue
            p = os.path.join(_dir(), fn)
            if getattr(os.stat(p), "st_flags", 0) & 0x40000000:          # SF_DATALESS — iCloud 가 내려 둔 파일(내용 없음). 읽으면 내려받기를 기다려 기동이 멈췄다(디스크가 차면 수백 개)
                continue                                                 # 내려간 파일은 오래된 잡 — running 으로 남았을 리 없다
            d = json.load(open(p, encoding="utf-8"))
            if d.get("status") in ("queued", "running"):
                d["status"] = "lost"
                d["finished"] = d.get("finished") or time.time()
                d.setdefault("log", []).append("[재시작] 서버가 다시 떠서 이 잡은 끊겼다")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception:
        pass


class _Stored(object):
    """디스크에서 읽은 지난 잡 — 읽기 전용."""

    def __init__(self, d):
        self._d = d

    def __getattr__(self, k):
        try:
            return self._d[k]
        except KeyError:
            raise AttributeError(k)

    def to_dict(self, since=0, full=False):
        d = dict(self._d)
        d["log"] = d.get("log", []) if full else d.get("log", [])[since:]
        d["n"] = len(self._d.get("log", []))
        return d


def run_cmd(job, cmd, cwd=None, timeout=1800, env=None, quiet=("DeprecationWarning", "fitz")):
    """자식 프로세스를 돌리며 출력을 잡 로그에 흘린다. 반환값은 exit code."""
    job.add("$ " + " ".join(os.path.basename(c) if i == 0 else c for i, c in enumerate(cmd)))
    p = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, bufsize=1, env=env)
    try:
        for line in p.stdout:
            line = line.rstrip()
            if line and not any(q in line for q in quiet):
                job.add(line)
                if len(job.log) % 25 == 0:
                    job.save()
        p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        job.add(f"[시간 초과] {timeout}초")
        return -9
    return p.returncode
