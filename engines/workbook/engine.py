import json
import os
import re
import shutil
import unicodedata

from core.base import BaseEngine, safe_copy_indd, safe_copy
from core.paths import resolve_config
from engines.workbook.parser import parse_manuscript_folder

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(_DIR, "jsx", "run.jsx")

_SETTINGS_PATH_MARKER = '    var settingsPath = "__SETTINGS_PATH__";'

_PATH_KEYS = ["indd_output_dir", "indd_original", "manuscript_base", "completed_base"]


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class WorkbookEngine(BaseEngine):

    @property
    def material_id(self) -> str:
        return "workbook"

    @property
    def display_name(self) -> str:
        return "워크북"

    @property
    def description(self) -> str:
        return "고1·고2 워크북 조판 자동화 (모의고사/교과서/EBS)"

    @property
    def subject_prefix(self) -> str:
        return "워크북"

    @property
    def template_name(self) -> str:
        return "typeset_workbook.html"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {
                    "key": "manuscripts",
                    "label": "원고 파일 (Step1~3 전체)",
                    "required": True,
                    "multiple": True,
                    "accept": ".docx,.hwp,.hwpx",
                },
            ]
        }

    # ── 1단계: 원고 폴더 → content.json ─────────────────────────────────

    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        # 멀티파일 업로드: manuscripts 키에 파일 경로 리스트 또는 폴더 경로
        manuscripts = uploaded_files.get("manuscripts")
        if isinstance(manuscripts, list):
            # 멀티파일 업로드 — job_dir/uploads/ 에 파일이 저장됨
            # uploads 폴더를 원고 폴더로 사용
            manuscript_dir = os.path.join(job_dir, "uploads")
            os.makedirs(manuscript_dir, exist_ok=True)
            # Step3 서브폴더도 생성
            step3_dir = os.path.join(manuscript_dir, "Step3")
            os.makedirs(step3_dir, exist_ok=True)
            # 파일 분류: Step3 hwp는 Step3 폴더로, 나머지는 루트로
            # 업로드 시 "manuscripts_" 접두사가 붙으므로 원본 파일명으로 복원.
            # 파일명 앞뒤 공백은 외부 폴더(EBS 등)에서 섞여 들어오므로 strip.
            # 변형 매칭(괄호 안 내용 다름 등)은 parser._find_manuscript_file이 처리.
            for fpath in manuscripts:
                fname = os.path.basename(fpath)
                if fname.startswith("manuscripts_"):
                    fname = fname[len("manuscripts_"):]
                fname_nfc = unicodedata.normalize("NFC", fname).strip()
                # STEP3 식별 (파일명 변형에 robust하게):
                #   1) "Step3"/"스텝3" 계열 — 대소문자 무시(re.I), step과 3 사이
                #      공백/언더스코어/하이픈 허용([\s_-]*: "Step 3"·"Step_3"·"Step-3").
                #      3 뒤는 (?!\d)로 숫자만 배제(Step31 등 오인 방지).
                #      \b는 "_"를 단어문자로 봐 "Step 3_본문.docx"를 놓치므로 쓰지 않는다.
                #   2) "N번" 또는 "N~N번" 패턴 포함 (예: "20번", "41~42번", "15강 1번")
                is_step3 = (
                    bool(re.search(r'(?:스텝|step)[\s_-]*3(?!\d)', fname_nfc, re.I)) or
                    bool(re.search(r'\d+(?:\s*~\s*\d+)?\s*번', fname_nfc))
                )
                if is_step3:
                    dest = os.path.join(step3_dir, fname_nfc)
                else:
                    dest = os.path.join(manuscript_dir, fname_nfc)
                if fpath != dest:
                    safe_copy(fpath, dest)
        elif isinstance(manuscripts, str) and os.path.isdir(manuscripts):
            manuscript_dir = manuscripts
        else:
            # 폴더 경로 직접 지정 (CLI 모드)
            manuscript_dir = uploaded_files.get("manuscript_folder", "")

        if not manuscript_dir or not os.path.isdir(manuscript_dir):
            raise ValueError(f"원고 폴더를 찾을 수 없습니다: {manuscript_dir}")

        # job_dir에서 학년/연도/월 메타 읽기
        grade = self._read_meta(job_dir, "grade", 1)
        year = self._read_meta(job_dir, "year", 25)
        month = self._read_meta(job_dir, "month", 10)

        cfg = _load_config()

        log(f"[파서] 시작: 고{grade} {year}년 {month}월")
        data = parse_manuscript_folder(manuscript_dir, cfg, grade, year, month, log)

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Split into per-step files (ExtendScript can't eval >1MB JSON)
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
        log(f"[파서] 완료: {step_count}개 STEP → content_meta.json + "
            f"{step_count}개 분할 파일")

        return json_path

    # ── 2단계: JSX 준비 ─────────────────────────────────────────────────

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = _load_config()

        grade = self._read_meta(job_dir, "grade", 1)
        year = self._read_meta(job_dir, "year", 25)
        month = self._read_meta(job_dir, "month", 10)
        workbook_type = self._read_meta_str(job_dir, "workbook_type", "모의고사")
        school = self._read_meta_str(job_dir, "school", "")

        # 출력 파일명 생성
        yy = str(year)[-2:]
        mm = str(month).zfill(2)
        out_name = f"고{grade}_{yy}년_{mm}월_전체(C).indd"
        indd_path = os.path.join(cfg["indd_output_dir"], out_name)

        # 원본 indd → 작업 경로로 복사 (JSX에서 기존 문서를 별도 저장 후 닫음)
        # 학교 전용 템플릿 우선 → 없으면 기본 템플릿
        indd_map = cfg.get("indd_original", {})
        src = ""
        if school:
            src = indd_map.get(f"{workbook_type}_{school}", "")
            if src:
                log(f"[내지] 학교 전용 템플릿: {school}")
        if not src:
            src = indd_map.get(workbook_type, "")
        if os.path.exists(src):
            os.makedirs(os.path.dirname(indd_path), exist_ok=True)
            indd_path = safe_copy_indd(src, indd_path)
            log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            raise FileNotFoundError(f"내지 파일 없음: {indd_path}")

        # 제외 섹션 (UI 체크박스로 전달됨)
        exclude_path = os.path.join(job_dir, "exclude.txt")
        exclude = []
        if os.path.exists(exclude_path):
            raw = open(exclude_path, encoding="utf-8").read().strip()
            exclude = [s.strip() for s in raw.split(",") if s.strip()]
            if exclude:
                log(f"[JSX] 제외 섹션: {', '.join(exclude)}")

        # settings.json 작성
        settings_path = os.path.join(job_dir, ".settings.json")
        settings = {
            "json_path": json_path,
            "indd_path": indd_path,
            "output_dir": job_dir,
            "grade": grade,
            "year": year,
            "month": month,
            "exclude": exclude,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        # run.jsx 임시 사본 — settingsPath 교체
        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()

        new_line = f'    var settingsPath = "{settings_path}";'
        jsx_src = re.sub(
            r'var settingsPath\s*=\s*"[^"]*";',
            f'var settingsPath = "{settings_path}";',
            jsx_src,
        )

        jsx_copy = os.path.join(job_dir, "run.jsx")
        with open(jsx_copy, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        log(f"[JSX] 준비 완료: {jsx_copy}")
        return jsx_copy

    # ── 3단계: 검수 ─────────────────────────────────────────────────────

    def verify(self, job_dir: str, log) -> dict:
        cfg = _load_config()
        max_overflow = cfg["verify"]["max_overflow"]

        log_path = os.path.join(job_dir, cfg["log_filename"])
        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "error": "로그 파일 없음", "warnings": []}

        content = open(log_path, encoding="utf-8", errors="ignore").read()

        # 스텝별 완료 수
        step_m = re.search(r"STEP완료:\s*(\d+)개", content)
        actual_steps = int(step_m.group(1)) if step_m else None

        # 오버플로우
        overflow_m = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(overflow_m.group(1)) if overflow_m else None

        # 스타일 불일치
        style_warnings = re.findall(r"스타일불일치:\s*(.+)", content)

        # PDF
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

    # ── 유틸리티 ─────────────────────────────────────────────────────────

    def _read_meta(self, job_dir, key, default=None):
        p = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(p):
            val = open(p).read().strip()
            # "고2" 같은 값에서 숫자만 추출
            import re
            digits = re.sub(r'[^0-9]', '', val)
            if digits:
                return int(digits)
            try:
                return int(val)
            except ValueError:
                return default
        return default

    def _read_meta_str(self, job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p).read().strip() if os.path.exists(p) else default
