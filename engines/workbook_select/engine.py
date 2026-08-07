# -*- coding: utf-8 -*-
"""워크북 선택 결합 엔진 (원고 기반).

여러 회차 모의고사 워크북 "원고"에서 요청한 문항(YYMMQQ 코드)만 뽑아
사용자 입력 순서대로 전체(C) 워크북 형식으로 새로 조판한다.

기존 mockexam_horiz_merge(완성 .indd 페이지 오려붙이기)와의 차이:
  - 가로판 완성본은 1페이지 2문항 + 유형별 섹션 구조라 페이지 추출로는
    문항 단위 선택이 원리적으로 불가 — 이 엔진은 원고에서 직접 조판한다.
  - 완성본 오염(예: 고1_22년_6월_전체(C) 본편에 24년10월 내용)이
    산출물에 전파되지 않는다.
  - 원고가 없는 회차(16년 이전 등)는 조판 불가 — 에러에 회차를 명시한다.

파이프라인:
  parse  : 코드 → 회차별 GDrive 원고 폴더 매칭 → 로컬 복사 →
           workbook 파서 → merge_select 병합 → content.json + coverage.json
  jsx    : workbook 엔진의 run.jsx 그대로 (전체(C) 템플릿에 스텝별 부기)
  verify : STEP완료/오버플로우 + 문항 커버리지 + PDF 페이지수
"""

import json
import os
import re
import shutil
import unicodedata

from core.base import BaseEngine, safe_copy_indd, safe_copy
from core.paths import resolve_config
from engines.workbook.engine import _load_config as _load_workbook_config
from engines.workbook.parser import parse_manuscript_folder
from engines.workbook_select.merge_select import merge_selected
from engines.workbook_select import motherteng as _mt

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(
    os.path.dirname(_DIR), "workbook", "jsx", "run.jsx")

_MS_EXTS = (".docx", ".hwp", ".hwpx")


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _load_config():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["manuscript_base", "indd_original",
                                "output_base"])


