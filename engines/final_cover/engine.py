"""파이널 직전보충 표지 엔진.

시험기간 / 학교 / 학년 / Vol 을 선택하면 고정 템플릿(.ai)에서 텍스트를 교체하고
앞표지 + 빈 2P + 뒤표지 = 4페이지 CMYK A4(도련 없음) 고품질 인쇄용 PDF 를 출력한다.
Vol 복수선택 시 선택한 개수만큼 PDF 를 개별 생성한다.

파일 매핑: 세종->(세종), 광문->(세희T_광문), 배재->(윤기T_배재), 그 외 학교->(각인북스).

조판(내지)용 `final` 엔진과는 별개. 이 엔진은 표지(Illustrator)만 담당한다.
"""

import hashlib
import json
import os
import re
import subprocess
import time
import unicodedata
import zipfile

from core.base import BaseEngine, safe_copy

_DIR = os.path.dirname(os.path.abspath(__file__))
_JSX_TEMPLATE = os.path.join(_DIR, "final_cover.jsx")

_BASE = "/Users/nhj/Documents/작업/Y.ONE STUDIO/디자인/표지/파이널 직전보충"
# 고정 템플릿 .ai 4종 (열기만 하고 저장하지 않음 — 원본 보호)
_TEMPLATE_DIR = os.path.join(_BASE, "src_local")
_OUTPUT_DIR = os.path.join(_BASE, "OUTPUT")

_FILE_BY_KEY = {
    "세종": "파이널_표지(세종).ai",
    "광문": "파이널_표지(세희T_광문).ai",
    "배재": "파이널_표지(윤기T_배재).ai",
    "각인": "파이널_표지(각인북스).ai",
}
EXAMS = ["1학기 중간고사", "1학기 기말고사", "2학기 중간고사", "2학기 기말고사"]

ILLUSTRATOR_VERSIONS = ["2026", "2025", "2024", "2023"]


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _resolve_template_key(school):
    """학교명에서 전용 템플릿 결정. 세종/광문/배재 외에는 각인북스."""
    s = _nfc(school)
    if "세종" in s:
        return "세종"
    if "광문" in s:
        return "광문"
    if "배재" in s:
        return "배재"
    return "각인"


def _find_illustrator():
    for ver in ILLUSTRATOR_VERSIONS:
        if os.path.isdir(f"/Applications/Adobe Illustrator {ver}"):
            return "Adobe Illustrator"
    raise RuntimeError("Adobe Illustrator를 찾을 수 없습니다.")


def _run_illustrator_jsx(jsx_path, log, log_file_path, timeout=300):
    """osascript로 Illustrator에서 JSX 실행, 로그 파일에 'DONE' 나타날 때까지 대기."""
    app = _find_illustrator()
    log(f"[Illustrator] {app} 사용")

    script = (
        f'tell application "{app}"\n'
        f'    activate\n'
        f'    do javascript file "{jsx_path}"\n'
        f'end tell'
    )
    proc = subprocess.Popen(
        ["osascript", "-e", script],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
    )
    try:
        _, stderr = proc.communicate(timeout=60)
        if proc.returncode != 0 and stderr:
            log(f"[경고] osascript: {stderr.strip()}")
    except subprocess.TimeoutExpired:
        proc.kill()

    elapsed = 0
    last_len = 0
    while elapsed < timeout:
        time.sleep(2)
        elapsed += 2
        if os.path.exists(log_file_path):
            try:
                content = open(log_file_path, encoding="utf-8", errors="ignore").read()
                if len(content) > last_len:
                    for line in content[last_len:].strip().split("\n"):
                        line = line.strip()
                        if line and line != "DONE":
                            log(line)
                    last_len = len(content)
                if "DONE" in content:
                    time.sleep(1)
                    return
            except Exception:
                pass
    log(f"[경고] Illustrator 완료 대기 시간 초과 ({timeout}초)")


