"""
원고 파일(hwpx/hwp/docx) → 텍스트/발문 추출.

기본 사용:
    from engines._taxonomy import extract_text, extract_questions
    text = extract_text("path/to/manuscript.hwpx")
    questions = extract_questions("path/to/manuscript.hwpx")
    # questions = [{"q": "발문...", "line_idx": 5}, ...]
"""
import os
import re
import shutil
import subprocess
import unicodedata
import hashlib
import zipfile

from .classify import is_question


def extract_hwpx(path: str) -> str:
    """hwpx (ZIP + XML) → 문단 단위 텍스트."""
    try:
        with zipfile.ZipFile(path) as z:
            sections = []
            for name in z.namelist():
                if "section" in name.lower() and name.endswith(".xml"):
                    sections.append(z.read(name).decode("utf-8", "replace"))
            if not sections:
                return ""
            chunks = []
            for xml in sections:
                for para in re.findall(r"<hp:p[^>]*>(.*?)</hp:p>", xml, re.DOTALL):
                    txts = re.findall(r"<hp:t[^>]*>([^<]*)</hp:t>", para)
                    chunks.append("".join(txts))
            return "\n".join(chunks)
    except Exception as e:
        return f"__ERR__:hwpx:{e}"


def extract_hwp(path: str) -> str:
    """hwp (OLE2 바이너리) → pyhwp의 hwp5txt 사용."""
    local = f"/tmp/_hwp_{hashlib.md5(path.encode()).hexdigest()[:8]}.hwp"
    try:
        shutil.copy2(path, local)
        r = subprocess.run(["hwp5txt", local], capture_output=True, timeout=60)
        return r.stdout.decode("utf-8", "replace")
    except FileNotFoundError:
        return "__ERR__:hwp:hwp5txt 명령 없음 (pip install pyhwp)"
    except Exception as e:
        return f"__ERR__:hwp:{e}"
    finally:
        try:
            os.remove(local)
        except OSError:
            pass


def extract_docx(path: str) -> str:
    """docx (ZIP + XML) → 문단 단위 텍스트."""
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
            paras = re.findall(r"<w:p[^>]*>(.*?)</w:p>", xml, re.DOTALL)
            lines = []
            for p in paras:
                txts = re.findall(r"<w:t[^>]*>([^<]*)</w:t>", p)
                lines.append("".join(txts))
            return "\n".join(lines)
    except Exception as e:
        return f"__ERR__:docx:{e}"


def extract_text(path: str) -> str:
    """확장자에 따라 자동 디스패치. 출력 = 문단 줄바꿈된 단일 문자열.

    오류 시 "__ERR__:<ext>:<message>" 형태로 반환 (예외 throw 안 함).
    호출자가 startswith("__ERR__") 체크로 분기 가능.
    """
    ext = path.lower().rsplit(".", 1)[-1] if "." in path else ""
    if ext == "hwpx":
        return extract_hwpx(path)
    if ext == "hwp":
        return extract_hwp(path)
    if ext == "docx":
        return extract_docx(path)
    return f"__ERR__:unsupported_ext:{ext}"


def extract_questions(path: str):
    """원고에서 발문 라인만 추출. 출력 = list[{"q": str, "line_idx": int}]."""
    text = extract_text(path)
    if text.startswith("__ERR__"):
        return []
    out = []
    for i, line in enumerate(text.split("\n")):
        if is_question(line):
            out.append({"q": line.strip(), "line_idx": i})
    return out


def extract_and_classify(path: str):
    """원고 한 파일 → 발문별 분류 결과.

    출력: list[{"q", "code", "label", "kind", "line_idx"}]
    """
    from .classify import classify
    qs = extract_questions(path)
    out = []
    for item in qs:
        code, label, kind = classify(item["q"])
        out.append({
            "q": item["q"],
            "line_idx": item["line_idx"],
            "code": code,
            "label": label,
            "kind": kind,
        })
    return out
