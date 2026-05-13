"""
조교 공유 폴더로 작업 결과 비동기 복사.

ASSISTANT_SHARE_DIR 환경변수가 설정되어 있으면 작업 완료 시
- 조판된 .indd 파일 (settings.json 또는 .settings.json의 indd_path)
- 결과 PDF
- 핵심 메타 (school.txt, issue_num.txt)
만 그곳으로 복사. 메타데이터/JSON/JSX/로그 등은 제외 (조교에게 불필요).

별도 thread에서 동작하므로 복사 중 GoogleDrive 가상 마운트
지연/잠금이 발생해도 메인 pipeline에는 영향 없음.
shutil.copy2는 app.py에서 GDrive EDEADLK 대응 패치된 상태.
"""

import json
import os
import shutil
import threading
import traceback


def _find_indd_paths(job_dir, log_fn):
    """job_dir의 settings.json 또는 .settings.json에서 indd_path 추출.

    반환: list of paths (single 또는 multi). 못 찾으면 빈 리스트.
    """
    for fname in (".settings.json", "settings.json"):
        p = os.path.join(job_dir, fname)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log_fn(f"[공유] {fname} 파싱 실패: {e}")
            continue

        paths = []
        # 단일 indd_path
        if isinstance(data, dict):
            single = data.get("indd_path")
            if single and isinstance(single, str):
                paths.append(single)
            # jobs 배열 (hanyoung 등 여러 .indd 만드는 엔진)
            jobs_arr = data.get("jobs")
            if isinstance(jobs_arr, list):
                for j in jobs_arr:
                    if isinstance(j, dict):
                        ip = j.get("indd_path")
                        if ip and isinstance(ip, str):
                            paths.append(ip)
        if paths:
            return paths
    return []


def _share_worker(job_id, job_dir, dest_root, label, log_fn):
    try:
        if not os.path.isdir(job_dir):
            log_fn(f"[공유] 소스 폴더 없음: {job_dir}")
            return

        if not os.path.isdir(dest_root):
            try:
                os.makedirs(dest_root, exist_ok=True)
                log_fn(f"[공유] 대상 폴더 생성: {dest_root}")
            except Exception as e:
                log_fn(f"[공유] 대상 폴더 생성 실패: {dest_root}: {e}")
                return

        dest_dir = os.path.join(dest_root, label)
        os.makedirs(dest_dir, exist_ok=True)
        log_fn(f"[공유] 복사 시작: {dest_dir}")

        copied = 0

        # 1) .indd 파일 — settings에서 경로 추출 후 복사
        indd_paths = _find_indd_paths(job_dir, log_fn)
        if not indd_paths:
            log_fn("[공유] .indd 경로 찾을 수 없음 (settings.json 미존재 또는 indd_path 없음)")
        else:
            for indd_path in indd_paths:
                if not indd_path or not os.path.exists(indd_path):
                    log_fn(f"[공유] .indd 파일 없음: {indd_path}")
                    continue
                try:
                    shutil.copy2(indd_path, dest_dir)
                    copied += 1
                    log_fn(f"[공유] .indd → {os.path.basename(indd_path)}")
                except Exception as e:
                    log_fn(f"[공유] .indd 복사 실패 ({os.path.basename(indd_path)}): {e}")

        # 2) 결과 PDF (job_dir 최상위)
        for entry in os.listdir(job_dir):
            if entry.lower().endswith(".pdf"):
                src_pdf = os.path.join(job_dir, entry)
                try:
                    shutil.copy2(src_pdf, dest_dir)
                    copied += 1
                    log_fn(f"[공유] PDF → {entry}")
                except Exception as e:
                    log_fn(f"[공유] PDF 복사 실패 ({entry}): {e}")

        # 3) 핵심 메타 (조교가 어느 학교/회차인지 알 수 있도록)
        for meta in ("school.txt", "issue_num.txt", "grade.txt", "year.txt", "month.txt"):
            mp = os.path.join(job_dir, meta)
            if os.path.exists(mp):
                try:
                    shutil.copy2(mp, dest_dir)
                except Exception:
                    pass

        if copied == 0:
            log_fn("[공유] ⚠️ .indd/PDF 모두 못 찾음 — 조교가 검수할 파일 없음")
        else:
            log_fn(f"[공유] 완료 ({copied}개 핵심 파일): {dest_dir}")

    except Exception as e:
        log_fn(f"[공유] 실패: {e}")
        log_fn(traceback.format_exc())


def share_job_async(job_id, job_dir, school, log_fn):
    """작업 결과(.indd + PDF + 핵심 메타)를 ASSISTANT_SHARE_DIR로 비동기 복사.

    환경변수 ASSISTANT_SHARE_DIR이 없으면 아무 동작 안 함 (선택 기능).
    복사 실패는 메인 pipeline에 영향 없음 (로그만 남음).
    """
    dest_root = os.environ.get("ASSISTANT_SHARE_DIR", "").strip()
    if not dest_root:
        return

    safe_school = (school or "unknown").replace("/", "_").strip()
    label = f"{safe_school}_{job_id}" if safe_school != "unknown" else job_id

    t = threading.Thread(
        target=_share_worker,
        args=(job_id, job_dir, dest_root, label, log_fn),
        daemon=True,
        name=f"share-{job_id}",
    )
    t.start()
