"""동형모의고사 v2 (Vivliostyle 백엔드) — W51.

mockexam_v2 와 **같은 렌더 플랜**(engines.mockexam_v2.render.ir_to_render_plan)을
소비하되, 조판을 InDesign JSX 대신 core.render_vivlio(CSS Paged Media → PDF)로
수행한다. 파서/구조 인식/렌더 플랜은 전부 부모(MockexamV2Engine)에서 상속 —
"같은 플랜, 다른 백엔드"를 실증한다.

무회귀 원칙: 부모의 InDesign 경로(prepare_jsx/run_indesign)는 **호출되지 않는다**.
파이프라인이 render_backend=="vivliostyle" 를 보고 render_vivlio 로 분기하기
때문이다(core/pipeline.py). 이 엔진은 신규 material_id·신규 카드로만 노출되는
opt-in 경로다.
"""
import glob
import json
import os

from config import STUDIO_ROOT
from engines.mockexam_v2.engine import (MockexamV2Engine, _load_v1_config,
                                        _nfc, _norm_typo, _RE_WORD)


class MockexamV2VivEngine(MockexamV2Engine):

    # 파이프라인이 이 값으로 2단계를 Vivliostyle 경로로 분기 (base 기본은 indesign)
    render_backend = "vivliostyle"

    @property
    def material_id(self):
        return "mockexam_v2_viv"

    @property
    def display_name(self):
        return "동형모의고사 v2 (Vivliostyle)"

    @property
    def description(self):
        return "동형모의고사 조판 v2 — 렌더 플랜 → CSS Paged Media → PDF (Vivliostyle 백엔드)"

    @property
    def template_name(self):
        return "typeset_mockexam_v2_viv.html"

    # parse()/upload_spec 는 부모 그대로 상속(같은 원고·같은 content.json).

    # ── 2단계: Vivliostyle 조판 ──────────────────────────────────────────────
    def render_vivlio(self, json_path, job_dir, log):
        from engines.mockexam_v2.render import ir_to_render_plan
        from core.render_vivlio.build import render_plan_to_pdf, cli_available
        from core.render_vivlio.case import build_case

        if not cli_available():
            from core.render_vivlio.build import CLI_BIN, PILOT_DIR
            raise RuntimeError(
                f"Vivliostyle CLI 미설치: {CLI_BIN}\n"
                f"→ `cd {PILOT_DIR} && npm ci` 후 재시도 (opt-in 백엔드 전제조건)")

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

        case = build_case(content, job_dir=job_dir)

        jobs = []
        for rd in content["rounds"]:
            n = rd["round"]
            # InDesign 경로와 동일한 플랜 (overrides 없이 = 파일럿 검증 매핑).
            plan = ir_to_render_plan(rd["doc"])
            plan_path = os.path.join(job_dir, f"render_plan_{n}.json")
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False)

            pdf_path = os.path.join(
                output_dir, f"{short}{grade_num}_동형모의고사_viv({n}회).pdf")
            build_dir = os.path.join(job_dir, f"vivlio_build_{n}")
            log(f"[Vivliostyle] {n}회 렌더 시작 (플랜 {len(plan)}단락)")
            res = render_plan_to_pdf(plan, "mockexam", pdf_path, log,
                                     case=case, build_dir=build_dir,
                                     last_page_end=True, timeout=600)
            log(f"[Vivliostyle] {n}회 완료: {os.path.basename(pdf_path)} "
                f"({res['pages']}p, {res['seconds']}s)")
            jobs.append({"round": n, "source_file": rd["source_file"],
                         "pdf_path": pdf_path, "plan_path": plan_path,
                         "paragraphs": len(plan), "pages": res["pages"]})

        settings = {"engine": self.material_id, "backend": "vivliostyle",
                    "jobs": jobs, "output_dir": output_dir, "school": school,
                    "grade": grade, "exam_period": exam_period}
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return settings_path

    # ── 3단계: 검수 — PDF 기반 (덤프 불가, 내용보존은 PDF 텍스트 대조) ─────────
    def verify(self, job_dir, log):
        from engines.mockexam_v2.parser import extract_file_paragraphs
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))

        ok = True
        warnings = []
        pdf_paths = []
        rounds_report = []
        for jb in settings["jobs"]:
            n = jb["round"]
            # 원고 원본 단어셋 (검수 기준)
            src_words = set()
            src = next((p for p in glob.glob(os.path.join(job_dir, "uploads", "*"))
                        if _nfc(os.path.basename(p)).endswith(
                            _nfc(jb["source_file"]))), None)
            if src:
                for para in extract_file_paragraphs(src):
                    for w in _RE_WORD.findall(_norm_typo(para["text"])):
                        src_words.add(w.lower())

            # 조판 결과 단어셋 — PDF 텍스트(우선) 또는 렌더 플랜(폴백)
            got, source = self._pdf_words(jb["pdf_path"])
            if got is None:
                got, source = self._plan_words(jb.get("plan_path")), "plan"

            missing = src_words - got
            pdf_ok = os.path.exists(jb["pdf_path"])
            pages = jb.get("pages")
            if pdf_ok:
                pdf_paths.append(jb["pdf_path"])

            if missing:
                ok = False
                msg = (f"❌ {n}회 내용누락 {len(missing)}단어: "
                       + ", ".join(sorted(missing)[:8]))
                warnings.append(msg)
                log(f"[검수] {msg}")
            if not pdf_ok:
                ok = False
                warnings.append(f"❌ {n}회 PDF 미생성")
            log(f"[검수] {n}회: 원고 {len(src_words)}단어 중 누락 {len(missing)} "
                f"({source} 대조) / {pages}p / PDF {'OK' if pdf_ok else '실패'}")
            rounds_report.append({"round": n, "missing_words": len(missing),
                                  "pages": pages, "pdf": pdf_ok})

        return {
            "ok": ok,
            "overflow": 0,   # Vivliostyle 은 무한 페이지네이션 — 오버셋 개념 없음
            "stories": {f"{r['round']}회": {"actual": r["pages"],
                                            "expected": None}
                        for r in rounds_report},
            "pdf_path": pdf_paths[0] if pdf_paths else None,
            "pdf_paths": pdf_paths,
            "warnings": warnings,
            "rounds": rounds_report,
            "backend": "vivliostyle",
        }

    # ── 헬퍼 ────────────────────────────────────────────────────────────────
    def _pdf_words(self, pdf_path):
        """PDF 텍스트 → 단어셋 (fitz 없거나 실패 시 (None, None))."""
        if not os.path.exists(pdf_path):
            return None, None
        try:
            import fitz
            words = set()
            with fitz.open(pdf_path) as doc:
                for page in doc:
                    for w in _RE_WORD.findall(_norm_typo(page.get_text())):
                        words.add(w.lower())
            return words, "PDF"
        except Exception:
            return None, None

    def _plan_words(self, plan_path):
        words = set()
        if plan_path and os.path.exists(plan_path):
            plan = json.load(open(plan_path, encoding="utf-8"))
            for item in plan:
                text = item.get("t", "")
                for r in item.get("runs") or []:
                    text += " " + r.get("t", "")
                for w in _RE_WORD.findall(_norm_typo(text)):
                    words.add(w.lower())
        return words
