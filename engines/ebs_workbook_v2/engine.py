"""리딩파워(EBS) 워크북 v2 엔진 — WorkbookV2Engine 상속.

v1(engines/ebs_workbook)과의 차이는 전부 훅으로 표현:
  - parse: v1 완전 위임 (GDrive 단원 폴더 복사 + workbook 파서 재사용 —
    workbook_type "EBS" 포함 content.json 산출)
  - _load_cfg: v1 ebs config (indd_original 단일 경로, ebs_base 등)
  - _workbook_type: "EBS" 고정 → 플랜 EBS 분기:
      · step1_c1 헤더 = NEXT_FRAME (페이지당 2프레임 — v1 run.jsx 1230)
        + 화살표 답지 빈 단락 재사용 (1469)
      · step2_c2 bracket 프레임브레이크 생략, 빈 줄 2개만 (2125 — 문제들이
        연속해서 흐름)
  - _step_map: engines/ebs_workbook_v2/step_map.json — v1 settings의
    ebs_step_story_map + step3 마스터 O (리딩파워 내지 페이지 구성)
  - _output_name: EBS_리딩파워_{단원}_전체(C)_v2.indd
  - _select_template: 단일 indd_original (구버전 dict 호환)

v1 무변경. 출력 파일명 _v2 접미로 공존. run/verify는 WorkbookV2Engine
(플랜 단어 보존 검수 게이트 + 오버플로우 지목 + PDF).

주의 (v2 이식 타협 — workbook_v2 W4 미해결 1번과 동일): v1은 EBS에서
startParagraph 외에 ~M(FRAME_BREAK 메타문자) GREP을 이중 안전장치로 추가
했다. v2는 유닛 경계 NEXT_FRAME만 사용 — E2E에서 frame 분리가 깨지면
실행기에 FRAME_BREAK 삽입 op 추가 필요.
"""
import json
import os
import re

from core.paths import resolve_config
from engines.workbook_v2.engine import WorkbookV2Engine

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "ebs_workbook",
                          "config.json")
_PATH_KEYS = ["indd_output_dir", "indd_original", "ebs_base"]

_STEP_MAP = json.load(open(os.path.join(_DIR, "step_map.json"),
                           encoding="utf-8"))
_STEP_MAP.pop("_doc", None)


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class EbsWorkbookV2Engine(WorkbookV2Engine):

    @property
    def material_id(self):
        return "ebs_workbook_v2"

    @property
    def display_name(self):
        return "리딩파워 워크북 v2 (베타)"

    @property
    def description(self):
        return ("EBS 리딩파워(유형편 완성) 워크북 조판 v2 — 데이터 플랜 + "
                "자동 검수 (워크북 v2 로직 공유)")

    @property
    def subject_prefix(self):
        return "리딩파워워크북"

    @property
    def template_name(self):
        return "typeset_ebs_workbook_v2.html"

    @property
    def upload_spec(self):
        from engines.ebs_workbook.engine import EbsWorkbookEngine
        return EbsWorkbookEngine().upload_spec

    # ── 1단계: parse — v1 완전 위임 (GDrive 복사 + 파서) ────────────────────

    def parse(self, uploaded_files, job_dir, log):
        from engines.ebs_workbook.engine import EbsWorkbookEngine
        return EbsWorkbookEngine().parse(uploaded_files, job_dir, log)

    # ── WorkbookV2Engine 훅 오버라이드 ──────────────────────────────────────

    def _load_cfg(self):
        return _load_v1_config()

    def _workbook_type(self, job_dir):
        return "EBS"

    def _step_map(self):
        return dict(_STEP_MAP)

    def _output_name(self, job_dir, grade, year, month, workbook_type,
                     school):
        """v1 규칙(EBS_리딩파워_{단원}_전체(C)) + _v2 접미."""
        unit = self._read_meta_str(job_dir, "lesson", "")
        unit_short = re.sub(r"\s+", "", unit) if unit else "단원"
        return f"EBS_리딩파워_{unit_short}_전체(C)_v2.indd"

    def _select_template(self, cfg, workbook_type, school, log):
        """단일 원본 indd (구버전 dict config 호환 — v1 동일)."""
        src = cfg.get("indd_original", "")
        if isinstance(src, dict):
            src = src.get("모의고사", "")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(f"내지 원본 없음: {src}")
        return src
