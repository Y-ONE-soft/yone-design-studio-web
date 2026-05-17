"""마더텅 결합 엔진.

엑셀에 정의된 강별 지문 출처 리스트를 보고, 해당 코드들을 모아 분석본
마스터 템플릿 위에 결합한다.

소스 우선순위:
  1) 모의고사 작업/고{N}/고{N} {YY}년 {M}월/*분석본*.indd
     (analysis_merge 엔진과 동일 — 마커 텍스트 매칭)
  2) Fallback: {fallback_base}/{N}강 .../*.indd 의 고정 위치
     (엑셀 행 순서 → 페이지 인덱스 = 1 + 2 * (rowOffset) 0-기반)

엑셀 형식 (header_row=3, first_data_row=4 기준):
  - 헤더 행: 첫 셀은 None, 나머지는 "{N:02d} {강명}" 형식
  - 데이터 행: A 열 = 강 내 순번, B~ 열 = 6자리 YYMMQQ 코드 (또는 빈셀)
"""

import json
import os
import re
import unicodedata

from core.base import BaseEngine, safe_copy_indd


def _nfc(s):
    return unicodedata.normalize("NFC", s)


_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_PATH_KEYS = ["template_path", "gdrive_base", "output_base"]


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _expand_path(p):
    if not p:
        return p
    return os.path.expanduser(p)


_LESSON_HEADER_RE = re.compile(r"^\s*(\d{1,2})\s*(.*)$")


def _parse_excel_lessons(excel_path, header_row=3, first_data_row=4):
    """엑셀에서 강 목록과 강별 코드 리스트 반환.

    Returns:
        list of dict: [
            {
              "lesson_num": "03",
              "lesson_name": "필자의 주장",
              "column": 2,          # openpyxl 1-기반 column index
              "header_label": "03 필자의 주장",
              "passages": [
                  {"row_offset": 0, "code": "221120"},
                  {"row_offset": 1, "code": "230920"},
                  ...
              ]
            },
            ...
        ]
    """
    import openpyxl
    wb = openpyxl.load_workbook(excel_path, data_only=True)
    ws = wb[wb.sheetnames[0]]

    lessons = []
    # 헤더 행 스캔 — 2열부터
    max_col = ws.max_column
    for col in range(2, max_col + 1):
        cell = ws.cell(header_row, col).value
        if cell is None:
            continue
        text = str(cell).strip()
        m = _LESSON_HEADER_RE.match(text)
        if not m:
            continue
        lesson_num = m.group(1).zfill(2)  # "3" → "03"
        lesson_name = m.group(2).strip()
        # 코드 수집 (first_data_row 부터, 빈셀이면 skip)
        passages = []
        row_offset = 0
        for r in range(first_data_row, ws.max_row + 1):
            v = ws.cell(r, col).value
            if v is None or str(v).strip() == "":
                row_offset += 1
                continue
            code_str = str(v).strip()
            # 숫자값이면 zfill, 문자열이면 그대로
            if isinstance(v, (int, float)):
                code_str = str(int(v)).zfill(6)
            if not re.match(r"^\d{6}$", code_str):
                row_offset += 1
                continue
            passages.append({"row_offset": row_offset, "code": code_str})
            row_offset += 1
        lessons.append({
            "lesson_num": lesson_num,
            "lesson_name": lesson_name,
            "column": col,
            "header_label": text,
            "passages": passages,
        })
    return lessons


def _find_fallback_file(fallback_base, lesson_num):
    """fallback_base 안에서 {N}강... 시작 폴더 → 안의 .indd 첫 후보 반환."""
    if not fallback_base or not os.path.isdir(fallback_base):
        return None
    lesson_int = int(lesson_num)
    # 폴더명: "{N}강 {lesson_name}" — N 은 0-padded 가 아니므로 lesson_int 와 매칭
    target_prefixes = [f"{lesson_int}강", f"{lesson_int:02d}강"]
    for raw in os.listdir(fallback_base):
        nfc = _nfc(raw)
        if not any(nfc.startswith(p) for p in target_prefixes):
            continue
        full = os.path.join(fallback_base, raw)
        if not os.path.isdir(full):
            continue
        # 해당 폴더 안에서 .indd 후보 (마더텅 강 파일)
        for raw_f in os.listdir(full):
            nfc_f = _nfc(raw_f)
            if not nfc_f.lower().endswith(".indd"):
                continue
            if nfc_f.startswith("~") or "idlk" in nfc_f.lower():
                continue
            # "분석본_내지(마스터).indd" 같은 템플릿 사본 제외
            if "마스터" in nfc_f:
                continue
            return os.path.join(full, raw_f)
    return None


