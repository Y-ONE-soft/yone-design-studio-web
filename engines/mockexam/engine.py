"""동형모의고사 엔진 -- BaseEngine 구현."""

import json
import os
import re
import shutil
import unicodedata

from config import STUDIO_ROOT
from core.base import BaseEngine, safe_copy_indd


def _nfc(s):
    return unicodedata.normalize("NFC", s)


_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_PATH_KEYS = ["template_base", "output_base"]


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class MockexamEngine(BaseEngine):

    @property
    def material_id(self):
        return "mockexam"

    @property
    def display_name(self):
        return "동형모의고사"

    @property
    def description(self):
        return "동형모의고사 조판 자동화 -- 원고(hwpx/docx) -> InDesign 내지 배치"

    @property
    def subject_prefix(self):
        return "동형"

    @property
    def template_name(self):
        return "typeset_mockexam.html"

    @property
    def log_filename(self):
        return "typeset_log.txt"

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "manuscripts",
                    "label": "동형 원고 (.hwpx/.docx)",
                    "required": True,
                    "multiple": True,
                    "accept": ".hwpx,.docx,.hwp",
                }
            ]
        }

    # -- 헬퍼 --

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    def _resolve_template(self, cfg, school, grade):
        """학교+학년에 맞는 InDesign 템플릿 경로 반환."""
        school_cfg = cfg["schools"].get(school)
        if not school_cfg:
            raise FileNotFoundError(f"학교 설정을 찾을 수 없습니다: {school}")

        grade_num = grade.replace("고", "")
        pattern = school_cfg["template_pattern"]
        filename = pattern.replace("{grade_num}", grade_num)

        template_path = os.path.join(cfg["template_base"], filename)

        # {grade_num} 없는 패턴이면 학년 무관 단일 템플릿
        if "{grade_num}" not in pattern:
            template_path = os.path.join(cfg["template_base"], pattern)

        if not os.path.exists(template_path):
            raise FileNotFoundError(f"템플릿을 찾을 수 없습니다: {template_path}")

        return template_path

    # -- 학교 목록 스캔 --

    @staticmethod
    def scan_schools():
        """config에서 학교 목록 반환."""
        cfg = _load_config()
        result = {}
        for school_name, school_cfg in cfg["schools"].items():
            for grade in school_cfg["grades"]:
                if grade not in result:
                    result[grade] = []
                result[grade].append(school_name)
        for grade in result:
            result[grade].sort()
        return result

    # -- 파이프라인: parse --

    def parse(self, uploaded_files, job_dir, log):
        cfg = _load_config()
        school = _nfc(self._get_meta(job_dir, "school", ""))
        grade = self._get_meta(job_dir, "grade", "고1")
        exam_period = self._get_meta(job_dir, "exam_period", cfg["exam_period"])
        exam_date = self._get_meta(job_dir, "exam_date", "")
        exam_type = self._get_meta(job_dir, "exam_type", "")

        log(f"[설정] 학교={school}, 학년={grade}, 시험={exam_period}")
        log(f"[설정] 날짜={exam_date}, 종류={exam_type}")

        # 업로드된 원고 파일
        manuscript_files = uploaded_files.get("manuscripts", [])
        if not manuscript_files:
            raise FileNotFoundError("원고 파일이 업로드되지 않았습니다.")

        log(f"[원고] {len(manuscript_files)}개 파일:")
        for f in manuscript_files:
            log(f"  - {os.path.basename(f)}")

        from engines.mockexam.parser import parse_manuscripts
        content_path = parse_manuscripts(
            manuscript_files, school, grade, exam_period,
            exam_date, exam_type, job_dir, log
        )

        return content_path

    # -- 파이프라인: prepare_jsx --

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        school = _nfc(self._get_meta(job_dir, "school", "학교미선택"))
        grade = self._get_meta(job_dir, "grade", "고1")
        exam_period = self._get_meta(job_dir, "exam_period", cfg["exam_period"])

        school_cfg = cfg["schools"].get(school, {})
        short = school_cfg.get("short", school)

        # content.json 로드
        with open(json_path, encoding="utf-8") as f:
            content = json.load(f)

        # 회차별 처리
        rounds = content.get("rounds", [content])

        # 출력 디렉터리 — 조판/교재/동형모의고사/{학년}/{시험기간}/{학교}/
        grade_num = grade.replace("고", "")
        output_dir = os.path.join(
            STUDIO_ROOT, "조판", "교재", "동형모의고사",
            grade, exam_period, school
        )
        os.makedirs(output_dir, exist_ok=True)

        # 템플릿 복사 + jobs 구성
        template_path = self._resolve_template(cfg, school, grade)
        log(f"[템플릿] {os.path.basename(template_path)}")

        jobs = []
        for rd in rounds:
            round_num = rd.get("round", 1)
            indd_name = f"{short}{grade_num}_동형모의고사({round_num}회).indd"
            indd_path = os.path.join(output_dir, indd_name)
            indd_path = safe_copy_indd(template_path, indd_path)
            log(f"[내지] {round_num}회: {os.path.basename(indd_path)}")

            jobs.append({
                "round": round_num,
                "indd_path": indd_path,
                "data": rd,
            })

        # .settings.json
        settings = {
            "jobs": jobs,
            "output_dir": output_dir,
            "school": school,
            "grade": grade,
            "exam_period": exam_period,
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        return settings_path

    # -- 파이프라인: run_indesign --

    def run_indesign(self, job_dir, log):
        """JSX를 InDesign에서 실행."""
        settings_path = os.path.join(job_dir, ".settings.json")

        # JSX 템플릿 복사 + settings path 치환
        jsx_src = os.path.join(_DIR, "jsx", "run.jsx")
        jsx_dst = os.path.join(job_dir, "run.jsx")
        with open(jsx_src, encoding="utf-8") as f:
            jsx_code = f.read()
        jsx_code = jsx_code.replace("__SETTINGS_PATH__", settings_path)
        with open(jsx_dst, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        # 로그 경로
        log_path = os.path.join(job_dir, "typeset_log.txt")

        from core.indesign.runner import run_jsx
        run_jsx(jsx_dst, log, poll_log_path=log_path, timeout=self.jsx_timeout)

    @property
    def jsx_timeout(self):
        return 300  # 5분

    # -- 파이프라인: verify --

    def verify(self, job_dir, log):
        cfg = _load_config()
        log_path = os.path.join(job_dir, cfg["log_filename"])

        warnings = []
        overflow = 0
        pdf_paths = []

        if os.path.exists(log_path):
            lc = open(log_path, encoding="utf-8", errors="ignore").read()
            for m in re.finditer(r"오버플로우:\s*(\d+)개", lc):
                overflow += int(m.group(1))
            if overflow > 0:
                warnings.append(f"오버플로우 {overflow}개")

        # PDF 수집 — 이번 실행에서 생성된 indd에 대응하는 PDF만 수집
        sp = os.path.join(job_dir, ".settings.json")
        if os.path.exists(sp):
            with open(sp, encoding="utf-8") as f:
                settings = json.load(f)
            out_dir = settings.get("output_dir", "")
            if out_dir and os.path.isdir(out_dir):
                expected_pdfs = []
                for j in settings.get("jobs", []):
                    indd = j.get("indd_path", "")
                    if indd:
                        expected_pdfs.append(
                            os.path.splitext(os.path.basename(indd))[0] + ".pdf"
                        )
                for pdf_name in expected_pdfs:
                    full = os.path.join(out_dir, pdf_name)
                    if os.path.exists(full):
                        pdf_paths.append(full)

        for f_name in os.listdir(job_dir):
            if f_name.endswith(".pdf"):
                full = os.path.join(job_dir, f_name)
                if full not in pdf_paths:
                    pdf_paths.append(full)

        ok = len(pdf_paths) > 0 and overflow == 0

        return {
            "ok": ok,
            "overflow": overflow,
            "stories": {},
            "pdf_path": pdf_paths[0] if pdf_paths else None,
            "pdf_paths": pdf_paths,
            "warnings": warnings,
        }
