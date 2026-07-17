# -*- coding: utf-8 -*-
"""워크북 전체(C) → 세로버전 변환 엔진 (W27) — 수동 ConvertToVertical.jsx 웹 흡수.

수동본(manual_jsx_mirror/ConvertToVertical.jsx, 2026-06-17 최신본)의 변환
의미론을 core/jsx/convert_vertical.body.jsx 로 이식했다:

  전체(C) = 섹션별 구성 (표지 3p → 어휘 18p → A섹션 5종×18p → 구분 2p →
            C섹션 어법3종×18p+영작배열 → 구분 2p → 실전문제 O/M → 마지막p)
  세로(C) = 지문별 구성 (지문 1개의 [어휘결합 1p + A 5p + 어법 3p +
            영작배열 np + 실전문제 mp] 사이클 × 18)

수동본 하드코딩 상수의 검증/외부화 (W27 과제 — 상수 규명):
  - A_SECT_COUNT=90 / NUM_PROBLEMS=18 / 어휘 9쌍 / A시작 21 → 문서의 구분
    페이지 위치(sep1)에서 유도로 대체: NUM=(sep1-front)/6. 표준 문서에서
    수동본 공식과 동치, 비표준 구조는 침묵 오배치 대신 [오류] 중단.
  - front_pages=3 / sep_scan_start=100 / 마진 20·22 → config.json 외부화.
  - GDrive 개인 경로 3종(세로 마스터/STEP123.ai/이미지 폴더) → config.json.
    세로 마스터는 GDrive 직접 열기 금지 규칙에 따라 job_dir 로컬 사본으로
    전달 (relink 대상 ai/이미지는 읽기 전용 참조라 GDrive 경로 그대로).

흐름:
  1. parse: 전체(C) .indd 선택(업로드 또는 서버 경로) → job_dir 사본
  2. prepare_jsx: 사본 → 출력 경로 복사 + 세로 마스터 로컬 사본 +
     설정 JSON + convert_vertical.body.jsx 빌드
  3. run_indesign: 러너 (stall_limit 1800 — 재배치+save+export 장시간)
  4. verify: 원본/출력 dump 대조 — 내용 보존 + 사이클 구조 + 오버플로우 +
     페이지/PDF/[경고] (감사 3패턴: 부트스트랩 try-catch·job 전용 로그·
     export 정규화는 JSX에 내장)
"""

from __future__ import annotations

import json
import os
import re
import unicodedata

from core.base import BaseEngine, safe_copy_indd
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config

_DIR = os.path.dirname(os.path.abspath(__file__))
_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                     "core", "jsx", "convert_vertical.body.jsx")

_PATH_KEYS = ["output_base", "master_indd", "step123_ai", "image_base"]


def _nfc(s):
    return unicodedata.normalize("NFC", s) if s else s


