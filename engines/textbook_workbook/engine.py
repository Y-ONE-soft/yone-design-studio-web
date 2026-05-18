import json
import os
import re
import shutil
import unicodedata

from core.base import BaseEngine, safe_copy_indd
from core.paths import resolve_config
from engines.final.extractor import _gdrive_safe_copy
from engines.workbook.parser import parse_manuscript_folder

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
# JSX는 기존 워크북 엔진의 run.jsx 공유
_JSX_TEMPLATE = os.path.join(os.path.dirname(_DIR), "workbook", "jsx", "run.jsx")

_PATH_KEYS = ["indd_output_dir", "indd_original", "textbook_base"]


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _is_step3_name(name_nfc: str) -> bool:
    """파일명에 Step3/스텝3 토큰이 포함되어 있는지 (확장자 무관)."""
    return bool(re.search(r'(?:[Ss]tep\s*3|스텝\s*3)', name_nfc))


def _is_answer_or_explanation(name_nfc: str) -> bool:
    """파일명에 정답/해설 토큰이 포함되어 있는지."""
    return ("정답" in name_nfc) or ("해설" in name_nfc)


class TextbookWorkbookEngine(BaseEngine):

    @property
    def material_id(self) -> str:
        return "textbook_workbook"

    @property
    def display_name(self) -> str:
        return "교과서 워크북"

    @property
    def description(self) -> str:
        return "교과서 워크북 조판 자동화 (과목/출판사/과 선택)"

    @property
    def subject_prefix(self) -> str:
        return "교과서워크북"

    @property
    def template_name(self) -> str:
        return "typeset_textbook_workbook.html"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {
                    "key": "manuscripts",
                    "label": "추가 원고 파일 (선택)",
                    "required": False,
                    "multiple": True,
                    "accept": ".docx,.hwp,.hwpx",
                },
            ]
        }

    # ── 폴더 탐색 API용 헬퍼 ────────────────────────────────────────────

    @staticmethod
    def list_subjects():
        cfg = _load_config()
        base = cfg["textbook_base"]
        excludes = set(cfg.get("exclude_folders", []))
        if not os.path.isdir(base):
            return []
        result = []
        for raw in sorted(os.listdir(base)):
            name = _nfc(raw)
            if name.startswith(".") or name in excludes:
                continue
            full = os.path.join(base, raw)
            if os.path.isdir(full):
                result.append(name)
        return result

    @staticmethod
    def list_publishers(subject):
        cfg = _load_config()
        base = os.path.join(cfg["textbook_base"], subject)
        if not os.path.isdir(base):
            return []
        result = []
        for raw in sorted(os.listdir(base)):
            name = _nfc(raw)
            if name.startswith("."):
                continue
            full = os.path.join(base, raw)
            if os.path.isdir(full):
                result.append(name)
        return result

    @staticmethod
    def list_lessons(subject, publisher):
        cfg = _load_config()
        base = os.path.join(cfg["textbook_base"], subject, publisher)
        if not os.path.isdir(base):
            return []
        result = []
        for raw in sorted(os.listdir(base)):
            name = _nfc(raw)
            if name.startswith("."):
                continue
            full = os.path.join(base, raw)
            if os.path.isdir(full):
                # "공통영어1 YBM(박) 1과" -> "1과" 추출
                m = re.search(r'(\d+과|SL\d+|Project\s*\d+)', name)
                if m:
                    result.append({"folder": name, "label": m.group(1)})
        return result

    @staticmethod
    def list_files(subject, publisher, lesson_folder):
        """워크북 폴더 안의 원고 파일 목록 반환. 사용 여부를 함께 표시."""
        cfg = _load_config()
        workbook_dir = None
        lesson_path = os.path.join(
            cfg["textbook_base"], subject, publisher, lesson_folder
        )
        if not os.path.isdir(lesson_path):
            return {"workbook_dir": None, "files": []}

        # 워크북 서브폴더 찾기
        for raw in os.listdir(lesson_path):
            name = _nfc(raw)
            if "워크북" in name and os.path.isdir(os.path.join(lesson_path, raw)):
                workbook_dir = os.path.join(lesson_path, raw)
                break

        if not workbook_dir:
            return {"workbook_dir": None, "files": []}

        # 파서가 사용할 파일을 시뮬레이션: 각 step_key마다 _find_manuscript_file 로직 재현
        file_map = cfg.get("manuscript_file_map", {})
        used_files = set()  # NFC 정규화된 파일명

        def _sim_find(all_names, expected_filename):
            """_find_manuscript_file과 동일한 로직으로 매칭되는 파일명 반환."""
            base = os.path.splitext(expected_filename)[0].replace(" ", "").lower()
            norm_base = unicodedata.normalize("NFC", base)
            exact = []
            partial = []
            for fn in all_names:
                f_base = os.path.splitext(fn)[0].replace(" ", "").lower()
                f_norm = unicodedata.normalize("NFC", f_base)
                if f_norm == norm_base:
                    exact.append(fn)
                elif f_norm.startswith(norm_base) or norm_base.startswith(f_norm):
                    partial.append(fn)
            ext = os.path.splitext(expected_filename)[1].lower()
            if exact:
                for c in exact:
                    if os.path.splitext(c)[1].lower() == ext:
                        return c
                return exact[0]
            if partial:
                for c in partial:
                    if os.path.splitext(c)[1].lower() == ext:
                        return c
                return partial[0]
            return None

        # 모든 원고 파일명 수집 (매칭 시뮬레이션용)
        all_names = []
        for raw in sorted(os.listdir(workbook_dir)):
            name = _nfc(raw)
            if name.startswith("."):
                continue
            full = os.path.join(workbook_dir, raw)
            if os.path.isfile(full):
                ext = os.path.splitext(name)[1].lower()
                if ext in (".docx", ".hwp", ".hwpx"):
                    all_names.append(name)

        # 각 step_key에 대해 매칭되는 파일 찾기
        for _key, expected in file_map.items():
            matched = _sim_find(all_names, expected)
            if matched:
                used_files.add(matched)

        # 대체 파일명도 used로 표시 (원본이 없을 때만)
        alternatives = cfg.get("manuscript_file_alternatives", {})
        for alt_name, target_name in alternatives.items():
            if target_name not in used_files and alt_name in all_names:
                used_files.add(alt_name)

        files = []
        for raw in sorted(os.listdir(workbook_dir)):
            name = _nfc(raw)
            if name.startswith("."):
                continue
            full = os.path.join(workbook_dir, raw)
            if os.path.isfile(full):
                ext = os.path.splitext(name)[1].lower()
                if ext in (".docx", ".hwp", ".hwpx"):
                    used = (name in used_files) or (
                        _is_step3_name(name) and not _is_answer_or_explanation(name)
                    )
                    files.append({"name": name, "used": used})
            elif os.path.isdir(full):
                lower = name.lower()
                if "step3" in lower or "스텝3" in _nfc(lower):
                    # Step3 폴더 내 후보 파일 수집 (정답해설 제외)
                    step3_candidates = []
                    for raw2 in sorted(os.listdir(full)):
                        name2 = _nfc(raw2)
                        if name2.startswith("."):
                            continue
                        ext2 = os.path.splitext(name2)[1].lower()
                        if ext2 not in (".docx", ".hwp", ".hwpx"):
                            continue
                        if _is_answer_or_explanation(name2):
                            continue
                        step3_candidates.append(name2)
                    # MIXED 파일이 있으면 그것만 used=True (파서 동작과 일치)
                    mixed_set = {n for n in step3_candidates if "MIXED" in n.upper()}
                    used_step3 = mixed_set if mixed_set else set(step3_candidates)
                    # 모든 파일 표시 (used 여부만 차별)
                    for raw2 in sorted(os.listdir(full)):
                        name2 = _nfc(raw2)
                        if name2.startswith("."):
                            continue
                        ext2 = os.path.splitext(name2)[1].lower()
                        if ext2 in (".docx", ".hwp", ".hwpx"):
                            used2 = name2 in used_step3
                            files.append({"name": f"[Step3] {name2}", "used": used2})

        return {"workbook_dir": workbook_dir, "files": files}

    # ── 1단계: 원고 폴더 -> content.json ──────────────────────────────────

    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        cfg = _load_config()

        # 메타데이터 읽기
        subject = self._read_meta_str(job_dir, "subject", "")
        publisher = self._read_meta_str(job_dir, "publisher", "")
        lesson = self._read_meta_str(job_dir, "lesson", "")
        lesson_folder = self._read_meta_str(job_dir, "lesson_folder", "")

        # grade 결정 (과목 -> 학년 매핑)
        grade_map = cfg.get("subject_grade_map", {})
        grade = grade_map.get(subject, 1)

        # 교과서는 year/month 불필요 -> 더미값
        year = 0
        month = 0

        log(f"[파서] 교과서 워크북: {subject} {publisher} {lesson}")

        # 원고 폴더 결정
        manuscript_dir = os.path.join(job_dir, "uploads")
        os.makedirs(manuscript_dir, exist_ok=True)
        step3_dir = os.path.join(manuscript_dir, "Step3")
        os.makedirs(step3_dir, exist_ok=True)

        # 대체 파일명 매핑 (원본명 -> 기대 파일명으로 rename)
        alternatives = cfg.get("manuscript_file_alternatives", {})

        # GDrive Stream EDEADLK 회피 안전 복사 — _gdrive_safe_copy 직접 호출로
        # app.py monkey-patch 의존성 제거 (worker 등 monkey-patch 미적용 경로 포함).
        def _safe_copy(src_path, dst_path):
            ok, err = _gdrive_safe_copy(src_path, dst_path, log=log)
            if not ok:
                raise RuntimeError(
                    f"GDrive 복사 실패: {os.path.basename(src_path)} -> "
                    f"{os.path.basename(dst_path)} ({err[:200]})"
                )

        # 1) 구글 드라이브 워크북 폴더에서 파일 복사
        gdrive_workbook = self._read_meta_str(job_dir, "manuscript_folder", "")
        if gdrive_workbook and os.path.isdir(gdrive_workbook):
            log(f"[파서] 원고 폴더: {os.path.basename(gdrive_workbook)}")
            for raw in os.listdir(gdrive_workbook):
                src = os.path.join(gdrive_workbook, raw)
                name = _nfc(raw)
                if name.startswith("."):
                    continue
                if os.path.isfile(src):
                    ext = os.path.splitext(name)[1].lower()
                    if ext in (".docx", ".hwp", ".hwpx"):
                        # Step3 원고 파일은 step3_dir로 (정답/해설은 제외)
                        if _is_step3_name(name) and not _is_answer_or_explanation(name):
                            _safe_copy(src, os.path.join(step3_dir, name))
                            continue
                        # 대체 파일명이면 기대 파일명으로 rename (기대 파일이 없을 때만)
                        dest_name = name
                        if name in alternatives:
                            target = alternatives[name]
                            target_path = os.path.join(manuscript_dir, target)
                            orig_path = os.path.join(gdrive_workbook, target)
                            if not os.path.exists(target_path) and not os.path.exists(orig_path):
                                dest_name = target
                                log(f"[파서] 대체 파일명: {name} -> {target}")
                        _safe_copy(src, os.path.join(manuscript_dir, dest_name))
                elif os.path.isdir(src):
                    # Step3/스텝3 서브폴더 복사
                    lower = name.lower()
                    if "step3" in lower or "스텝3" in _nfc(lower):
                        for raw2 in os.listdir(src):
                            src2 = os.path.join(src, raw2)
                            name2 = _nfc(raw2)
                            if name2.startswith(".") or not os.path.isfile(src2):
                                continue
                            ext2 = os.path.splitext(name2)[1].lower()
                            if ext2 in (".docx", ".hwp", ".hwpx"):
                                if _is_answer_or_explanation(name2):
                                    continue
                                _safe_copy(src2, os.path.join(step3_dir, name2))
            log(f"[파서] 원고 복사 완료")
        else:
            log(f"[파서] 워크북 폴더 없음, 업로드 파일만 사용")

        # 2) 추가 업로드 파일 처리
        extra_files = uploaded_files.get("manuscripts", [])
        if isinstance(extra_files, list):
            for fpath in extra_files:
                fname = os.path.basename(fpath)
                if fname.startswith("manuscripts_"):
                    fname = fname[len("manuscripts_"):]
                fname_nfc = _nfc(fname)
                is_step3 = (
                    (_is_step3_name(fname_nfc) and not _is_answer_or_explanation(fname_nfc))
                    or "번.hwp" in fname_nfc or "번.hwpx" in fname_nfc
                    or "번.docx" in fname_nfc
                )
                if is_step3:
                    dest = os.path.join(step3_dir, fname)
                else:
                    dest = os.path.join(manuscript_dir, fname)
                if fpath != dest:
                    _safe_copy(fpath, dest)

        # 파서 실행 (기존 워크북 파서 재사용)
        log(f"[파서] 파싱 시작")
        data = parse_manuscript_folder(manuscript_dir, cfg, grade, year, month, log)

        # 교과서 메타 추가
        data["workbook_type"] = "교과서"
        data["subject"] = subject
        data["publisher"] = publisher
        data["lesson"] = lesson

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Split into per-step files
        meta = {
            "grade": data.get("grade"),
            "year": data.get("year"),
            "month": data.get("month"),
            "step_files": {},
        }
        for key, step_data in data.get("steps", {}).items():
            step_path = os.path.join(job_dir, f"step_{key}.json")
            with open(step_path, "w", encoding="utf-8") as f:
                json.dump(step_data, f, ensure_ascii=False)
            meta["step_files"][key] = step_path

        meta_path = os.path.join(job_dir, "content_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        step_count = len(data.get("steps", {}))
        log(f"[파서] 완료: {step_count}개 STEP")

        return json_path

    # ── 2단계: JSX 준비 ──────────────────────────────────────────────────

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = _load_config()

        subject = self._read_meta_str(job_dir, "subject", "")
        publisher = self._read_meta_str(job_dir, "publisher", "")
        lesson = self._read_meta_str(job_dir, "lesson", "")

        grade_map = cfg.get("subject_grade_map", {})
        grade = grade_map.get(subject, 1)

        # 출력 파일명
        # publisher에서 과목명 제거: "공통영어1 YBM(박)" -> "YBM(박)"
        pub_short = publisher
        if subject and publisher.startswith(subject):
            pub_short = publisher[len(subject):].strip()
        out_name = f"{subject}_{pub_short}_{lesson}_전체(C).indd"
        indd_path = os.path.join(cfg["indd_output_dir"], out_name)

        # 원본 indd 복사
        src = cfg.get("indd_original", "")
        if isinstance(src, dict):
            src = src.get("모의고사", "")
        if os.path.exists(src):
            os.makedirs(os.path.dirname(indd_path), exist_ok=True)
            indd_path = safe_copy_indd(src, indd_path)
            log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            raise FileNotFoundError(f"내지 파일 없음: {indd_path}")

        # settings.json
        settings_path = os.path.join(job_dir, ".settings.json")
        settings = {
            "json_path": json_path,
            "indd_path": indd_path,
            "output_dir": job_dir,
            "grade": grade,
            "year": 0,
            "month": 0,
            "workbook_type": "교과서",
            "subject": subject,
            "publisher": pub_short,
            "lesson": lesson,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        # run.jsx 임시 사본
        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()

        jsx_src = re.sub(
            r'var settingsPath\s*=\s*"[^"]*";',
            f'var settingsPath = "{settings_path}";',
            jsx_src,
            count=1,
        )

        jsx_path = os.path.join(job_dir, "run.jsx")
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        log(f"[JSX] 준비 완료: {os.path.basename(indd_path)}")
        return jsx_path

    # ── 3단계: 검수 ──────────────────────────────────────────────────────

    def verify(self, job_dir: str, log) -> dict:
        cfg = _load_config()
        max_overflow = cfg["verify"]["max_overflow"]

        log_path = os.path.join(job_dir, cfg["log_filename"])
        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "error": "로그 파일 없음", "warnings": []}

        content = open(log_path, encoding="utf-8", errors="ignore").read()

        step_m = re.search(r"STEP완료:\s*(\d+)개", content)
        actual_steps = int(step_m.group(1)) if step_m else None

        overflow_m = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(overflow_m.group(1)) if overflow_m else None

        style_warnings = re.findall(r"스타일불일치:\s*(.+)", content)

        pdf_path = None
        if re.search(r"PDF:\s*성공", content):
            for fname in os.listdir(job_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_path = os.path.join(job_dir, fname)
                    break

        warnings = list(style_warnings)
        if actual_steps is None:
            warnings.append("STEP 완료 수 확인 불가")
        if overflow is None:
            warnings.append("오버플로우 수치 확인 불가")
        elif overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")

        ok = (overflow is not None and overflow <= max_overflow
              and len(style_warnings) == 0
              and pdf_path is not None)

        result = {
            "ok": ok,
            "overflow": overflow,
            "steps_completed": actual_steps,
            "pdf_path": pdf_path,
            "warnings": warnings,
        }

        status = "✅ 통과" if ok else f"⚠️ 경고 {len(warnings)}건"
        log(f"[검수] {status} | 오버플로우: {overflow}개 | PDF: {'있음' if pdf_path else '없음'}")
        return result

    # ── 유틸리티 ──────────────────────────────────────────────────────────

    def _read_meta_str(self, job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p).read().strip() if os.path.exists(p) else default
