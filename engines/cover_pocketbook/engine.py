"""포켓북 표지 엔진.

분석본 PDF 업로드 -> 색상/일러스트 추출 -> Illustrator에서 포켓북 표지 AI 수정 -> PDF 출력.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import time
import unicodedata
import zipfile

import fitz
import numpy as np

from core.base import BaseEngine

_DIR = os.path.dirname(os.path.abspath(__file__))
_JSX_TEMPLATE = os.path.join(_DIR, "pocketbook_cover.jsx")
_TEMPLATE_AI = "/Users/nhj/Documents/작업/Y.ONE STUDIO/디자인/표지/포켓북/강동1_포켓북_표지.ai"
_OUTPUT_DIR = "/Users/nhj/Documents/작업/Y.ONE STUDIO/디자인/표지/포켓북"

# 포켓북 템플릿(강동1) 기준 색상
REF_TITLE = [80.1, 49.6, 81.6, 10.9]
REF_SUB = [51.7, 69.2, 84.3, 13.6]
REF_BG = [48.2, 0.0, 20.0, 0.0]

# 분석본에서 제외할 공통 색상 (tolerance 1.0)
_EXCLUDE_CMYK = [
    (71.7, 72.8, 83.7, 49.4),
    (0.0, 0.0, 12.0, 65.0),
]

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


def _cmyk_near(a, b, tol=1.0):
    return all(abs(a[i] - b[i]) < tol for i in range(4))


# ---- 색상 추출 --------------------------------------------------------


def _parse_cmyk_from_stream(doc, page):
    """page의 content stream에서 CMYK fill 색상 목록 추출."""
    colors = set()
    for cref in page.get_contents():
        content = doc.xref_stream(cref).decode("latin-1")
        for m in re.findall(r"([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+([\d.]+)\s+k", content):
            c, mm, y, kk = (float(x) for x in m)
            colors.add((round(c * 100, 1), round(mm * 100, 1),
                         round(y * 100, 1), round(kk * 100, 1)))
    return colors


def _extract_colors(pdf_path):
    """분석본 PDF에서 title/sub/bg CMYK 추출."""
    doc = fitz.open(pdf_path)
    front_colors = _parse_cmyk_from_stream(doc, doc[0])
    back_colors = _parse_cmyk_from_stream(
        doc, doc[1] if doc.page_count > 1 else doc[0]
    )
    doc.close()

    all_colors = front_colors | back_colors
    variable = {c for c in all_colors
                if not any(_cmyk_near(c, ex) for ex in _EXCLUDE_CMYK)}

    back_variable = {c for c in back_colors
                     if not any(_cmyk_near(c, ex) for ex in _EXCLUDE_CMYK)}
    bg = min(back_variable, key=lambda c: sum(c))

    text_colors = sorted(variable - {bg}, key=lambda c: sum(c), reverse=True)
    title = text_colors[0] if len(text_colors) >= 1 else bg
    sub = text_colors[1] if len(text_colors) >= 2 else title

    return {
        "title": list(title),
        "sub": list(sub),
        "bg": list(bg),
    }


# ---- 일러스트 추출 ----------------------------------------------------


def _extract_illustration(pdf_path, out_path):
    """분석본 PDF에서 텍스트 제거 후 일러스트 영역만 렌더링."""
    doc = fitz.open(pdf_path)
    page = doc[0]

    # content stream을 q..Q 블록으로 분리
    contents = page.get_contents()
    content = doc.xref_stream(contents[0]).decode("latin-1")
    lines = content.split("\n")

    blocks = []
    current = []
    depth = 0
    pre = []

    for line in lines:
        stripped = line.strip()
        if depth == 0 and stripped != "q" and not current:
            pre.append(line)
            continue
        current.append(line)
        if stripped == "q":
            depth += 1
        elif stripped == "Q":
            depth -= 1
            if depth == 0:
                blocks.append("\n".join(current))
                current = []

    # 처음 3 블록(Im0 sky, Fm0 overlay, Im1 land)만 유지, 나머지(텍스트) 제거
    new_content = "\n".join(pre) + "\n"
    for i, block in enumerate(blocks):
        if i <= 2:
            new_content += block + "\n"
    if "/OC /MC0 BDC" in new_content and "EMC" not in new_content:
        new_content += "EMC\n"

    doc.update_stream(contents[0], new_content.encode("latin-1"))

    # Image[1] (land) bbox로 크롭
    img_info = page.get_image_info(xrefs=True)
    if len(img_info) >= 2:
        bbox = img_info[1]["bbox"]
    else:
        bbox = page.rect

    clip = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
    pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), clip=clip)
    pix.save(out_path)
    doc.close()
    return out_path


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
        return "분석본 PDF에서 색상/삽화를 추출하여 포켓북 표지 PDF를 자동 생성합니다."

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
                    "label": "분석본 PDF (.pdf)",
                    "required": True,
                    "accept": ".pdf",
                    "multiple": True,
                },
            ]
        }

    def parse(self, uploaded_files, job_dir, log):
        pdfs = uploaded_files.get("analysis_pdfs", [])
        if isinstance(pdfs, str):
            pdfs = [pdfs]
        if not pdfs:
            raise ValueError("분석본 PDF가 업로드되지 않았습니다.")

        log(f"[분석본] {len(pdfs)}개 파일")

        illust_dir = os.path.join(job_dir, "illustrations")
        os.makedirs(illust_dir, exist_ok=True)

        schools_data = []
        for pdf_path in pdfs:
            basename = _nfc(os.path.basename(pdf_path))
            # app.py가 저장 시 "{key}_" 접두사를 붙이므로 제거
            if basename.startswith("analysis_pdfs_"):
                basename = basename[len("analysis_pdfs_"):]
            school_key = basename.split("_")[0]
            school_name = _school_display_name(school_key)

            log(f"  {school_key} ({school_name})")

            # 색상 추출
            colors = _extract_colors(pdf_path)
            log(f"    title=CMYK({colors['title']})")
            log(f"    sub=CMYK({colors['sub']})")
            log(f"    bg=CMYK({colors['bg']})")

            # 일러스트 추출
            illust_path = os.path.join(illust_dir, f"{school_key}_illust.png")
            _extract_illustration(pdf_path, illust_path)
            log(f"    일러스트 추출 완료")

            schools_data.append({
                "school_key": school_key,
                "school_name": school_name,
                "title_cmyk": colors["title"],
                "sub_cmyk": colors["sub"],
                "bg_cmyk": colors["bg"],
                "illustration_path": illust_path,
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

        # 생성된 PDF를 job_dir에 복사
        generated = []
        for sd in schools_data:
            pdf_name = f"{sd['school_key']}_포켓북_표지.pdf"
            src = os.path.join(_OUTPUT_DIR, pdf_name)
            if os.path.exists(src):
                dst = os.path.join(job_dir, pdf_name)
                shutil.copy2(src, dst)
                generated.append(dst)

        log(f"[완료] {len(generated)}/{len(schools_data)}개 PDF 생성")
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
