"""코퍼스 케이스 재실행 + 정규화 공용 로직 (test / regen 스크립트 공유)."""
import json
import os
import shutil
import unicodedata


def build_job(case_dir: str, job_dir: str) -> None:
    """corpus 케이스 → 임시 job_dir 구성 (meta/*.txt → 루트, inputs/* → uploads/)."""
    uploads = os.path.join(job_dir, "uploads")
    os.makedirs(uploads, exist_ok=True)
    meta_dir = os.path.join(case_dir, "meta")
    if os.path.isdir(meta_dir):
        for n in os.listdir(meta_dir):
            shutil.copy2(os.path.join(meta_dir, n), os.path.join(job_dir, n))
    for n in os.listdir(os.path.join(case_dir, "inputs")):
        shutil.copy2(os.path.join(case_dir, "inputs", n),
                     os.path.join(uploads, n))


def build_uploaded(engine, job_dir: str) -> dict:
    """app.py:api_run 의 슬롯 처리(1167~1207)를 재현해 uploaded dict 구성."""
    uploads = os.path.join(job_dir, "uploads")
    uploaded = {}
    for slot in engine.upload_spec["slots"]:
        key = slot["key"]
        if slot.get("type") in ("text", "textarea"):
            txt = os.path.join(job_dir, f"{key}.txt")
            if os.path.isfile(txt):
                uploaded[key] = open(txt, encoding="utf-8").read().strip()
            continue
        matches = sorted(
            os.path.join(uploads, n) for n in os.listdir(uploads)
            if n.startswith(f"{key}_")
        ) if os.path.isdir(uploads) else []
        if not matches:
            continue
        uploaded[key] = matches if slot.get("multiple") else matches[0]
    return uploaded


def replay(engine, case_dir: str, job_dir: str) -> dict:
    """케이스를 parse 재실행하고 content.json 을 dict 로 반환."""
    build_job(case_dir, job_dir)
    uploaded = build_uploaded(engine, job_dir)
    assert uploaded, "업로드 재구성 실패 — 코퍼스 inputs/슬롯 키 불일치"
    logs = []
    json_path = engine.parse(uploaded, job_dir, logs.append)
    assert os.path.isfile(json_path), f"parse가 content.json을 만들지 않음: {json_path}"
    return json.load(open(json_path, encoding="utf-8"))


def canonicalize(obj, job_paths):
    """비교/저장용 정규화: 절대경로 → <JOB> 토큰, 문자열 NFC 통일."""
    if isinstance(obj, str):
        for p in job_paths:
            if p:
                obj = obj.replace(p, "<JOB>")
        return unicodedata.normalize("NFC", obj)
    if isinstance(obj, list):
        return [canonicalize(v, job_paths) for v in obj]
    if isinstance(obj, dict):
        return {canonicalize(k, job_paths): canonicalize(v, job_paths)
                for k, v in obj.items()}
    return obj


def first_diff(a, b, path="$"):
    """두 JSON 값의 첫 불일치 지점을 사람이 읽을 수 있게 반환. 없으면 None."""
    if type(a) is not type(b):
        return f"{path}: 타입 불일치 {type(a).__name__} != {type(b).__name__}"
    if isinstance(a, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a:
                return f"{path}.{k}: 결과에 없음 (키 누락)"
            if k not in b:
                return f"{path}.{k}: 골든에 없음 (새 키)"
            d = first_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: 길이 {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if a != b:
        return f"{path}: {str(a)[:120]!r} != {str(b)[:120]!r}"
    return None
