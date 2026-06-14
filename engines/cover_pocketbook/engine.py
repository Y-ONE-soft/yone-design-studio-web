"""포켓북 표지 엔진.

분석본 일러스트(.ai) 업로드 -> 색상 3종 추출 -> Illustrator에서 포켓북 표지 AI 색상/학교명 교체 -> PDF 출력.

규칙(학교마다 풍경은 동일, 색상만 다르게):
- 풍경 일러스트: 템플릿(강동1) 고정 — 학교별로 추출하지 않는다.
- 배경색: 분석본 배경색으로 교체 (앞면 크림 + 뒷면 패널).
- 포인트색 -> "POCKET BOOK" 제목.
- 보조색 -> 2026 / 학교명 / 학기 / 포켓북 등 나머지 문구.
"""

import hashlib
import json
import os
import re
import shutil
from core.base import safe_copy
import subprocess
import time
import unicodedata
import zipfile

import fitz
import numpy as np

from core.base import BaseEngine

_DIR = os.path.dirname(os.path.abspath(__file__))
_JSX_TEMPLATE = os.path.join(_DIR, "pocketbook_cover.jsx")
_OUTPUT_DIR = "/Users/nhj/Documents/작업/Y.ONE STUDIO/디자인/표지/포켓북"
# 템플릿은 보호 폴더(_template)의 사본을 사용 — 출력 .ai가 원본 템플릿을 덮어쓰지 않게 한다.
_TEMPLATE_AI = os.path.join(_OUTPUT_DIR, "_template", "강동1_포켓북_표지.ai")

# 포켓북 템플릿(강동1) 기준 색상 (find-and-replace 대상)
REF_TITLE = [80.1, 49.6, 81.6, 10.9]   # 'POCKET BOOK' -> 포인트색
REF_SUB = [51.7, 69.2, 84.3, 13.6]     # 2026/학교명/학기/포켓북 -> 보조색
REF_BG = [48.2, 0.0, 20.0, 0.0]        # 뒷면 패널 -> 배경색
REF_BG2 = [5.0, 5.0, 19.0, 0.0]        # 앞면 크림 배경 -> 배경색

ILLUSTRATOR_VERSIONS = ["2026", "2025", "2024", "2023"]


def _nfc(s):
    return unicodedata.normalize("NFC", s)


_YEOGO = {"상일", "명일"}


def _school_display_name(key):
    """'강동2' -> '강동고 2', '상일1' -> '상일여고 1'."""
    m = re.match(r"^(.+?)(\d+)$", key)
    if m:
        name, num = m.group(1), m.group(2)
        suffix = "여고 " if name in _YEOGO else "고 "
        return name + suffix + num
    return key


# ---- 색상 추출 --------------------------------------------------------
# 분석본 .ai의 '실제 요소 색상값'을 콘텐츠 스트림(CMYK fill 연산자 k)에서 그대로
# 읽는다. 렌더 픽셀은 텍스처+COLOR 블렌드로 요소 원색과 달라지므로 쓰지 않는다.
# 전 학교 공통(풍경/로고) 벡터색은 제외하고, 학교별 변동색에서 bg/제목/보조를 식별.

