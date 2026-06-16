"""워크북 가공 — runner.jsx를 osascript로 호출하는 헬퍼.

JSX와 옵션/결과 텍스트 파일(K=V + ---BODY---)을 주고받는다.
ScriptUI 다이얼로그 없이 동작하므로 웹에서 그대로 호출 가능.
"""

from __future__ import annotations

import datetime
import os
import re
import subprocess
import threading
from typing import Any


# ===== 경로 =====
JSX_RUNNER = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/워크북가공/jsx/web/runner.jsx"
)
OPTS_PATH = "/tmp/wb_opts.txt"
RESULT_PATH = "/tmp/wb_result.txt"
DOCX_CONVERTER = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/워크북가공/docx_converter.py"
)
UPLOADS_DIR = os.path.expanduser(
    "~/Documents/작업/Y.ONE STUDIO/워크북가공/uploads"
)

INDESIGN_APP = "Adobe InDesign 2026"
DEFAULT_TIMEOUT = 180  # 초

# 동시 호출 방지 (옵션/결과 파일 공유)
_lock = threading.Lock()


# ===== I/O =====
def _write_opts(opts: dict[str, Any]) -> None:
    with open(OPTS_PATH, "w", encoding="utf-8") as f:
        for k, v in opts.items():
            if v is None:
                continue
            f.write(f"{k}={v}\n")


def _parse_result(text: str) -> dict[str, Any]:
    fields: dict[str, str] = {}
    body_lines: list[str] = []
    body_mode = False
    for line in text.splitlines():
        if not body_mode:
            if line.strip() == "---BODY---":
                body_mode = True
                continue
            eq = line.find("=")
            if eq < 0:
                continue
            k = line[:eq]
            v = line[eq + 1:].replace("\\n", "\n")
            fields[k] = v
        else:
            body_lines.append(line)
    out: dict[str, Any] = dict(fields)
    out["body"] = "\n".join(body_lines)
    return out


# ===== JSX 호출 =====
def call_runner(opts: dict[str, Any], timeout: int = DEFAULT_TIMEOUT) -> dict[str, Any]:
    """runner.jsx를 InDesign에서 실행하고 결과 dict 반환."""
    with _lock:
        # 결과 파일 초기화
        try:
            os.remove(RESULT_PATH)
        except FileNotFoundError:
            pass

        _write_opts(opts)

        # with timeout: 긴 작업(지문선별 등)이 기본 AppleEvent 2분 한도에 걸리지 않게
        script = (
            f'with timeout of {int(timeout)} seconds\n'
            f'tell application "{INDESIGN_APP}"\n'
            f'do script POSIX file "{JSX_RUNNER}" language javascript\n'
            f'end tell\n'
            f'end timeout'
        )
        try:
            proc = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"status": "err", "msg": f"osascript 타임아웃 ({timeout}s)"}

        if not os.path.isfile(RESULT_PATH):
            return {
                "status": "err",
                "msg": "결과 파일 없음. osascript stderr: " + (proc.stderr or "")[:500],
            }

        with open(RESULT_PATH, "r", encoding="utf-8") as f:
            text = f.read()
        return _parse_result(text)


