import json
import os
import re
import shutil
import unicodedata

from core.base import BaseEngine, safe_copy_indd, safe_copy
from core.paths import resolve_config
from engines.workbook.parser import parse_manuscript_folder
from engines.final.extractor import _gdrive_safe_copy

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
# JSX는 워크북 엔진의 run.jsx 공유 (동일한 STEP 처리 로직)
_JSX_TEMPLATE = os.path.join(os.path.dirname(_DIR), "workbook", "jsx", "run.jsx")

# 모듈 로드 시점에 JSX 템플릿을 1회만 읽어 메모리에 캐시 (iCloud dataless EDEADLK 회피)
with open(_JSX_TEMPLATE, encoding="utf-8") as _f:
    _JSX_TEMPLATE_CONTENT = _f.read()

_PATH_KEYS = ["indd_output_dir", "indd_original", "ebs_base"]


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _norm_filename(name_or_base):
    """파일명 정규화 — NFC + lower + 공백 제거 + 시작부 "<digits><punct>"
    를 "<digits>." 으로 통일. "7,", "7)", "7." 모두 동치 취급.
    extension 포함된 경로는 splitext 후 호출할 것."""
    s = unicodedata.normalize("NFC", name_or_base.replace(" ", "").lower())
    s = re.sub(r'^(\d+)[.,)]+', r'\1.', s)
    return s


def _is_step3_name(name_nfc: str) -> bool:
    """파일명에 Step3/스텝3 토큰 또는 '수능특강 N강' 본문 패턴 포함 여부."""
    if re.search(r'(?:[Ss]tep\s*3|스텝\s*3)', name_nfc):
        return True
    # "2027 수능특강 13강.docx" 같은 본문 자료를 Step3 본문으로 사용
    if re.search(r'수능특강\s*\d+강\.(?:docx|hwpx?)$', name_nfc):
        return True
    return False


def _is_answer_or_explanation(name_nfc: str) -> bool:
    """파일명에 정답/해설/답지 토큰이 포함되어 있는지."""
    return ("정답" in name_nfc) or ("해설" in name_nfc) or ("답지" in name_nfc)


