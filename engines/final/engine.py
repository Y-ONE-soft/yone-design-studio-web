"""파이널 직전보충 엔진 — BaseEngine 구현."""

import json
import os
import re
import shutil
import subprocess
import unicodedata

from core.base import BaseEngine, safe_copy_indd


def _nfc(s):
    """macOS NFD 한글 경로를 NFC로 정규화."""
    return unicodedata.normalize("NFC", s)

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")


def _convert_grammar_header(header, scope_text, scope_type):
    """어법수정 Word 헤더를 파이널 형식으로 변환.

    "1. L2-본문1" → "2과 본문1"
    "2. L1-p.17" → "1과 p.17"
    "1. p22-no.01" → "251020" (모의고사의 경우)
    """
    header = _nfc(header).strip()

    # 숫자. 제거
    header = re.sub(r"^\d+\.\s*", "", header)

    if scope_type == "textbook":
        # SL/SpecialLesson 패턴 (L보다 먼저 체크해야 SL1을 L1로 잘못 매칭하지 않음)
        m_sl = re.search(r"(?:SL|Special\s*Lesson)\s*(\d+)?[-.]?(.*)", header, re.IGNORECASE)
        if m_sl:
            sl_num = m_sl.group(1) or ""
            rest = (m_sl.group(2) or "").strip()
            if rest.startswith("-"):
                rest = rest[1:].strip()
            prefix = f"교과서S{sl_num}과" if sl_num else "교과서SL"
            return f"{prefix} {rest}" if rest else prefix
        # "L2-본문1" → "교과서2과 본문1"
        m = re.search(r"L(\d+)[-.]?(.*)", header)
        if m:
            lesson = m.group(1)
            rest = m.group(2).strip()
            if rest.startswith("-"):
                rest = rest[1:].strip()
            return f"교과서{lesson}과 {rest}" if rest else f"교과서{lesson}과"

    elif scope_type == "mockexam":
        # "p22-no.01" → YYMMQQ, "no.41~42" → YYMM41~42
        m_year = re.search(r"(\d{2})년\s*(\d{1,2})월", _nfc(scope_text))
        if m_year:
            yy = m_year.group(1)
            mm = m_year.group(2).zfill(2)
            # 문항번호 추출 (범위 포함: no.41~42, no.43~45)
            m_q = re.search(r"no\.?\s*(\d+)(?:\s*[~\-]\s*(\d+))?", header, re.IGNORECASE)
            if m_q:
                qq = m_q.group(1).zfill(2)
                if m_q.group(2):
                    qq2 = m_q.group(2).zfill(2)
                    return f"{yy}{mm}{qq}~{qq2}"
                return f"{yy}{mm}{qq}"
            m_p = re.search(r"p\.?(\d+)", header)
            if m_p:
                qq = m_p.group(1).zfill(2)
                return f"{yy}{mm}{qq}"

    elif scope_type in ("ebs_olympos", "ebs_readingpower"):
        # "올포 5강-본문2" 등
        return header

    return header


