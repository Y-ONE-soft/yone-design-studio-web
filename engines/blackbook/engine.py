import json
import os
import re
import shutil

from core.base import BaseEngine, safe_copy_indd
from core.paths import resolve_config
from engines.blackbook.kind_parser import classify_filename, parse_by_kind

_SECTION_KEYS = (
    "part1_problem", "part1_vocab", "part2_problem",
    "part1_answer",  "part2_answer",
)

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(_DIR, "jsx", "run.jsx")

_SETTINGS_PATH_MARKER = '__SETTINGS_PATH__'

_PATH_KEYS = ["indd_output_dir", "indd_original"]


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _make_indd_path(cfg: dict, school: str, issue_num: str) -> str:
    """학교 + 번호로 내지 파일 경로 생성. 예: 배재1_블랙북03_내지.indd"""
    num = issue_num.zfill(2)
    prefix = cfg["indd_name_prefix"]
    filename = f"{school}_{prefix}{num}_내지.indd"
    return os.path.join(cfg["indd_output_dir"], filename)


class BlackbookEngine(BaseEngine):

    jsx_timeout = 1200  # InDesign 조판+저장+PDF 내보내기 최대 20분

    @property
    def material_id(self) -> str:
        return "blackbook"

    @property
    def display_name(self) -> str:
        return "블랙북"

    @property
    def description(self) -> str:
        return "프리미엄북 블랙북 조판 자동화 (PART1 문제·어휘 + PART2 문제 + 해설)"

    @property
    def subject_prefix(self) -> str:
        return "블랙북"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {
                    "key": "manuscript",
                    "label": "문제 원고 (PART1 문제·어휘, PART2 문제 — 여러 파일)",
                    "required": True,
                    "multiple": True,
                    "accept": ".docx,.hwpx,.hwp",
                },
                {
                    "key": "answers",
                    "label": "해설 원고 (PART1·PART2 해설 — 여러 파일)",
                    "required": False,
                    "multiple": True,
                    "accept": ".docx,.hwpx,.hwp",
                },
            ]
        }

    # ── 1단계: 다중 docx/hwpx → content.json ──────────────────────────

    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        """파일명 키워드로 5종 분류 → 종류별 파서 호출 → sections dict 생성."""

        def _as_list(v):
            if v is None: return []
            if isinstance(v, str): return [v]
            return list(v)

        manuscript_files = _as_list(uploaded_files.get("manuscript"))
        answer_files     = _as_list(uploaded_files.get("answers"))

        all_files = manuscript_files + answer_files
        if not all_files:
            raise ValueError("업로드된 원고가 없습니다.")

        sections = {k: [] for k in _SECTION_KEYS}
        unmatched = []

        for fpath in all_files:
            if not os.path.exists(fpath):
                log(f"[파서] 파일 없음 (무시): {fpath}")
                continue
            # 업로드 접두사 제거하여 분류 (manuscript_xxx, answers_xxx)
            basename = os.path.basename(fpath)
            cleaned = basename
            for prefix in ("manuscript_", "answers_"):
                if cleaned.startswith(prefix):
                    cleaned = cleaned[len(prefix):]
                    break
            kind = classify_filename(cleaned)
            if kind is None:
                unmatched.append(basename)
                # 배치 G (W37): 반침묵 강등 가시화 — [경고] 승격 + 판정 근거
                # (동작 무변경: 종전과 동일하게 무시하되 로그만 상세화)
                from engines.blackbook.kind_parser import classify_filename_reason
                log(f"[경고] 파일명 분류 실패(원고 무시됨): {basename}")
                log(f"    근거: {classify_filename_reason(cleaned)}")
                continue
            try:
                sections[kind] = parse_by_kind(kind, fpath)
                log(f"[파서] {kind} ← {basename} ({len(sections[kind])}개 단위)")
            except Exception as e:
                log(f"[파서] {kind} 파싱 실패: {basename} — {e}")

        # 필수 영역 누락 검사 (문제 슬롯에서 최소 하나는 있어야)
        problem_present = any(
            sections[k] for k in ("part1_problem", "part2_problem")
        )
        if not problem_present:
            raise ValueError(
                "문제 원고가 누락됐거나 파일명에서 'Part1 문제' / 'Part2 문제' 키워드를 찾지 못했습니다. "
                f"전달된 파일: {[os.path.basename(p) for p in all_files]}"
            )

        data = {"sections": sections, "unmatched": unmatched}

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        counts = " | ".join(f"{k}={len(sections[k])}" for k in _SECTION_KEYS)
        log(f"[파서] 완료: {counts}")
        if unmatched:
            log(f"[파서] ⚠ 분류 실패 파일: {', '.join(unmatched)}")

        if not os.path.exists(json_path):
            raise RuntimeError("content.json 생성 실패")
        log(f"[파서] content.json 생성 완료 ({os.path.getsize(json_path):,} bytes)")
        return json_path

    # ── 2단계: JSX 임시 사본 생성 + settings.json 작성 ──────────────────

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = _load_config()

        issue_num = self._get_issue_num(job_dir)
        school = self._get_school(job_dir)
        indd_path = _make_indd_path(cfg, school, issue_num)
        log(f"[내지] 출력 파일: {os.path.basename(indd_path)}")

        # 원본 indd → 작업 경로로 복사
        src = cfg.get("indd_original", "")
        if os.path.exists(src):
            indd_path = safe_copy_indd(src, indd_path)
            log(f"[내지] 원본 복사 완료: {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            raise FileNotFoundError(f"내지 파일 없음: {indd_path}")

        # job별 .settings.json 작성
        settings_path = os.path.join(job_dir, ".settings.json")
        settings = {
            "json_path": json_path,
            "indd_path": indd_path,
            "output_dir": job_dir,
            "issue_num": issue_num,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        # run.jsx 임시 사본 — settingsPath 교체
        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()

        new_line = f'    var settingsPath = "{settings_path}";'
        if _SETTINGS_PATH_MARKER in jsx_src:
            jsx_src = jsx_src.replace(_SETTINGS_PATH_MARKER, new_line)
        else:
            jsx_src = re.sub(
                r'var settingsPath\s*=\s*"[^"]+";',
                f'var settingsPath = "{settings_path}";',
                jsx_src
            )

        jsx_copy = os.path.join(job_dir, "run.jsx")
        with open(jsx_copy, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        return jsx_copy

    def _get_issue_num(self, job_dir: str) -> str:
        p = os.path.join(job_dir, "issue_num.txt")
        return open(p).read().strip() if os.path.exists(p) else "01"

    def _get_school(self, job_dir: str) -> str:
        p = os.path.join(job_dir, "school.txt")
        return open(p).read().strip() if os.path.exists(p) else "학교미선택"

    # ── 3단계: 검수 ──────────────────────────────────────────────────────

    def verify(self, job_dir: str, log) -> dict:
        cfg = _load_config()
        expected_body   = cfg["verify"].get("expected_body_stories", 3)
        expected_answer = cfg["verify"].get("expected_answer_stories", 2)
        max_overflow    = cfg["verify"]["max_overflow"]

        log_path = os.path.join(job_dir, cfg["log_filename"])
        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "error": "로그 파일 없음", "warnings": []}

        content = open(log_path, encoding="utf-8", errors="ignore").read()

        body_m = re.search(r"본문조판완료:\s*(\d+)개", content)
        ans_m  = re.search(r"정답조판완료:\s*(\d+)개", content)
        actual_body   = int(body_m.group(1)) if body_m else None
        actual_answer = int(ans_m.group(1))  if ans_m  else None

        overflow_m = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(overflow_m.group(1)) if overflow_m else None

        pdf_path = None
        if re.search(r"PDF:\s*성공", content):
            for fname in os.listdir(job_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_path = os.path.join(job_dir, fname)
                    break

        warnings = []
        stories_ok = True

        if actual_body is None:
            warnings.append("본문 조판 수 확인 불가")
            stories_ok = False
        elif actual_body != expected_body:
            warnings.append(f"본문 영역: {actual_body}개 (예상 {expected_body}개)")
            stories_ok = False

        if actual_answer is None:
            warnings.append("정답 조판 수 확인 불가")
            stories_ok = False
        elif actual_answer != expected_answer:
            warnings.append(f"정답 영역: {actual_answer}개 (예상 {expected_answer}개)")
            stories_ok = False

        if overflow is None:
            warnings.append("오버플로우 수치 확인 불가")
        elif overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")

        ok = stories_ok and (overflow is not None and overflow <= max_overflow) and pdf_path is not None

        stories = {
            "본문": {"actual": actual_body,   "expected": expected_body},
            "정답": {"actual": actual_answer, "expected": expected_answer},
        }

        result = {
            "ok": ok,
            "overflow": overflow,
            "stories": stories,
            "pdf_path": pdf_path,
            "warnings": warnings,
        }

        status = "✅ 통과" if ok else f"⚠️ 경고 {len(warnings)}건"
        log(f"[검수] {status} | 본문 {actual_body}/{expected_body} | 정답 {actual_answer}/{expected_answer} | 오버플로우 {overflow}개")
        return result