class SuneungteukgangWorkbookEngine(BaseEngine):
    """EBS 수능특강 영어 워크북 조판 엔진."""

    @property
    def material_id(self) -> str:
        return "suneungteukgang_workbook"

    @property
    def display_name(self) -> str:
        return "수능특강 워크북"

    @property
    def description(self) -> str:
        return "EBS 수능특강 영어 워크북 조판 자동화"

    @property
    def subject_prefix(self) -> str:
        return "수능특강워크북"

    @property
    def template_name(self) -> str:
        return "typeset_suneungteukgang_workbook.html"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {
                    "key": "manuscripts",
                    "label": "추가 원고 파일 (선택)",
                    "required": False,
                    "multiple": True,
                    "accept": ".docx,.hwp,.hwpx",
                },
            ]
        }

    # ── 폴더 탐색 API용 헬퍼 ────────────────────────────────────────────

    @staticmethod
    def _series_path():
        cfg = _load_config()
        base = os.path.join(cfg["ebs_base"], cfg["fixed_series"])
        subdir = cfg.get("series_subdir", "")
        if subdir:
            base = os.path.join(base, subdir)
        return base

    @staticmethod
    def list_units():
        """수능특강 영어 워크북 폴더 안의 단원(N강 워크북) 목록."""
        cfg = _load_config()
        base = SuneungteukgangWorkbookEngine._series_path()
        excludes = set(cfg.get("exclude_folders", []))
        if not os.path.isdir(base):
            return []

        def _unit_sort_key(folder):
            m = re.search(r'(\d+)', folder)
            return (int(m.group(1)) if m else 9999, folder)

        result = []
        for raw in sorted(os.listdir(base)):
            name = _nfc(raw)
            stripped = name.strip()
            if stripped.startswith(".") or stripped in excludes:
                continue
            full = os.path.join(base, raw)
            if not os.path.isdir(full):
                continue
            if "워크북" not in stripped:
                continue
            # "변형문제" 폴더 제외
            if "변형문제" in stripped:
                continue
            m = re.match(r'(.+?)\s*워크북\s*$', stripped)
            label = m.group(1).strip() if m else stripped
            result.append({"folder": stripped, "label": label})
        result.sort(key=lambda x: _unit_sort_key(x["folder"]))
        return result

    @staticmethod
    def list_files(unit_folder):
        """단원 폴더 안의 원고 파일 목록 + 사용 여부 표시."""
        cfg = _load_config()
        unit_path = os.path.join(SuneungteukgangWorkbookEngine._series_path(), unit_folder)
        if not os.path.isdir(unit_path):
            return {"workbook_dir": None, "files": []}

        file_map = cfg.get("manuscript_file_map", {})
        used_files = set()

        def _sim_find(all_names, expected_filename):
            """엄격 매칭 — 정규화된 베이스명이 같을 때만 매칭. 확장자 차이 허용.
            정규화: 공백 제거, 소문자, 시작부 숫자+punct 통일 ("7," == "7." == "7)")."""
            expected_base, expected_ext = os.path.splitext(expected_filename)
            norm_base = _norm_filename(expected_base)
            exact_same_ext = None
            ext_diff = None
            for fn in all_names:
                f_base, f_ext = os.path.splitext(fn)
                f_norm = _norm_filename(f_base)
                if f_norm != norm_base:
                    continue
                if f_ext.lower() == expected_ext.lower():
                    exact_same_ext = fn
                else:
                    ext_diff = fn
            return exact_same_ext or ext_diff

        all_names = []
        for raw in sorted(os.listdir(unit_path)):
            name = _nfc(raw)
            if name.startswith("."):
                continue
            full = os.path.join(unit_path, raw)
            if os.path.isfile(full):
                ext = os.path.splitext(name)[1].lower()
                if ext in (".docx", ".hwp", ".hwpx"):
                    all_names.append(name)

        for _key, expected in file_map.items():
            matched = _sim_find(all_names, expected)
            if matched:
                used_files.add(matched)

        alternatives = cfg.get("manuscript_file_alternatives", {})
        for alt_name, target_name in alternatives.items():
            if target_name not in used_files and alt_name in all_names:
                used_files.add(alt_name)

        # Step3 본문 후보 추가
        for fn in all_names:
            if _is_step3_name(fn) and not _is_answer_or_explanation(fn):
                used_files.add(fn)

        files = []
        for raw in sorted(os.listdir(unit_path)):
            name = _nfc(raw)
            if name.startswith("."):
                continue
            full = os.path.join(unit_path, raw)
            if os.path.isfile(full):
                ext = os.path.splitext(name)[1].lower()
                if ext in (".docx", ".hwp", ".hwpx"):
                    files.append({"name": name, "used": name in used_files})

        return {"workbook_dir": unit_path, "files": files}

    # ── 1단계: 원고 폴더 → content.json ─────────────────────────────────

    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        cfg = _load_config()

        series = cfg.get("fixed_series", "")
        unit = self._read_meta_str(job_dir, "lesson", "")
        unit_folder = self._read_meta_str(job_dir, "lesson_folder", "")

        grade = 0
        year = 0
        month = 0

        log(f"[파서] 수능특강 워크북: {series} / {unit}")

        manuscript_dir = os.path.join(job_dir, "uploads")
        os.makedirs(manuscript_dir, exist_ok=True)
        step3_dir = os.path.join(manuscript_dir, "Step3")
        os.makedirs(step3_dir, exist_ok=True)

        alternatives = cfg.get("manuscript_file_alternatives", {})

        # GDrive Stream EDEADLK 회피용 안전 복사
        def _safe_copy(src_path, dst_path):
            ok, err = _gdrive_safe_copy(src_path, dst_path, log=log)
            if not ok:
                raise RuntimeError(
                    f"GDrive 복사 실패: {os.path.basename(src_path)} -> "
                    f"{os.path.basename(dst_path)} ({err[:200]})"
                )

        unit_dir = self._read_meta_str(job_dir, "manuscript_folder", "")
        # manuscript_folder가 비어있고 lesson_folder만 있는 경우 (다중 선택 시 UI가 hidden 안 채움) → 자동 계산
        if not unit_dir or not os.path.isdir(unit_dir):
            lesson_folder = self._read_meta_str(job_dir, "lesson_folder", "")
            if lesson_folder:
                base = os.path.join(cfg["ebs_base"], cfg.get("fixed_series", ""))
                subdir = cfg.get("series_subdir", "")
                if subdir:
                    base = os.path.join(base, subdir)
                candidate = os.path.join(base, lesson_folder)
                if os.path.isdir(candidate):
                    unit_dir = candidate
                    log(f"[파서] manuscript_folder 자동 계산: {os.path.basename(unit_dir)}")
                elif os.path.isdir(base):
                    target_norm = _nfc(lesson_folder).strip()
                    for entry in os.listdir(base):
                        if _nfc(entry).strip() != target_norm:
                            continue
                        actual = os.path.join(base, entry)
                        if os.path.isdir(actual):
                            unit_dir = actual
                            log(f"[파서] manuscript_folder 자동 계산: '{entry}' (정규화 매칭: '{lesson_folder}')")
                            break
        if unit_dir and os.path.isdir(unit_dir):
            log(f"[파서] 단원 폴더: {os.path.basename(unit_dir)}")
            for raw in os.listdir(unit_dir):
                src = os.path.join(unit_dir, raw)
                name = _nfc(raw)
                if name.startswith("."):
                    continue
                if os.path.isfile(src):
                    ext = os.path.splitext(name)[1].lower()
                    if ext in (".docx", ".hwp", ".hwpx"):
                        # Step3 원고 (정답/해설/답지가 아닌 본문만)
                        if _is_step3_name(name) and not _is_answer_or_explanation(name):
                            _safe_copy(src, os.path.join(step3_dir, name))
                            continue
                        # Step3 정답지/해설지는 사용 안 함
                        if _is_step3_name(name) and _is_answer_or_explanation(name):
                            continue
                        dest_name = name
                        # 1) alternatives 명시적 매핑 우선
                        if name in alternatives:
                            target = alternatives[name]
                            target_path = os.path.join(manuscript_dir, target)
                            orig_path = os.path.join(unit_dir, target)
                            if not os.path.exists(target_path) and not os.path.exists(orig_path):
                                dest_name = target
                                log(f"[파서] 대체 파일명: {name} -> {target}")
                        else:
                            # 2) 정규화 매칭: file_map의 expected와 베이스명이 동치면
                            #    expected 이름으로 rename (예: "7, 영작배열" → "7. 영작배열" 오타 흡수)
                            cur_base = os.path.splitext(name)[0]
                            cur_ext  = os.path.splitext(name)[1].lower()
                            cur_norm = _norm_filename(cur_base)
                            file_map_local = cfg.get("manuscript_file_map", {})
                            for _key, expected_fn in file_map_local.items():
                                exp_base = os.path.splitext(expected_fn)[0]
                                exp_ext  = os.path.splitext(expected_fn)[1].lower()
                                if cur_norm != _norm_filename(exp_base):
                                    continue
                                if cur_ext != exp_ext and cur_ext not in (".docx", ".hwp", ".hwpx"):
                                    continue
                                if cur_norm == _norm_filename(cur_base) and name == expected_fn:
                                    break  # 이미 정확한 이름
                                tgt_path = os.path.join(manuscript_dir, expected_fn)
                                if not os.path.exists(tgt_path) and \
                                   not os.path.exists(os.path.join(unit_dir, expected_fn)):
                                    dest_name = expected_fn
                                    log(f"[파서] 정규화 매칭: {name} -> {expected_fn}")
                                break
                        _safe_copy(src, os.path.join(manuscript_dir, dest_name))
                elif os.path.isdir(src):
                    lower = name.lower()
                    if "step3" in lower or "스텝3" in _nfc(lower):
                        for raw2 in os.listdir(src):
                            src2 = os.path.join(src, raw2)
                            name2 = _nfc(raw2)
                            if name2.startswith(".") or not os.path.isfile(src2):
                                continue
                            ext2 = os.path.splitext(name2)[1].lower()
                            if ext2 in (".docx", ".hwp", ".hwpx"):
                                if _is_answer_or_explanation(name2):
                                    continue
                                _safe_copy(src2, os.path.join(step3_dir, name2))
            log(f"[파서] 원고 복사 완료")
        else:
            log(f"[파서] 단원 폴더 없음, 업로드 파일만 사용")

        # 추가 업로드 파일
        extra_files = uploaded_files.get("manuscripts", [])
        if isinstance(extra_files, list):
            for fpath in extra_files:
                fname = os.path.basename(fpath)
                if fname.startswith("manuscripts_"):
                    fname = fname[len("manuscripts_"):]
                fname_nfc = _nfc(fname)
                is_step3 = (
                    (_is_step3_name(fname_nfc) and not _is_answer_or_explanation(fname_nfc))
                    or "번.hwp" in fname_nfc or "번.hwpx" in fname_nfc
                    or "번.docx" in fname_nfc
                )
                if is_step3:
                    dest = os.path.join(step3_dir, fname)
                else:
                    dest = os.path.join(manuscript_dir, fname)
                if fpath != dest:
                    safe_copy(fpath, dest)

        log(f"[파서] 파싱 시작")
        data = parse_manuscript_folder(manuscript_dir, cfg, grade, year, month, log)

        data["workbook_type"] = "EBS"  # JSX의 stepStoryMap 분기와 호환
        data["series"] = series
        data["unit"] = unit

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        meta = {
            "grade": data.get("grade"),
            "year": data.get("year"),
            "month": data.get("month"),
            "step_files": {},
        }
        for key, step_data in data.get("steps", {}).items():
            step_path = os.path.join(job_dir, f"step_{key}.json")
            with open(step_path, "w", encoding="utf-8") as f:
                json.dump(step_data, f, ensure_ascii=False)
            meta["step_files"][key] = step_path

        meta_path = os.path.join(job_dir, "content_meta.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)

        step_count = len(data.get("steps", {}))
        log(f"[파서] 완료: {step_count}개 STEP")

        return json_path

    # ── 2단계: JSX 준비 ─────────────────────────────────────────────────
    # 수능특강은 두 원본 .indd를 사용:
    #  - 분석본: step1_a1, a2, c1, c2 / step2_a1, a1_btm, c2 (1~7번)
    #  - 문제본: step3 (실전문제)
    # prepare_jsx에서 두 settings + 두 jsx 만들고, run_indesign에서 순차 실행.

    # 분석본 .indd의 페이지/마커 매핑 (사용자가 만든 [원본]고3_수능특강(분석) 기준)
    _ANALYSIS_STEP_STORY_MAP = {
        "step1_a1":     {"page": "6",  "marker": "어휘선택"},
        "step1_a2":     {"page": "8",  "marker": "본문 O/X"},
        "step1_c1":     {"page": "10", "marker": "문장배열"},
        "step1_c2":     {"page": "12", "marker": "빈칸어휘"},
        "step2_a1":     {"page": "16", "marker": "어법선택"},
        "step2_a1_btm": {"page": "16", "marker": "어법선택", "rank": 2},
        "step2_c2":     {"page": "20", "marker": "영작배열"},
    }
    # 문제본 .indd의 step3 매핑 — master prefix "D"의 첫 메인 스토리(실전문제)
    _PROBLEM_STEP_STORY_MAP = {
        "step3": {"master": "D"},
    }

    def _copy_indd(self, src_path, dst_dir, base_name, log):
        """원본 .indd → dst_dir/<base_name>.indd 로 안전 복사. 충돌 시 _2, _3 ..."""
        dst_path = os.path.join(dst_dir, f"{base_name}.indd")
        if os.path.exists(dst_path) and os.path.getsize(dst_path) > 0:
            base_p, ext_p = os.path.splitext(dst_path)
            n = 2
            while os.path.exists(f"{base_p}_{n}{ext_p}") and \
                  os.path.getsize(f"{base_p}_{n}{ext_p}") > 0:
                n += 1
            dst_path = f"{base_p}_{n}{ext_p}"
        ok, err = _gdrive_safe_copy(src_path, dst_path, log=log)
        if not ok:
            raise RuntimeError(
                f"내지 원본 복사 실패: {os.path.basename(src_path)} ({err[:200]})"
            )
        log(f"[내지] 원본 복사: {os.path.basename(dst_path)}")
        return dst_path

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = _load_config()

        series = cfg.get("fixed_series", "")
        unit = self._read_meta_str(job_dir, "lesson", "")
        unit_short = re.sub(r'\s+', '', unit) if unit else "단원"

        # 두 원본 indd
        indd_originals = cfg.get("indd_original", {})
        if not isinstance(indd_originals, dict):
            raise ValueError("indd_original은 {analysis, problem} 객체여야 함")

        os.makedirs(cfg["indd_output_dir"], exist_ok=True)

        # 두 단계 메타: (라벨, 파일명 prefix, 원본 키, stepStoryMap)
        stages = [
            ("analysis", f"EBS_수능특강_{unit_short}_분석", indd_originals.get("analysis"),
             self._ANALYSIS_STEP_STORY_MAP),
            ("problem",  f"EBS_수능특강_{unit_short}_문제", indd_originals.get("problem"),
             self._PROBLEM_STEP_STORY_MAP),
        ]

        first_jsx_path = None
        for stage_label, out_base, src, story_map in stages:
            if not src or not os.path.exists(src):
                raise FileNotFoundError(
                    f"{stage_label} 원본 indd 없음: {src}"
                )
            indd_path = self._copy_indd(src, cfg["indd_output_dir"], out_base, log)
            settings_path = os.path.join(job_dir, f".settings_{stage_label}.json")
            settings = {
                "json_path": json_path,
                "indd_path": indd_path,
                "output_dir": job_dir,
                "grade": 0,
                "year": 0,
                "month": 0,
                "workbook_type": "EBS",
                "series": series,
                "unit": unit,
                "stage": stage_label,
                "stepStoryMap": story_map,
            }
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, ensure_ascii=False)

            jsx_src = re.sub(
                r'var settingsPath\s*=\s*"[^"]*";',
                f'var settingsPath = "{settings_path}";',
                _JSX_TEMPLATE_CONTENT,
                count=1,
            )
            jsx_path = os.path.join(job_dir, f"run_{stage_label}.jsx")
            with open(jsx_path, "w", encoding="utf-8") as f:
                f.write(jsx_src)
            log(f"[JSX] {stage_label} 준비: {os.path.basename(jsx_path)}")
            if first_jsx_path is None:
                first_jsx_path = jsx_path

        log(f"[JSX] 준비 완료 (분석본 + 문제본 2단계)")
        return first_jsx_path

    # ── InDesign 실행 — 두 단계 순차 ─────────────────────────────────────
    # app.py의 _run_pipeline은 engine.run_indesign이 정의되어 있으면 그걸 호출
    # (기본 단일 jsx 실행 대신).
    def run_indesign(self, job_dir: str, log) -> None:
        from core.indesign import runner as indesign

        log_filename = "조판_로그.txt"
        # 두 단계: analysis(1~7) → problem(step3)
        for stage_label, stage_kor in [("analysis", "분석본"), ("problem", "문제본")]:
            jsx_path = os.path.join(job_dir, f"run_{stage_label}.jsx")
            if not os.path.exists(jsx_path):
                log(f"[{stage_kor}] JSX 없음, 건너뜀: {jsx_path}")
                continue
            log(f"━━━ {stage_kor} 조판 시작 ━━━")
            log_file = os.path.join(job_dir, log_filename)
            indesign.run_jsx(
                jsx_path, log,
                poll_log_path=log_file,
                timeout=getattr(self, "jsx_timeout", 300),
            )
            log(f"━━━ {stage_kor} 조판 완료 ━━━")

    # ── 다중 강 통합 merge ─────────────────────────────────────────────
    # 강별 indd가 모두 만들어진 후 호출. 첫 강 indd를 base로 다른 강의 spread를
    # 끝에 duplicate하여 한 파일로 합친다. 분석본/문제본 각각.
    @staticmethod
    def merge_lessons(lesson_labels, log) -> dict:
        """lesson_labels: ['21강', '22강', ...] (UI에서 선택된 순서대로)
        Returns: {'analysis': merged_path or None, 'problem': merged_path or None,
                  'errors': [...]}
        """
        cfg = _load_config()
        out_dir = cfg["indd_output_dir"]
        if len(lesson_labels) < 2:
            return {"analysis": None, "problem": None,
                    "errors": ["통합할 강이 2개 미만입니다."]}

        def _strip_dot(label):
            return re.sub(r'\s+', '', label)

        merged_results = {"analysis": None, "problem": None, "errors": []}

        # 통합 파일명: "EBS_수능특강_21-23강_분석.indd" (한글+~ 조합이 InDesign saveAs에서
        # 가끔 silent fail하므로 `-`로 결합)
        first = _strip_dot(lesson_labels[0])
        last = _strip_dot(lesson_labels[-1])
        if first == last:
            merged_label = first
        elif len(lesson_labels) <= 4:
            merged_label = "-".join(_strip_dot(l) for l in lesson_labels)
        else:
            merged_label = f"{first}-{last}"

        for stage_label, stage_kor in [("분석", "분석본"), ("문제", "문제본")]:
            # 강별 source indd 경로 (다른 _N 사본은 가장 최신 것 자동 선택)
            src_paths = []
            missing = []
            for label in lesson_labels:
                short = _strip_dot(label)
                # 가장 최신 사본 찾기 — 정확명 우선, 없으면 _N 사본
                exact = os.path.join(out_dir, f"EBS_수능특강_{short}_{stage_label}.indd")
                candidates = [exact] if os.path.exists(exact) else []
                # _2, _3 ... 사본도 검색
                base_p = os.path.join(out_dir, f"EBS_수능특강_{short}_{stage_label}")
                n = 2
                while os.path.exists(f"{base_p}_{n}.indd"):
                    candidates.append(f"{base_p}_{n}.indd")
                    n += 1
                if not candidates:
                    missing.append(f"{label} {stage_kor}")
                    continue
                # 가장 최신 (mtime)
                candidates.sort(key=lambda p: os.path.getmtime(p), reverse=True)
                src_paths.append(candidates[0])

            if missing:
                merged_results["errors"].append(
                    f"{stage_kor} 통합 실패 — 원본 indd 누락: {', '.join(missing)}"
                )
                continue

            # 통합 출력 경로 (충돌 시 _2)
            merged_path = os.path.join(out_dir,
                f"EBS_수능특강_{merged_label}_{stage_label}.indd")
            if os.path.exists(merged_path):
                base_p, ext_p = os.path.splitext(merged_path)
                k = 2
                while os.path.exists(f"{base_p}_{k}{ext_p}"):
                    k += 1
                merged_path = f"{base_p}_{k}{ext_p}"

            log(f"[{stage_kor} 통합] {len(src_paths)}개 강 → "
                f"{os.path.basename(merged_path)}")

            # JSX merge 스크립트 생성
            jsx = SuneungteukgangWorkbookEngine._build_merge_jsx(
                src_paths, merged_path
            )
            jsx_path = os.path.join(out_dir, f"_merge_{stage_label}.jsx")
            with open(jsx_path, "w", encoding="utf-8") as f:
                f.write(jsx)

            # InDesign 실행
            from core.indesign import runner as indesign
            try:
                indesign.run_jsx(jsx_path, log, poll_log_path=None, timeout=600)
            except Exception as e:
                merged_results["errors"].append(
                    f"{stage_kor} 통합 InDesign 실행 실패: {e}"
                )
                continue

            if os.path.exists(merged_path):
                merged_results[stage_label.replace("분석", "analysis").replace("문제", "problem")] = merged_path
                log(f"[{stage_kor} 통합] 완료: {os.path.basename(merged_path)}")
            else:
                merged_results["errors"].append(
                    f"{stage_kor} 통합 결과 파일 미생성"
                )

        return merged_results

    @staticmethod
    def _build_merge_jsx(src_paths, merged_path):
        """src_paths의 첫 indd를 merged_path로 복사 후, 나머지 indd의 spread를
        끝에 duplicate하여 한 파일로 합치는 JSX 스크립트 문자열 생성."""
        # ExtendScript 문자열 안전 escape
        def esc(s):
            return s.replace("\\", "\\\\").replace('"', '\\"')
        first = esc(src_paths[0])
        rest = src_paths[1:]
        rest_js = ",\n        ".join(f'"{esc(p)}"' for p in rest)
        merged_esc = esc(merged_path)
        # 디버그 로그 파일 경로 (한글 회피 위해 /tmp 사용)
        log_path = "/tmp/_merge_jsx_log.txt"
        return (
            "#target indesign\n"
            '    var settingsPath = "/tmp/_merge_dummy.json";\n'
            "(function() {\n"
            f'    var firstSrc = "{first}";\n'
            f'    var mergedPath = "{merged_esc}";\n'
            f'    var restSrcs = [\n        {rest_js}\n    ];\n'
            f'    var logFile = File("{log_path}");\n'
            '    function L(s) { try { logFile.encoding = "UTF-8"; logFile.open("a"); logFile.writeln(s); logFile.close(); } catch(_){} }\n'
            '    L("--- merge start ---");\n'
            "    var firstFile = File(firstSrc);\n"
            '    L("first exists: " + firstFile.exists);\n'
            "    if (!firstFile.exists) return;\n"
            "    var dst = app.open(firstFile);\n"
            '    L("dst opened, init pages: " + dst.pages.length);\n'
            "    var mergedFile = File(mergedPath);\n"
            "    try { dst.save(mergedFile); } catch(e) { L('saveAs err: ' + e); return; }\n"
            "    try { L('after saveAs, dst.fullName: ' + dst.fullName.fsName); } catch(_){}\n"
            "    for (var i = 0; i < restSrcs.length; i++) {\n"
            "        var srcFile = File(restSrcs[i]);\n"
            "        if (!srcFile.exists) { L('src miss: ' + restSrcs[i]); continue; }\n"
            "        var src = app.open(srcFile);\n"
            "        var spreadCount = src.spreads.length;\n"
            "        L('append ' + spreadCount + ' spreads from src#' + i);\n"
            "        var spreads = src.spreads.everyItem().getElements();\n"
            "        var dupOk = 0, dupFail = 0;\n"
            "        for (var s = 0; s < spreads.length; s++) {\n"
            "            try { spreads[s].duplicate(LocationOptions.AT_END, dst); dupOk++; }\n"
            "            catch(e) { dupFail++; L('  dup err: ' + e); }\n"
            "        }\n"
            "        L('  dupOk=' + dupOk + ' dupFail=' + dupFail + ' dst.pages=' + dst.pages.length);\n"
            "        src.close(SaveOptions.NO);\n"
            "    }\n"
            "    try { dst.save(); L('dst saved, final pages: ' + dst.pages.length); } catch(e) { L('save err: ' + e); }\n"
            "    try { dst.close(SaveOptions.YES); L('dst closed OK'); } catch(e) { L('close err: ' + e); }\n"
            '    L("--- merge end ---");\n'
            "})();\n"
        )

    # ── 3단계: 검수 ─────────────────────────────────────────────────────

    def verify(self, job_dir: str, log) -> dict:
        cfg = _load_config()
        max_overflow = cfg["verify"]["max_overflow"]

        log_path = os.path.join(job_dir, cfg["log_filename"])
        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "error": "로그 파일 없음", "warnings": []}

        content = open(log_path, encoding="utf-8", errors="ignore").read()

        step_m = re.search(r"STEP완료:\s*(\d+)개", content)
        actual_steps = int(step_m.group(1)) if step_m else None

        overflow_m = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(overflow_m.group(1)) if overflow_m else None

        style_warnings = re.findall(r"스타일불일치:\s*(.+)", content)

        pdf_path = None
        if re.search(r"PDF:\s*성공", content):
            for fname in os.listdir(job_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_path = os.path.join(job_dir, fname)
                    break

        warnings = list(style_warnings)
        if actual_steps is None:
            warnings.append("STEP 완료 수 확인 불가")
        if overflow is None:
            warnings.append("오버플로우 수치 확인 불가")
        elif overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")

        ok = (overflow is not None and overflow <= max_overflow
              and len(style_warnings) == 0
              and pdf_path is not None)

        result = {
            "ok": ok,
            "overflow": overflow,
            "steps_completed": actual_steps,
            "pdf_path": pdf_path,
            "warnings": warnings,
        }

        status = "✅ 통과" if ok else f"⚠️ 경고 {len(warnings)}건"
        log(f"[검수] {status} | 오버플로우: {overflow}개 | PDF: {'있음' if pdf_path else '없음'}")
        return result

    # ── 유틸리티 ─────────────────────────────────────────────────────────

    def _read_meta_str(self, job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p).read().strip() if os.path.exists(p) else default