def _load_config():
    with open(os.path.join(_DIR, "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _norm_line(t):
    """덤프 라인 정규화 (passage_remove norm_line 준용 — 대조 키)."""
    t = unicodedata.normalize("NFC", t or "")
    t = t.replace("﻿", "").replace("￼", "")
    t = re.sub(r"\s+", " ", t).strip()
    return t


# 지문 코드: {YYMMQQ} → 뒤 2자리 / [NN]·{NN} → 그대로 (JSX leadPassageNum 동일)
_RE_CODE6 = re.compile(r"^\s*\{(\d{4})(\d{2}(?:~\d+)?)\}")
_RE_CODE_SHORT = re.compile(r"^\s*[\[{]\s*(\d{1,3}(?:~\d+)?)\s*[\]}]")


def _lead_code_of_text(t):
    m = _RE_CODE6.match(t or "")
    if m:
        return m.group(2)
    m = _RE_CODE_SHORT.match(t or "")
    if m:
        return m.group(1)
    return None


def page_code_sequence(dump):
    """덤프에서 페이지 순서대로 지문 코드 나열 (코드 없는 페이지는 건너뜀).

    스토리의 fp(프레임별 페이지)와 첫 단락 텍스트로 페이지→코드를 만든다.
    한 페이지에 코드 프레임이 여럿이면 첫 발견 코드 사용.
    """
    page_order = [p["p"] for p in (dump.get("pages") or [])]
    by_page = {}
    for st in dump.get("stories", []):
        pgs = st.get("pg") or []
        if len(pgs) != 1:
            continue          # 코드 프레임은 단일 페이지 프레임
        code = None
        for para in st.get("paragraphs", []):
            code = _lead_code_of_text(para.get("t", ""))
            if code is not None:
                break
        if code is not None and pgs[0] not in by_page:
            by_page[pgs[0]] = code
    return [(p, by_page[p]) for p in page_order if p in by_page]


def contiguous_blocks(seq):
    """[(page, code)...] → 코드 등장 블록 리스트 (연속 동일 코드 병합)."""
    blocks = []
    for _p, c in seq:
        if not blocks or blocks[-1] != c:
            blocks.append(c)
    return blocks


class ConvertToVerticalEngine(BaseEngine):
    """워크북 전체(C) → 세로버전 변환 — [가공] > 변환."""

    @property
    def material_id(self):
        return "convert_to_vertical"

    @property
    def display_name(self):
        return "워크북 세로 변환 (베타)"

    @property
    def description(self):
        return ("조판된 모의고사 워크북 전체(C) .indd를 지문별 사이클의 "
                "세로버전으로 변환 (수동 ConvertToVertical.jsx 웹 흡수)")

    @property
    def subject_prefix(self):
        return "세로변환"

    @property
    def template_name(self):
        return "typeset_convert_to_vertical.html"

    @property
    def log_filename(self):
        return "조판_로그.txt"

    @property
    def jsx_timeout(self):
        return 5400

    @property
    def upload_spec(self):
        return {
            "slots": [
                {"key": "indd", "label": "전체(C) .indd (업로드)",
                 "type": "file", "accept": ".indd", "required": False},
                {"key": "doc_path", "label": "서버 파일 경로 (폴더 스캔 선택)",
                 "type": "text", "required": False},
                {"key": "result_name", "label": "결과 파일명 (선택)",
                 "type": "text", "required": False},
                {"key": "export_pdf", "label": "PDF 함께 출력 (on/off, 기본 on)",
                 "type": "text", "required": False},
            ]
        }

    def _config(self):
        return _load_config()

    def _read_meta_str(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    # ── 1단계: parse ────────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        src = uploaded_files.get("indd")
        if not (src and os.path.exists(src)):
            doc_path = (uploaded_files.get("doc_path") or "").strip()
            if not doc_path:
                raise ValueError(
                    "전체(C) .indd를 업로드하거나 서버 파일을 선택하세요")
            src = os.path.abspath(os.path.expanduser(doc_path))
        if not (os.path.isfile(src) and src.lower().endswith(".indd")):
            raise FileNotFoundError(f".indd 파일을 찾을 수 없습니다: {src}")

        src_name = _nfc(os.path.basename(src))
        log(f"[세로변환] 입력: {src_name}")

        # GDrive/원본 보호 — job_dir 로컬 사본에서만 작업
        local_src = safe_copy_indd(src, os.path.join(job_dir, "source.indd"))
        log(f"[세로변환] 로컬 사본 복사 완료 ({os.path.getsize(local_src)//(1024*1024)}MB)")

        content = {
            "source_name": src_name,
            "source_path": src,
            "source_local": local_src,
        }
        path = os.path.join(job_dir, "content.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=1)
        return path

    # ── 2단계: prepare_jsx ──────────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = self._config()
        content = json.load(open(json_path, encoding="utf-8"))

        # 출력 파일명: 기본 = 원본명에서 '전체' → '세로'
        result_name = self._read_meta_str(job_dir, "result_name", "").strip()
        if not result_name:
            base = os.path.splitext(content["source_name"])[0]
            if "전체" in base:
                result_name = base.replace("전체", "세로")
            else:
                result_name = base + "_세로"
        out_dir = cfg["output_base"]
        os.makedirs(out_dir, exist_ok=True)
        out_indd = safe_copy_indd(content["source_local"],
                                  os.path.join(out_dir, result_name + ".indd"))
        log(f"[세로변환] 작업 사본(출력 위치): {os.path.basename(out_indd)}")

        export_pdf_raw = self._read_meta_str(job_dir, "export_pdf", "on").lower()
        export_pdf = export_pdf_raw in ("", "on", "true", "1", "yes")
        pdf_path = out_indd[:-5] + ".pdf" if export_pdf else ""

        # 세로 마스터 원본 — GDrive 직접 열기 금지 → job_dir 로컬 사본
        master_local = ""
        master_src = os.path.expanduser(cfg.get("master_indd") or "")
        if master_src and os.path.exists(master_src):
            master_local = safe_copy_indd(
                master_src, os.path.join(job_dir, "master_세로원본.indd"))
            log(f"[세로변환] 세로 마스터 로컬 사본: {os.path.basename(master_local)}")
        else:
            log(f"[경고] 세로 마스터 원본 없음 — STEP10(마스터/스타일 동기화) 생략: "
                f"{master_src}")

        jsx_log = os.path.abspath(os.path.join(job_dir, self.log_filename))
        result_json = os.path.abspath(os.path.join(job_dir, "convert_result.json"))

        jsx_cfg = {
            "doc_path": out_indd,
            "out_indd": out_indd,
            "out_pdf": pdf_path,
            "master_indd": master_local,
            "step123_ai": os.path.expanduser(cfg.get("step123_ai") or ""),
            "image_base": os.path.expanduser(cfg.get("image_base") or ""),
            "front_pages": cfg.get("front_pages", 3),
            "sep_scan_start": cfg.get("sep_scan_start", 100),
            "margin_outside": cfg.get("margin_outside", 20),
            "margin_inside": cfg.get("margin_inside", 22),
            "result_json": result_json,
        }
        jsx_cfg_path = os.path.abspath(os.path.join(job_dir, "convert_cfg.json"))
        with open(jsx_cfg_path, "w", encoding="utf-8") as f:
            json.dump(jsx_cfg, f, ensure_ascii=False, indent=1)

        jsx_path = build_jsx(
            _BODY,
            {"__CFG_PATH__": jsx_cfg_path},
            log_path=jsx_log,
            out_path=os.path.join(job_dir, "run.jsx"))

        settings = {"engine": self.material_id,
                    "indd_path": out_indd,
                    "pdf_path": pdf_path or None,
                    "export_pdf": export_pdf,
                    "source_local": content["source_local"],
                    "jsx_path": jsx_path, "log_path": jsx_log,
                    "log_paths": [jsx_log],
                    "result_json": result_json,
                    "json_path": json_path,
                    "output_dir": out_dir}
        with open(os.path.join(job_dir, ".settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return jsx_path

    # ── 3단계: run_indesign ─────────────────────────────────────────────────

    def run_indesign(self, job_dir, log):
        from core.indesign.runner import run_jsx
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        # 재실행 안전 — stale 완료 마커 제거
        try:
            os.remove(settings["log_path"])
        except OSError:
            pass
        run_jsx(settings["jsx_path"], log,
                poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="세로 변환 완료",
                stall_limit=1800)

    # ── 4단계: verify ───────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        from core.inspect import dump_indd

        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        warnings = []
        ok = True

        indd_path = settings["indd_path"]
        if not os.path.exists(indd_path):
            return {"ok": False, "overflow": 0, "stories": {},
                    "pdf_path": None, "pdf_paths": [], "indd_path": None,
                    "warnings": [f"❌ .indd 미생성: {os.path.basename(indd_path)}"]}

        # 실행 로그 (job 전용 — 공용 로그 누적 오염 방지 패턴)
        render_warns = []
        log_content = ""
        try:
            with open(settings["log_path"], encoding="utf-8") as f:
                log_content = f.read()
            render_warns = [ln.strip() for ln in log_content.splitlines()
                            if "[경고]" in ln or "[오류]" in ln]
        except OSError:
            pass
        if "세로 변환 완료" not in log_content:
            ok = False
            warnings.append("❌ 완료 마커 없음 — JSX 중단 의심")
        for w in render_warns[:8]:
            warnings.append(f"⚠️ {w}")
        if any("[오류]" in w for w in render_warns):
            ok = False

        # 변환 결과 통계 (JSX가 기록)
        stats = {}
        try:
            stats = json.load(open(settings["result_json"], encoding="utf-8"))
        except (OSError, ValueError):
            warnings.append("⚠️ 변환 결과 JSON 없음 — 구조 게이트 축소 판정")
        num_problems = stats.get("num_problems")

        # 원본/출력 dump 대조
        src_dump = dump_indd(settings["source_local"],
                             os.path.join(job_dir, "source_dump.json"),
                             log, timeout=1800)
        out_dump = dump_indd(indd_path,
                             os.path.join(job_dir, "typeset_dump.json"),
                             log, timeout=1800)

        # (a) 내용 보존 — 원본 본문 라인(len>=25)이 출력에 존재.
        #     의도적 손실 제외: 구분 페이지(none-master, sep_scan 위치 이후)·
        #     첫 페이지(간지 처리로 비간지 프레임 제거)에 걸친 스토리.
        cfg = self._config()
        sep_start = cfg.get("sep_scan_start", 100)
        src_pages_inv = src_dump.get("pages") or []
        excluded_pages = set()
        if src_pages_inv:
            excluded_pages.add(src_pages_inv[0]["p"])          # 첫 페이지
            for idx, p in enumerate(src_pages_inv):
                if idx >= sep_start and not p.get("m"):
                    excluded_pages.add(p["p"])                 # 구분 페이지
        must_keep = set()
        for st in src_dump.get("stories", []):
            pgs = set(st.get("pg") or [])
            if not pgs or (pgs & excluded_pages):
                continue
            # 헤더 프레임(y<=0) 스토리 — STEP2가 어휘 페이지에서 제거 (의도 손실)
            b = st.get("b")
            if b and b[0] <= 0:
                continue
            for para in st.get("paragraphs", []):
                t = _norm_line(para.get("t"))
                if len(t) >= 25:
                    must_keep.add(t)
        got = set()
        out_overflow = 0
        for st in out_dump.get("stories", []):
            for para in st.get("paragraphs", []):
                t = _norm_line(para.get("t"))
                if len(t) >= 25:
                    got.add(t)
            if st.get("overflow"):
                out_overflow += 1
        missing = must_keep - got
        if missing:
            ok = False
            warnings.append(
                f"❌ 내용 누락 {len(missing)}라인 (원본 대비): "
                + " | ".join(sorted(missing)[:3]))
        log(f"[검수] 내용 보존: 원본 {len(must_keep)}라인 중 "
            f"누락 {len(missing)}")

        # (b) 사이클 구조 — 출력의 지문 코드가 연속 블록으로 그룹화됐는지
        seq = page_code_sequence(out_dump)
        blocks = contiguous_blocks(seq)
        dup = [b for b in set(blocks) if blocks.count(b) > 1]
        if dup:
            ok = False
            warnings.append(
                f"❌ 지문 흩어짐: 코드 {sorted(dup)[:5]} 가 비연속 블록으로 등장 "
                "— 사이클 재배치 불완전")
        if num_problems:
            canon = [c for c in (stats.get("canon") or []) if c]
            canon_set = set(canon)
            main_blocks = [b for b in blocks if b in canon_set]
            # canon 지문은 각 1블록 = num_problems개 블록이어야 함
            if len(set(main_blocks)) < len(canon_set):
                missing_codes = sorted(canon_set - set(main_blocks))
                warnings.append(
                    f"⚠️ canon 지문 {len(missing_codes)}개 코드 미검출 "
                    f"(코드 프레임 부재 가능): {missing_codes[:5]}")
        log(f"[검수] 사이클 구조: 코드 페이지 {len(seq)}개 → 블록 "
            f"{len(blocks)}개 (문제 {num_problems or '?'}개)")

        # (c) 오버플로우 — 원본 대비 증가만 실패
        src_overflow = src_dump.get("overflow_stories", 0)
        if out_overflow > src_overflow:
            ok = False
            warnings.append(f"❌ 오버플로우 증가: {src_overflow} → {out_overflow}")
        elif out_overflow:
            warnings.append(f"⚠️ 오버플로우 스토리 {out_overflow}개 (원본에도 존재)")

        # (d) 페이지 정리 리포트
        src_pages = src_dump.get("page_count") or 0
        out_pages = out_dump.get("page_count") or 0
        deleted = stats.get("sep_pages_deleted")
        log(f"[검수] 페이지 {src_pages} → {out_pages} "
            f"(구분 삭제 {deleted if deleted is not None else '?'})")
        if deleted is not None and src_pages and out_pages != src_pages - deleted:
            warnings.append(
                f"⚠️ 페이지 수 불일치: {src_pages} - {deleted} != {out_pages}")

        # (e) PDF
        pdf_path = settings.get("pdf_path")
        pdf_ok = bool(pdf_path) and os.path.exists(pdf_path)
        if settings.get("export_pdf") and not pdf_ok:
            ok = False
            warnings.append("❌ PDF 미생성")

        log(f"[검수] {'통과' if ok else '실패'} — 경고 {len(warnings)}건")
        return {
            "ok": ok,
            "overflow": out_overflow,
            "stories": {},
            "pdf_path": pdf_path if pdf_ok else None,
            "pdf_paths": [pdf_path] if pdf_ok else [],
            "indd_path": indd_path,
            "warnings": warnings,
        }
