import json
import os
import re
import shutil
import unicodedata

from core.base import BaseEngine, safe_copy_indd, safe_copy
from core.paths import resolve_config
from engines.workbook.parser import parse_manuscript_folder
from engines.final.extractor import _gdrive_safe_copy

from engines.workbook_v2.routing import pdf_routes_to_step3 as _pdf_step3

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
# JSX는 기존 워크북 엔진의 run.jsx 공유
_JSX_TEMPLATE = os.path.join(os.path.dirname(_DIR), "workbook", "jsx", "run.jsx")

# 모듈 로드 시점에 JSX 템플릿을 1회만 읽어 메모리에 캐시.
# per-request 파일 I/O 제거 → iCloud Documents의 dataless 파일에서 발생하는
# launchd 컨텍스트 EDEADLK(Errno 11) 회피. 템플릿 변경 시 Flask 재시작 필요.
with open(_JSX_TEMPLATE, encoding="utf-8") as _f:
    _JSX_TEMPLATE_CONTENT = _f.read()

_PATH_KEYS = ["indd_output_dir", "indd_original", "ebs_base"]


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _is_step3_name(name_nfc: str) -> bool:
    """파일명에 Step3/스텝3 토큰이 포함되어 있는지 (확장자 무관)."""
    return bool(re.search(r'(?:[Ss]tep\s*3|스텝\s*3)', name_nfc))


def _is_answer_or_explanation(name_nfc: str) -> bool:
    """파일명에 정답/해설/답지 토큰이 포함되어 있는지."""
    return ("정답" in name_nfc) or ("해설" in name_nfc) or ("답지" in name_nfc)


