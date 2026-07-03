"""동형모의고사 v2 엔진 — 새 아키텍처 파일럿의 운영 래퍼.

파이프라인: core.extract → core.structure → content v2 IR → 렌더 플랜(데이터)
→ render_flow JSX(실행만) → 검수 게이트(verify에 내장).

v1(engines/mockexam)과의 차이:
  - 레이아웃/스타일 결정이 파이썬(render.py + style_map.json 데이터)
  - 템플릿에 없는 스타일 자동 생성 금지 (경고)
  - verify가 조판 결과를 다시 열어 원고 원본 단어셋과 대조 (내용 누락 검출)
  - 출력 파일명에 _v2 접미 (v1 산출물과 공존)

학교/학년/템플릿 설정은 v1의 engines/mockexam/config.json을 공유한다
(스타일 차이는 core/structure/style_map.json의 overrides 데이터로 흡수).
"""
import glob
import json
import os
import re
import unicodedata

from config import STUDIO_ROOT
from core.base import BaseEngine, safe_copy_indd
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config

_V1_CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "mockexam", "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "core", "jsx", "render_flow.body.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def _norm_typo(s):
    """타이포그래피 정규화 — InDesign이 곧은따옴표를 굽은따옴표(''""), 
    하이픈을 대시로 자동 치환하므로 단어 대조 전에 통일한다."""
    return (s.replace("\u2019", "'").replace("\u2018", "'")
             .replace("\u201c", '"').replace("\u201d", '"'))


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["template_base", "output_base"])


