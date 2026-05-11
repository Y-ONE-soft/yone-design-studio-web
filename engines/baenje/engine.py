import json
import os
import re
import shutil

from core.base import BaseEngine, safe_copy_indd
from core.paths import resolve_config
from engines.baenje.parser import hwpx_to_rtf, docx_to_rtf

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(_DIR, "jsx", "run.jsx")

_PATH_KEYS = ["indd_output_dir", "indd_original"]


def _load_config():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _make_indd_path(cfg, school, issue_num):
    """배재2_배N제01_내지.indd 형식으로 출력 경로 생성."""
    num = issue_num.zfill(2) if issue_num else ""
    prefix = cfg["indd_name_prefix"]
    filename = f"{school}_{prefix}{num}_내지.indd"
    return os.path.join(cfg["indd_output_dir"], filename)


class BaenjeEngine(BaseEngine):

    jsx_timeout = 900  # 원고 1000+ 단락 처리에 충분한 시간

    @property
    def material_id(self):
        return "baenje"

    @property
    def display_name(self):
        return "배N제"

    @property
    def description(self):
        return "프리미엄북 배N제 조판 자동화 (HWPX/DOCX → RTF → InDesign)"

    @property
    def subject_prefix(self):
        return "배N제"

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "manuscript",
                    "label": "원고 .hwpx / .docx",
                    "required": True,
                },
                {
                    "key": "answers",
                    "label": "정답지 .hwpx / .docx",
                    "required": False,
                },
            ]
        }

    # ── 1단계: hwpx → RTF ────────────────────────────────────────────────

    def _convert_to_rtf(self, src_path, rtf_path, label, log):
        """HWPX 또는 DOCX → RTF 변환."""
        ext = os.path.splitext(src_path)[1].lower()
        if ext == ".docx":
            log(f"[파서] {label} DOCX → RTF: {os.path.basename(src_path)}")
            docx_to_rtf(src_path, rtf_path)
        else:
            log(f"[파서] {label} HWPX → RTF: {os.path.basename(src_path)}")
            hwpx_to_rtf(src_path, rtf_path)
        size = os.path.getsize(rtf_path)
        log(f"[파서] {label} RTF 완료 ({size:,} bytes)")

    def parse(self, uploaded_files, job_dir, log):
        ms_path = uploaded_files.get("manuscript")
        if not ms_path:
            raise ValueError("원고 파일이 없습니다.")

        rtf_path = os.path.join(job_dir, "manuscript.rtf")
        self._convert_to_rtf(ms_path, rtf_path, "원고", log)

        # 정답지 (선택)
        ans_path = uploaded_files.get("answers")
        answers_rtf = None
        if ans_path:
            answers_rtf = os.path.join(job_dir, "answers.rtf")
            self._convert_to_rtf(ans_path, answers_rtf, "정답지", log)

        return {"manuscript": rtf_path, "answers": answers_rtf}

    # ── 2단계: JSX 임시 사본 생성 + settings.json 작성 ──────────────────

    def prepare_jsx(self, parse_result, job_dir, log):
        # parse_result: dict {"manuscript": rtf_path, "answers": rtf_path|None}
        if isinstance(parse_result, dict):
            rtf_path = parse_result["manuscript"]
            answers_rtf = parse_result.get("answers")
        else:
            rtf_path = parse_result
            answers_rtf = None

        cfg = _load_config()

        issue_num = self._get_meta(job_dir, "issue_num") or "01"
        school = self._get_meta(job_dir, "school") or "학교미선택"

        indd_path = _make_indd_path(cfg, school, issue_num)
        log(f"[내지] 출력 파일: {os.path.basename(indd_path)}")

        # 원본 내지 → 작업 경로로 복사
        src = cfg.get("indd_original", "")
        if os.path.exists(src):
            indd_path = safe_copy_indd(src, indd_path)
            log(f"[내지] 원본 복사 완료: {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            raise FileNotFoundError(f"내지 파일 없음: {indd_path}")

        settings_path = os.path.join(job_dir, ".settings.json")
        settings = {
            "rtf_path": rtf_path,
            "answers_rtf_path": answers_rtf or "",
            "indd_path": indd_path,
            "output_dir": job_dir,
            "school": school,
            "issue_num": issue_num,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()

        jsx_src = re.sub(
            r'var settingsPath\s*=\s*"[^"]+";',
            f'var settingsPath = "{settings_path}";',
            jsx_src,
        )

        jsx_copy = os.path.join(job_dir, "run.jsx")
        with open(jsx_copy, "w", encoding="utf-8") as f:
            f.write(jsx_src)

        return jsx_copy

    def _get_meta(self, job_dir, key):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p, encoding="utf-8").read().strip() if os.path.exists(p) else ""

    # ── 3단계: 검수 ──────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        cfg = _load_config()
        log_path = os.path.join(job_dir, cfg["log_filename"])

        if not os.path.exists(log_path):
            log("[검수] 조판_로그.txt 없음")
            return {"ok": False, "error": "로그 파일 없음", "warnings": []}

        content = open(log_path, encoding="utf-8", errors="ignore").read()

        overflow_m = re.search(r"오버플로우:\s*(\d+)개", content)
        overflow = int(overflow_m.group(1)) if overflow_m else None

        q_count_m = re.search(r"문제 수:\s*(\d+)", content)
        q_count = int(q_count_m.group(1)) if q_count_m else None

        pdf_path = None
        if re.search(r"PDF:\s*성공", content):
            for fname in os.listdir(job_dir):
                if fname.lower().endswith(".pdf"):
                    pdf_path = os.path.join(job_dir, fname)
                    break

        warnings = []
        max_overflow = cfg["verify"]["max_overflow"]

        if overflow is None:
            warnings.append("오버플로우 수치 확인 불가")
        elif overflow > max_overflow:
            warnings.append(f"오버플로우 {overflow}개 발생")

        if q_count is not None:
            log(f"[검수] 문제 수: {q_count}개")

        ok = (overflow == max_overflow) and (pdf_path is not None)

        status = "통과" if ok else f"경고 {len(warnings)}건"
        log(f"[검수] {status} | 오버플로우: {overflow}개 | PDF: {'있음' if pdf_path else '없음'}")

        return {
            "ok": ok,
            "overflow": overflow,
            "q_count": q_count,
            "pdf_path": pdf_path,
            "warnings": warnings,
        }