class EbsWorkbookEngine(BaseEngine):
    """EBS 리딩파워(유형편 완성) 등 EBS 시리즈 워크북 조판 엔진.

    config/단원 폴더 구조는 클래스 훅으로 열어 둔다 — 같은 원고 수집
    로직을 다른 EBS 시리즈(리딩파워 유형편 기본)가 재사용한다:
      · CONFIG_PATH        : 엔진별 config.json
      · _resolve_workbook_dir: 단원 폴더 → 실제 원고 폴더
        (완성=단원 폴더 자신, 기본=그 아래 '워크북' 폴더)
    """

    CONFIG_PATH = _CONFIG_PATH

    @classmethod
    def _cfg(cls) -> dict:
        with open(cls.CONFIG_PATH, encoding="utf-8") as f:
            cfg = json.load(f)
        return resolve_config(cfg, _PATH_KEYS)

    @staticmethod
    def _alt_target(alternatives: dict, name_nfc: str):
        """대체 파일명 매핑 조회 — 공백/대소문자 차이를 무시한다.

        실물 원고는 같은 뜻의 파일명이 토씨만 다르게 온다
        (' Step2 A1 어법선택(문법 기본 문제).docx' 앞 공백, 'Step2 B1
        어법 OX 정답지.docx' 중간 공백). 정확 일치로만 보면 매핑이 조용히
        빗나가 그 스텝 원고가 통째로 빠진다.
        """
        def _key(n):
            return _nfc(n).replace(" ", "").lower()
        want = _key(name_nfc)
        for alt_name, target in alternatives.items():
            if _key(alt_name) == want:
                return target
        return None

    @classmethod
    def _is_step3_manuscript(cls, name_nfc: str) -> bool:
        """단원 폴더의 이 파일이 Step3(실전문제) 원고인가 — 이름 모양만
        본다 (정답/해설 여부는 호출부가 따로 판정). 파생 시리즈 확장점."""
        return _is_step3_name(name_nfc)

    @classmethod
    def _resolve_workbook_dir(cls, unit_path: str) -> str:
        """단원 폴더 안에서 원고가 실제로 놓인 폴더. 완성 시리즈는 단원
        폴더 자신 ('Unit 15 워크북/Step1 …')."""
        return unit_path

    @property
    def material_id(self) -> str:
        return "ebs_workbook"

    @property
    def display_name(self) -> str:
        return "리딩파워 워크북"

    @property
    def description(self) -> str:
        return "EBS 리딩파워(유형편 완성) 워크북 조판 자동화"

    @property
    def subject_prefix(self) -> str:
        return "리딩파워워크북"

    @property
    def template_name(self) -> str:
        return "typeset_ebs_workbook.html"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {
                    "key": "manuscripts",
                    "label": "추가 원고 파일 (선택 · PDF는 Step3만)",
                    "required": False,
                    "multiple": True,
                    "accept": ".docx,.hwp,.hwpx,.pdf",
                },
            ]
        }

    # ── 폴더 탐색 API용 헬퍼 ────────────────────────────────────────────

    @classmethod
    def _series_path(cls):
        cfg = cls._cfg()
        return os.path.join(cfg["ebs_base"], cfg["fixed_series"])

    @classmethod
    def list_units(cls):
        """리딩파워(고정 시리즈) 안의 워크북 단원 목록."""
        cfg = cls._cfg()
        base = cls._series_path()
        # 미러 ∪ GDrive 합집합 — 미러 단독 listdir 금지 (2026-08-07 사고).
        # 새로 만든 단원 폴더가 미러 동기화 전이면 UI 목록에서 통째로 사라진다.
        from engines.final.extractor import list_manuscript_entries
        excludes = set(cfg.get("exclude_folders", []))

        def _unit_sort_key(folder):
            # "Unit 1", "Unit 11 3, 4번" 등 → 첫 숫자 추출 후 자연 정렬
            m = re.search(r'\d+', folder)
            return (int(m.group()) if m else 9999, folder)

        result = []
        for name, full in list_manuscript_entries(base, None):
            stripped = name.strip()
            if stripped.startswith(".") or stripped in excludes:
                continue
            if not os.path.isdir(full):
                continue
            if "워크북" not in stripped:
                continue
            m = re.match(r'(.+?)\s*워크북\s*$', stripped)
            label = m.group(1).strip() if m else stripped
            # folder는 **실제 폴더명 그대로** (trim 금지) — GDrive에 끝에
            # 공백이 붙은 폴더가 있다('Unit 3 워크북 '). trim한 이름으로
            # 경로를 만들면 list_files가 폴더를 못 찾아 '원고 0개'가 된다.
            result.append({"folder": name, "label": label})
        result.sort(key=lambda x: _unit_sort_key(x["folder"]))
        return result

    @classmethod
    def list_files(cls, unit_folder):
        """단원 폴더 안의 원고 파일 목록 + 사용 여부 표시."""
        cfg = cls._cfg()
        unit_path = cls._resolve_workbook_dir(
            os.path.join(cls._series_path(), unit_folder))
        # 미러 redirect — Drive zombie 시 GDrive listdir EDEADLK 회피
        from engines.final.extractor import _resolve_local_mirror as _rlm
        unit_path = _rlm(unit_path, None)
        if not os.path.isdir(unit_path):
            return {"workbook_dir": None, "files": []}

        file_map = cfg.get("manuscript_file_map", {})
        used_files = set()  # NFC 정규화된 파일명

        def _sim_find(all_names, expected_filename):
            """엄격 매칭 — 베이스명이 정확히 같을 때만 매칭. 확장자 차이는 허용.
            본문/정답지 같이 베이스명이 다른 변형은 alternatives에서 명시적으로 처리한다."""
            expected_base, expected_ext = os.path.splitext(expected_filename)
            norm_base = unicodedata.normalize(
                "NFC", expected_base.replace(" ", "").lower()
            )
            exact_same_ext = None
            ext_diff = None
            for fn in all_names:
                f_base, f_ext = os.path.splitext(fn)
                f_norm = unicodedata.normalize(
                    "NFC", f_base.replace(" ", "").lower()
                )
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
        for fn in all_names:
            target_name = cls._alt_target(alternatives, fn)
            if target_name and target_name not in used_files:
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
                    used = (name in used_files) or (
                        cls._is_step3_manuscript(name)
                        and not _is_answer_or_explanation(name)
                    )
                    files.append({"name": name, "used": used})
            elif os.path.isdir(full):
                lower = name.lower()
                if "step3" in lower or "스텝3" in _nfc(lower):
                    for raw2 in sorted(os.listdir(full)):
                        name2 = _nfc(raw2)
                        if name2.startswith("."):
                            continue
                        ext2 = os.path.splitext(name2)[1].lower()
                        if ext2 in (".docx", ".hwp", ".hwpx"):
                            used2 = not _is_answer_or_explanation(name2)
                            files.append({"name": f"[Step3] {name2}", "used": used2})

        return {"workbook_dir": unit_path, "files": files}

    # ── 1단계: 원고 폴더 → content.json ─────────────────────────────────

    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        cfg = self._cfg()

        # 시리즈는 고정 (Reading Power 유형편(완성)). UI에서는 단원만 선택.
        series = cfg.get("fixed_series", "")
        unit = self._read_meta_str(job_dir, "lesson", "")  # UI 호환을 위해 lesson 키 사용
        unit_folder = self._read_meta_str(job_dir, "lesson_folder", "")

        # EBS는 시험 연도/월/학년 개념이 없음 → 더미값
        grade = 0
        year = 0
        month = 0

        log(f"[파서] EBS 워크북: {series} / {unit}")

        # 원고 폴더 결정
        manuscript_dir = os.path.join(job_dir, "uploads")
        os.makedirs(manuscript_dir, exist_ok=True)
        step3_dir = os.path.join(manuscript_dir, "Step3")
        os.makedirs(step3_dir, exist_ok=True)

        alternatives = cfg.get("manuscript_file_alternatives", {})

        # GDrive Stream EDEADLK 회피용 안전 복사 — 7-경로 syscall 폴백 + 백오프
        def _safe_copy(src_path, dst_path):
            ok, err = _gdrive_safe_copy(src_path, dst_path, log=log)
            if not ok:
                raise RuntimeError(
                    f"GDrive 복사 실패: {os.path.basename(src_path)} -> "
                    f"{os.path.basename(dst_path)} ({err[:200]})"
                )

        # 1) 단원 폴더에서 파일 복사
        unit_dir = self._read_meta_str(job_dir, "manuscript_folder", "")
        # 미러 ∪ GDrive 합집합 — 미러 단독 listdir 금지 (2026-08-07 사고).
        # 미러 동기화 전에 추가·교체된 원고가 조용히 누락된다.
        from engines.final.extractor import list_manuscript_entries
        if unit_dir and os.path.isdir(unit_dir):
            log(f"[파서] 단원 폴더: {os.path.basename(unit_dir)}")
            unit_entries = list_manuscript_entries(unit_dir, log)
            unit_names = {n for n, _ in unit_entries}
            step3_dirs = []     # 단원 폴더에서 본 Step3 하위폴더 이름
            for name, src in unit_entries:
                if name.startswith("."):
                    continue
                if os.path.isfile(src):
                    ext = os.path.splitext(name)[1].lower()
                    if ext in (".docx", ".hwp", ".hwpx"):
                        # Step3 원고 (정답/해설/답지가 아닌 본문만 Step3 폴더로)
                        if self._is_step3_manuscript(name) \
                                and not _is_answer_or_explanation(name):
                            _safe_copy(src, os.path.join(step3_dir, name))
                            continue
                        # Step3 정답지/해설지는 사용하지 않음 (Step3 본문에 endnote로 합쳐져 있음)
                        if self._is_step3_manuscript(name) \
                                and _is_answer_or_explanation(name):
                            continue
                        # 그 외 일반 파일은 모두 복사 (C2 정답지 같이 풀이용 답지 포함).
                        # 대체 파일명 매핑은 기대 파일명이 없는 경우에만 발동.
                        dest_name = name
                        target = self._alt_target(alternatives, name)
                        if target:
                            target_path = os.path.join(manuscript_dir, target)
                            # 원본 폴더 존재 여부는 합집합 목록으로 판정
                            # (미러/GDrive 어느 쪽에 있어도 '있음')
                            if not os.path.exists(target_path) \
                                    and _nfc(target) not in unit_names:
                                dest_name = target
                                log(f"[파서] 대체 파일명: {name} -> {target}")
                        _safe_copy(src, os.path.join(manuscript_dir, dest_name))
                elif os.path.isdir(src):
                    lower = name.lower()
                    if "step3" in lower or "스텝3" in _nfc(lower):
                        step3_dirs.append(name)
                        # 하위 폴더 목록은 **GDrive(정본)** 로 연다. src는
                        # 같은 이름이 미러에 있으면 미러 경로인데, 미러가
                        # 동기화 도중이면 그 폴더가 비어 보인다 —
                        # 2026-09-05 실사고(job 52fecafe): 미러
                        # 'Unit 4 …/워크북/Step3'에 .rsync-partial만 있어
                        # STEP3 원고가 0개로 수집되고 '0단락 배치'로 조용히
                        # 조판됐다. 미러는 GDrive를 못 읽을 때만 폴백.
                        sub = os.path.join(unit_dir, name)
                        if not os.path.isdir(sub):
                            sub = src
                        for name2, src2 in list_manuscript_entries(sub, log):
                            if name2.startswith(".") or not os.path.isfile(src2):
                                continue
                            ext2 = os.path.splitext(name2)[1].lower()
                            if ext2 in (".docx", ".hwp", ".hwpx", ".pdf"):
                                if _is_answer_or_explanation(name2):
                                    continue
                                _safe_copy(src2, os.path.join(step3_dir, name2))
            log(f"[파서] 원고 복사 완료")
            # 침묵 유실 금지: Step3 폴더가 있는데 원고를 하나도 못 담았으면
            # 여기서 멈춘다. 그냥 두면 '0단락 배치'로 STEP3만 빠진 완제품이
            # 성공으로 남는다 (2026-09-05 job 52fecafe 실사고).
            if step3_dirs and not [
                    f for f in os.listdir(step3_dir)
                    if not f.startswith(".")]:
                raise RuntimeError(
                    f"STEP3 원고 0개 — 단원 폴더의 '{step3_dirs[0]}' 폴더에서 "
                    f"원고를 읽지 못했습니다. 구글 드라이브 동기화가 끝났는지 "
                    f"확인하고 다시 실행하거나, STEP3 원고를 '추가 원고 파일'로 "
                    f"직접 올려 주세요.")

        # 2) 추가 업로드 파일 처리
        extra_files = uploaded_files.get("manuscripts", [])
        if isinstance(extra_files, list):
            for fpath in extra_files:
                fname = os.path.basename(fpath)
                if fname.startswith("manuscripts_"):
                    fname = fname[len("manuscripts_"):]
                fname_nfc = _nfc(fname)
                is_step3 = (
                    (self._is_step3_manuscript(fname_nfc)
                     and not _is_answer_or_explanation(fname_nfc))
                    or "번.hwp" in fname_nfc or "번.hwpx" in fname_nfc
                    or "번.docx" in fname_nfc
                    or _pdf_step3(fname_nfc)   # PDF 는 Step3 원고로만 (2026-09-12)
                )
                if is_step3:
                    dest = os.path.join(step3_dir, fname)
                else:
                    dest = os.path.join(manuscript_dir, fname)
                if fpath != dest:
                    safe_copy(fpath, dest)

        log(f"[파서] 파싱 시작")
        data = parse_manuscript_folder(manuscript_dir, cfg, grade, year, month, log)

        # EBS 메타 추가
        data["workbook_type"] = "EBS"
        data["series"] = series
        data["unit"] = unit

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        # Split into per-step files
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

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = self._cfg()

        series = cfg.get("fixed_series", "")
        unit = self._read_meta_str(job_dir, "lesson", "")

        # 출력 파일명: "EBS_리딩파워_{단원}_전체.indd"
        unit_short = re.sub(r'\s+', '', unit) if unit else "단원"
        out_name = f"EBS_리딩파워_{unit_short}_전체.indd"
        indd_path = os.path.join(cfg["indd_output_dir"], out_name)

        # 원본 indd 복사 — _gdrive_safe_copy로 EDEADLK 폴백 (7-경로 syscall + 백오프)
        src = cfg.get("indd_original", "")
        if isinstance(src, dict):
            src = src.get("모의고사", "")
        if os.path.exists(src):
            os.makedirs(os.path.dirname(indd_path), exist_ok=True)
            # 동일 이름 파일이 이미 존재하면 _2, _3 ... 붙여서 새 경로 사용
            if os.path.exists(indd_path) and os.path.getsize(indd_path) > 0:
                base_p, ext_p = os.path.splitext(indd_path)
                n = 2
                while os.path.exists(f"{base_p}_{n}{ext_p}") and \
                      os.path.getsize(f"{base_p}_{n}{ext_p}") > 0:
                    n += 1
                indd_path = f"{base_p}_{n}{ext_p}"
            ok, err = _gdrive_safe_copy(src, indd_path, log=log)
            if not ok:
                raise RuntimeError(
                    f"내지 원본 복사 실패: {os.path.basename(src)} ({err[:200]})"
                )
            log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            raise FileNotFoundError(f"내지 파일 없음: {indd_path}")

        # settings.json
        # EBS 리딩파워 원본 .indd의 페이지/마커 구조 (조사 결과 기반):
        #   p4 어휘 선택 / p7 본문 O/X / p10 문장 배열 / p13 빈칸 어휘
        #   p22 어법 수정 (서술형 + 객관식 같은 페이지) / p28 영작 배열 / p34~ 실전 문제(STEP3)
        ebs_step_story_map = {
            "step1_a1":     {"page": "4",  "marker": "어휘 선택"},
            "step1_a2":     {"page": "7",  "marker": "본문 O/X"},
            "step1_c1":     {"page": "10", "marker": "문장 배열"},
            "step1_c2":     {"page": "13", "marker": "빈칸 어휘"},
            "step2_a1":     {"page": "22", "marker": "어법 수정"},
            "step2_a1_btm": {"page": "22", "marker": "어법 수정", "rank": 2},
            "step2_c2":     {"page": "28", "marker": "영작 배열"},
        }
        settings_path = os.path.join(job_dir, ".settings.json")
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
            "stepStoryMap": ebs_step_story_map,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        # run.jsx 임시 사본 — 모듈 로드 시 캐시한 콘텐츠 사용 (EDEADLK 회피)
        jsx_src = re.sub(
            r'var settingsPath\s*=\s*"[^"]*";',
            f'var settingsPath = "{settings_path}";',
            _JSX_TEMPLATE_CONTENT,
            count=1,
        )

        jsx_path = os.path.join(job_dir, "run.jsx")
        with open(jsx_path, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        log(f"[JSX] 준비 완료: {os.path.basename(indd_path)}")
        return jsx_path

    # ── 3단계: 검수 ─────────────────────────────────────────────────────

    def verify(self, job_dir: str, log) -> dict:
        cfg = self._cfg()
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
