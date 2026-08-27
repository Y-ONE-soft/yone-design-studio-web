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
_JSX_DIR = os.path.join(os.path.dirname(os.path.dirname(_DIR)), "core", "jsx")
_BODY = os.path.join(_JSX_DIR, "convert_vertical.body.jsx")
_SPLIT_JSX = os.path.join(_JSX_DIR, "cv_split_exam.jsx")
_FINISH_JSX = os.path.join(_JSX_DIR, "cv_finish.jsx")

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


def line_counts(dump, min_len=25):
    """덤프의 정규화 라인 → 등장 횟수 (중복 배치 게이트용)."""
    counts = {}
    for st in dump.get("stories", []):
        for para in st.get("paragraphs", []):
            t = _norm_line(para.get("t"))
            if len(t) >= min_len:
                counts[t] = counts.get(t, 0) + 1
    return counts


def expected_page_count(src_pages, stats):
    """출력 기대 페이지 수 = 원본 - 구분삭제 - arrange삭제 + arrange추가.

    W27 6차: STEP4.4가 영작배열 스레드를 코드당 1페이지로 재배분하면서
    페이지를 추가/삭제한다 (stats: arrange_pages_added/deleted). 통계가
    없으면(구버전 JSX/실패) None — 판정 생략.
    """
    deleted = stats.get("sep_pages_deleted")
    if deleted is None or not src_pages:
        return None
    arr_add = stats.get("arrange_pages_added") or 0
    arr_del = stats.get("arrange_pages_deleted") or 0
    return src_pages - deleted - arr_del + arr_add


