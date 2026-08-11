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
from engines.workbook_v2.engine import WorkbookV2Engine
from core.paths import resolve_config
from engines.workbook.engine import _load_config as _load_workbook_config
from engines.workbook.parser import parse_manuscript_folder
from engines.workbook_select.merge_select import merge_selected
from engines.workbook_select.merge_select import load_fill as _load_fill
from engines.workbook_select import motherteng as _mt

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(
    os.path.dirname(_DIR), "workbook", "jsx", "run.jsx")

_MS_EXTS = (".docx", ".hwp", ".hwpx")

# 문항당 유닛 수가 원래 가변인 스텝 (문장배열=순서+삽입, 본문정리=지문+문제)
# — 나머지 스텝은 "문항 1개 = 유닛 1개"가 계약이다.
_VARIABLE_UNIT_STEPS = {"step1_b1", "step1_c1"}


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _load_config():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["manuscript_base", "indd_original",
                                "output_base"])


class WorkbookSelectEngine(WorkbookV2Engine):

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
                    "key": "mt_gang",
                    "label": "마더텅 강 번호 (예: 11) — 넣으면 코드는 "
                             "지문 출처 엑셀에서 자동 조달",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "codes",
                    "label": "문항 코드 (YYMMQQ, 순서대로 — 줄바꿈/콤마 구분). "
                             "강 번호를 넣었으면 비워둘 것",
                    "type": "text",
                    "required": False,
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

        mt_gang = (uploaded_files.get("mt_gang", "")
                   or self._get_meta(job_dir, "mt_gang", "")
                   or cfg.get("mt_gang"))
        try:
            mt_gang = int(mt_gang) if mt_gang else None
        except (TypeError, ValueError):
            mt_gang = None

        # 코드를 직접 안 주면 강 번호로 엑셀에서 조달한다 (사용자 요청
        # 2026-08-08: "엑셀에서 해당 번호 읽어서 바로 작업"). 코드를 준
        # 경우는 그쪽이 우선 — 강 밖 지문을 섞는 워크북도 가능해야 한다.
        mt_numbers = {}
        if not codes_text.strip():
            if mt_gang is None:
                raise ValueError(
                    "문항 코드를 입력하거나 마더텅 강 번호를 지정하세요.")
            codes, mt_numbers, col = _mt.codes_for_gang(
                cfg.get("motherteng_xlsx"), mt_gang, log=log)
            if not codes:
                raise ValueError(
                    "마더텅 %s강을 지문 출처 엑셀에서 찾지 못했습니다: %s"
                    % (mt_gang, cfg.get("motherteng_xlsx")))
            log("[코드] %d개 — 엑셀 '%s' 에서 조달" % (len(codes), col))
        else:
            codes = self._parse_codes(codes_text)
            log("[코드] %d개 (직접 입력)" % len(codes))

        # 마더텅 지문번호 — 엑셀(강별 열 × 행)에서 조달. 사용자 확정 스펙
        # (2026-08-07): 조판 순서와 지문번호를 이 번호로 맞춘다. 순차
        # 1,2,3,4 로 다시 매기지 않는다 (짝수만 뽑힌 워크북이면 2,4,6…).
        mt_index = {} if mt_numbers else _mt.load_index(
            cfg.get("motherteng_xlsx"))
        if mt_numbers:
            codes = _mt.sort_by_number(codes, mt_numbers)
            log("[마더텅] 지문번호 %s"
                % ", ".join(str(mt_numbers[c]) for c in codes))
        elif mt_index:
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
        # 보충 데이터 — 원고가 아예 없는 칸을 이전 산출물(.indd)에서 뽑아둔 것.
        # job 폴더의 fill.json 이 있으면 그것을, 없으면 config 경로를 쓴다.
        fill_path = os.path.join(job_dir, "fill.json")
        if not os.path.exists(fill_path):
            fill_path = cfg.get("fill_json") or ""
            if fill_path.startswith("~"):
                fill_path = os.path.expanduser(fill_path)
        fill = _load_fill(fill_path, log)

        merged, coverage, defects = merge_selected(
            sources, codes, log=log,
            labels={c: str(n) for c, n in mt_numbers.items()},
            fill=fill)
        merged["grade"] = int(grade_num)
        if mt_numbers:
            # 독립 지문번호 프레임(workbook_v2 passage_numbers)도 같은 번호를
            # 쓰도록 전달 — 코드 뒤 2자리(문항번호) 폴백을 덮는다.
            merged["_passage_labels"] = [str(mt_numbers[c])
                                         for c in codes if c in mt_numbers]

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False)

        self._write_prompts(job_dir, merged, fill, log)

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

    # ── 조판: workbook_v2 경로 사용 (사용자 확정 스펙 2026-08-07) ─────────
    # 이전에는 v1 engines/workbook/jsx/run.jsx 를 직접 실행했다. v1 경로는
    # 지문번호 프레임 갱신(passage_numbers)·간지 표기·선지 정렬 등 v2 에만
    # 있는 계약을 전부 못 받아, 신규 3건 조판에서 지문 1개만 나오고 간지가
    # '고2 모의고사'로 찍히는 결함이 났다. 이제 v2 엔진의 prepare_jsx /
    # run_indesign 을 그대로 상속하고, 출력 경로·파일명만 여기서 정한다.

    def _load_cfg(self):
        """v2 가 쓰는 config 에 선택 결합용 출력 경로/템플릿을 얹는다."""
        cfg = dict(_load_workbook_config())
        sel = _load_config()
        cfg["indd_output_dir"] = self._select_output_dir
        cfg["indd_original"] = sel["indd_original"]
        return cfg

    def _select_template(self, cfg, workbook_type, school, log):
        """선택 결합은 내지가 하나로 고정 — v2 의 학교별 매핑(dict)을 쓰지
        않고 config 의 단일 경로를 그대로 쓴다."""
        src = cfg["indd_original"]
        if not os.path.exists(src):
            raise FileNotFoundError("워크북 원본 템플릿 없음: %s" % src)
        log("[내지] %s" % os.path.basename(src))
        return src

    def _output_name(self, job_dir, grade, year, month, workbook_type,
                     school):
        name = self._get_meta(job_dir, "result_name", "").strip()
        if not name:
            raise ValueError("결과 파일명을 입력하세요.")
        return "%s.indd" % name

    def prepare_jsx(self, json_path, job_dir, log):
        sel = _load_config()
        grade = self._get_meta(job_dir, "grade", "고1")
        school = _nfc(self._get_meta(job_dir, "school", "학교미지정"))
        exam_period = self._get_meta(job_dir, "exam_period", "기간미지정")
        out_dir = os.path.join(sel["output_base"], grade, exam_period, school)
        os.makedirs(out_dir, exist_ok=True)
        self._select_output_dir = out_dir
        log("[출력 폴더] %s" % out_dir)
        jsx_path = WorkbookV2Engine.prepare_jsx(self, json_path, job_dir, log)
        self._check_plan_invariants(job_dir, json_path, log)
        return jsx_path

    # ── G2: 구조 불변식 — 조판 전에 깨지면 멈춘다 ───────────────────────
    #
    # 조판이 끝난 뒤엔 이 결함들이 오버셋·링크·폰트·중복 검사를 전부
    # 통과해버려 사람 눈에만 걸린다. 실측 2026-08-08:
    #   - 짝 스텝 유닛수 불일치(20 vs 17) → 상·하단 13페이지가 다른 지문끼리
    #   - 원문자 단락마다 유닛 분할(17문항이 48·57유닛) → 프레임 3배
    # 둘 다 플랜 단계에서 숫자 하나로 잡힌다.

    def _check_plan_invariants(self, job_dir, json_path, log):
        from engines.workbook_select.merge_select import ALIGNED_STEPS

        plan_path = os.path.join(job_dir, "render_plan.json")
        if not os.path.exists(plan_path):
            settings = os.path.join(job_dir, ".settings.json")
            if os.path.exists(settings):
                plan_path = json.load(
                    open(settings, encoding="utf-8")).get("plan_path", "")
        if not plan_path or not os.path.exists(plan_path):
            log("[불변식] render_plan.json 없음 — 검사 생략")
            return

        plan = json.load(open(plan_path, encoding="utf-8"))
        units = {f.get("step"): len(f.get("units") or [])
                 for f in plan.get("flows") or []}
        cov_path = os.path.join(job_dir, "coverage.json")
        n_codes = 0
        if os.path.exists(cov_path):
            n_codes = len(json.load(
                open(cov_path, encoding="utf-8")).get("codes") or [])

        errors = []

        # (1) 짝 스텝은 유닛 수가 같아야 한다 — 한 페이지에 같이 얹히므로
        for a, b in ALIGNED_STEPS.items():
            if a in units and b in units and units[a] != units[b]:
                errors.append(
                    "짝 스텝 유닛수 불일치: %s=%d vs %s=%d "
                    "(그대로 조판하면 상·하단이 다른 지문끼리 붙는다)"
                    % (a, units[a], b, units[b]))

        # (2) 문항 1개 = 유닛 1개인 스텝은 유닛 수가 문항 수와 정확히 같아야
        #     한다. 문장배열(순서+삽입)·본문정리처럼 문항당 유닛 수가 원래
        #     가변인 스텝은 제외하고 로그만 남긴다.
        if n_codes:
            for step, n in sorted(units.items()):
                if step in _VARIABLE_UNIT_STEPS:
                    if n < n_codes:
                        errors.append(
                            "%s 유닛수 %d < 문항수 %d (문항 누락)"
                            % (step, n, n_codes))
                    continue
                if n != n_codes:
                    errors.append(
                        "%s 유닛수 %d ≠ 문항수 %d "
                        "(한 문항이 여러 프레임으로 쪼개졌거나 빠졌다)"
                        % (step, n, n_codes))

        log("[불변식] 문항 %d개 / 유닛: %s"
            % (n_codes, ", ".join("%s=%d" % (k, v)
                                  for k, v in sorted(units.items()))))
        if errors:
            for e in errors:
                log("[불변식 실패] " + e)
            raise ValueError("조판 전 구조 검사 실패:\n  " + "\n  ".join(errors))
        log("[불변식] 통과")

    def run_indesign(self, job_dir, log, **kwargs):
        """v2 조판 후 trim 후처리(jsx/trim_pages.jsx)를 이어서 실행한다.

        선택 조판은 문항 수가 템플릿 용량(18문항)보다 적어 섹션마다 미사용
        페이지가 남는데, run.jsx 16.5(전 프레임 빈 페이지만 삭제)는 템플릿
        유래 정적 잔재(발문 보일러플레이트·낡은 지문번호 라벨)가 있는
        페이지를 지우지 못한다. trim_pages.jsx 는 그 판정을 "스레드 스토리에
        실내용이 있는가"로 하고 고아 간지까지 정리한다.

        연결이 빠져 있어 2026-08-08 빌드에 빈 페이지 19개가 잔존했다
        (개발가이드 "trim 후처리가 v1 경로에만 연결" 건과 같은 원인).
        verify() 가 trim_로그.txt 의 "잔여 오버플로우"를 읽는 것도 이 단계가
        돌아야 성립한다.
        """
        from core.indesign.runner import run_jsx

        # v2 는 (job_dir, log) 만 받는다 — kwargs 를 넘기지 않는다
        WorkbookV2Engine.run_indesign(self, job_dir, log)

        settings_path = os.path.join(job_dir, ".settings.json")

        # trim 보다 먼저 — 짝 스텝(상단/하단)이 따로 오버플로우 페이지를
        # 만들어 갈라진 것을 합친다. 합치면 꼬리 프레임이 비고, 그 페이지는
        # 바로 뒤 trim 이 지운다.
        self._run_post_jsx(job_dir, settings_path, log,
                           "pair_overflow.jsx", "pair_로그.txt",
                           "===== 짝 정리 완료 =====", "[짝정리]",
                           timeout=1800, stall=900)

        # 발문 유형 교정 (네모형 문항에 밑줄형 발문이 붙는 것 방지)
        self._run_post_jsx(job_dir, settings_path, log,
                           "fix_prompt.jsx", "prompt_로그.txt",
                           "===== 발문 교정 완료 =====", "[발문]",
                           timeout=900, stall=600)

        tpl = os.path.join(_DIR, "jsx", "trim_pages.jsx")
        if not os.path.exists(tpl):
            log("[trim] 템플릿 없음 — 건너뜀: %s" % tpl)
            return
        with open(tpl, encoding="utf-8") as f:
            src = f.read()
        src = src.replace("__SETTINGS_PATH__", settings_path)
        out = os.path.join(job_dir, "trim_pages.jsx")
        with open(out, "w", encoding="utf-8") as f:
            f.write(src)

        trim_log = os.path.join(job_dir, "trim_로그.txt")
        try:
            os.remove(trim_log)
        except OSError:
            pass
        log("[trim] 미사용 페이지 정리 시작")
        run_jsx(out, log, poll_log_path=trim_log,
                timeout=1800,
                completion_marker="===== trim 완료 =====",
                stall_limit=900)

        # trim 이 페이지를 지운 뒤이므로 PDF 를 다시 뽑는다 — 안 하면 PDF 만
        # trim 이전 상태로 남는다 (2026-08-08 실측 INDD 292p vs PDF 310p).
        self._reexport_pdf(job_dir, settings_path, log)

    # ── 하단 문제 발문 — 유형이 다른 문항만 원고 발문으로 교체 ──────────
    #
    # 발문은 템플릿 정적 프레임이라 밑줄형 문구가 고정돼 있다. 네모형
    # ((A)(B)(C) 고르기) 문항에는 맞지 않는다. 문구를 지어내지 않고
    # **원고(또는 보충 데이터)에 있는 발문**을 그대로 쓴다.
    _RE_EN8 = re.compile(r"[A-Za-z']+")

    def _write_prompts(self, job_dir, merged, fill, log):
        step = "step2_a1_btm"
        specs = []

        def match_of(paras):
            for p in paras:
                t = (p.get("text") if isinstance(p, dict) else str(p)) or ""
                if len(self._RE_EN8.findall(t)) >= 8:
                    return t[:80]
            return ""

        # (1) 회차 원고 유래 — 병합 결과에서 네모형 발문 단락을 찾는다
        st = (merged.get("steps") or {}).get(step) or {}
        paras = st.get("paragraphs") if isinstance(st, dict) else st
        paras = paras if isinstance(paras, list) else []
        pending = None
        for p in paras:
            t = (p.get("text") if isinstance(p, dict) else str(p)) or ""
            if "네모" in t and "어법" in t:
                pending = t.strip()
                continue
            if pending and len(self._RE_EN8.findall(t)) >= 8:
                specs.append({"match": t[:80], "prompt": pending})
                pending = None

        # (2) 보충 데이터 유래 — fill 의 prompt
        for code, ent in ((fill or {}).get(step) or {}).items():
            pr = (ent.get("prompt") or "").strip()
            if "네모" not in pr:
                continue
            mt = match_of(ent.get("paras") or [])
            if mt:
                specs.append({"match": mt, "prompt": pr})

        path = os.path.join(job_dir, "prompts.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(specs, f, ensure_ascii=False, indent=1)
        if specs:
            log("[발문] 유형이 다른 문항 %d건 — 원고 발문으로 교체 예약"
                % len(specs))

    def _run_post_jsx(self, job_dir, settings_path, log, tpl_name,
                      log_name, marker, tag, timeout=1800, stall=900):
        """엔진 jsx/ 의 후처리 템플릿 하나를 실행한다."""
        from core.indesign.runner import run_jsx

        tpl = os.path.join(_DIR, "jsx", tpl_name)
        if not os.path.exists(tpl):
            log("%s 템플릿 없음 — 건너뜀: %s" % (tag, tpl))
            return
        with open(tpl, encoding="utf-8") as f:
            src = f.read()
        src = src.replace("__SETTINGS_PATH__", settings_path)
        out = os.path.join(job_dir, tpl_name)
        with open(out, "w", encoding="utf-8") as f:
            f.write(src)
        poll = os.path.join(job_dir, log_name)
        try:
            os.remove(poll)
        except OSError:
            pass
        log("%s 시작" % tag)
        run_jsx(out, log, poll_log_path=poll, timeout=timeout,
                completion_marker=marker, stall_limit=stall)

    def _reexport_pdf(self, job_dir, settings_path, log):
        from core.indesign.runner import run_jsx

        tpl = os.path.join(_DIR, "jsx", "reexport_pdf.jsx")
        if not os.path.exists(tpl):
            log("[재출력] 템플릿 없음 — 건너뜀: %s" % tpl)
            return
        with open(tpl, encoding="utf-8") as f:
            src = f.read()
        src = src.replace("__SETTINGS_PATH__", settings_path)
        out = os.path.join(job_dir, "reexport_pdf.jsx")
        with open(out, "w", encoding="utf-8") as f:
            f.write(src)

        re_log = os.path.join(job_dir, "reexport_로그.txt")
        try:
            os.remove(re_log)
        except OSError:
            pass
        log("[재출력] trim 반영 PDF 재출력 시작")
        run_jsx(out, log, poll_log_path=re_log,
                timeout=3600,
                completion_marker="===== 재출력 완료 =====",
                stall_limit=2700)

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