# 14개교 전부에서 등장하는 공통(풍경/로고) 벡터색 — 추출에서 제외
_COMMON_CMYK = [(71.7, 72.8, 83.7, 49.4), (0.0, 0.0, 12.0, 65.0)]
_K_PAT = re.compile(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+k\b")


def _near_cmyk(a, b, tol=2.5):
    return all(abs(a[i] - b[i]) < tol for i in range(4))


def _cmyk_to_rgb(c):
    C, M, Y, K = [v / 100.0 for v in c]
    return ((1 - C) * (1 - K) * 255.0, (1 - M) * (1 - K) * 255.0, (1 - Y) * (1 - K) * 255.0)


def _extract_colors(analysis_path):
    """분석본 .ai 콘텐츠 스트림에서 실제 요소 CMYK를 그대로 읽어 3색 식별.

    - 공통(풍경/로고)색 제외 후 남는 '학교별 변동색'에서:
      - bg        = 상단 여백 렌더색에 가장 가까운 변동색 (배경 식별)
      - secondary = 변동색 중 최다 빈도 (작은 문구 다수) -> 2026/학교명/학기/포켓북
      - title     = 그다음 빈도 (큰 제목)               -> 'POCKET BOOK'
    반환값은 분석본 요소의 CMYK 원값 그대로(렌더 근사 아님).
    """
    doc = fitz.open(analysis_path)
    counts = {}
    for xref in range(1, doc.xref_length()):
        try:
            s = doc.xref_stream(xref)
        except Exception:
            continue
        if not s:
            continue
        try:
            txt = s.decode("latin-1")
        except Exception:
            continue
        for m in _K_PAT.findall(txt):
            c = tuple(round(float(x) * 100, 1) for x in m)
            counts[c] = counts.get(c, 0) + 1
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.0, 1.0))
    arr = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n)[:, :, :3]
    doc.close()

    var = {c: n for c, n in counts.items()
           if not any(_near_cmyk(c, x) for x in _COMMON_CMYK)}
    if not var:
        return {"title": list(REF_TITLE), "sub": list(REF_SUB), "bg": list(REF_BG)}

    # 배경: 상단 좌/우 여백의 렌더 최빈색에 가장 가까운 변동색
    H, W = arr.shape[0], arr.shape[1]
    marg = np.concatenate([
        arr[int(H * 0.08):int(H * 0.22), 0:int(W * 0.05)].reshape(-1, 3),
        arr[int(H * 0.08):int(H * 0.22), int(W * 0.95):W].reshape(-1, 3),
    ]).astype(np.int32)
    mq = (marg // 6) * 6
    mc, mn = np.unique(mq, axis=0, return_counts=True)
    rough = mc[mn.argmax()]
    bg = min(var, key=lambda c: sum(abs(_cmyk_to_rgb(c)[i] - rough[i]) for i in range(3)))

    rest = sorted([c for c in var if c != bg], key=lambda c: -var[c])
    secondary = rest[0] if rest else bg
    title = rest[1] if len(rest) > 1 else secondary

    return {"title": list(title), "sub": list(secondary), "bg": list(bg)}


# ---- 학기 문구 추출 ---------------------------------------------------

_SEMESTER_RE = re.compile(r"(\d)\s*학기\s*([가-힣]*고사)")


def _extract_semester(analysis_path):
    """분석본에서 'N학기 X고사' 문구 추출 (예: '1학기 기말고사'). 못 찾으면 None."""
    doc = fitz.open(analysis_path)
    txt = ""
    for p in range(doc.page_count):
        txt += doc[p].get_text()
    doc.close()
    m = _SEMESTER_RE.search(_nfc(txt))
    if m:
        return m.group(1) + "학기 " + m.group(2)
    return None


# ---- Illustrator 실행 ------------------------------------------------


def _find_illustrator():
    for ver in ILLUSTRATOR_VERSIONS:
        if os.path.isdir(f"/Applications/Adobe Illustrator {ver}"):
            return "Adobe Illustrator"
    raise RuntimeError("Adobe Illustrator를 찾을 수 없습니다.")


def _run_illustrator_jsx(jsx_path, log, log_file_path, timeout=300):
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
    while elapsed < timeout:
        time.sleep(2)
        elapsed += 2
        if os.path.exists(log_file_path):
            try:
                content = open(log_file_path, encoding="utf-8", errors="ignore").read()
                if "DONE" in content:
                    time.sleep(1)
                    for line in content.strip().split("\n"):
                        line = line.strip()
                        if line:
                            log(line)
                    return
            except Exception:
                pass
    log(f"[경고] Illustrator 완료 대기 시간 초과 ({timeout}초)")


# ---- 엔진 클래스 ------------------------------------------------------


class CoverPocketbookEngine(BaseEngine):

    @property
    def material_id(self):
        return "cover_pocketbook"

    @property
    def display_name(self):
        return "포켓북 표지"

    @property
    def description(self):
        return "분석본 일러스트(.ai)에서 색상/풍경을 추출하여 포켓북 표지 PDF를 자동 생성합니다."

    @property
    def template_name(self):
        return "typeset_cover_pocketbook.html"

    @property
    def skip_indesign(self):
        return True

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "analysis_pdfs",
                    "label": "분석본 일러스트 (.ai)",
                    "required": True,
                    "accept": ".ai",
                    "multiple": True,
                },
            ]
        }

    def parse(self, uploaded_files, job_dir, log):
        pdfs = uploaded_files.get("analysis_pdfs", [])
        if isinstance(pdfs, str):
            pdfs = [pdfs]
        if not pdfs:
            raise ValueError("분석본 .ai가 업로드되지 않았습니다.")

        log(f"[분석본] {len(pdfs)}개 파일")

        schools_data = []
        for ai_path in pdfs:
            basename = _nfc(os.path.basename(ai_path))
            # app.py가 저장 시 "{key}_" 접두사를 붙이므로 제거
            if basename.startswith("analysis_pdfs_"):
                basename = basename[len("analysis_pdfs_"):]
            school_key = basename.split("_")[0]
            school_name = _school_display_name(school_key)

            log(f"  {school_key} ({school_name})")

            # 색상 3종 추출 (풍경은 템플릿 고정 — 추출하지 않음)
            colors = _extract_colors(ai_path)
            log(f"    point(POCKET BOOK)=CMYK({colors['title']})")
            log(f"    secondary(2026/학교/학기/포켓북)=CMYK({colors['sub']})")
            log(f"    bg=CMYK({colors['bg']})")

            # 학기 문구 추출 (예: '1학기 기말고사')
            semester = _extract_semester(ai_path)
            if semester:
                log(f"    학기={semester}")

            schools_data.append({
                "school_key": school_key,
                "school_name": school_name,
                "title_cmyk": colors["title"],
                "sub_cmyk": colors["sub"],
                "bg_cmyk": colors["bg"],
                "semester": semester or "",
            })

        # settings.json -> /tmp (한글 경로 회피)
        job_hash = hashlib.md5(job_dir.encode()).hexdigest()[:8]
        work_dir = f"/tmp/cover_pocketbook_{job_hash}"
        os.makedirs(work_dir, exist_ok=True)

        log_file = os.path.join(work_dir, "cover_log.txt")
        settings = {
            "template_path": _TEMPLATE_AI,
            "output_dir": _OUTPUT_DIR,
            "job_dir": job_dir,
            "ref_title": REF_TITLE,
            "ref_sub": REF_SUB,
            "ref_bg": REF_BG,
            "ref_bg2": REF_BG2,
            "schools": schools_data,
            "log_path": log_file,
        }
        settings_path = os.path.join(work_dir, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        # JSX 생성
        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()
        jsx_src = jsx_src.replace("%%SETTINGS_PATH%%", settings_path)
        jsx_path = os.path.join(work_dir, "pocketbook_cover.jsx")
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        # 디버그용 사본
        with open(os.path.join(job_dir, ".settings.json"), "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        # Illustrator 실행
        log(f"[Illustrator] {len(schools_data)}개 학교 표지 생성 중...")
        _run_illustrator_jsx(jsx_path, log, log_file, timeout=len(schools_data) * 60 + 60)

        # 생성된 PDF + 작업한 .ai를 job_dir에 복사
        generated = []
        for sd in schools_data:
            base = f"{sd['school_key']}_포켓북_표지"
            for ext in (".pdf", ".ai"):
                src = os.path.join(_OUTPUT_DIR, base + ext)
                if os.path.exists(src):
                    dst = os.path.join(job_dir, base + ext)
                    safe_copy(src, dst)
                    if ext == ".pdf":
                        generated.append(dst)

        log(f"[완료] {len(generated)}/{len(schools_data)}개 생성 (PDF + AI)")
        return settings_path

    def prepare_jsx(self, json_path, job_dir, log):
        return ""

    def verify(self, job_dir, log):
        pdfs = [os.path.join(job_dir, f)
                for f in os.listdir(job_dir)
                if _nfc(f).endswith("_표지.pdf")]

        warnings = []
        pdf_path = None

        if len(pdfs) == 0:
            warnings.append("PDF가 생성되지 않았습니다.")
        elif len(pdfs) == 1:
            pdf_path = pdfs[0]
        else:
            # 여러 개면 zip
            zip_path = os.path.join(job_dir, "포켓북_표지_전체.zip")
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for p in pdfs:
                    zf.write(p, os.path.basename(p))
            pdf_path = zip_path
            log(f"[ZIP] {len(pdfs)}개 PDF -> {os.path.basename(zip_path)}")

        ok = len(pdfs) > 0 and not warnings
        if ok:
            names = [os.path.basename(p) for p in pdfs]
            log(f"[검수] 완료: {', '.join(names)}")

        return {
            "ok": ok,
            "overflow": 0,
            "stories": {},
            "pdf_path": pdf_path,
            "warnings": warnings,
        }
