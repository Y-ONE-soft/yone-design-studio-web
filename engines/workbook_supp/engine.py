"""부교재 워크북 엔진.

모의고사 워크북(WorkbookEngine)과 100% 동일한 파서/JSX/검수 로직을 그대로 사용한다.
유일한 차이:
  - 원본 indd 선택: 학교명을 키로 모의고사 워크북 config.indd_original에서 lookup,
                    없으면 "_default" 키로 fallback (= 모의고사 워크북과 같은 베이스)
  - 출력 파일명: {학교}_워크북{stem}_내지.indd / 워크북{stem}_내지.indd
"""

import json
import os
import re

from core.base import safe_copy_indd
from engines.workbook.engine import WorkbookEngine, _load_config, _JSX_TEMPLATE


class WorkbookSuppEngine(WorkbookEngine):

    @property
    def material_id(self) -> str:
        return "workbook_supp"

    @property
    def display_name(self) -> str:
        return "부교재 워크북"

    @property
    def description(self) -> str:
        return "부교재 워크북 조판 자동화 (모의고사 워크북 로직 동일, 학교 전용 내지 + 사용자 지정 파일명)"

    @property
    def subject_prefix(self) -> str:
        return "부교재워크북"

    @property
    def template_name(self) -> str:
        return "typeset_workbook_supp.html"

    # parse(), verify() — WorkbookEngine 그대로 사용 (모의고사 워크북과 동일)

    def prepare_jsx(self, json_path: str, job_dir: str, log) -> str:
        # 모의고사 워크북 config을 그대로 사용 (manuscript_file_map, step_order,
        # mockexam, needs_underline, verify, log_filename 모두 동일)
        cfg = _load_config()

        grade = self._read_meta(job_dir, "grade", 1)
        school = self._read_meta_str(job_dir, "school", "")
        filename_stem = self._read_meta_str(job_dir, "filename_stem", "")
        if not filename_stem:
            raise ValueError("파일명을 입력해야 합니다")

        # 출력 파일명
        safe_stem = filename_stem.replace("/", "_").replace("\\", "_").strip()
        if school:
            out_name = f"{school}_워크북{safe_stem}_내지.indd"
        else:
            out_name = f"워크북{safe_stem}_내지.indd"
        indd_path = os.path.join(cfg["indd_output_dir"], out_name)

        # 원본 indd: 학교 키 → "_default" fallback (= 모의고사 베이스)
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

        os.makedirs(os.path.dirname(indd_path), exist_ok=True)
        indd_path = safe_copy_indd(src, indd_path)
        log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")

        # 제외 섹션
        exclude_path = os.path.join(job_dir, "exclude.txt")
        exclude = []
        if os.path.exists(exclude_path):
            raw = open(exclude_path, encoding="utf-8").read().strip()
            exclude = [s.strip() for s in raw.split(",") if s.strip()]
            if exclude:
                log(f"[JSX] 제외 섹션: {', '.join(exclude)}")

        # settings.json — 모의고사 워크북과 동일 키
        settings_path = os.path.join(job_dir, ".settings.json")
        settings = {
            "json_path": json_path,
            "indd_path": indd_path,
            "output_dir": job_dir,
            "grade": grade,
            "year": self._read_meta(job_dir, "year", 25),
            "month": self._read_meta(job_dir, "month", 10),
            "exclude": exclude,
        }
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)

        # run.jsx — 모의고사 워크북 템플릿 (engines/workbook/jsx/run.jsx) 그대로
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

        log(f"[JSX] 준비 완료: {jsx_copy}")
        return jsx_copy
