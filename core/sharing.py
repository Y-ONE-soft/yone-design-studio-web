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


def _typeset_reference_mtime(job_dir):
    """이번 조판 '준비 시각'의 하한선 — job_dir의 settings*.json 중 가장 과거 mtime.

    왜 이게 '조판 완료'와 '조판 전 템플릿'을 가르는 기준이 되는가:
      - prepare_jsx가 원본 템플릿을 출력 경로로 복사할 때 safe_copy_indd가
        copystat으로 *템플릿의 옛 mtime*(예: 01:34, 수일 전)을 그대로 남긴다.
        → 조판 전 복사본의 mtime은 항상 이 settings.json 작성 시각보다 과거.
      - 실제 조판 결과는 settings.json 작성 *이후* doc.save() 시점에 저장되므로
        그 mtime보다 미래.
    따라서 "indd mtime >= 이 기준" 이면 '이번 조판으로 새로 저장된 파일'임이 보장된다.

    여러 settings(예: 수능특강 분석/문제 2개)가 있어도, 가장 과거(min) mtime을
    기준으로 삼으면 모든 출력본(각자 자기 settings 이후 저장됨)이 통과하고,
    옛 템플릿(모든 settings보다 과거)만 걸러진다.

    못 찾으면 None → 신선도 검사 생략(기존 안정성-only 동작으로 폴백).
    """
    import re

    newest_settings = None  # 실제로는 '가장 과거' 값을 모은다(아래 min 비교)
    pattern = re.compile(r"^\.?settings.*\.json$")
    try:
        candidates = os.listdir(job_dir)
    except OSError:
        return None
    for fname in candidates:
        if not pattern.match(fname):
            continue
        try:
            m = os.stat(os.path.join(job_dir, fname)).st_mtime
        except OSError:
            continue
        if newest_settings is None or m < newest_settings:
            newest_settings = m
    return newest_settings


def _wait_for_stable_file(path, log_fn, min_mtime=None, timeout=600,
                          check_interval=3, stable_required_seconds=15):
    """파일이 '이번 조판으로 새로 저장된 뒤' mtime·크기가 안정화될 때까지 대기.

    핵심(과거 버그 방지):
      조판 전 원본 템플릿 복사본은 safe_copy_indd의 copystat 때문에 템플릿의
      옛 mtime(예: 01:34, 수일 전)을 그대로 가진다. 이 파일은 InDesign이 아직
      덮어쓰기 전이라 '변화 없이 안정'한 상태로 보여, 기존 로직은 이 옛 템플릿을
      조판 결과로 오인해 복사했다(= 조판결과에 '조판 안 된 1시34분 파일' 업로드).

      min_mtime(조판 준비 시각, 보통 .settings.json mtime)을 주면, 그 이후로
      저장된 파일만 '조판 완료'로 인정한다. 옛 템플릿 복사본은 min_mtime보다
      항상 과거라 절대 통과하지 못한다.

    min_mtime=None이면 신선도 검사를 생략하고 안정성만 본다(기존 동작 유지).

    반환:
      True  — (신선 +) 안정 도달 → 복사해도 됨
      False — timeout 내 신선한 저장본이 안 나타남(=조판 전 템플릿일 가능성) → 복사 skip
              (min_mtime=None일 때는 기존처럼 안정 신호만 있으면 True)
    """
    last_sig = None
    last_change_at = time.time()
    elapsed = 0
    fresh_seen = False

    while elapsed < timeout:
        if not os.path.exists(path):
            time.sleep(check_interval)
            elapsed += check_interval
            continue
        try:
            st = os.stat(path)
        except OSError:
            time.sleep(check_interval)
            elapsed += check_interval
            continue

        sig = (st.st_size, int(st.st_mtime))

        # 신선도 게이트: 아직 이번 조판으로 저장되지 않은 옛 파일(템플릿)은
        # '안정'하게 보여도 복사 금지하고 새 저장 신호를 계속 기다린다.
        # (-1: 초 단위 반올림 여유)
        if min_mtime is not None and st.st_mtime < min_mtime - 1:
            last_sig = None          # 안정성 타이머 리셋
            time.sleep(check_interval)
            elapsed += check_interval
            continue

        if min_mtime is not None and not fresh_seen:
            log_fn(f"[공유] 조판 결과 저장 감지 — 안정화 대기: {os.path.basename(path)}")
            fresh_seen = True

        if last_sig is None or last_sig != sig:
            # 첫 관측 또는 변화 발생 → 다시 안정 대기
            last_sig = sig
            last_change_at = time.time()
        else:
            # 변화 없음 → 안정 시간 누적
            if time.time() - last_change_at >= stable_required_seconds:
                return True

        time.sleep(check_interval)
        elapsed += check_interval

    if min_mtime is not None and not fresh_seen:
        # 끝내 새 저장본이 안 나타남 → 옛 템플릿 보호 위해 복사하지 않음
        log_fn(f"[공유] ⚠️ 조판 결과가 timeout({timeout}s) 내 저장 안 됨 — "
               f"옛 템플릿 오복사 방지로 skip: {os.path.basename(path)}")
        return False

    log_fn(f"[공유] 안정 대기 timeout ({timeout}s) — 일단 복사 시도: {os.path.basename(path)}")
    return last_sig is not None


def _find_indd_paths(job_dir, log_fn):
    """job_dir의 settings*.json 파일들에서 indd_path 추출.

    지원하는 파일 패턴:
      - .settings.json, settings.json (단일)
      - .settings_analysis.json, .settings_problem.json (수능특강: 분석/문제 2개)
      - settings_*.json 등 (확장)

    반환: list of paths (단일 또는 여러 개). 못 찾으면 빈 리스트.
    """
    import re

    paths = []
    seen_files = set()

    try:
        candidates = os.listdir(job_dir)
    except OSError:
        return []

    # settings 관련 모든 json 검색
    pattern = re.compile(r"^\.?settings.*\.json$")
    for fname in candidates:
        if not pattern.match(fname):
            continue
        if fname in seen_files:
            continue
        seen_files.add(fname)
        p = os.path.join(job_dir, fname)
        try:
            with open(p, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            log_fn(f"[공유] {fname} 파싱 실패: {e}")
            continue

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

    return paths


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

        # 이번 조판의 '준비 시각' 하한선 — 이 이후로 저장된 .indd만 '조판 완료'로 인정.
        # 조판 전 원본 템플릿 복사본(옛 mtime)이 조판결과로 잘못 올라가는 것을 막는다.
        typeset_ref = _typeset_reference_mtime(job_dir)

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
                # 이번 조판으로 새로 저장된(=조판 완료된) 파일이 될 때까지 대기.
                # 아직 조판 전 템플릿(옛 mtime)이면 복사하지 않고 건너뛴다.
                if not _wait_for_stable_file(indd_path, log_fn, min_mtime=typeset_ref):
                    log_fn(f"[공유] ⏭️  조판 미완료로 .indd 복사 건너뜀: "
                           f"{os.path.basename(indd_path)}")
                    continue
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