def _find_month_folder(gdrive_base, grade_num, year, month):
    grade_dir = os.path.join(gdrive_base, f"고{grade_num}")
    if not os.path.isdir(grade_dir):
        return None

    month_int = int(month)
    month_variants = [str(month_int)]
    if month_int < 10:
        month_variants.append(f"0{month_int}")

    prefix = f"고{grade_num} "
    for raw in os.listdir(grade_dir):
        nfc = _nfc(raw)
        if not nfc.startswith(prefix):
            continue
        if f"{year}년" not in nfc:
            continue
        if not any(f"{mv}월" in nfc for mv in month_variants):
            continue
        full = os.path.join(grade_dir, raw)
        if os.path.isdir(full):
            return full
    return None


def _find_analysis_files(month_folder, patterns=None):
    if not month_folder or not os.path.isdir(month_folder):
        return []
    patterns = patterns or ["분석본"]
    results = []
    for raw in os.listdir(month_folder):
        nfc = _nfc(raw)
        if not nfc.lower().endswith(".indd"):
            continue
        if not any(pat in nfc for pat in patterns):
            continue
        if nfc.startswith("~") or "idlk" in nfc.lower():
            continue
        results.append(os.path.join(month_folder, raw))
    results.sort(key=lambda p: (len(os.path.basename(p)), os.path.basename(p)))
    return results


