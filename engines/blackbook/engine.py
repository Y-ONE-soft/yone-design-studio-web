import json
import os
import re
import shutil

from core.base import BaseEngine, safe_copy_indd
from core.paths import resolve_config
from engines.blackbook.parser import parse_hwpx, parse_answers_hwp

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
        return "프리미엄북 블랙북 조판 자동화 (독해 서술형 Day 1–5)"

    @property
    def subject_prefix(self) -> str:
        return "블랙북"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {"key": "manuscript", "label": "블랙북 원고", "required": True},
                {"key": "answers",    "label": "정답 및 해설", "required": False},
            ]
        }

    # ── 1단계: hwpx → content.json ──────────────────────────────────────

    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        hwpx_path = uploaded_files.get("manuscript")
        if not hwpx_path:
            raise ValueError("원고 hwpx 파일이 없습니다.")

        log(f"[파서] 파싱 중: {os.path.basename(hwpx_path)}")
        data = parse_hwpx(hwpx_path)

        # 정답 파일 파싱 (선택 사항) → Day별로 분배
        answers_path = uploaded_files.get("answers")
        if answers_path and os.path.exists(answers_path):
            log(f"[파서] 정답 파싱 중: {os.path.basename(answers_path)}")
            try:
                answers = parse_answers_hwp(answers_path)
                # Day별 문제 수 기반으로 정답 분배
                day_answers = []
                ans_idx = 0
                for day in data["days"]:
                    problem_count = sum(
                        1 for p in day["paragraphs"] if p["type"] == "problem"
                    )
                    day_ans = answers[ans_idx : ans_idx + problem_count]
                    day_answers.append({
                        "day_num": day["day_num"],
                        "answers": day_ans,
                    })
                    ans_idx += problem_count
                data["day_answers"] = day_answers
                log(f"[파서] 정답 완료: {len(answers)}개 → {len(day_answers)}개 Day")
            except Exception as e:
                log(f"[파서] 정답 파싱 실패 (무시): {e}")
                data["day_answers"] = []
        else:
            data["day_answers"] = []

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        total_paras = sum(len(d["paragraphs"]) for d in data["days"])
        ans_total = sum(len(da["answers"]) for da in data.get("day_answers", []))
        log(f"[파서] 완료: {len(data['days'])}개 Day, {total_paras}개 단락, 정답 {ans_total}개")

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
        expected_days = cfg["verify"]["expected_days"]
        max_overflow = cfg["verify"]["max_overflow"]

        log_path = os.path.join(job_dir, cfg["log_filename"])
        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "error": "로그 파일 없음", "warnings": []}

        content = open(log_path, encoding="utf-8", errors="ignore").read()

        # Day 조판 완료 수
        m = re.search(r"Day조판완료:\s*(\d+)개", content)
        actual_days = int(m.group(1)) if m else None

        overflow_m = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(overflow_m.group(1)) if overflow_m else None

        pdf_path = None
        if re.search(r"PDF:\s*성공", content):
            for fname in os.listdir(job_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_path = os.path.join(job_dir, fname)
                    break

        warnings = []
        days_ok = True

        if actual_days is None:
            warnings.append("Day 조판 완료 수 확인 불가")
            days_ok = False
        elif actual_days != expected_days:
            warnings.append(f"Day 수: {actual_days}개 (예상 {expected_days}개)")
            days_ok = False

        if overflow is None:
            warnings.append("오버플로우 수치 확인 불가")
        elif overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")

        ok = days_ok and (overflow is not None and overflow <= max_overflow) and pdf_path is not None

        stories = {
            "Day조판": {"actual": actual_days, "expected": expected_days}
        }

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