class FinalCoverEngine(BaseEngine):

    @property
    def material_id(self):
        return "final_cover"

    @property
    def display_name(self):
        return "파이널 직전보충 표지"

    @property
    def description(self):
        return ("시험기간/학교/학년/Vol을 선택하면 파이널 직전보충 표지를 "
                "4페이지 CMYK A4 PDF로 자동 생성합니다.")

    @property
    def template_name(self):
        return "typeset_final_cover.html"

    @property
    def skip_indesign(self):
        return True

    @property
    def upload_spec(self):
        # 커스텀 UI(typeset_final_cover.html)가 hidden 필드로 값을 넘긴다.
        # app.py 는 type=text 슬롯을 request.form 에서 읽어 uploaded 에 넣는다.
        return {
            "slots": [
                {"key": "exam", "label": "시험 기간", "required": True, "type": "text"},
                {"key": "school", "label": "학교", "required": True, "type": "text"},
                {"key": "grade", "label": "학년", "required": True, "type": "text"},
                {"key": "vols", "label": "Vol", "required": True, "type": "text"},
            ]
        }

    def parse(self, uploaded_files, job_dir, log):
        exam = _nfc(uploaded_files.get("exam", "")).strip()
        school = _nfc(uploaded_files.get("school", "")).strip()
        grade = _nfc(uploaded_files.get("grade", "")).strip()
        vols = [v.strip() for v in _nfc(uploaded_files.get("vols", "")).split(",") if v.strip()]

        if exam not in EXAMS:
            raise ValueError(f"시험 기간이 올바르지 않습니다: '{exam}'")
        if not school:
            raise ValueError("학교를 선택하세요.")
        if not grade:
            raise ValueError("학년을 선택하세요.")
        if not vols:
            raise ValueError("Vol을 하나 이상 선택하세요.")

        key = _resolve_template_key(school)
        template_path = os.path.join(_TEMPLATE_DIR, _FILE_BY_KEY[key])
        if not os.path.exists(template_path):
            raise ValueError(f"템플릿 파일이 없습니다: {template_path}")

        log(f"템플릿: {_FILE_BY_KEY[key]}  (학교={school} {grade}학년)")
        log(f"시험기간: {exam}  /  Vol: {', '.join(vols)}")

        os.makedirs(_OUTPUT_DIR, exist_ok=True)

        exam_nospace = re.sub(r"\s+", "", exam)
        outputs = []
        for vol in vols:
            vol_token = vol.replace(".", "")
            fname = f"파이널_표지_{school}{grade}_{exam_nospace}_{vol_token}.pdf"
            outputs.append({"vol": vol, "path": os.path.join(_OUTPUT_DIR, fname), "name": fname})

        # settings.json + JSX -> /tmp (한글 경로 회피)
        job_hash = hashlib.md5(job_dir.encode()).hexdigest()[:8]
        work_dir = f"/tmp/final_cover_{job_hash}"
        os.makedirs(work_dir, exist_ok=True)
        log_file = os.path.join(work_dir, "cover_log.txt")

        settings = {
            "template_path": template_path,
            "exam": exam,
            "school": school,
            "grade": grade,
            "outputs": outputs,
            "log_path": log_file,
        }
        settings_path = os.path.join(work_dir, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        # 디버그용 사본 (job_dir)
        with open(os.path.join(job_dir, ".settings.json"), "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()
        jsx_src = jsx_src.replace("%%SETTINGS_PATH%%", settings_path)
        jsx_path = os.path.join(work_dir, "final_cover.jsx")
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        log(f"[Illustrator] {len(outputs)}개 Vol 표지 생성 중...")
        _run_illustrator_jsx(jsx_path, log, log_file, timeout=len(outputs) * 60 + 60)

        # 생성된 PDF 를 job_dir 로 복사 (다운로드용)
        made = []
        for o in outputs:
            if os.path.exists(o["path"]):
                dst = os.path.join(job_dir, o["name"])
                safe_copy(o["path"], dst)
                made.append(dst)
                log(f"  생성: {o['name']}")
            else:
                log(f"  [경고] 미생성: {o['name']}")
        log(f"[생성] {len(made)}/{len(outputs)}개 완료")
        return settings_path

    def prepare_jsx(self, json_path, job_dir, log):
        # skip_indesign=True 이므로 호출되지 않음
        return ""

    def verify(self, job_dir, log):
        pdfs = [os.path.join(job_dir, f) for f in os.listdir(job_dir)
                if _nfc(f).endswith(".pdf")]
        warnings = []
        pdf_path = None

        if not pdfs:
            warnings.append("PDF가 생성되지 않았습니다.")
        elif len(pdfs) == 1:
            pdf_path = pdfs[0]
        else:
            zip_path = os.path.join(job_dir, "파이널_표지_전체.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in pdfs:
                    zf.write(p, os.path.basename(p))
            pdf_path = zip_path
            log(f"[ZIP] {len(pdfs)}개 PDF -> {os.path.basename(zip_path)}")

        ok = bool(pdfs) and not warnings
        if ok:
            log(f"[검수] 완료: {', '.join(os.path.basename(p) for p in pdfs)}")
        else:
            log("[검수] PDF가 생성되지 않았습니다.")

        return {
            "ok": ok,
            "overflow": 0,
            "stories": {},
            "pdf_path": pdf_path,
            "warnings": warnings,
        }
