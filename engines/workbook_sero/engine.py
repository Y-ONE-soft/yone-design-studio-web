"""세로 워크북 엔진.

가로 워크북 엔진(workbook)과 동일한 원고 입력을 받지만, 세로 원본
([원본]워크북(모의고사_세로)_내지.indd)에 조판한다.

핵심 차이:
  - 원본의 한 문제(예: 20번) 사이클이 ~14페이지 (STEP1/2 = 10p + STEP3 = 4p)
  - 사이클이 문제 수만큼 반복되는 구조
  - JSX 는 사이클을 동적으로 복제/삭제하여 문제 수에 맞춤
  - STEP3 는 지문 길이에 따라 페이지를 동적 추가 (overflow 방지)

원고 형식은 가로와 동일 (parser는 workbook.parser 재사용 + q_num 분할 후처리).
"""

import json
import os
import re

from core.base import BaseEngine, safe_copy_indd, safe_copy
from core.paths import resolve_config

from engines.workbook_sero.parser import parse_manuscript_folder

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(_DIR, "jsx", "run.jsx")
_PATH_KEYS = [
    "indd_output_dir",
    "indd_original",
    "indd_original_gdrive_fallback",
    "manuscript_base",
]


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class WorkbookSeroEngine(BaseEngine):

    @property
    def material_id(self) -> str:
        return "workbook_sero"

    @property
    def display_name(self) -> str:
        return "워크북 세로"

    @property
    def description(self) -> str:
        return "세로버전 워크북 조판 자동화 (모의고사) - 문제별 사이클 구조"

    @property
    def subject_prefix(self) -> str:
        return "워크북세로"

    @property
    def template_name(self) -> str:
        return "typeset_workbook_sero.html"

    @property
    def jsx_timeout(self) -> int:
        return 1500  # 25분 — 사이클 복제 + 페이지 채우기 + PDF export

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
        manuscripts = uploaded_files.get("manuscripts")
        if isinstance(manuscripts, list):
            manuscript_dir = os.path.join(job_dir, "uploads")
            os.makedirs(manuscript_dir, exist_ok=True)
            step3_dir = os.path.join(manuscript_dir, "Step3")
            os.makedirs(step3_dir, exist_ok=True)
            import unicodedata
            for fpath in manuscripts:
                fname = os.path.basename(fpath)
                if fname.startswith("manuscripts_"):
                    fname = fname[len("manuscripts_"):]
                fname_nfc = unicodedata.normalize("NFC", fname)
                # STEP3 식별 (파일명 변형에 robust하게):
                #   1) "Step3"/"스텝3" 계열 — 대소문자 무시(re.I), step과 3 사이
                #      공백/언더스코어/하이픈 허용([\s_-]*: "Step 3"·"Step_3"·"Step-3").
                #      3 뒤는 (?!\d)로 숫자만 배제(Step31 등 오인 방지).
                #      \b는 "_"를 단어문자로 봐 "Step 3_본문.docx"를 놓치므로 쓰지 않는다.
                #   2) "N번" 또는 "N~N번" 패턴 (예: "20번", "41~42번", "15강 1번")
                is_step3 = (
                    bool(re.search(r'(?:스텝|step)[\s_-]*3(?!\d)', fname_nfc, re.I)) or
                    bool(re.search(r'\d+(?:\s*~\s*\d+)?\s*번', fname_nfc))
                )
                dest = os.path.join(step3_dir if is_step3 else manuscript_dir, fname)
                if fpath != dest:
                    safe_copy(fpath, dest)
        elif isinstance(manuscripts, str) and os.path.isdir(manuscripts):
            manuscript_dir = manuscripts
        else:
            manuscript_dir = uploaded_files.get("manuscript_folder", "")

        if not manuscript_dir or not os.path.isdir(manuscript_dir):
            raise ValueError(f"원고 폴더를 찾을 수 없습니다: {manuscript_dir}")

        grade = self._read_meta_int(job_dir, "grade", 1)
        year = self._read_meta_int(job_dir, "year", 25)
        month = self._read_meta_int(job_dir, "month", 10)

        cfg = _load_config()
        log(f"[파서] 시작: 고{grade} {year}년 {month}월 (세로 워크북)")
        data = parse_manuscript_folder(manuscript_dir, cfg, grade, year, month, log)

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # 사이클별 분할 — ExtendScript eval() 1MB 제한 회피
        meta = {
            "grade": data.get("grade"),
            "year": data.get("year"),
            "month": data.get("month"),
            "cycle_files": [],
            "cycle_count": len(data.get("cycles", [])),
        }
        for idx, cyc in enumerate(data.get("cycles", [])):
            cyc_path = os.path.join(job_dir, f"cycle_{idx:02d}.json")
            with open(cyc_path, "w", encoding="utf-8") as f:
                json.dump(cyc, f, ensure_ascii=False)
            meta["cycle_files"].append({
                "index": idx,
                "q_num": cyc.get("q_num"),
                "q_num_end": cyc.get("q_num_end"),
                "code": cyc.get("code"),
                "path": cyc_path,
            })

        meta_path = os.path.join(job_dir, "content_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        log(f"[파서] 완료: {meta['cycle_count']}개 사이클")
        return json_path

    # ── 2단계: JSX 준비 ─────────────────────────────────────────────────

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = _load_config()

        grade = self._read_meta_int(job_dir, "grade", 1)
        year = self._read_meta_int(job_dir, "year", 25)
        month = self._read_meta_int(job_dir, "month", 10)
        workbook_type = self._read_meta_str(job_dir, "workbook_type", "모의고사")

        yy = str(year)[-2:]
        mm = str(month).zfill(2)
        out_name = f"고{grade}_{yy}년_{mm}월_세로.indd"
        indd_path = os.path.join(cfg["indd_output_dir"], out_name)

        # 원본 .indd 경로 결정 — 로컬 원본 우선, 없으면 GDrive
        src = cfg.get("indd_original", {}).get(workbook_type, "")
        if not os.path.exists(src):
            src = cfg.get("indd_original_gdrive_fallback", {}).get(workbook_type, "")
        if not os.path.exists(src):
            raise FileNotFoundError(
                f"세로 원본 .indd 를 찾을 수 없습니다: {workbook_type}"
            )

        os.makedirs(os.path.dirname(indd_path), exist_ok=True)
        indd_path = safe_copy_indd(src, indd_path)
        log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")

        # 제외 섹션 (UI 체크박스로 전달됨)
        exclude_path = os.path.join(job_dir, "exclude.txt")
        exclude = []
        if os.path.exists(exclude_path):
            raw = open(exclude_path, encoding="utf-8").read().strip()
            exclude = [s.strip() for s in raw.split(",") if s.strip()]
            if exclude:
                log(f"[JSX] 제외 섹션: {', '.join(exclude)}")

        # settings.json
        settings_path = os.path.join(job_dir, ".settings.json")
        settings = {
            "json_path": json_path,
            "meta_path": os.path.join(job_dir, "content_meta.json"),
            "indd_path": indd_path,
            "output_dir": job_dir,
            "grade": grade,
            "year": year,
            "month": month,
            "workbook_type": workbook_type,
            "exclude": exclude,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        # JSX 사본 — settingsPath 토큰 치환
        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()
        jsx_src = jsx_src.replace("__SETTINGS_PATH__", settings_path)
        # 기존 'var settingsPath = "...";' 형식도 함께 치환 (이전 패턴 호환)
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
        content = ""
        if os.path.exists(log_path):
            content = open(log_path, encoding="utf-8", errors="ignore").read()

        overflow_m = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(overflow_m.group(1)) if overflow_m else None

        cycles_m = re.search(r"사이클완료:\s*(\d+)개", content)
        cycles_done = int(cycles_m.group(1)) if cycles_m else None

        pdf_path = None
        if re.search(r"PDF:\s*성공", content):
            for fname in os.listdir(job_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_path = os.path.join(job_dir, fname)
                    break

        warnings = []
        if overflow is None:
            warnings.append("오버플로우 수치 확인 불가")
        elif overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")
        if cycles_done is None:
            warnings.append("사이클 완료 수 확인 불가")

        ok = (
            overflow is not None and overflow <= max_overflow
            and pdf_path is not None
        )

        status = "✅ 통과" if ok else f"⚠️ 경고 {len(warnings)}건"
        log(f"[검수] {status} | 오버플로우: {overflow}개 | 사이클: {cycles_done} | PDF: {'있음' if pdf_path else '없음'}")

        return {
            "ok": ok,
            "overflow": overflow,
            "cycles_completed": cycles_done,
            "pdf_path": pdf_path,
            "warnings": warnings,
        }

    # ── 유틸리티 ─────────────────────────────────────────────────────────

    def _read_meta_int(self, job_dir, key, default=None):
        p = os.path.join(job_dir, f"{key}.txt")
        if not os.path.exists(p):
            return default
        val = open(p).read().strip()
        digits = re.sub(r'[^0-9]', '', val)
        if digits:
            return int(digits)
        try:
            return int(val)
        except ValueError:
            return default

    def _read_meta_str(self, job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p).read().strip() if os.path.exists(p) else default
