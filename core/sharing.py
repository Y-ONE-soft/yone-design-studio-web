"""
조교 공유 폴더로 작업 결과 비동기 복사.

ASSISTANT_SHARE_DIR 환경변수가 설정되어 있으면 작업 완료 시
- 조판된 .indd 파일 (settings.json 또는 .settings.json의 indd_path)
- 결과 PDF
- linked assets (Links/, Fonts/)
만 그곳으로 복사.

폴더 구조: ASSISTANT_SHARE_DIR / 카테고리 / 파일.indd
(카테고리는 subjects.json의 category 기준 — 워크북·프리미엄북·포켓북 등)

별도 thread에서 동작하므로 복사 중 GoogleDrive 가상 마운트
지연/잠금이 발생해도 메인 pipeline에는 영향 없음.
shutil.copy2는 app.py에서 GDrive EDEADLK 대응 패치된 상태.
"""

import json
import os
import shutil
import threading
import time
import traceback


_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SUBJECTS_PATH = os.path.join(_BASE_DIR, "data", "subjects.json")
_category_cache = None


def _load_category_map():
    """material_id → category 매핑. subjects.json 1회 로드 + 캐싱."""
    global _category_cache
    if _category_cache is not None:
        return _category_cache
    mapping = {}
    try:
        with open(_SUBJECTS_PATH, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            for block in data:
                cat = (block.get("category") or "").strip()
                for item in block.get("items", []):
                    eng = item.get("engine_id")
                    if eng and cat:
                        mapping[eng] = cat
    except Exception:
        pass
    _category_cache = mapping
    return mapping


def _resolve_category(material_id):
    """material_id → 카테고리 폴더명. 매핑 없으면 '기타'."""
    if not material_id:
        return "기타"
    mapping = _load_category_map()
    return mapping.get(material_id) or "기타"


def _wait_for_stable_file(path, log_fn, timeout=60, check_interval=2):
    """파일 mtime·크기가 N초간 변경 없을 때까지 대기 (InDesign 저장 완료 신호).

    InDesign이 .indd 저장은 비동기라 sharing.py가 너무 빨리 실행되면
    옛 .indd 그대로 복사될 수 있음. 이걸 방지.

    반환: True(안정 도달) / False(파일 없음 또는 timeout)
    """
    last_sig = None
    elapsed = 0
    stable_required = 4  # 4초간 변화 없으면 안정

    while elapsed < timeout:
        if not os.path.exists(path):
            time.sleep(check_interval)
            elapsed += check_interval
            continue
        try:
            st = os.stat(path)
            sig = (st.st_size, int(st.st_mtime))
        except OSError:
            time.sleep(check_interval)
            elapsed += check_interval
            continue

        if last_sig == sig:
            # mtime/size 변화 없음 → 안정 도달
            return True
        last_sig = sig
        time.sleep(check_interval)
        elapsed += check_interval

    log_fn(f"[공유] 안정 대기 timeout ({timeout}s) — 일단 복사 시도: {os.path.basename(path)}")
    return last_sig is not None


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
        if isinstance(data, dict):
            single = data.get("indd_path")
            if single and isinstance(single, str):
                paths.append(single)
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


def _copy_linked_assets(indd_path, dest_dir, log_fn):
    """`.indd`와 같은 폴더에 있는 Links/Fonts 같은 패키지 자료를 함께 복사.

    InDesign Package 관습:
      - Links/  (이미지/외부 자료)
      - Fonts/ 또는 'Document fonts'/  (커스텀 폰트)
    이런 폴더가 있으면 조교 PC에서 .indd 열 때 링크 깨지지 않음.
    """
    indd_dir = os.path.dirname(indd_path)
    candidates = ("Links", "Fonts", "Document fonts", "Document Fonts",
                  "links", "fonts")
    for name in candidates:
        src = os.path.join(indd_dir, name)
        if not os.path.isdir(src):
            continue
        try:
            dst = os.path.join(dest_dir, name)
            shutil.copytree(src, dst, dirs_exist_ok=True)
            log_fn(f"[공유] linked → {name}/")
        except Exception as e:
            log_fn(f"[공유] linked 복사 실패 ({name}): {e}")


def _share_worker(job_id, job_dir, dest_root, category, log_fn, hint_indd_path=None):
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

        # 카테고리 폴더로 평탄하게 복사 (Y.ONE WEB/조판결과/워크북/...)
        dest_dir = os.path.join(dest_root, category)
        os.makedirs(dest_dir, exist_ok=True)
        log_fn(f"[공유] 복사 시작: {dest_dir}")

        copied = 0

        # .indd 경로 수집
        candidate_paths = []
        if hint_indd_path:
            if isinstance(hint_indd_path, (list, tuple)):
                candidate_paths.extend(hint_indd_path)
            else:
                candidate_paths.append(hint_indd_path)
        candidate_paths.extend(_find_indd_paths(job_dir, log_fn))

        seen = set()
        indd_paths = []
        for p in candidate_paths:
            if p and p not in seen:
                seen.add(p)
                indd_paths.append(p)

        if not indd_paths:
            log_fn("[공유] .indd 경로 찾을 수 없음")
        else:
            assets_copied_dirs = set()
            for indd_path in indd_paths:
                if not os.path.exists(indd_path):
                    log_fn(f"[공유] .indd 파일 없음: {indd_path}")
                    continue
                # InDesign 저장 완료까지 대기 (mtime/size 안정화)
                _wait_for_stable_file(indd_path, log_fn)
                try:
                    shutil.copy2(indd_path, dest_dir)
                    copied += 1
                    log_fn(f"[공유] .indd → {os.path.basename(indd_path)}")
                except Exception as e:
                    log_fn(f"[공유] .indd 복사 실패 ({os.path.basename(indd_path)}): {e}")
                    continue

                indd_dir = os.path.dirname(indd_path)
                if indd_dir not in assets_copied_dirs:
                    _copy_linked_assets(indd_path, dest_dir, log_fn)
                    assets_copied_dirs.add(indd_dir)

        # 결과 PDF (job_dir 최상위)
        for entry in os.listdir(job_dir):
            if entry.lower().endswith(".pdf"):
                src_pdf = os.path.join(job_dir, entry)
                _wait_for_stable_file(src_pdf, log_fn)
                try:
                    shutil.copy2(src_pdf, dest_dir)
                    copied += 1
                    log_fn(f"[공유] PDF → {entry}")
                except Exception as e:
                    log_fn(f"[공유] PDF 복사 실패 ({entry}): {e}")

        # 메타 txt(school·grade·year·month·issue)는 복사 안 함 (요청에 따라)

        if copied == 0:
            log_fn("[공유] ⚠️ .indd/PDF 모두 못 찾음")
        else:
            log_fn(f"[공유] 완료 ({copied}개 파일): {dest_dir}")

    except Exception as e:
        log_fn(f"[공유] 실패: {e}")
        log_fn(traceback.format_exc())


def share_job_async(job_id, job_dir, school, log_fn, indd_path=None, material_id=None):
    """작업 결과(.indd + PDF + linked assets)를 ASSISTANT_SHARE_DIR/카테고리/로 비동기 복사.

    Args:
        material_id: 엔진 ID. subjects.json의 카테고리로 매핑됨 (예: workbook → "워크북").
                     None이면 '기타' 폴더.
        indd_path: 운영자가 명시 전달한 .indd 경로. verify result에서 가져오면 우선 사용.
                   None이면 job_dir/.settings.json에서 fallback 추출. list 가능.

    환경변수 ASSISTANT_SHARE_DIR이 없으면 아무 동작 안 함 (선택 기능).
    복사 실패는 메인 pipeline에 영향 없음 (로그만 남음).
    """
    dest_root = os.environ.get("ASSISTANT_SHARE_DIR", "").strip()
    if not dest_root:
        return

    category = _resolve_category(material_id)

    t = threading.Thread(
        target=_share_worker,
        args=(job_id, job_dir, dest_root, category, log_fn, indd_path),
        daemon=True,
        name=f"share-{job_id}",
    )
    t.start()
