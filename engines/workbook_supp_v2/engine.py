"""부교재 워크북 v2 엔진 — WorkbookV2Engine 상속 (v1 supp의 상속 구조 그대로).

v1 workbook_supp가 WorkbookEngine을 100% 상속하고 내지 lookup(학교명 키,
"_default" 폴백)과 출력 파일명(filename_stem)만 바꾸듯, v2도
WorkbookV2Engine의 _select_template / _output_name 훅만 오버라이드한다.
파서/플랜/렌더/검수 게이트는 workbook_v2와 완전히 동일.

v1(engines/workbook_supp) 무변경. 출력 파일명 v1 규칙 + _v2 접미로 공존.
"""
import os

from engines.workbook_v2.engine import WorkbookV2Engine


class WorkbookSuppV2Engine(WorkbookV2Engine):

    @property
    def material_id(self):
        return "workbook_supp_v2"

    @property
    def display_name(self):
        return "부교재 워크북 v2 (베타)"

    @property
    def description(self):
        return ("부교재 워크북 조판 v2 — 데이터 플랜 + 자동 검수 "
                "(워크북 v2 로직 동일, 학교 전용 내지 + 사용자 지정 파일명)")

    @property
    def subject_prefix(self):
        return "부교재워크북"

    @property
    def template_name(self):
        return "typeset_workbook_supp_v2.html"

    # ── 훅 오버라이드 (v1 WorkbookSuppEngine.prepare_jsx의 차이 2가지) ──────

    def _output_name(self, job_dir, grade, year, month, workbook_type,
                     school):
        """{학교}_워크북{stem}_내지_v2.indd — v1 supp 규칙 + _v2 접미."""
        filename_stem = self._read_meta_str(job_dir, "filename_stem", "")
        if not filename_stem:
            raise ValueError("파일명을 입력해야 합니다")
        safe_stem = (filename_stem.replace("/", "_").replace("\\", "_")
                     .strip())
        if school:
            return f"{school}_워크북{safe_stem}_내지_v2.indd"
        return f"워크북{safe_stem}_내지_v2.indd"

    def _select_template(self, cfg, workbook_type, school, log):
        """학교명 키 lookup → "_default" 폴백 (v1 supp와 동일)."""
        indd_map = cfg.get("indd_original", {})
        src = ""
        if school:
            src = indd_map.get(school, "")
            if src:
                log(f"[내지] 학교 전용 템플릿: {school}")
        if not src:
            src = indd_map.get("_default", "")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(f"내지 원본 파일 없음: {src}")
        return src