class MothertongueMergeEngine(BaseEngine):

    @property
    def material_id(self):
        return "mothertongue_merge"

    @property
    def display_name(self):
        return "마더텅 결합"

    @property
    def description(self):
        return "마더텅 지문 출처 엑셀에 따라 강 단위로 분석본을 결합 → .indd + PDF"

    @property
    def subject_prefix(self):
        return "마더텅결합"

    @property
    def template_name(self):
        return "typeset_mothertongue_merge.html"

    @property
    def log_filename(self):
        return "merge_log.txt"

    @property
    def jsx_timeout(self):
        return 1200  # 20분 — 여러 .indd 열기 + 큰 강 (11강 72지문) 대비

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "lessons",
                    "label": "선택한 강 (콤마 구분)",
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
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    @staticmethod
    def list_lessons(grade, school):
        """API 용 — 주어진 학년+학교의 강 목록 반환."""
        cfg = _load_config()
        key = f"{grade}-{school}"
        scfg = cfg["schools"].get(key)
        if not scfg:
            return {"lessons": [], "error": f"엑셀 설정 없음: {key}"}
        excel_path = _expand_path(scfg["excel_path"])
        if not os.path.exists(excel_path):
            return {"lessons": [], "error": f"엑셀 파일 없음: {excel_path}"}
        try:
            lessons = _parse_excel_lessons(
                excel_path,
                header_row=scfg.get("header_row", 3),
                first_data_row=scfg.get("first_data_row", 4),
            )
        except Exception as e:
            return {"lessons": [], "error": f"엑셀 파싱 실패: {e}"}
        return {
            "lessons": [
                {
                    "lesson_num": l["lesson_num"],
                    "lesson_name": l["lesson_name"],
                    "header_label": l["header_label"],
                    "count": len(l["passages"]),
                }
                for l in lessons
            ]
        }

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        cfg = _load_config()
        patterns = cfg.get("file_patterns", ["분석본"])

        grade = self._get_meta(job_dir, "grade", "고1")
        school = _nfc(self._get_meta(job_dir, "school", "한영고1"))
        grade_num = grade.replace("고", "")

        school_key = f"{grade}-{school}"
        scfg = cfg["schools"].get(school_key)
        if not scfg:
            raise ValueError(f"엑셀 설정 없음 (config.json schools 에 추가 필요): {school_key}")

        excel_path = _expand_path(scfg["excel_path"])
        fallback_base = _expand_path(scfg.get("fallback_base", ""))
        pages_per_passage = scfg.get("pages_per_passage", 2)

        if not os.path.exists(excel_path):
            raise FileNotFoundError(f"엑셀 파일 없음: {excel_path}")

        # 선택한 강 (콤마 구분 lesson_num 또는 header_label)
        lessons_raw = uploaded_files.get("lessons", "")
        selected = [s.strip() for s in lessons_raw.split(",") if s.strip()]
        if not selected:
            raise ValueError("강이 선택되지 않았습니다.")

        log(f"[엑셀] {os.path.basename(excel_path)}")
        log(f"[선택 강] {', '.join(selected)}")

        all_lessons = _parse_excel_lessons(
            excel_path,
            header_row=scfg.get("header_row", 3),
            first_data_row=scfg.get("first_data_row", 4),
        )

        # 선택된 강만 필터 — lesson_num 또는 header_label 일치
        selected_lessons = []
        for l in all_lessons:
            if (l["lesson_num"] in selected or
                l["lesson_name"] in selected or
                l["header_label"] in selected or
                str(int(l["lesson_num"])) in selected):
                selected_lessons.append(l)

        if not selected_lessons:
            raise ValueError(f"선택한 강을 엑셀에서 찾지 못함: {selected}")

        log(f"[강] {len(selected_lessons)}개 매칭됨")
        for l in selected_lessons:
            log(f"  - {l['header_label']}: {len(l['passages'])}개 지문")

        # 각 강의 코드별로 후보 파일 결정
        gdrive_base = _expand_path(cfg["gdrive_base"])

        # 후보 캐시 — 같은 파일 중복 복사 방지
        local_copied = {}      # gdrive_path → local_path

        # ym 캐시 — 같은 (year, month) 월 폴더는 한 번만 스캔
        ym_cache = {}          # (year, month) → list[local_path]

        # fallback 캐시 — 강 파일 한 번만 복사
        fallback_cache = {}    # lesson_num → local_path

        # GDrive 파일은 EDEADLK 회피를 위해 7-경로 폴백 + 지수 백오프 사용
        # (.claude/rules/gdrive_copy_robust.md 참조)
        from engines.final.extractor import _gdrive_safe_copy

        def _local_copy(src_path):
            if src_path in local_copied:
                return local_copied[src_path]
            base = os.path.basename(src_path)
            local_path = os.path.join(job_dir, f"src_{base}")
            # 같은 이름이 있으면 _2, _3 suffix
            if os.path.isfile(local_path) and os.path.getsize(local_path) > 0:
                b, ext = os.path.splitext(local_path)
                n = 2
                while (os.path.isfile(f"{b}_{n}{ext}") and
                       os.path.getsize(f"{b}_{n}{ext}") > 0):
                    n += 1
                local_path = f"{b}_{n}{ext}"
            ok, err = _gdrive_safe_copy(src_path, local_path, log=log)
            if not ok:
                raise RuntimeError(f"GDrive 파일 복사 실패: {base} — {err}")
            local_copied[src_path] = local_path
            return local_path

        passage_entries = []
        for lesson in selected_lessons:
            ln = lesson["lesson_num"]
            for passage in lesson["passages"]:
                code = passage["code"]
                year = code[0:2]
                month = code[2:4]
                qNum = code[4:6]
                row_offset = passage["row_offset"]

                # 1차 후보: 모의고사 작업/고{N}/고{N} {YY}년 {M}월/*분석본*.indd
                key = (year, month)
                if key not in ym_cache:
                    folder = _find_month_folder(gdrive_base, grade_num, year, month)
                    if not folder:
                        ym_cache[key] = []
                    else:
                        files = _find_analysis_files(folder, patterns)
                        locals_ = []
                        for f in files:
                            locals_.append(_local_copy(f))
                            log(f"    로컬 복사: {os.path.basename(f)}")
                        ym_cache[key] = locals_
                primary_candidates = list(ym_cache[key])

                # 2차 후보 (fallback): {fallback_base}/{N}강 .../*.indd 의 고정 위치
                fallback_info = None
                if ln not in fallback_cache:
                    fb_src = _find_fallback_file(fallback_base, ln)
                    if fb_src:
                        fb_local = _local_copy(fb_src)
                        log(f"    fallback 로컬 복사: {os.path.basename(fb_src)} (강 {ln})")
                        fallback_cache[ln] = fb_local
                    else:
                        fallback_cache[ln] = None
                fb_local = fallback_cache[ln]
                if fb_local:
                    # 강 파일 안에서의 위치: 1페이지(간지)+ row_offset 단위 * pages_per_passage
                    # 0-인덱스 페이지: 1 + row_offset * pages_per_passage
                    fixed_start = 1 + row_offset * pages_per_passage
                    fallback_info = {
                        "local_path": fb_local,
                        "start_idx": fixed_start,
                        "page_count": pages_per_passage,
                    }

                if not primary_candidates and not fallback_info:
                    log(f"  [경고] 해결 불가: 강 {ln} 코드 {code} — 1차/폴백 모두 없음")

                passage_entries.append({
                    "code": code,
                    "year": year,
                    "month": month,
                    "qNum": qNum,
                    "lesson_num": ln,
                    "lesson_name": lesson["lesson_name"],
                    "lesson_label": lesson["header_label"],
                    "row_offset": row_offset,
                    "primary_candidates": primary_candidates,
                    "fallback": fallback_info,
                })

        log(f"[지문] 총 {len(passage_entries)}개")

        meta_path = os.path.join(job_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"passages": passage_entries, "selected_lessons": selected_lessons},
                f, ensure_ascii=False, indent=2
            )
        return meta_path

    # ─── prepare_jsx ───────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        grade = self._get_meta(job_dir, "grade", "고1")
        school = _nfc(self._get_meta(job_dir, "school", "한영고1"))
        exam_period = self._get_meta(job_dir, "exam_period", "기간미지정")
        result_name = self._get_meta(job_dir, "result_name", "").strip()
        if not result_name:
            raise ValueError("결과 파일명을 입력하세요.")

        _studio = os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        ))
        output_dir = os.path.join(
            _studio, "조판", "교재", "마더텅결합",
            grade, exam_period, school
        )
        os.makedirs(output_dir, exist_ok=True)
        log(f"[출력 폴더] {output_dir}")

        indd_out = os.path.join(output_dir, f"{result_name}.indd")
        if os.path.exists(indd_out):
            n = 2
            while n < 1000:
                trial = os.path.join(output_dir, f"{result_name}_{n}.indd")
                if not os.path.exists(trial):
                    indd_out = trial
                    break
                n += 1
        pdf_out = os.path.splitext(indd_out)[0] + ".pdf"

        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)

        settings = {
            "template_path": cfg["template_path"],
            "output_indd": indd_out,
            "output_pdf": pdf_out,
            "output_dir": output_dir,
            "log_path": os.path.join(output_dir, self.log_filename),
            "log_paths": [os.path.join(job_dir, self.log_filename)],
            "keep_head": cfg.get("keep_head", 1),
            "school": school,
            "grade": grade,
            "exam_period": exam_period,
            "passages": meta["passages"],
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        jsx_src = os.path.join(_DIR, "jsx", "run.jsx")
        jsx_dst = os.path.join(job_dir, "run.jsx")
        with open(jsx_src, encoding="utf-8") as f:
            jsx_code = f.read()
        jsx_code = jsx_code.replace("__SETTINGS_PATH__", settings_path)
        with open(jsx_dst, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        log(f"[결과 .indd] {os.path.basename(indd_out)}")
        log(f"[결과 PDF]  {os.path.basename(pdf_out)}")
        return jsx_dst

    # ─── verify ────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        indd_out = settings["output_indd"]
        pdf_out = settings["output_pdf"]

        warnings = []
        if not os.path.exists(indd_out):
            warnings.append(f".indd 미생성: {os.path.basename(indd_out)}")
        if not os.path.exists(pdf_out):
            warnings.append(f"PDF 미생성: {os.path.basename(pdf_out)}")

        log_path = settings.get("log_path", "")
        warn_count = 0
        if log_path and os.path.exists(log_path):
            try:
                content = open(log_path, encoding="utf-8", errors="ignore").read()
                warn_count = len(re.findall(r"\[경고\]|\[오류\]", content))
                if warn_count > 0:
                    warnings.append(f"JSX 경고/오류 {warn_count}건 (로그 확인)")
            except OSError:
                pass

        ok = os.path.exists(pdf_out) and len(warnings) == 0

        return {
            "ok": ok,
            "overflow": 0,
            "stories": {},
            "pdf_path": pdf_out if os.path.exists(pdf_out) else None,
            "pdf_paths": [pdf_out] if os.path.exists(pdf_out) else [],
            "warnings": warnings,
        }
