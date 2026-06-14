import json
import os
import re

from core.base import BaseEngine, safe_copy_indd
from core.paths import resolve_config
from engines.whitebook_problem.parser import parse_problem_docx, parse_answer_docx

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
    num = issue_num.zfill(2)
    return os.path.join(cfg["indd_output_dir"],
                        f"{school}_{cfg['indd_name_prefix']}{num}_내지.indd")


def _as_list(v):
    if v is None:
        return []
    return [v] if isinstance(v, str) else list(v)


class WhitebookProblemEngine(BaseEngine):

    jsx_timeout = 1800  # 500문항 조판 + 페이지 자동확장 — 넉넉히

    @property
    def material_id(self) -> str:
        return "whitebook_problem"

    @property
    def display_name(self) -> str:
        return "화이트북 실전문제"

    @property
    def description(self) -> str:
        return "프리미엄북 화이트북 실전문제(문제형) 조판 — Day별 객관식 + 정답·해설"

    @property
    def subject_prefix(self) -> str:
        return "화이트북실전"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {"key": "problem", "label": "문제 원고 (.docx — 여러 파일 가능)",
                 "required": True, "multiple": True, "accept": ".docx"},
                {"key": "answer", "label": "정답 원고 (.docx — 여러 파일 가능)",
                 "required": False, "multiple": True, "accept": ".docx"},
            ]
        }

    # ── 1단계: docx → content.json ──────────────────────────────────────
    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        probs = _as_list(uploaded_files.get("problem"))
        ans = _as_list(uploaded_files.get("answer"))
        if not probs:
            raise ValueError("문제 원고(.docx)가 없습니다.")

        problem_days = []
        for p in probs:
            problem_days += parse_problem_docx(p)
        answer_days = []
        for a in ans:
            try:
                answer_days += parse_answer_docx(a)
            except Exception as e:
                log(f"[파서] 정답 파싱 실패({os.path.basename(a)}): {e}")

        problem_days.sort(key=lambda x: x["day"])
        answer_days.sort(key=lambda x: x["day"])

        data = {"problem_days": problem_days, "answer_days": answer_days}
        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        nq = sum(1 for d in problem_days for ln in d["lines"] if ln["sty"] == "문제")
        na = sum(1 for d in answer_days for ln in d["lines"] if ln["sty"] == "정답_문제 번호")
        log(f"[파서] 문제 Day {len(problem_days)}개 ({nq}문항) / 정답 Day {len(answer_days)}개 ({na}문항)")
        if not os.path.exists(json_path):
            raise RuntimeError("content.json 생성 실패")
        return json_path

    # ── 2단계: 원본 복사 + settings + jsx ───────────────────────────────
    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = _load_config()
        issue_num = self._get_issue_num(job_dir)
        school = self._get_school(job_dir)
        indd_path = _make_indd_path(cfg, school, issue_num)
        os.makedirs(os.path.dirname(indd_path), exist_ok=True)

        src = cfg.get("indd_original", "")
        if os.path.exists(src):
            indd_path = safe_copy_indd(src, indd_path)
            log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            raise FileNotFoundError(f"내지 원본 없음: {src}")

        settings_path = os.path.join(job_dir, ".settings.json")
        settings = {
            "json_path": json_path,
            "indd_path": indd_path,
            "output_dir": job_dir,
            "issue_num": issue_num,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()
        new_line = f'    var settingsPath = "{settings_path}";'
        if _SETTINGS_PATH_MARKER in jsx_src:
            jsx_src = jsx_src.replace(_SETTINGS_PATH_MARKER, new_line)
        else:
            jsx_src = re.sub(r'var settingsPath\s*=\s*"[^"]+";', new_line, jsx_src)

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

    # ── 3단계: 검수 ─────────────────────────────────────────────────────
    def verify(self, job_dir: str, log) -> dict:
        cfg = _load_config()
        max_overflow = cfg["verify"]["max_overflow"]
        log_path = os.path.join(job_dir, cfg["log_filename"])
        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "error": "로그 파일 없음", "warnings": [], "stories": {}}

        content = open(log_path, encoding="utf-8", errors="ignore").read()
        ov_m = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(ov_m.group(1)) if ov_m else None

        pdf_path = None
        if re.search(r"PDF:\s*성공", content):
            for fn in os.listdir(job_dir):
                if fn.lower().endswith(".pdf"):
                    pdf_path = os.path.join(job_dir, fn)
                    break

        warnings = []
        if overflow is None:
            warnings.append("오버플로우 수치 확인 불가")
        elif overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")
        if not pdf_path:
            warnings.append("PDF 파일 없음")

        ok = (overflow is not None and overflow <= max_overflow) and pdf_path is not None
        status = "✅ 통과" if ok else f"⚠️ 경고 {len(warnings)}건"
        log(f"[검수] {status} | 오버플로우: {overflow}")
        return {
            "ok": ok,
            "overflow": overflow,
            "pdf_path": pdf_path,
            "warnings": warnings,
            "stories": {},
        }