# ===== 모드별 헬퍼 =====
def active_info() -> dict[str, Any]:
    """현재 활성 문서 정보 + 열린 문서 목록."""
    r = call_runner({"mode": "active_info"})
    if r.get("status") != "ok":
        return r
    open_docs = []
    for line in (r.get("body") or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            open_docs.append({"idx": parts[0], "name": parts[1], "path": parts[2]})
    r["openDocs"] = open_docs
    return r


def list_candidates(doc_path: str | None = None) -> dict[str, Any]:
    """후보 스토리 목록."""
    opts = {"mode": "list_candidates"}
    if doc_path:
        opts["docPath"] = doc_path
    r = call_runner(opts)
    if r.get("status") != "ok":
        return r
    cands = []
    for line in (r.get("body") or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 7:
            cands.append({
                "idx": int(parts[0]),
                "firstPage": parts[1],
                "frameCount": int(parts[2]),
                "paraCount": int(parts[3]),
                "promptCount": int(parts[4]),
                "passageCount": int(parts[5]),
                "sampleText": parts[6],
            })
    r["candidates"] = cands
    return r


def identify_rounds(doc_path: str | None = None,
                    story_indices: list[int] | None = None) -> dict[str, Any]:
    """회차 목록 (복수 스토리). 각 회차에 storyIdx 포함."""
    opts: dict[str, Any] = {"mode": "identify_rounds"}
    if doc_path:
        opts["docPath"] = doc_path
    if story_indices:
        opts["storyIndices"] = ",".join(str(i) for i in story_indices)
    r = call_runner(opts)
    if r.get("status") != "ok":
        return r
    rounds = []
    for line in (r.get("body") or "").splitlines():
        parts = line.split("\t")
        if len(parts) >= 7:
            rounds.append({
                "storyIdx": int(parts[0]),
                "idx": int(parts[1]),
                "page": parts[2],
                "paraCount": int(parts[3]),
                "seoCount": int(parts[4]),
                "objCount": int(parts[5]),
                "engStart": parts[6],
            })
    r["rounds"] = rounds
    return r


def remove_seo(doc_path: str | None = None, backup: bool = True, extract: bool = True,
               story_indices: list[int] | None = None) -> dict[str, Any]:
    opts: dict[str, Any] = {
        "mode": "remove_seo",
        "backup": "1" if backup else "0",
        "extract": "1" if extract else "0",
    }
    if doc_path:
        opts["docPath"] = doc_path
    if story_indices:
        opts["storyIndices"] = ",".join(str(i) for i in story_indices)
    return call_runner(opts, timeout=600)


def remove_rounds(round_spec: dict[Any, list[int]], doc_path: str | None = None,
                  backup: bool = True, extract: bool = True) -> dict[str, Any]:
    """round_spec: {storyIdx: [roundIdx, ...]} → roundSpec="0:1,3|2:0,4"."""
    parts = []
    for s_idx, r_idxs in round_spec.items():
        if not r_idxs:
            continue
        parts.append(f"{int(s_idx)}:" + ",".join(str(int(i)) for i in r_idxs))
    opts: dict[str, Any] = {
        "mode": "remove_rounds",
        "roundSpec": "|".join(parts),
        "backup": "1" if backup else "0",
        "extract": "1" if extract else "0",
    }
    if doc_path:
        opts["docPath"] = doc_path
    return call_runner(opts, timeout=600)


def compare(doc_path: str | None, orig_path: str) -> dict[str, Any]:
    opts = {"mode": "compare", "origPath": orig_path}
    if doc_path:
        opts["docPath"] = doc_path
    return call_runner(opts, timeout=300)


def save_doc(doc_path: str | None = None) -> dict[str, Any]:
    opts = {"mode": "save"}
    if doc_path:
        opts["docPath"] = doc_path
    return call_runner(opts)


# ===== 지문번호 선별 (PassageSelect 엔진: 모의고사/교과서/부교재/수능특강 범용) =====
def passage_detect(doc_path: str | None = None, readers: str = "") -> dict[str, Any]:
    """문서의 지문번호 + 섹션 구성을 탐지(미리보기). readers: 라벨리더 추가(콤마구분)."""
    opts: dict[str, Any] = {"mode": "passage_detect"}
    if doc_path:
        opts["docPath"] = doc_path
    if readers:
        opts["readers"] = readers
    return call_runner(opts, timeout=300)


def passage_select(doc_path: str | None, nums: str, select_mode: str = "keep",
                   backup: bool = True, relayout: bool = True,
                   leftover: str = "tight", save: bool = True,
                   readers: str = "") -> dict[str, Any]:
    """지문번호로 선별. select_mode='keep'(입력만 남김) | 'delete'(입력 삭제).
    nums="21, 31-34, 38"  leftover='none'|'empty'|'tight'."""
    opts: dict[str, Any] = {
        "mode": "passage_select",
        "selectMode": "delete" if select_mode == "delete" else "keep",
        "nums": nums or "",
        "backup": "1" if backup else "0",
        "relayout": "1" if relayout else "0",
        "leftover": leftover or "tight",
        "save": "1" if save else "0",
    }
    if doc_path:
        opts["docPath"] = doc_path
    if readers:
        opts["readers"] = readers
    return call_runner(opts, timeout=900)


# ===== 업로드 =====
_SAFE_NAME = re.compile(r"[^\w가-힣ㄱ-ㅎㅏ-ㅣ()\-.]")


def _sanitize_filename(name: str) -> str:
    name = os.path.basename(name).strip()
    name = _SAFE_NAME.sub("_", name)
    if not name.lower().endswith(".indd"):
        raise ValueError("indd 파일만 업로드 가능합니다.")
    return name


def save_upload(file_storage) -> dict[str, Any]:
    """Flask FileStorage를 잡 폴더에 저장하고 작업 경로 반환.

    잡 폴더: uploads/{YYYYMMDD_HHMMSS}_{stem}/{원본명}.indd
    같은 폴더에 백업/추출/docx도 함께 쌓이도록 함.
    """
    raw_name = getattr(file_storage, "filename", "") or ""
    try:
        safe = _sanitize_filename(raw_name)
    except ValueError as e:
        return {"status": "err", "msg": str(e)}

    stem = os.path.splitext(safe)[0]
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    job_dir = os.path.join(UPLOADS_DIR, f"{ts}_{stem}")
    os.makedirs(job_dir, exist_ok=True)
    out_path = os.path.join(job_dir, safe)
    file_storage.save(out_path)
    size = os.path.getsize(out_path)
    return {
        "status": "ok",
        "docPath": out_path,
        "jobDir": job_dir,
        "fileName": safe,
        "fileSize": size,
    }


def list_job_files(job_dir: str) -> list[dict[str, Any]]:
    """잡 폴더 안 파일 목록 (다운로드 링크 생성용)."""
    if not os.path.isdir(job_dir):
        return []
    out = []
    for name in sorted(os.listdir(job_dir)):
        full = os.path.join(job_dir, name)
        if os.path.isfile(full):
            out.append({
                "name": name,
                "path": full,
                "size": os.path.getsize(full),
            })
    return out


# ===== docx 변환 =====
def convert_txt_to_docx(txt_path: str) -> dict[str, Any]:
    """docx_converter.py를 호출. 결과 path 반환."""
    if not os.path.isfile(txt_path):
        return {"status": "err", "msg": f"파일 없음: {txt_path}"}
    try:
        proc = subprocess.run(
            ["python3", DOCX_CONVERTER, txt_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {"status": "err", "msg": "변환 타임아웃"}
    if proc.returncode != 0:
        return {"status": "err", "msg": proc.stderr or proc.stdout}
    docx_path = os.path.splitext(txt_path)[0] + ".docx"
    if not os.path.isfile(docx_path):
        return {"status": "err", "msg": "변환됐지만 파일 없음", "stdout": proc.stdout}
    return {"status": "ok", "docxPath": docx_path, "stdout": proc.stdout.strip()}