class WorkbookSelectEngine(BaseEngine):

    @property
    def material_id(self):
        return "workbook_select"

    @property
    def display_name(self):
        return "워크북 선택 결합 (원고)"

    @property
    def description(self):
        return ("여러 회차 모의고사 워크북 원고에서 선택한 문항(YYMMQQ)만 "
                "뽑아 입력 순서대로 전체 워크북 조판 → .indd + PDF")

    @property
    def template_name(self):
        return "typeset_workbook_select.html"

    @property
    def jsx_timeout(self):
        return 3600  # 전체(C) 254p 템플릿 풀 조판 + 저장

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "codes",
                    "label": "문항 코드 (YYMMQQ, 순서대로 — 줄바꿈/콤마 구분)",
                    "type": "text",
                    "required": True,
                },
                {
                    "key": "result_name",
                    "label": "결과 파일명 (확장자 제외)",
                    "type": "text",
                    "required": True,
                },
            ]
        }

    # ─── 헬퍼 ───────────────────────────────────────────────────────

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, "%s.txt" % key)
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    @staticmethod
    def _parse_codes(text):
        """입력 텍스트 → 순서 보존 6자리 코드 리스트 (중복 제거).

        허용: "231133" / "23년 11월 33번" / 콤마·줄바꿈 혼합
        """
        codes = []
        seen = set()
        for piece in re.split(r"[,\n]+", text):
            piece = piece.strip()
            if not piece:
                continue
            m = re.fullmatch(r"(\d{6})", piece)
            if not m:
                m2 = re.fullmatch(
                    r"(\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*번?", piece)
                if not m2:
                    raise ValueError("코드 형식 인식 실패: %r" % piece)
                code = "%s%02d%02d" % (m2.group(1), int(m2.group(2)),
                                       int(m2.group(3)))
            else:
                code = m.group(1)
            if code in seen:
                continue
            seen.add(code)
            codes.append(code)
        if not codes:
            raise ValueError("문항 코드가 입력되지 않았습니다.")
        return codes

    @staticmethod
    def _find_manuscript_dir(base, grade_num, yy, mm):
        """GDrive에서 회차 워크북 원고 폴더 탐색.

        구조: {base}/고N/고N YY년 M월/(워크북 | *워크북*)
        폴더명 변형("고1 22년 6월 워크북")과 NFD 파일명을 흡수한다.
        """
        grade_dir = os.path.join(base, "고%s" % grade_num)
        if not os.path.isdir(grade_dir):
            return None, "학년 폴더 없음: %s" % grade_dir

        wanted = ["고%s %d년 %d월" % (grade_num, yy, mm),
                  "고%s %d년 %02d월" % (grade_num, yy, mm)]
        ym_dir = None
        for raw in os.listdir(grade_dir):
            if _nfc(raw) in wanted:
                ym_dir = os.path.join(grade_dir, raw)
                break
        if ym_dir is None or not os.path.isdir(ym_dir):
            return None, "회차 폴더 없음: %s" % wanted[0]

        exact = None
        fuzzy = []
        for raw in os.listdir(ym_dir):
            n = _nfc(raw)
            p = os.path.join(ym_dir, raw)
            if not os.path.isdir(p):
                continue
            if n == "워크북":
                exact = p
            elif "워크북" in n and "이전" not in n:
                fuzzy.append(p)
        if exact:
            return exact, None
        if fuzzy:
            fuzzy.sort(key=lambda p: len(os.path.basename(p)))
            return fuzzy[0], None
        listing = ", ".join(sorted(_nfc(x) for x in os.listdir(ym_dir))[:15])
        return None, "워크북 폴더 없음 (%s 내: %s)" % (wanted[0], listing)

    @staticmethod
    def _copy_manuscripts(src_dir, dst_dir, log):
        """원고 파일 로컬 복사 — 루트 원고(.docx/.hwp/.hwpx) + Step3 폴더.

        GDrive partial copy 방지: safe_copy가 크기 검증. '이전 파일' 등
        하위 폴더는 Step3(스텝3) 외에는 복사하지 않는다.
        """
        os.makedirs(dst_dir, exist_ok=True)
        copied = 0
        for raw in os.listdir(src_dir):
            sp = os.path.join(src_dir, raw)
            n = _nfc(raw)
            if os.path.isfile(sp):
                if not n.lower().endswith(_MS_EXTS):
                    continue
                safe_copy(sp, os.path.join(dst_dir, n))
                copied += 1
            elif os.path.isdir(sp) and n in ("Step3", "스텝3", "step3"):
                s3_dst = os.path.join(dst_dir, "Step3")
                os.makedirs(s3_dst, exist_ok=True)
                for raw3 in os.listdir(sp):
                    sp3 = os.path.join(sp, raw3)
                    n3 = _nfc(raw3)
                    if os.path.isfile(sp3) and n3.lower().endswith(_MS_EXTS):
                        safe_copy(sp3, os.path.join(s3_dst, n3))
                        copied += 1
        log("  원고 %d개 파일 복사" % copied)
        return copied

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        cfg = _load_config()
        wb_cfg = _load_workbook_config()

        # 원고 파일 선택 오버라이드 — workbook 기본 config 는 빈칸어휘/빈칸어법에
        # '정답지'(정답 단어 목록)를 지정한다. 학생용 워크북에 그대로 부으면
        # 정답이 그대로 조판된다(2026-08-05 실측: "1. 521. suggests …").
        # 문제지 파일은 21~26년 전 회차에 동일 이름·형식으로 존재.
        override = cfg.get("manuscript_file_map_override") or {}
        if override:
            wb_cfg = dict(wb_cfg)
            fm = dict(wb_cfg.get("manuscript_file_map", {}))
            for k, v in override.items():
                if fm.get(k) != v:
                    log("[원고 선택] %s: %s → %s" % (k, fm.get(k), v))
                fm[k] = v
            wb_cfg["manuscript_file_map"] = fm

        codes_text = uploaded_files.get("codes", "") or \
            self._get_meta(job_dir, "codes", "")
        codes = self._parse_codes(codes_text)
        log("[코드] %d개" % len(codes))

        # 마더텅 지문번호 — 엑셀(강별 열 × 행)에서 조달. 사용자 확정 스펙
        # (2026-08-07): 조판 순서와 지문번호를 이 번호로 맞춘다. 순차
        # 1,2,3,4 로 다시 매기지 않는다 (짝수만 뽑힌 워크북이면 2,4,6…).
        mt_numbers = {}
        mt_gang = self._get_meta(job_dir, "mt_gang", "") or cfg.get("mt_gang")
        try:
            mt_gang = int(mt_gang) if mt_gang else None
        except (TypeError, ValueError):
            mt_gang = None
        mt_index = _mt.load_index(cfg.get("motherteng_xlsx"))
        if mt_index:
            mt_numbers = _mt.numbers_for(mt_index, codes, gang=mt_gang)
            if mt_numbers:
                codes = _mt.sort_by_number(codes, mt_numbers)
                log("[마더텅] %d/%d개 번호 매핑, 번호순 정렬 (%s)"
                    % (len(mt_numbers), len(codes),
                       ", ".join(str(mt_numbers[c]) for c in codes
                                 if c in mt_numbers)))
            else:
                log("[마더텅] 엑셀에 매칭 코드 없음 — 입력 순서 유지")
        else:
            log("[마더텅] 지문 출처 엑셀 없음 — 입력 순서 유지")

        grade = self._get_meta(job_dir, "grade", "고1")
        grade_num = grade.replace("고", "").strip() or "1"

        # 회차 그룹 (등장 순서 보존)
        rounds = []
        for c in codes:
            ym = (int(c[:2]), int(c[2:4]))
            if ym not in rounds:
                rounds.append(ym)
        log("[회차] %s" % ", ".join("%d년 %d월" % ym for ym in rounds))

        # 회차별 원고 폴더 매칭 → 로컬 복사 → 파싱
        not_found = []
        sources = []
        for yy, mm in rounds:
            src_dir, err = self._find_manuscript_dir(
                cfg["manuscript_base"], grade_num, yy, mm)
            if src_dir is None:
                not_found.append("%d년 %d월 — %s" % (yy, mm, err))
                continue
            log("[원고] %d년 %d월: %s" % (yy, mm,
                                          os.path.basename(src_dir)))
            ms_dir = os.path.join(job_dir, "ms_%02d%02d" % (yy, mm))
            self._copy_manuscripts(src_dir, ms_dir, log)
            content = parse_manuscript_folder(
                ms_dir, wb_cfg, int(grade_num), yy, mm, log=log)
            sources.append({"yy": yy, "mm": mm, "content": content})

        # 보충 원고 폴더 — 회차 폴더가 없는 옛 기출은 교재팀이 워크북 단위로
        # 따로 준다 (실증 2026-08-07: 마더텅 11강 zip 에 16년11월/19년6월/
        # 21년6월 3개 지문이 회차 구분 없이 한 폴더로 들어옴). 한 번 파싱해
        # 못 찾은 회차 전부에 같은 content 를 등록하면, merge_selected 가
        # 코드로 블록을 골라내므로 회차가 섞여 있어도 정확히 뽑힌다.
        if not_found:
            sup = cfg.get("supplement_dir")
            sup = os.path.expanduser(sup) if sup else None
            if sup and os.path.isdir(sup):
                log("[보충원고] %s" % sup)
                sup_ms = os.path.join(job_dir, "ms_supplement")
                self._copy_manuscripts(sup, sup_ms, log)
                sup_content = parse_manuscript_folder(
                    sup_ms, wb_cfg, int(grade_num), 0, 0, log=log)
                still = []
                for entry in not_found:
                    yy, mm = entry.split("년")[0].strip(), \
                        entry.split("년")[1].split("월")[0].strip()
                    try:
                        yy, mm = int(yy), int(mm)
                    except ValueError:
                        still.append(entry)
                        continue
                    sources.append({"yy": yy, "mm": mm,
                                    "content": sup_content})
                    log("[보충원고] %d년 %d월 → 보충 폴더로 대체" % (yy, mm))
                not_found = still
        if not_found:
            raise FileNotFoundError(
                "원고 폴더를 찾지 못한 회차:\n  " + "\n  ".join(not_found)
                + "\n(교재팀에 해당 회차 워크북 원고 업로드를 요청하세요)")

        # 병합
        merged, coverage, defects = merge_selected(
            sources, codes, log=log,
            labels={c: str(n) for c, n in mt_numbers.items()})
        merged["grade"] = int(grade_num)
        if mt_numbers:
            # 독립 지문번호 프레임(workbook_v2 passage_numbers)도 같은 번호를
            # 쓰도록 전달 — 코드 뒤 2자리(문항번호) 폴백을 덮는다.
            merged["_passage_labels"] = [str(mt_numbers[c])
                                         for c in codes if c in mt_numbers]

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False)

        with open(os.path.join(job_dir, "coverage.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"codes": codes, "coverage": coverage,
                       "defects": defects}, f,
                      ensure_ascii=False, indent=2)

        # 원고 결손 목록을 별도 파일로 — 교재팀 재요청 근거 (사용자 요청
        # 2026-08-06: "예전 원고라서 없을 때는 따로 요청해야 되니까 로그 남게")
        if defects:
            req = os.path.join(job_dir, "원고재요청.txt")
            with open(req, "w", encoding="utf-8") as f:
                f.write("워크북 조판 중 발견한 원고 결손 목록\n")
                f.write("(코드는 원고에 있으나 내용이 비었거나 정답만 있음)\n\n")
                for d in defects:
                    yy, mm, qq = d["code"][:2], d["code"][2:4], d["code"][4:6]
                    f.write("- 고%s %s년 %s월 %s번 [%s] %s / %s\n"
                            % (grade_num, yy, int(mm), int(qq), d["code"],
                               d["step"], d["reason"]))
            log("[원고재요청] %s (%d건)" % (req, len(defects)))

        # 커버리지 요약 로그 — 스텝별 누락 즉시 노출 (침묵 금지)
        for step_key, cov in coverage.items():
            missing = [c for c, ok in cov.items() if not ok]
            if missing and any(cov.values()):
                log("[경고] %s: 원고에 없는 문항 %s" % (step_key, missing))
        return json_path

    # ─── prepare_jsx ───────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        grade = self._get_meta(job_dir, "grade", "고1")
        school = _nfc(self._get_meta(job_dir, "school", "학교미지정"))
        exam_period = self._get_meta(job_dir, "exam_period", "기간미지정")
        result_name = self._get_meta(job_dir, "result_name", "").strip()
        if not result_name:
            raise ValueError("결과 파일명을 입력하세요.")

        output_dir = os.path.join(cfg["output_base"], grade, exam_period,
                                  school)
        os.makedirs(output_dir, exist_ok=True)
        log("[출력 폴더] %s" % output_dir)

        indd_out = os.path.join(output_dir, "%s.indd" % result_name)
        n = 2
        while os.path.exists(indd_out) and n < 1000:
            indd_out = os.path.join(output_dir,
                                    "%s_%d.indd" % (result_name, n))
            n += 1

        src = cfg["indd_original"]
        if not os.path.exists(src):
            raise FileNotFoundError("워크북 원본 템플릿 없음: %s" % src)
        indd_out = safe_copy_indd(src, indd_out)
        log("[내지] 원본 복사: %s" % os.path.basename(indd_out))

        with open(json_path, encoding="utf-8") as f:
            merged = json.load(f)

        settings = {
            "json_path": json_path,
            "indd_path": indd_out,
            "output_dir": job_dir,
            "grade": merged.get("grade", 1),
            "year": merged.get("year", 25),
            "month": merged.get("month", 10),
            "exclude": [],
            "pdf_path": os.path.splitext(indd_out)[0] + ".pdf",
            # 회차 혼합본이므로 간지의 "YY년 MM월" 표기는 비운다
            "divider_line2": "",
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()
        jsx_src = re.sub(r'var settingsPath\s*=\s*"[^"]*";',
                         'var settingsPath = "%s";' % settings_path, jsx_src)
        jsx_copy = os.path.join(job_dir, "run.jsx")
        with open(jsx_copy, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        # 후처리 trim JSX (미사용 페이지 제거 + 간지 텍스트)
        trim_tpl = os.path.join(_DIR, "jsx", "trim_pages.jsx")
        with open(trim_tpl, encoding="utf-8") as f:
            trim_src = f.read()
        trim_src = trim_src.replace("__SETTINGS_PATH__", settings_path)
        with open(os.path.join(job_dir, "trim_pages.jsx"), "w",
                  encoding="utf-8") as f:
            f.write(trim_src)

        log("[JSX] 준비 완료")
        return jsx_copy

    # ─── run_indesign: 본 조판 + PDF export ────────────────────────

    @staticmethod
    def _wait_indesign_ready(log, max_wait=600):
        """InDesign이 AppleEvents에 응답할 때까지 대기.

        run.jsx 완료 로그 후에도 대형 문서 recompose/save 로 수 분간
        바쁠 수 있고, 그 동안 do script 제출은 AppleScript 용어 조회
        실패("expected end of line but found script")로 죽는다
        (2026-08-04 실측 — trim/export 제출 실패의 원인).
        """
        import subprocess, time
        deadline = time.time() + max_wait
        probe = ('with timeout of 15 seconds\n'
                 'tell application "Adobe InDesign 2026" to do script '
                 '"1+1" language javascript\n'
                 'end timeout')
        waited = False
        while time.time() < deadline:
            try:
                r = subprocess.run(["osascript", "-e", probe],
                                   capture_output=True, timeout=30)
                ok = (r.returncode == 0)
            except (subprocess.TimeoutExpired, OSError):
                # osascript 자체가 행 — InDesign busy. 재시도.
                ok = False
            if ok:
                if waited:
                    log("[InDesign] 응답 회복 — 다음 단계 진행")
                return True
            waited = True
            time.sleep(10)
        log("[경고] InDesign %d초 무응답 — 그대로 제출 시도" % max_wait)
        return False

    def run_indesign(self, job_dir, log):
        from core.indesign import runner
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        # 본조판 제출 전에도 응답성 확인 — 직전 작업(다른 엔진 포함)의
        # recompose/save 로 InDesign 이 바쁘면 do script 가 AppleScript
        # 용어 조회 실패로 죽는다 (2026-08-05 실측: run.jsx 2회 연속 실패).
        self._wait_indesign_ready(log)
        log_file = os.path.join(job_dir, "조판_로그.txt")
        runner.run_jsx(os.path.join(job_dir, "run.jsx"), log,
                       poll_log_path=log_file, timeout=self.jsx_timeout,
                       stall_limit=900)

        # 후처리 1: 미사용 페이지 제거 + 간지 텍스트 (선택 조판 전용)
        self._wait_indesign_ready(log)
        trim_log = os.path.join(job_dir, "trim_로그.txt")
        runner.run_jsx(os.path.join(job_dir, "trim_pages.jsx"), log,
                       poll_log_path=trim_log, timeout=1200, stall_limit=600,
                       completion_marker="===== trim 완료 =====")

        # 후처리 2: PDF export (run.jsx는 저장까지만 한다)
        self._wait_indesign_ready(log)
        export_jsx = os.path.join(job_dir, "export_pdf.jsx")
        indd = settings["indd_path"].replace("\\", "\\\\").replace('"', '\\"')
        pdf = settings["pdf_path"].replace("\\", "\\\\").replace('"', '\\"')
        export_log = os.path.join(job_dir, "export_로그.txt")
        with open(export_jsx, "w", encoding="utf-8") as f:
            f.write(
                '#target indesign\n'
                # runner.run_jsx 는 JSX 안의 settingsPath 변수를 요구한다
                'var settingsPath = "%s";\n' % settings_path.replace("\\", "\\\\") +
                '(function () {\n'
                '    var lf = new File("%s");\n'
                '    lf.encoding = "UTF-8"; lf.lineFeed = "Unix";\n'
                '    function W(s) { lf.open("a"); lf.writeln(s); lf.close(); }\n'
                '    try {\n'
                '        var f = new File("%s");\n'
                '        var d = app.open(f, false);\n'
                '        app.pdfExportPreferences.pageRange = PageRange.ALL_PAGES;\n'
                '        app.pdfExportPreferences.exportReaderSpreads = false;\n'
                '        try { app.pdfExportPreferences.viewPDF = false; } catch (e0) {}\n'
                '        d.exportFile(ExportFormat.PDF_TYPE, new File("%s"), false);\n'
                '        d.close(SaveOptions.NO);\n'
                '        W("===== PDF export 완료 =====");\n'
                '    } catch (e) { W("[오류] " + e.message); }\n'
                '})();\n'
                % (export_log.replace("\\", "\\\\").replace('"', '\\"'),
                   indd, pdf))
        runner.run_jsx(export_jsx, log, poll_log_path=export_log,
                       timeout=1200, stall_limit=600,
                       completion_marker="===== PDF export 완료 =====")

    # ─── verify ────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        warnings = []

        log_path = os.path.join(job_dir, "조판_로그.txt")
        steps_done = None
        if os.path.exists(log_path):
            content = open(log_path, encoding="utf-8",
                           errors="ignore").read()
            m = re.search(r"STEP완료:\s*(\d+)개", content)
            steps_done = int(m.group(1)) if m else None
        else:
            warnings.append("조판 로그 없음 — JSX 미실행 의심")

        # 최종 오버플로우 = trim 후 잔여치 (run.jsx 로그의 "오버플로우: N개"는
        # 흡수용 추가 페이지 수라 판정 기준이 아니다)
        overflow = None
        trim_log = os.path.join(job_dir, "trim_로그.txt")
        if os.path.exists(trim_log):
            tcontent = open(trim_log, encoding="utf-8",
                            errors="ignore").read()
            m = re.search(r"잔여 오버플로우:\s*(\d+)개", tcontent)
            overflow = int(m.group(1)) if m else None
        if overflow is None:
            warnings.append("잔여 오버플로우 수치 확인 불가 (trim 로그)")
        elif overflow > 0:
            warnings.append("오버플로우 %d개 발생 — 내용 잘림 의심" % overflow)

        # 문항 커버리지 — 스텝별 누락 문항 노출
        cov_path = os.path.join(job_dir, "coverage.json")
        if os.path.exists(cov_path):
            cov = json.load(open(cov_path, encoding="utf-8"))
            for step_key, per_code in cov["coverage"].items():
                if not any(per_code.values()):
                    continue  # 원고 전체에 없는 스텝 (예: a1_btm)
                missing = [c for c, ok in per_code.items() if not ok]
                if missing:
                    warnings.append(
                        "%s: 원고에 없는 문항 %s" % (step_key, missing))

        # PDF 페이지수
        pdf_path = settings.get("pdf_path", "")
        pdf_pages = None
        if pdf_path and os.path.exists(pdf_path):
            try:
                from pypdf import PdfReader
                pdf_pages = len(PdfReader(pdf_path).pages)
                log("[검수] PDF %dp 생성 확인" % pdf_pages)
            except Exception:
                warnings.append("PDF 페이지수 확인 실패")
        else:
            warnings.append("PDF 미생성")
            pdf_path = None

        indd_path = settings.get("indd_path")
        if indd_path and not os.path.exists(indd_path):
            warnings.append(".indd 미생성")

        ok = (overflow == 0 and pdf_path is not None and
              not any("원고에 없는" in w for w in warnings))
        result = {
            "ok": ok,
            "overflow": overflow,
            "steps_completed": steps_done,
            "pdf_path": pdf_path,
            "pdf_paths": [pdf_path] if pdf_path else [],
            "indd_path": indd_path if (indd_path and
                                       os.path.exists(indd_path)) else None,
            "warnings": warnings,
        }
        log("[검수] %s | 오버플로우 %s | STEP %s | 경고 %d건"
            % ("통과" if ok else "경고", overflow, steps_done, len(warnings)))
        return result
