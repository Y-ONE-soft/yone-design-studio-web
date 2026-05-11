import json
import os
import re
import shutil
import subprocess
import threading
import time
import unicodedata

from core.base import BaseEngine

_DIR = os.path.dirname(os.path.abspath(__file__))
_JSX_TEMPLATE = os.path.join(_DIR, "cover_spine.jsx")
_COVER_OUTPUT_DIR = "/Users/nhj/Documents/작업/Y.ONE STUDIO/디자인/표지"

# 모듈 로드 시점에 JSX 템플릿을 1회만 읽어 메모리에 캐시.
# per-request 파일 I/O를 제거하여 macOS EDEADLK(Errno 11) 회피.
# 템플릿 변경 시 Flask 서버 재시작 필요.
with open(_JSX_TEMPLATE, encoding="utf-8") as _f:
    _JSX_TEMPLATE_CONTENT = _f.read()

# 파일명 키워드 → 하위 폴더 매핑
_SUBFOLDER_RULES = [
    (["워크북", "WORKBOOK"], "워크북"),
    (["FINALEDGE", "파이널엣지"], "파이널엣지"),
    (["포켓북", "POCKETBOOK"], "포켓북"),
]
_SUBFOLDER_DEFAULT = "프리미엄북"


def _resolve_cover_subdir(filename):
    """파일명에서 교재 키워드를 찾아 하위 폴더 결정."""
    upper = unicodedata.normalize("NFC", filename).upper()
    for keywords, folder in _SUBFOLDER_RULES:
        for kw in keywords:
            if kw.upper() in upper:
                return folder
    return _SUBFOLDER_DEFAULT

ILLUSTRATOR_VERSIONS = ["2026", "2025", "2024", "2023"]


def _find_illustrator():
    """설치된 Illustrator 앱 이름 반환 (AppleScript용)."""
    for ver in ILLUSTRATOR_VERSIONS:
        folder = f"/Applications/Adobe Illustrator {ver}"
        if os.path.isdir(folder):
            return "Adobe Illustrator"
    raise RuntimeError("Adobe Illustrator를 찾을 수 없습니다.")


def _run_illustrator_jsx(jsx_path, log, log_file_path, timeout=180):
    """osascript로 Illustrator에서 JSX 실행, 로그 파일 완료 대기."""
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
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
    )

    try:
        _, stderr = proc.communicate(timeout=60)
        if proc.returncode != 0 and stderr:
            log(f"[경고] osascript: {stderr.strip()}")
    except subprocess.TimeoutExpired:
        proc.kill()

    # 로그 파일에 "완료" 나타날 때까지 대기
    elapsed = 0
    last_len = 0
    while elapsed < timeout:
        time.sleep(2)
        elapsed += 2
        if os.path.exists(log_file_path):
            try:
                content = open(log_file_path, encoding="utf-8", errors="ignore").read()
                # 새 로그가 추가되면 실시간 전송
                if len(content) > last_len:
                    new_part = content[last_len:]
                    for line in new_part.strip().split("\r"):
                        line = line.strip()
                        if line:
                            log(line)
                    last_len = len(content)
                if "PDF:" in content:
                    time.sleep(1)
                    return
            except Exception:
                pass
    log(f"[경고] Illustrator 완료 대기 시간 초과 ({timeout}초)")


