"""세서특필 조판 엔진.

특강교재 > 세서특필 (광문1/광문2)
PART1 중요문장 + PART2 실전문제+정답지 hwpx를 파싱하여
InDesign으로 자동 조판한다.
"""
import json
import os
import re
import shutil

from core.base import BaseEngine, safe_copy
<<<<<<< Updated upstream
from core.paths import resolve_config
=======
>>>>>>> Stashed changes
from engines.seseospecial.parser import parse_all

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(_DIR, "jsx", "run.jsx")
_PATH_KEYS = ["templates"]


def _load_config() -> dict:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    # templates 의 '조판/인디자인 원본/...' 경로를 INDD_ORIGINAL_BASE(GDrive)로 redirect
    return resolve_config(cfg, _PATH_KEYS)


def _make_indd_path(cfg: dict, school: str, issue_num: str) -> str:
    num = issue_num.zfill(2)
    prefix = cfg["indd_name_prefix"]
    filename = f"{school}_{prefix}{num}_내지.indd"
    return os.path.join(cfg["indd_output_dir"], filename)


def _school_key(school: str) -> str:
    """'광문1' -> '광문1', '광문2' -> '광문2', '광문3' -> '광문3' 등 템플릿 키 추출."""
    for key in ("광문1", "광문2", "광문3"):
        if key in school:
            return key
    return school


class SeseoSpecialEngine(BaseEngine):

    @property
    def material_id(self) -> str:
        return "seseospecial"

    @property
    def display_name(self) -> str:
        return "세서특필"

    @property
    def description(self) -> str:
        return "특강교재 세서특필 조판 (PART1 중요문장 + PART2 실전문제)"

    @property
    def subject_prefix(self) -> str:
        return "세서특필"

    @property
    def upload_spec(self) -> dict:
        return {
            "slots": [
                {"key": "part1", "label": "PART1 중요문장 (.hwpx)", "required": True},
                {"key": "part2", "label": "PART2 실전문제 (.hwpx)", "required": True},
                {"key": "answers",
                 "label": "정답·해설 (.hwpx/.docx — 여러 파일 가능)",
                 "required": False, "multiple": True,
                 "accept": ".hwpx,.docx"},
            ]
        }

    # -- 1단계: hwpx -> content.json ------------------------------------------

    def parse(self, uploaded_files: dict, job_dir: str, log) -> str:
        part1_path = uploaded_files.get("part1")
        part2_path = uploaded_files.get("part2")
        answer_files = uploaded_files.get("answers")
        if isinstance(answer_files, str):
            answer_files = [answer_files]
        if not part1_path:
            raise ValueError("PART1 중요문장 hwpx 파일이 없습니다.")
        if not part2_path:
            raise ValueError("PART2 실전문제 hwpx 파일이 없습니다.")
        if not answer_files:
            log("[내지] ⚠ 정답·해설 파일 없음 — 정답지는 비워둡니다.")

        school = self._get_school(job_dir)
        json_path = os.path.join(job_dir, "content.json")
        parse_all(part1_path, part2_path, school, json_path, log,
                  answer_paths=answer_files)
        return json_path

    # -- 2단계: JSX 준비 + InDesign 파일 복사 ---------------------------------

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        cfg = _load_config()
        school = self._get_school(job_dir)
        issue_num = self._get_issue_num(job_dir)
        indd_path = _make_indd_path(cfg, school, issue_num)

        # 출력 디렉터리 생성
        os.makedirs(os.path.dirname(indd_path), exist_ok=True)

        # 재실행 충돌 방지: 출력 indd가 InDesign에 열려 있으면 '덮어쓰기 전에' 닫는다
        # (열린 채로 덮어쓰면 문서가 invalid 되어 app.open 시 'Object is invalid')
        try:
            from core.indesign.runner import close_open_indd
            close_open_indd(indd_path, log)
        except Exception:
            pass

        # 원본 템플릿 복사
        key = _school_key(school)
        template_path = cfg["templates"].get(key, "")
        if os.path.exists(template_path):
            safe_copy(template_path, indd_path)
            log(f"[내지] 원본 복사: {os.path.basename(template_path)} -> {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            raise FileNotFoundError(
                f"템플릿 없음: {template_path}\n내지 파일 없음: {indd_path}"
            )

        # .settings.json 작성
        settings_path = os.path.join(job_dir, ".settings.json")
        settings = {
            "json_path": json_path,
            "indd_path": indd_path,
            "output_dir": job_dir,
            "school": school,
            "school_key": key,
            "issue_num": issue_num,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        # run.jsx 임시 사본 (settingsPath 주입)
        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()

        jsx_src = re.sub(
            r'var settingsPath\s*=\s*"[^"]*";',
            f'var settingsPath = "{settings_path}";',
            jsx_src,
        )

        jsx_copy = os.path.join(job_dir, "run.jsx")
        with open(jsx_copy, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        log(f"[내지] JSX 준비 완료: {os.path.basename(jsx_copy)}")
        return jsx_copy

    # -- 3단계: 검수 -----------------------------------------------------------

    def verify(self, job_dir: str, log) -> dict:
        cfg = _load_config()
        max_overflow = cfg["verify"]["max_overflow"]
        log_path = os.path.join(job_dir, cfg["log_filename"])

        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "warnings": ["로그 파일 없음"]}

        content = open(log_path, encoding="utf-8", errors="ignore").read()

        # PART1 단락 수
        m1 = re.search(r"PART1:\s*(\d+)개", content)
        part1_count = int(m1.group(1)) if m1 else None

        # PART2 문항 수
        m2 = re.search(r"PART2:\s*(\d+)\s*(?:문항|그룹)", content)
        part2_count = int(m2.group(1)) if m2 else None

        # 정답 수
        m3 = re.search(r"정답:\s*(\d+)개", content)
        answer_count = int(m3.group(1)) if m3 else None

        # 오버플로우
        m_ov = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(m_ov.group(1)) if m_ov else None

        # PDF
        pdf_path = None
        if re.search(r"PDF:\s*성공", content):
            for fname in os.listdir(job_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_path = os.path.join(job_dir, fname)
                    break

        warnings = []
        if part1_count is None:
            warnings.append("PART1 단락 수 확인 불가")
        if part2_count is None:
            warnings.append("PART2 문항 수 확인 불가")
        if overflow is not None and overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")
        if not pdf_path:
            warnings.append("PDF 파일 없음")

        ok = len(warnings) == 0

        stories = {}
        if part1_count is not None:
            stories["PART1"] = {"actual": part1_count}
        if part2_count is not None:
            stories["PART2 문항"] = {"actual": part2_count}
        if answer_count is not None:
            stories["정답"] = {"actual": answer_count}

        result = {
            "ok": ok,
            "overflow": overflow,
            "stories": stories,
            "pdf_path": pdf_path,
            "warnings": warnings,
        }

        status = "통과" if ok else f"경고 {len(warnings)}건"
        log(f"[검수] {status} | PART1: {part1_count} | PART2: {part2_count}문항 | 정답: {answer_count}")
        return result

    # -- 헬퍼 ------------------------------------------------------------------

    def _get_school(self, job_dir: str) -> str:
        p = os.path.join(job_dir, "school.txt")
        return open(p).read().strip() if os.path.exists(p) else "학교미선택"

    def _get_issue_num(self, job_dir: str) -> str:
        p = os.path.join(job_dir, "issue_num.txt")
        return open(p).read().strip() if os.path.exists(p) else "01"