def residual_thread_count(dump, max_gap=4):
    """섹션 관통 스레드 수 — 페이지 간격이 max_gap 초과인 다중 페이지 스토리.

    STEP4.5 분리 실패 검출 (W27 실기 실증): 분리 안 된 스레드는 재배치 후
    사이클들을 관통해 큰 페이지 간격으로 남는다. 정상 잔존(문제 내 O/M
    연속 3~4p 스레드)은 간격 1이라 미검출.
    """
    residual = 0
    for st in dump.get("stories", []):
        pgs = st.get("pg") or []
        if len(pgs) < 2:
            continue
        nums = []
        for p in pgs:
            digits = re.sub(r"\D", "", str(p))
            if digits:
                nums.append(int(digits))
        nums.sort()
        if any(b - a > max_gap for a, b in zip(nums, nums[1:])):
            residual += 1
    return residual


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
        return ("조판된 모의고사 워크북 전체 .indd를 지문별 사이클의 "
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
                {"key": "indd", "label": "전체 .indd (업로드)",
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
                    "전체 .indd를 업로드하거나 서버 파일을 선택하세요")
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
            # body 는 PDF 를 뽑지 않는다 — 그 뒤 cv_finish 가 마스터를 얹고
            # 파리티 패딩을 넣으므로 여기서 뽑으면 최종본이 아니다.
            "out_pdf": "",
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
                    "log_paths": [jsx_log,
                                  os.path.abspath(os.path.join(job_dir, "cv_split_로그.txt")),
                                  os.path.abspath(os.path.join(job_dir, "cv_finish_로그.txt"))],
                    "result_json": result_json,
                    "json_path": json_path,
                    "master_local": master_local,
                    "output_dir": out_dir}
        with open(os.path.join(job_dir, ".settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return jsx_path

    # ── 3단계: run_indesign ─────────────────────────────────────────────────

    def run_indesign(self, job_dir, log, cancel_check=None):
        """S1/S2 게이트 + 분할 → body 재배치 → 마스터/패딩 후처리.

        body(convert_vertical.body.jsx) 단독으로는 정본이 나오지 않는다
        (SPEC 4장 실측: 지문 30·33 실전 0페이지, 마스터 B/D/E 부재, 사이클
        9~29p). 앞뒤로 두 단계를 붙여야 정본 규격이 된다 — 2026-08-17 실기
        실증 경로를 그대로 코드화한 것이다.
        """
        from core.indesign.runner import run_jsx
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        # 재실행 안전 — stale 완료 마커 제거
        try:
            os.remove(settings["log_path"])
        except OSError:
            pass

        stage = self._pre_split(job_dir, settings, log, cancel_check)

        run_jsx(settings["jsx_path"], log,
                poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                cancel_check=cancel_check,
                completion_marker="세로 변환 완료",
                stall_limit=1800)

        self._post_finish(job_dir, settings, stage, log, cancel_check)

    # ── 3a. S1/S2 — 인벤토리 게이트 + 스레드 분할 ───────────────────────────

    def _run_aux_jsx(self, body_path, doc_path, cfg, job_dir, log,
                     log_name, marker, cancel_check=None, timeout=3600):
        """보조 JSX(cv_split_exam / cv_finish) 실행 — cfg 를 JSON 으로 넘긴다."""
        from core.indesign.runner import run_jsx
        cfg_path = os.path.abspath(os.path.join(job_dir, log_name + "_cfg.json"))
        with open(cfg_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=1)
        jsx_log = os.path.abspath(os.path.join(job_dir, log_name + "_로그.txt"))
        try:
            os.remove(jsx_log)
        except OSError:
            pass
        jsx_path = build_jsx(
            body_path,
            {"__DOC_PATH__": os.path.abspath(doc_path),
             "__CFG_PATH__": cfg_path},
            log_path=jsx_log,
            out_path=os.path.join(job_dir, log_name + ".jsx"))
        run_jsx(jsx_path, log, poll_log_path=jsx_log, timeout=timeout,
                cancel_check=cancel_check, completion_marker=marker,
                stall_limit=1800)
        content = ""
        try:
            content = open(jsx_log, encoding="utf-8").read()
        except OSError:
            pass
        if marker not in content:
            errs = [ln for ln in content.splitlines() if "[오류]" in ln]
            raise RuntimeError("%s 실패: %s" % (log_name,
                                               errs[0] if errs else "완료 마커 없음"))
        return content

    def _pre_split(self, job_dir, settings, log, cancel_check=None):
        """SPEC 5장 S1/S2 — 게이트가 실패하면 조판에 들어가지 않는다."""
        from core.inspect import dump_frames, dump_indd
        from . import exam as exam_mod
        from . import inventory as inv_mod

        out_indd = settings["indd_path"]
        frames_json = os.path.join(job_dir, "src_frames.json")
        stories_json = os.path.join(job_dir, "src_stories.json")

        log("[S1] 프레임 덤프 (대형 문서 — 수 분)")
        dump_frames(out_indd, frames_json, log)
        log("[S1] 스토리 덤프")
        dump_indd(out_indd, stories_json, log, timeout=1800)

        n = inv_mod.detect_n_problems(frames_json)
        sections = inv_mod.detect_sections(frames_json, n)
        canon = inv_mod.detect_canon(frames_json, n, sections)
        log(f"[S1] 지문 {n}개 — canon {canon}")

        result = inv_mod.build_inventory(frames_json, stories_json,
                                         sections, canon)
        fails = list(inv_mod.gate(result, canon))

        # S2 — 실전 구간 (영작 배열 다음 ~ 문서 끝)
        arr_first, arr_last = sections["영작배열"]
        efs, page_count = exam_mod.exam_frames(frames_json, arr_last + 1, 10 ** 6)
        bounds = exam_mod.find_boundaries(efs)
        blocks = exam_mod.blocks_from_boundaries(bounds, page_count)
        info = exam_mod.page_info(frames_json)
        exam_blocks, tail_blocks = exam_mod.partition(blocks, canon, info)
        fails += exam_mod.gate(exam_blocks, tail_blocks, canon)
        exam_targets = exam_mod.split_targets(blocks)

        # S2 — 영작 배열 스레드
        afs, _pc = exam_mod.arrange_frames(frames_json, arr_first, arr_last)
        abounds = exam_mod.arrange_boundaries(afs, canon)
        fails += exam_mod.arrange_gate(abounds, canon)
        arr_targets = exam_mod.arrange_split_targets(abounds)

        if fails:
            raise RuntimeError("S1/S2 게이트 실패 — 조판 미착수:\n  - "
                               + "\n  - ".join(fails))
        log(f"[S2] 게이트 통과 — 실전 {len(exam_blocks)}지문 · 짤지문 "
            f"{len(tail_blocks)}개, 분할 대상 실전 {len(exam_targets)}건 · "
            f"영작배열 {len(arr_targets)}건")

        targets = exam_targets + arr_targets
        inventory = result["inventory"]
        if targets:
            self._run_aux_jsx(
                _SPLIT_JSX, out_indd, {"targets": targets}, job_dir, log,
                "cv_split", "분할 완료", cancel_check)
            # 분할 후 재덤프 — 영작 배열이 스레드에서 페이지 단위로 바뀌면서
            # 슬롯 페이지가 이때 확정된다 (후처리 마스터 열의 근거).
            frames2 = os.path.join(job_dir, "split_frames.json")
            log("[S1'] 분할 후 프레임 재덤프")
            dump_frames(out_indd, frames2, log)
            n2 = inv_mod.detect_n_problems(frames2)
            sections2 = inv_mod.detect_sections(frames2, n2)
            result2 = inv_mod.build_inventory(frames2, stories_json, sections2,
                                              canon, threaded=set())
            fails2 = inv_mod.gate(result2, canon)
            if fails2:
                raise RuntimeError("분할 후 S1 게이트 실패:\n  - "
                                   + "\n  - ".join(fails2))
            inventory = result2["inventory"]
            log("[S1'] 분할 후 슬롯 인벤토리 확정")

        stage = {"canon": canon, "n_problems": n,
                 "sections": {k: list(v) for k, v in sections.items()},
                 "inventory": inventory,
                 "exam_targets": exam_targets,
                 "arrange_targets": arr_targets,
                 "tail_blocks": tail_blocks}
        with open(os.path.join(job_dir, "cv_stage.json"), "w",
                  encoding="utf-8") as f:
            json.dump(stage, f, ensure_ascii=False, indent=1)
        return stage

    # ── 3c. 후처리 — 슬롯 마스터 + 파리티 패딩 + PDF ────────────────────────

    def _post_finish(self, job_dir, settings, stage, log, cancel_check=None):
        from core.inspect import dump_frames
        from . import plan as plan_mod

        out_indd = settings["indd_path"]
        out_frames = os.path.join(job_dir, "out_frames.json")
        log("[S3] 산출물 프레임 덤프")
        dump_frames(out_indd, out_frames, log)

        cycles, fails = plan_mod.build_finish_cycles(
            out_frames, stage["inventory"], stage["canon"])
        if fails:
            raise RuntimeError("후처리 플랜 게이트 실패:\n  - " + "\n  - ".join(fails))
        lens = [c["length"] for c in cycles["cycles"]]
        log(f"[S3] 사이클 {len(lens)}개 — 길이 {min(lens)}~{max(lens)}p, "
            f"패딩 {sum(1 for c in cycles['cycles'] if c['pad'])}개")

        cfg = {"master_src": settings.get("master_local") or "",
               "out_pdf": settings.get("pdf_path") or "",
               "cycles": cycles["cycles"]}
        content = self._run_aux_jsx(
            _FINISH_JSX, out_indd, cfg, job_dir, log,
            "cv_finish", "후처리 완료", cancel_check)
        for ln in content.splitlines():
            if "마스터 적용" in ln or "[경고]" in ln:
                log("[S3] " + ln.strip())
        with open(os.path.join(job_dir, "cv_finish_plan.json"), "w",
                  encoding="utf-8") as f:
            json.dump(cycles, f, ensure_ascii=False, indent=1)

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
        src_counts = line_counts(src_dump)
        out_counts = line_counts(out_dump)
        got = set(out_counts)
        out_overflow = 0
        for st in out_dump.get("stories", []):
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

        # (a2) 중복 배치 게이트 (W27 실기 결함 실증 — 분리 부분 실패로
        #      원본 스레드 + 복제 프레임이 겹쳐 같은 라인이 2회 인쇄될 위험)
        dup_lines = [t for t, n in out_counts.items()
                     if n > src_counts.get(t, 0)]
        if len(dup_lines) >= 5:
            ok = False
            warnings.append(
                f"❌ 내용 중복 배치 {len(dup_lines)}라인 (원본보다 많이 등장 — "
                f"분리 실패 겹침 의심): " + " | ".join(
                    sorted(dup_lines)[:2]))
        elif dup_lines:
            warnings.append(f"⚠️ 내용 중복 배치 {len(dup_lines)}라인")
        log(f"[검수] 중복 배치: {len(dup_lines)}라인")

        # (a3) 섹션 관통 스레드 잔존 게이트 (W27 실기 결함 실증 — STEP4.5가
        #      분리하지 못한 스레드는 사이클을 관통해 페이지 간격이 크게 남음.
        #      수동 실물의 정상 잔존 스레드는 문제 내 연속 3~4p — 간격 1 이내)
        residual_threads = residual_thread_count(out_dump)
        if residual_threads:
            ok = False
            warnings.append(
                f"❌ 섹션 관통 스레드 잔존 {residual_threads}개 — "
                "STEP4.5 분리 실패 (재배치 후 텍스트 흐름 붕괴 위험)")
        log(f"[검수] 관통 스레드 잔존: {residual_threads}개")

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

        # (b2) 후처리 게이트 — 슬롯 마스터 + 파리티 (SPEC 5장 S7)
        pad_pages = 0
        try:
            fin = json.load(open(os.path.join(job_dir, "cv_finish_plan.json"),
                                 encoding="utf-8"))
        except (OSError, ValueError):
            fin = None
            ok = False
            warnings.append("❌ 후처리 플랜 없음 — cv_finish 미실행 의심")
        if fin:
            cyc = fin.get("cycles") or []
            pad_pages = sum(1 for c in cyc if c.get("pad"))
            odd = [c["code"] for c in cyc
                   if (c["length"] + (1 if c.get("pad") else 0)) % 2]
            if odd:
                ok = False
                warnings.append(f"❌ 사이클 길이 홀수: 지문 {odd[:5]} "
                                "(좌우 파리티 붕괴)")
            log(f"[검수] 사이클 {len(cyc)}개 — 파리티 패딩 {pad_pages}p")

            # 마스터 분포 — 정본은 A~E 가 각 2N (슬롯 2개씩). 하나라도 0이면
            # 후처리가 통째로 헛돈 것이다 (W27 결함: B/D/E 부재).
            mcount = {}
            for pg in (out_dump.get("pages") or []):
                m = (pg.get("m") or "").strip()
                if m:
                    mcount[m[:1]] = mcount.get(m[:1], 0) + 1
            lack = [k for k in "ABCDE" if mcount.get(k, 0) < (num_problems or 1)]
            if lack:
                ok = False
                warnings.append(
                    f"❌ 슬롯 마스터 부족: {lack} (지문당 1p 미만 — 분포 "
                    f"{ {k: mcount.get(k, 0) for k in 'ABCDEOM'} })")
            log("[검수] 마스터 분포: "
                + " ".join(f"{k}{mcount.get(k, 0)}" for k in "ABCDEOM"))

        # (d) 페이지 정리 리포트 (구분 삭제 + STEP4.4 arrange 재배분 + 패딩)
        src_pages = src_dump.get("page_count") or 0
        out_pages = out_dump.get("page_count") or 0
        deleted = stats.get("sep_pages_deleted")
        expected = expected_page_count(src_pages, stats)
        if expected is not None:
            expected += pad_pages
        log(f"[검수] 페이지 {src_pages} → {out_pages} "
            f"(구분 삭제 {deleted if deleted is not None else '?'}, "
            f"arrange +{stats.get('arrange_pages_added', '?')}"
            f"/-{stats.get('arrange_pages_deleted', '?')})")
        if expected is not None and out_pages != expected:
            warnings.append(
                f"⚠️ 페이지 수 불일치: 기대 {expected} != 실제 {out_pages}")

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