class CoverEngine(BaseEngine):

    @property
    def material_id(self):
        return "cover"

    @property
    def display_name(self):
        return "세네카 조정"

    @property
    def description(self):
        return "표지 AI 파일의 세네카(책등) 크기를 조정하고 PDF로 출력합니다."

    @property
    def template_name(self):
        return "typeset_cover.html"

    @property
    def skip_indesign(self):
        return True

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "ai_file",
                    "label": "표지 파일 (.ai)",
                    "required": True,
                    "accept": ".ai",
                },
                {
                    "key": "spine_mm",
                    "label": "세네카 (mm)",
                    "required": True,
                    "type": "text",
                },
                {
                    "key": "out_name",
                    "label": "교재명",
                    "required": False,
                    "type": "text",
                },
                {
                    "key": "issue_num",
                    "label": "주차수",
                    "required": False,
                    "type": "text",
                },
            ]
        }

    @staticmethod
    def _extract_old_issue(uploaded_name):
        """파일명에서 기존 주차수를 추출. 배재1_블랙북03_표지.ai → '03'"""
        name = unicodedata.normalize("NFC", uploaded_name)
        if name.startswith("ai_file_"):
            name = name[len("ai_file_"):]
        base = os.path.splitext(name)[0]
        idx = base.rfind("_표지")
        if idx == -1:
            m = re.search(r'(\d{2})$', base)
            return m.group(1) if m else None
        before = base[:idx]
        m2 = re.search(r'(\([^)]*\))$', before)
        if m2:
            before = before[:m2.start()]
        m3 = re.search(r'(\d{2})$', before)
        return m3.group(1) if m3 else None

    @staticmethod
    def _build_output_name(uploaded_name, issue_num):
        """업로드 파일명에서 주차수를 교체한 출력명 생성.

        명일2_워크북02_표지.ai + issue_num=4 → 명일2_워크북04_표지
        배재1_블랙북03_표지.ai + issue_num=5 → 배재1_블랙북05_표지
        """
        name = unicodedata.normalize("NFC", uploaded_name)
        if name.startswith("ai_file_"):
            name = name[len("ai_file_"):]
        base = os.path.splitext(name)[0]

        if not issue_num:
            return base

        padded = issue_num.zfill(2)

        # _표지 기준으로 분리
        idx = base.rfind("_표지")
        if idx == -1:
            return re.sub(r'\d{2}$', padded, base)

        before = base[:idx]
        after = base[idx:]

        paren = ""
        m = re.search(r'(\([^)]*\))$', before)
        if m:
            paren = m.group(1)
            before = before[:m.start()]

        before = re.sub(r'\d{2}$', padded, before)

        return before + paren + after

    def parse(self, uploaded_files, job_dir, log):
        """AI 파일을 열어 세네카 조정 + 주차수 변경 + 아웃라인 + PDF 저장."""
        ai_path = uploaded_files.get("ai_file")
        spine_str = uploaded_files.get("spine_mm", "")
        issue_num = uploaded_files.get("issue_num", "").strip()
        out_name = uploaded_files.get("out_name", "").strip()

        if not ai_path or not os.path.exists(ai_path):
            raise ValueError("AI 파일이 업로드되지 않았습니다.")

        try:
            spine_mm = float(spine_str)
        except (ValueError, TypeError):
            raise ValueError(f"세네카 값이 올바르지 않습니다: {spine_str}")

        if spine_mm < 0 or spine_mm > 50:
            raise ValueError(f"세네카 값 범위 초과: {spine_mm}mm (0~50mm)")

        # 출력 파일명: 교재명 + 주차수 + _표지
        # 교재명/주차수 미입력 시 원본 파일명 사용
        uploaded_name = os.path.basename(ai_path)
        old_issue = self._extract_old_issue(uploaded_name)

        if out_name:
            padded = issue_num.zfill(2) if issue_num else ""
            # 괄호 앞에 주차수 삽입: 워크북(범위) → 워크북04(범위)_표지
            paren = ""
            m = re.search(r'(\([^)]*\))$', out_name)
            if m:
                paren = m.group(1)
                out_name = out_name[:m.start()]
            out_base = out_name + padded + paren + "_표지"
        else:
            out_base = self._build_output_name(uploaded_name, issue_num)
        log(f"출력 파일명: {out_base}")

        # 출력 경로 (표지 폴더/하위폴더 + job_dir)
        sub = _resolve_cover_subdir(out_base)
        cover_dir = os.path.join(_COVER_OUTPUT_DIR, sub)
        os.makedirs(cover_dir, exist_ok=True)
        pdf_path = os.path.join(job_dir, out_base + ".pdf")
        ai_out_path = os.path.join(cover_dir, out_base + ".ai")
        pdf_out_path = os.path.join(cover_dir, out_base + ".pdf")
        log_file = os.path.join(job_dir, "cover_log.txt")

        # settings.json 생성
        settings = {
            "ai_path": ai_path,
            "spine_mm": spine_mm,
            "pdf_path": pdf_path,
            "ai_out_path": ai_out_path,
            "delete_spine": spine_mm <= 3,
            "outline": True,
            "log_path": log_file,
            "issue_num": issue_num if issue_num else None,
            "old_issue": old_issue,
        }
        settings_path = os.path.join(job_dir, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        # JSX 사본 생성 (settings 경로 삽입) — 템플릿은 모듈 로드 시 캐시됨
        jsx_content = _JSX_TEMPLATE_CONTENT.replace("%%SETTINGS_PATH%%", settings_path.replace("\\", "/"))
        jsx_path = os.path.join(job_dir, "cover_spine.jsx")
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_content)

        # Illustrator 실행
        log(f"세네카 {spine_mm}mm로 조정 중...")
        if issue_num:
            log(f"주차수 변경: → {issue_num}")
        _run_illustrator_jsx(jsx_path, log, log_file, timeout=180)

        # PDF를 표지 폴더에도 복사
        if os.path.exists(pdf_path):
            shutil.copy2(pdf_path, pdf_out_path)
            log(f"표지 폴더 저장: {os.path.basename(pdf_out_path)}")

        return settings_path

    def prepare_jsx(self, json_path, job_dir, log):
        # skip_indesign=True이므로 호출되지 않음
        return ""

    def verify(self, job_dir, log):
        """PDF 생성 여부 확인."""
        # PDF 찾기
        pdf_path = None
        for f in os.listdir(job_dir):
            if f.endswith(".pdf"):
                pdf_path = os.path.join(job_dir, f)
                break

        # 로그 파일 확인
        log_file = os.path.join(job_dir, "cover_log.txt")
        warnings = []
        if os.path.exists(log_file):
            content = open(log_file, encoding="utf-8", errors="ignore").read()
            if "ERROR" in content:
                warnings.append(content)

        ok = pdf_path is not None and os.path.exists(pdf_path)
        if ok:
            size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            log(f"PDF 생성 완료: {os.path.basename(pdf_path)} ({size_mb:.1f}MB)")
        else:
            log("[오류] PDF가 생성되지 않았습니다.")

        return {
            "ok": ok,
            "overflow": 0,
            "stories": {},
            "pdf_path": pdf_path,
            "warnings": warnings,
        }
