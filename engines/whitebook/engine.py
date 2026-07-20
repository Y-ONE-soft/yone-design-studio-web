import json
import os
import re
import shutil

from core.base import BaseEngine, safe_copy_indd
from core.paths import resolve_config
from engines.whitebook.parser import run_parse

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(_DIR, "jsx", "run.jsx")

_SETTINGS_PATH_MARKER = '__SETTINGS_PATH__'

_PATH_KEYS = ["indd_output_dir", "indd_original", "parse_script"]


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _make_indd_path(cfg: dict, school: str, issue_num: str) -> str:
    """학교 + 번호로 내지 파일 경로 생성. 예: 배재1_화이트북02_내지.indd"""
    num = issue_num.zfill(2)
    prefix = cfg["indd_name_prefix"]   # 예: "화이트북"
    filename = f"{school}_{prefix}{num}_내지.indd"
    return os.path.join(cfg["indd_output_dir"], filename)


class WhitebookEngine(BaseEngine):

    @property
    def material_id(self) -> str:
        return "whitebook"

    @property
    def display_name(self) -> str:
        return "화이트북 워크북"

    @property
    def description(self) -> str:
        return "프리미엄북 화이트북 1권 조판 자동화 (Day 1–10)"

    @property
    def subject_prefix(self) -> str:
        return "화이트북"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {"key": "w1_main",     "label": "WEEK1 원고 .hwpx",          "required": True},
                {"key": "w1_practice", "label": "WEEK1 연습문제 .docx",       "required": False},
                {"key": "w1_main_ans", "label": "WEEK1 원고 답지 .hwpx",      "required": False},
                {"key": "w1_prac_ans", "label": "WEEK1 연습문제 답지 .docx",  "required": False},

                {"key": "w2_main",     "label": "WEEK2 원고 .hwpx",          "required": True},
                {"key": "w2_practice", "label": "WEEK2 연습문제 .docx",       "required": False},
                {"key": "w2_main_ans", "label": "WEEK2 원고 답지 .hwpx",      "required": False},
                {"key": "w2_prac_ans", "label": "WEEK2 연습문제 답지 .docx",  "required": False},

                {"key": "w3_main",     "label": "WEEK3 원고 .hwpx",          "required": True},
                {"key": "w3_practice", "label": "WEEK3 연습문제 .docx",       "required": False},
                {"key": "w3_main_ans", "label": "WEEK3 원고 답지 .hwpx",      "required": False},
                {"key": "w3_prac_ans", "label": "WEEK3 연습문제 답지 .docx",  "required": False},
            ]
        }

    # ── 1단계: hwpx + docx → content.json ────────────────────────────────

    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        import json as _json
        cfg = _load_config()

        # 워크북 hwpx (Week1, 2, 3 순)
        hwpx = [uploaded_files[k] for k in ("w1_main", "w2_main", "w3_main")
                if k in uploaded_files]
        main_ans = [uploaded_files[k] for k in ("w1_main_ans", "w2_main_ans", "w3_main_ans")
                    if k in uploaded_files]

        if not hwpx:
            raise ValueError("원고 hwpx 파일이 없습니다.")

        # 1) 워크북 파서 → content.json (Day별 A~E)
        json_path = os.path.join(job_dir, "content.json")
        run_parse(cfg["parse_script"], hwpx, main_ans, json_path, log)

        if not os.path.exists(json_path):
            raise RuntimeError("content.json 생성 실패")

        # 2) 연습문제(.docx) 파서 → content.json에 'practices' 추가
        from engines.whitebook.practice_parser import parse_practice_docx, parse_practice_answer_docx

        with open(json_path, encoding="utf-8") as f:
            data = _json.load(f)

        practices = []
        for week_idx, (pkey, akey) in enumerate(
            [("w1_practice", "w1_prac_ans"),
             ("w2_practice", "w2_prac_ans"),
             ("w3_practice", "w3_prac_ans")], start=1
        ):
            entry = {"week": week_idx, "questions": [], "answers": []}
            if pkey in uploaded_files:
                try:
                    entry["questions"] = parse_practice_docx(uploaded_files[pkey], log=log)
                    log(f"[연습] WEEK{week_idx} 문제: {len(entry['questions'])}개")
                except Exception as e:
                    log(f"[연습] WEEK{week_idx} 문제 파싱 실패: {e}")
            if akey in uploaded_files:
                try:
                    entry["answers"] = parse_practice_answer_docx(uploaded_files[akey], log=log)
                    log(f"[연습] WEEK{week_idx} 답지: {len(entry['answers'])}개")
                except Exception as e:
                    log(f"[연습] WEEK{week_idx} 답지 파싱 실패: {e}")
            practices.append(entry)
        data["practices"] = practices

        with open(json_path, "w", encoding="utf-8") as f:
            _json.dump(data, f, ensure_ascii=False, indent=2)

        log(f"[파서] content.json 생성 완료 ({os.path.getsize(json_path):,} bytes)")
        return json_path

    # ── 2단계: JSX 임시 사본 생성 + settings.json 작성 ──────────────────

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = _load_config()

        # 학교 + 주차 번호로 내지 파일 경로 결정
        issue_num = self._get_issue_num(job_dir)
        school = self._get_school(job_dir)
        indd_path = _make_indd_path(cfg, school, issue_num)
        log(f"[내지] 출력 파일: {os.path.basename(indd_path)}")

        # 원본 내지 파일 → 작업 경로로 복사 (항상 깨끗한 상태로 시작)
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

        # run.jsx 임시 사본 — settingsPath만 교체
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
        expected = cfg["verify"]["expected_stories"]
        max_overflow = cfg["verify"]["max_overflow"]

        log_path = os.path.join(job_dir, cfg["log_filename"])
        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "error": "로그 파일 없음", "warnings": []}

        content = open(log_path, encoding="utf-8", errors="ignore").read()

        stories = {}
        for key, exp in expected.items():
            m = re.search(rf"{re.escape(key)}:\s*(\d+)", content)
            actual = int(m.group(1)) if m else None
            stories[key] = {"actual": actual, "expected": exp}

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
        for key, v in stories.items():
            if v["actual"] is None:
                warnings.append(f"{key} 수집 수 확인 불가")
                stories_ok = False
            elif v["actual"] != v["expected"]:
                warnings.append(f"{key}: {v['actual']}개 (예상 {v['expected']}개)")
                stories_ok = False

        if overflow is None:
            warnings.append("오버플로우 수치 확인 불가")
        elif overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")

        ok = stories_ok and overflow == max_overflow and pdf_path is not None

        result = {
            "ok": ok,
            "overflow": overflow,
            "stories": stories,
            "pdf_path": pdf_path,
            "warnings": warnings,
        }

        status = "✅ 통과" if ok else f"⚠️ 경고 {len(warnings)}건"
        log(f"[검수] {status} | 오버플로우: {overflow}개 | PDF: {'있음' if pdf_path else '없음'}")
        return result