class MockexamV2Engine(BaseEngine):

    jsx_timeout = 900

    @property
    def material_id(self):
        return "mockexam_v2"

    @property
    def display_name(self):
        return "동형모의고사 v2 (베타)"

    @property
    def description(self):
        return "동형모의고사 조판 v2 — 구조 인식 + 자동 검수 (신규 아키텍처)"

    @property
    def subject_prefix(self):
        return "동형"

    @property
    def template_name(self):
        return "typeset_mockexam_v2.html"

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "manuscripts",
                    "label": "동형 원고 (.hwpx/.docx/.hwp — 회차별 파일)",
                    "required": True,
                    "multiple": True,
                    "accept": ".hwpx,.docx,.hwp",
                }
            ]
        }

    # ── 헬퍼 ────────────────────────────────────────────────────────────────

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    def _resolve_template(self, cfg, school, grade):
        school_cfg = cfg["schools"].get(school)
        if not school_cfg:
            raise FileNotFoundError(f"학교 설정을 찾을 수 없습니다: {school}")
        grade_num = grade.replace("고", "")
        filename = school_cfg["template_pattern"].replace("{grade_num}", grade_num)
        template_path = os.path.join(cfg["template_base"], filename)
        if not os.path.exists(template_path):
            raise FileNotFoundError(f"템플릿을 찾을 수 없습니다: {template_path}")
        return template_path

    # ── 1단계: parse ────────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        from engines.mockexam_v2.parser import parse_manuscripts
        from core.schema import validate_v2

        files = uploaded_files.get("manuscripts") or []
        if isinstance(files, str):
            files = [files]
        if not files:
            raise ValueError("업로드된 원고가 없습니다.")

        school = _nfc(self._get_meta(job_dir, "school"))
        grade = self._get_meta(job_dir, "grade", "고1")

        docs = parse_manuscripts(files, meta={"school": school, "grade": grade},
                                 log=log)
        rounds = []
        for idx, (name, doc) in enumerate(docs, start=1):
            errs = validate_v2(doc)
            if errs:
                raise ValueError(f"v2 스키마 오류 ({name}): {errs[:3]}")
            n_uncls = sum(1 for it in doc["items"] if it["type"] is None)
            log(f"[v2] {idx}회({name}): 문항 {len(doc['items'])}"
                + (f", 미분류 {n_uncls} (검수 지목)" if n_uncls else ""))
            rounds.append({"round": idx, "source_file": name, "doc": doc})

        content = {"version": 2, "school": school, "grade": grade,
                   "rounds": rounds}
        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=1)
        return json_path

    # ── 2단계: prepare_jsx ──────────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.mockexam_v2.render import ir_to_render_plan
        from core.structure.style_resolver import load_style_map

        cfg = _load_v1_config()
        content = json.load(open(json_path, encoding="utf-8"))
        school = content["school"]
        grade = content["grade"]
        exam_period = self._get_meta(job_dir, "exam_period", cfg["exam_period"])
        short = cfg["schools"].get(school, {}).get("short", school)
        grade_num = grade.replace("고", "")

        output_dir = os.path.join(STUDIO_ROOT, "조판", "교재", "동형모의고사",
                                  grade, exam_period, school)
        os.makedirs(output_dir, exist_ok=True)
        template_path = self._resolve_template(cfg, school, grade)
        log(f"[템플릿] {os.path.basename(template_path)}")

        overrides = (load_style_map().get("mockexam_v2", {})
                     .get("overrides", {}).get(f"{short}{grade_num}"))

        jobs = []
        for rd in content["rounds"]:
            n = rd["round"]
            plan = ir_to_render_plan(rd["doc"], overrides=overrides)
            plan_path = os.path.join(job_dir, f"render_plan_{n}.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False)

            indd_path = safe_copy_indd(
                template_path,
                os.path.join(output_dir,
                             f"{short}{grade_num}_동형모의고사_v2({n}회).indd"))
            pdf_path = indd_path.replace(".indd", ".pdf")
            jsx_log = os.path.join(job_dir, f"조판_로그_{n}.txt")
            jsx_path = build_jsx(
                _RENDER_BODY,
                {"__TEMPLATE_PATH__": indd_path, "__PLAN_PATH__": plan_path,
                 "__OUT_INDD__": indd_path, "__OUT_PDF__": pdf_path},
                log_path=jsx_log,
                out_path=os.path.join(job_dir, f"run_{n}.jsx"))
            jobs.append({"round": n, "source_file": rd["source_file"],
                         "indd_path": indd_path, "pdf_path": pdf_path,
                         "jsx_path": jsx_path, "log_path": jsx_log,
                         "paragraphs": len(plan)})
            log(f"[내지] {n}회: {os.path.basename(indd_path)} (플랜 {len(plan)}단락)")

        settings = {"engine": "mockexam_v2", "jobs": jobs,
                    "output_dir": output_dir, "school": school, "grade": grade,
                    "exam_period": exam_period}
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return settings_path

    # ── 3단계: run_indesign ─────────────────────────────────────────────────

    def run_indesign(self, job_dir, log):
        from core.indesign.runner import run_jsx
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        for jb in settings["jobs"]:
            log(f"[InDesign] {jb['round']}회 조판 시작")
            run_jsx(jb["jsx_path"], log, poll_log_path=jb["log_path"],
                    timeout=self.jsx_timeout,
                    completion_marker="v2 조판 완료")
            log(f"[InDesign] {jb['round']}회 완료")

    # ── 4단계: verify — 검수 게이트 내장 ────────────────────────────────────

    def verify(self, job_dir, log):
        from core.inspect import dump_indd
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        from engines.mockexam_v2.parser import extract_file_paragraphs

        ok = True
        warnings = []
        pdf_paths = []
        rounds_report = []
        for jb in settings["jobs"]:
            n = jb["round"]
            # 원고 원본 단어셋 (검수 기준 — 순환 금지)
            src_words = set()
            src = next((p for p in glob.glob(os.path.join(job_dir, "uploads", "*"))
                        if _nfc(os.path.basename(p)).endswith(
                            _nfc(jb["source_file"]))), None)
            if src:
                for para in extract_file_paragraphs(src):
                    for w in _RE_WORD.findall(_norm_typo(para["text"])):
                        src_words.add(w.lower())

            dump = dump_indd(jb["indd_path"],
                             os.path.join(job_dir, f"typeset_dump_{n}.json"), log)
            got = set()
            for st in dump["stories"]:
                for pp in st["paragraphs"]:
                    for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                        got.add(w.lower())
            missing = src_words - got
            ovf = dump.get("overflow_stories", 0)
            render_warns = [l.strip() for l in open(jb["log_path"], encoding="utf-8")
                            if "[경고]" in l]
            pdf_ok = os.path.exists(jb["pdf_path"])
            if pdf_ok:
                pdf_paths.append(jb["pdf_path"])

            if missing:
                ok = False
                msg = (f"❌ {n}회 내용누락 {len(missing)}단어: "
                       + ", ".join(sorted(missing)[:8]))
                warnings.append(msg)
                log(f"[검수] {msg}")
            if ovf:
                warnings.append(f"⚠️ {n}회 오버플로우 스토리 {ovf}개")
            warnings.extend(f"⚠️ {n}회 {w}" for w in render_warns)
            if not pdf_ok:
                ok = False
                warnings.append(f"❌ {n}회 PDF 미생성")
            log(f"[검수] {n}회: 원고 {len(src_words)}단어 중 누락 {len(missing)} / "
                f"오버플로우 {ovf} / PDF {'OK' if pdf_ok else '실패'}")
            rounds_report.append({"round": n, "missing_words": len(missing),
                                  "overflow": ovf, "pdf": pdf_ok})

        return {
            "ok": ok,
            "overflow": sum(r["overflow"] for r in rounds_report),
            "stories": {f"{r['round']}회": {"actual": None, "expected": None}
                        for r in rounds_report},
            "pdf_path": pdf_paths[0] if pdf_paths else None,
            "pdf_paths": pdf_paths,
            "warnings": warnings,
            "rounds": rounds_report,
        }