_PATH_KEYS = ["gdrive_base", "gdrive_content_base", "template_vol1", "template_vol2"]


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class FinalEngine(BaseEngine):

    @property
    def material_id(self):
        return "final"

    @property
    def display_name(self):
        return "파이널 직전보충"

    @property
    def description(self):
        return "파이널(Vol1/Vol2) 조판 자동화 — 워크북 텍스트 추출 → 파이널 내지 배치"

    @property
    def subject_prefix(self):
        return "파이널"

    @property
    def template_name(self):
        return "typeset_final.html"

    @property
    def log_filename(self):
        return "typeset_log.txt"

    @property
    def jsx_timeout(self):
        return 900  # 추출 + Vol1 + Vol2 = 최대 15분

    @property
    def upload_spec(self):
        return {"slots": []}

    # ── 메타데이터 헬퍼 ──

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    # ── 워크북 자동 감지 ──

    @staticmethod
    def find_workbook_files(gdrive_base, exam_period, grade, school):
        """워크북 디렉터리에서 .indd 파일 자동 감지."""
        gdrive_base = os.path.expanduser(gdrive_base)
        wb_dir = os.path.join(gdrive_base, "워크북", exam_period, grade, school)
        if not os.path.isdir(wb_dir):
            return [], wb_dir
        files = sorted([
            os.path.join(wb_dir, f) for f in os.listdir(wb_dir)
            if f.endswith(".indd") and "워크북" in _nfc(f)
        ])
        return files, wb_dir

    @staticmethod
    def scan_schools(gdrive_base, exam_period):
        """시험 시기별 학교 목록 스캔."""
        result = {}
        for grade in ["고1", "고2"]:
            grade_dir = os.path.join(gdrive_base, "워크북", exam_period, grade)
            if not os.path.isdir(grade_dir):
                continue
            schools = sorted([
                d for d in os.listdir(grade_dir)
                if os.path.isdir(os.path.join(grade_dir, d))
                and not d.startswith(".")
            ])
            if schools:
                result[grade] = schools
        return result

    # ── 파이프라인: parse ──

    def parse(self, uploaded_files, job_dir, log):
        cfg = _load_config()
        school = unicodedata.normalize("NFC", self._get_meta(job_dir, "school", ""))
        grade = self._get_meta(job_dir, "grade", "고1")
        exam_period = self._get_meta(job_dir, "exam_period", cfg["exam_period"])

        log(f"[설정] 학교={school}, 학년={grade}, 시험={exam_period}")

        # 1) 워크북 파일 감지
        wb_files, wb_dir = self.find_workbook_files(
            cfg["gdrive_base"], exam_period, grade, school
        )
        if not wb_files:
            raise FileNotFoundError(f"워크북 파일을 찾을 수 없습니다: {wb_dir}")

        log(f"[감지] {len(wb_files)}개 워크북:")
        for f in wb_files:
            log(f"  • {os.path.basename(f)}")

        # 2) 시험범위 파싱 + 어법수정 소스 결정
        from engines.final.scope_parser import parse_all_scopes
        scopes = parse_all_scopes(wb_files)
        log("[범위] 시험범위 분석:")
        for s in scopes:
            log(f"  • {s['scope']} → {s['type']} (어법수정: {s['grammar_source']})")

        # 3) InDesign으로 텍스트 추출
        from engines.final.extractor import extract_from_workbooks
        extracted_path = os.path.join(job_dir, "extracted.json")
        extract_from_workbooks(
            wb_files, cfg["extract_styles"], extracted_path, log
        )

        # 4) 어법수정 Word 파일 수집 — 소스 유형별 분기
        #    + 교과서 과별 본문 수 카운트 (문장배열 과 경계 ground truth)
        lesson_block_counts = {}  # {"1": 6, "2": 6} — 과번호 → 본문 수
        from engines.final.grammar_word_parser import (
            find_grammar_word_files, find_mockexam_grammar_files,
            find_ebs_grammar_files, parse_grammar_word
        )
        content_base = cfg.get("gdrive_content_base", "")
        grammar_word_lines = []

        for s in scopes:
            if s["grammar_source"] != "word_file":
                continue  # 마더텅 등 workbook_a1 소스는 스킵

            scope_type = s["type"]
            scope_text = s["scope"]

            word_files = []
            if scope_type == "textbook":
                # 교과서 → 교과서 작업 폴더 (과별로 개별 탐색하여 레슨 추적)
                textbook_info = cfg.get("school_textbook_map", {}).get(exam_period, {}).get(school)
                if textbook_info:
                    for lesson in textbook_info["lessons"]:
                        lesson_files = find_grammar_word_files(
                            content_base,
                            textbook_info["subject"],
                            textbook_info["publisher"],
                            [lesson],
                            log=log
                        )
                        for lf in lesson_files:
                            word_files.append((lf, lesson))
                else:
                    log(f"  [어법수정] 학교-교재 매핑 없음 ({school})")

            elif scope_type == "mockexam":
                # 모의고사 → 모의고사 작업 폴더
                word_files = find_mockexam_grammar_files(
                    content_base, scope_text, grade, log=log
                )
                # 시험범위 시트에서 정확한 문항번호 추출 (짧은 지문 필터링용)
                from engines.final.vocab_fetcher import fetch_scope_for_school
                allowed_qnums = set()
                try:
                    exams = fetch_scope_for_school(school, log=None)
                    for e in exams:
                        allowed_qnums.update(e["numbers"])
                except Exception:
                    pass
                if allowed_qnums:
                    log(f"  [어법수정] 모의고사 허용 문항: {sorted(allowed_qnums)}")
                else:
                    log(f"  [어법수정] 시험범위 문항번호 미확인 — 전체 포함")

            elif scope_type in ("ebs_olympos", "ebs_readingpower"):
                # EBS → EBS 작업 폴더
                word_files = find_ebs_grammar_files(
                    content_base, scope_text, log=log
                )

            for wf_item in word_files:
                # textbook은 (path, lesson) 튜플, 나머지는 plain path
                if isinstance(wf_item, tuple):
                    wf, lesson_name = wf_item
                else:
                    wf, lesson_name = wf_item, None

                # Google Drive 스트림 파일은 로컬로 복사 후 사용
                if "GoogleDrive" in wf or "Google Drive" in wf or "CloudStorage" in wf:
                    local_copy = os.path.join(job_dir, os.path.basename(wf))
                    copied = False
                    for _retry in range(5):
                        try:
                            with open(wf, "rb") as _src:
                                with open(local_copy, "wb") as _dst:
                                    _dst.write(_src.read())
                            copied = True
                            break
                        except Exception:
                            import time; time.sleep(3)
                    if copied:
                        wf = local_copy
                        log(f"  [어법수정] GDrive -> 로컬 복사: {os.path.basename(wf)}")
                    else:
                        log(f"  [오류] GDrive 파일 복사 실패 (3회 재시도): {os.path.basename(wf)}")
                        continue

                blocks = parse_grammar_word(wf)
                # 교과서: 과별 본문 수 카운트 (ground truth)
                if scope_type == "textbook" and lesson_name:
                    lesson_num = re.sub(r"과$", "", lesson_name.strip())
                    valid_count = sum(
                        1 for b2 in blocks
                        if (b2.get("text") or "").strip()
                        and (b2.get("text") or "").strip().upper() not in
                            ("READING", "READ MORE", "READ MORE!")
                    )
                    if valid_count > 0:
                        lesson_block_counts[lesson_num] = valid_count
                        log(f"  [어법수정] {lesson_name}: {valid_count}개 본문 감지")

                for b in blocks:
                    text_content = (b.get("text") or "").strip()
                    # 섹션 제목만 있고 본문이 없는 블록 스킵 (예: "READING")
                    if not text_content or text_content.upper() in ("READING", "READ MORE", "READ MORE!"):
                        continue
                    if text_content:
                        # 헤더가 있으면 먼저 추가 (지문 구분용)
                        hdr = b.get("header", "")
                        if hdr:
                            # "1. L2-본문1" → "2과 본문1" 변환
                            hdr = _convert_grammar_header(hdr, scope_text, scope_type)

                            # SL 등 레슨 이름이 헤더에 반영 안 된 경우 보완
                            if lesson_name and hdr in ("본문", "전체"):
                                lesson_num = re.sub(r"과$", "", lesson_name.strip())
                                if lesson_num.startswith("S"):
                                    hdr = f"S{lesson_num[1:]}과 {hdr}"
                                else:
                                    hdr = f"{lesson_num}과 {hdr}"

                            # 모의고사 문항번호 필터링 (시험범위 밖 문항 제외)
                            if scope_type == "mockexam" and allowed_qnums:
                                # hdr = "251020" or "251041~42"
                                m_qq = re.match(r"^\d{4}(\d{2})(?:~(\d{2}))?$", hdr)
                                if m_qq:
                                    qq1 = int(m_qq.group(1))
                                    qq2 = int(m_qq.group(2)) if m_qq.group(2) else qq1
                                    # 범위 내 하나라도 포함되면 허용
                                    in_range = any(q in allowed_qnums for q in range(qq1, qq2 + 1))
                                    if not in_range:
                                        log(f"  [어법수정] 문항 {qq1}{'~'+str(qq2) if qq2!=qq1 else ''} 제외 (범위 밖)")
                                        continue

                            grammar_word_lines.append(hdr)
                        grammar_word_lines.append(b["text"])

        if grammar_word_lines:
            log(f"[어법수정] Word에서 총 {len(grammar_word_lines)}개 지문 추출")

        # 5) 중요어휘 자동 추출 (구글시트 — 모의고사 범위 기반)
        vocab_left = ""
        vocab_right = ""
        try:
            from engines.final.vocab_fetcher import fetch_vocab_for_school
            vocab_data = fetch_vocab_for_school(school, grade, log=log)
            vocab_left = vocab_data.get("left_text", "")
            vocab_right = vocab_data.get("right_text", "")
            log(f"[중요어휘] 결과: 왼쪽 {len(vocab_left)}자, 오른쪽 {len(vocab_right)}자")
        except Exception as e:
            import traceback
            log(f"[중요어휘] 자동 추출 실패: {e}")
            log(f"  {traceback.format_exc()}")

        # 6) 추출 데이터 + Word 어법수정 + 중요어휘 → content.json
        from engines.final.parser import parse_extracted
        content_path = parse_extracted(
            extracted_path, vocab_left, vocab_right,
            school, grade, exam_period, job_dir, log,
            grammar_word_lines=grammar_word_lines,
            lesson_block_counts=lesson_block_counts
        )
        return content_path

    # ── 파이프라인: prepare_jsx ──

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        school = self._get_meta(job_dir, "school", "학교미선택")
        grade = self._get_meta(job_dir, "grade", "고1")
        exam_period = self._get_meta(job_dir, "exam_period", cfg["exam_period"])

        with open(json_path, encoding="utf-8") as f:
            content = json.load(f)

        # 출력 디렉터리 (영문 경로 — InDesign ExtendScript 한글 경로 문제 방지)
        output_dir = os.path.join(
            os.path.expanduser("~/Documents/final_output"),
            grade, exam_period
        )
        os.makedirs(output_dir, exist_ok=True)

        # Vol1/Vol2 템플릿 복사 + jobs 구성
        jobs = []
        for vol_key, tpl_key, vol_label in [
            ("vol1", "template_vol1", "Vol1"),
            ("vol2", "template_vol2", "Vol2"),
        ]:
            vol_data = content.get(vol_key, {})
            # 데이터가 있는 경우에만 생성
            has_data = any(vol_data.get(k) for k in vol_data if k not in ("", None))
            if not has_data:
                log(f"[내지] {vol_label}: 데이터 없음 — 건너뜀")
                continue

            template_src = cfg[tpl_key]
            indd_name = f"{school}_파이널({vol_label})_내지.indd"
            indd_path = os.path.join(output_dir, indd_name)
            indd_path = safe_copy_indd(template_src, indd_path)
            log(f"[내지] {vol_label}: {os.path.basename(indd_path)}")

            jobs.append({
                "vol": vol_key,
                "indd_path": indd_path,
                "data": vol_data,
            })

        if not jobs:
            raise ValueError("Vol1/Vol2 모두 데이터가 없습니다.")

        # .settings.json
        settings = {
            "jobs": jobs,
            "output_dir": output_dir,
            "school": school,
            "grade": grade,
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        return settings_path

    # ── 파이프라인: run_indesign (stepper 방식) ──

    def run_indesign(self, job_dir, log):
        from engines.final.indesign_stepper import run_typeset
        settings_path = os.path.join(job_dir, ".settings.json")
        run_typeset(settings_path, log)

    # ── 파이프라인: verify ──

    def verify(self, job_dir, log):
        cfg = _load_config()
        log_path = os.path.join(job_dir, cfg["log_filename"])

        # content.json 통계
        content = {}
        cp = os.path.join(job_dir, "content.json")
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                content = json.load(f)

        warnings = []
        overflow = 0
        pdf_paths = []

        if os.path.exists(log_path):
            lc = open(log_path, encoding="utf-8", errors="ignore").read()
            for m in re.finditer(r"오버플로우:\s*(\d+)개", lc):
                overflow += int(m.group(1))
            if overflow > 0:
                warnings.append(f"오버플로우 {overflow}개")

        # PDF 수집
        for d in [job_dir]:
            for f in os.listdir(d):
                if f.endswith(".pdf") and "파이널" in f:
                    pdf_paths.append(os.path.join(d, f))

        # .settings.json에서 출력 디렉터리도 확인
        sp = os.path.join(job_dir, ".settings.json")
        if os.path.exists(sp):
            with open(sp, encoding="utf-8") as f:
                settings = json.load(f)
            out_dir = settings.get("output_dir", "")
            if out_dir and os.path.isdir(out_dir):
                for f in os.listdir(out_dir):
                    full = os.path.join(out_dir, f)
                    if f.endswith(".pdf") and full not in pdf_paths:
                        pdf_paths.append(full)

        totals = {
            "문장배열": content.get("총_문장배열", 0),
            "어법수정": content.get("총_어법수정", 0),
            "서술형영작": content.get("총_서술형영작", 0),
        }
        stories = {k: {"actual": v, "expected": v} for k, v in totals.items()}

        # 범위 검증 리포트
        report_lines = ["=== 범위 검증 리포트 ==="]
        vol1 = content.get("vol1", {})
        vol2 = content.get("vol2", {})

        arr_blocks = vol1.get("문장배열", [])
        ins_blocks = vol1.get("문장삽입", [])
        report_lines.append(f"문장배열: {len(arr_blocks)}개")
        report_lines.append(f"  헤더: {', '.join(b['header'] for b in arr_blocks)}")
        report_lines.append(f"문장삽입: {len(ins_blocks)}개")
        arr_set = set(b["header"] for b in arr_blocks)
        ins_set = set(b["header"] for b in ins_blocks)
        if arr_set != ins_set:
            report_lines.append(f"  ⚠ 문장배열/삽입 불일치: 배열만={arr_set-ins_set}, 삽입만={ins_set-arr_set}")
        else:
            report_lines.append(f"  ✓ 문장배열/삽입 1:1 일치")

        # 중요어휘
        vocab_left = vol1.get("중요어휘_왼", "")
        vocab_nums = [p.strip()[:6] for p in vocab_left.split("\n") if re.match(r"^\d{6}", p.strip())] if vocab_left else []
        vocab_count = len(vocab_nums)
        v_25_3 = [n for n in vocab_nums if n.startswith("2503")]
        v_25_6 = [n for n in vocab_nums if n.startswith("2506")]
        v_26_3 = [n for n in vocab_nums if n.startswith("2603")]
        report_lines.append(f"중요어휘: {vocab_count}개 지문 (25-3: {len(v_25_3)}, 25-6: {len(v_25_6)}, 26-3: {len(v_26_3)})")
        report_lines.append(f"  25-3: {', '.join(v_25_3)}")
        report_lines.append(f"  25-6: {', '.join(v_25_6)}")
        report_lines.append(f"  26-3: {', '.join(v_26_3)}")
        report_lines.append(f"  ※ 교과서는 중요어휘 대상 아님, 41~42 복합문항은 41번으로 포함")

        # Vol2
        grammar = vol2.get("어법수정", [])
        grammar_headers = vol2.get("어법_헤더", [])
        report_lines.append(f"어법수정: {len(grammar)}줄, {len(grammar_headers)}개 지문")
        report_lines.append(f"  헤더: {', '.join(grammar_headers[:10])}{'...' if len(grammar_headers)>10 else ''}")

        writing = vol2.get("서술형영작", [])
        writing_headers = vol2.get("영작_헤더_상세", [])
        report_lines.append(f"서술형영작: {len(writing)}쌍, {len(writing_headers)}개 지문")

        # 리포트 파일 저장
        report_path = os.path.join(job_dir, "scope_report.txt")
        with open(report_path, "w", encoding="utf-8") as rf:
            rf.write("\n".join(report_lines))
        log("[리포트] " + report_path)
        for line in report_lines:
            log(f"  {line}")

        ok = len(pdf_paths) > 0 and overflow == 0

        return {
            "ok": ok,
            "overflow": overflow,
            "stories": stories,
            "pdf_path": pdf_paths[0] if pdf_paths else None,
            "pdf_paths": pdf_paths,
            "warnings": warnings,
            "grade_label": f"PDF {len(pdf_paths)}개 | 문장배열 {totals['문장배열']} | 어법수정 {totals['어법수정']} | 영작 {totals['서술형영작']}",
        }
