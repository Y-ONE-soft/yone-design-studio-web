"""
조교 공유 폴더로 작업 결과 비동기 복사.

ASSISTANT_SHARE_DIR 환경변수가 설정되어 있으면 작업 완료 시
job_dir 내용을 그곳으로 복사. 별도 thread에서 동작하므로
복사 중 GoogleDrive 가상 마운트 지연/잠금이 발생해도
메인 pipeline(jm.done 응답)은 영향 없음.

shutil.copy2는 app.py에서 GDrive EDEADLK 대응 패치된 상태.
"""

import os
import shutil
import threading
import traceback


# 복사에서 제외할 항목 (대용량/무관)
_EXCLUDE_NAMES = {
    "uploads",          # 원본 업로드 (큼, 결과만 필요)
    ".settings.json",   # 내부 설정
    "__pycache__",
}


def _is_excluded(name):
    return name in _EXCLUDE_NAMES or name.startswith(".")


def _copy_filtered(src_dir, dest_dir, log_fn):
    """job_dir의 결과 파일만 선별 복사. _EXCLUDE_NAMES는 건너뜀."""
    os.makedirs(dest_dir, exist_ok=True)
    copied = 0
    for entry in os.listdir(src_dir):
        if _is_excluded(entry):
            continue
        src_path = os.path.join(src_dir, entry)
        dest_path = os.path.join(dest_dir, entry)
        try:
            if os.path.isdir(src_path):
                shutil.copytree(src_path, dest_path, dirs_exist_ok=True)
            else:
                shutil.copy2(src_path, dest_path)
            copied += 1
        except Exception as e:
            log_fn(f"[공유] 항목 복사 실패 ({entry}): {e}")
    return copied


def _share_worker(job_id, job_dir, dest_root, label, log_fn):
    try:
        if not os.path.isdir(job_dir):
            log_fn(f"[공유] 소스 폴더 없음: {job_dir}")
            return

        # 대상 루트가 없으면 생성 시도 (구글드라이브 폴더가 우연히 비어 있을 때 대비)
        if not os.path.isdir(dest_root):
            try:
                os.makedirs(dest_root, exist_ok=True)
                log_fn(f"[공유] 대상 폴더 생성: {dest_root}")
            except Exception as e:
                log_fn(f"[공유] 대상 폴더 생성 실패 (경로 확인 필요): {dest_root}: {e}")
                return

        dest_dir = os.path.join(dest_root, label)
        log_fn(f"[공유] 복사 시작: {dest_dir}")
        copied = _copy_filtered(job_dir, dest_dir, log_fn)
        log_fn(f"[공유] 완료 ({copied}개 항목): {dest_dir}")

    except Exception as e:
        log_fn(f"[공유] 실패: {e}")
        log_fn(traceback.format_exc())


def share_job_async(job_id, job_dir, school, log_fn):
    """작업 결과를 ASSISTANT_SHARE_DIR로 비동기 복사 (별도 thread).

    환경변수 ASSISTANT_SHARE_DIR이 없으면 아무 동작 안 함 (선택 기능).
    복사 실패는 메인 pipeline에 영향 없음 (로그만 남음).
    """
    dest_root = os.environ.get("ASSISTANT_SHARE_DIR", "").strip()
    if not dest_root:
        return  # 미설정 시 비활성

    safe_school = (school or "unknown").replace("/", "_").strip()
    label = f"{safe_school}_{job_id}" if safe_school != "unknown" else job_id

    t = threading.Thread(
        target=_share_worker,
        args=(job_id, job_dir, dest_root, label, log_fn),
        daemon=True,
        name=f"share-{job_id}",
    )
    t.start()
