"""리딩파워(기본) 워크북 v2 엔진 — WorkbookSuppV2Engine 상속.

**완성(engines/ebs_workbook_v2)과 왜 다른 계보인가**
리딩파워 유형편은 완성/기본 두 권의 원고 구성과 내지가 아예 다르다.
  · 완성: 7스텝(어휘선택·본문OX·문장배열·빈칸어휘·어법수정 2종·영작) →
    [원본]EBS리딩파워_내지 (페이지당 2프레임 구성)
  · 기본: 표준 워크북 12스텝(본문정리·내용종합·어법OX·빈칸어법까지) →
    세종 워크북 내지. 실물 완성본이 근거다 — 인디자인 파일/워크북/
    `고1 EBS 리딩파워(기본)/세종1_워크북(리딩파워N강)_내지.indd`
    (= 부교재 워크북 + 세종1 전용 내지로 조판해 온 그 산출물).
그래서 조판 계보는 EBS(v2)가 아니라 **부교재 워크북 v2(세종 내지)**를
그대로 잇고, 원고 수집만 GDrive 단원 폴더 연동으로 바꾼다:

  parse            → EbsWorkbookBasicEngine (EBS 작업/Reading Power
                     유형편(기본)/<단원>/워크북) + v2 Step3 선라우팅
  내지/플랜/게이트  → WorkbookSuppV2Engine (세종 내지 = step1_b2 미지원)
  출력 파일명       → 세종1_워크북{stem}_내지_v2.indd
                     (stem 미입력 시 '(리딩파워N강)' 자동)

기존 엔진 무변경 — 완성(ebs_workbook, ebs_workbook_v2)도 부교재
(workbook_supp_v2)도 이 엔진이 건드리지 않는다.
"""
import os
import re

from core.paths import resolve_config
from engines.ebs_workbook_basic.engine import EbsWorkbookBasicEngine
from engines.workbook_supp_v2.engine import (WorkbookSuppV2Engine,
                                             _TEMPLATE_STEP_MAPS)

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(os.path.dirname(_DIR), "ebs_workbook_basic",
                            "config.json")
_PATH_KEYS = ["indd_output_dir", "indd_original", "ebs_base"]

# 리딩파워(기본)은 세종고(=세종1) 교재다 — 완성본 실물 파일명이 전부
# '세종1_워크북…'. 출력 파일명 접두이자 학교 표기.
_SCHOOL = "세종1"


def _load_basic_config():
    import json
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class EbsWorkbookBasicV2Engine(WorkbookSuppV2Engine):

    @property
    def material_id(self):
        return "ebs_workbook_basic_v2"

    @property
    def display_name(self):
        return "리딩파워(기본) 워크북 v2 (베타)"

    @property
    def description(self):
        return ("EBS 리딩파워(유형편 기본) 워크북 조판 v2 — 단원 폴더 "
                "연동 + 세종 워크북 내지 (부교재 워크북 v2 로직 공유)")

    @property
    def subject_prefix(self):
        return "리딩파워기본워크북"

    @property
    def template_name(self):
        return "typeset_ebs_workbook_basic_v2.html"

    @property
    def upload_spec(self):
        """단원은 폼(lesson/manuscript_folder)에서 오고, 여기서는 추가
        업로드와 텍스트 슬롯만 정의한다. 간지 두 줄은 부교재 v2와 같은
        계약이되 기본값이 '리딩파워 / N강'."""
        return {"slots": [
            {"key": "manuscripts",
             "label": "추가 원고 파일 (선택 — 단원 폴더에 없는 파일 · PDF는 Step3만)",
             "required": False, "multiple": True,
             "accept": ".docx,.hwp,.hwpx,.pdf"},
            {"key": "filename_stem",
             "label": "파일명 (워크북 뒤 — 미입력 시 '(리딩파워N강)')",
             "type": "text", "required": False},
            {"key": "divider_line1",
             "label": "간지 첫 줄 (선택 — 미입력 시 '리딩파워')",
             "type": "text", "required": False},
            {"key": "divider_line2",
             "label": "간지 둘째 줄 (선택 — 미입력 시 'N강')",
             "type": "text", "required": False},
        ]}

    # ── 1단계: parse — 기본 시리즈 단원 폴더 수집 ──────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        from engines.ebs_workbook_v2.engine import parse_with_step3_routing
        return parse_with_step3_routing(EbsWorkbookBasicEngine(),
                                        uploaded_files, job_dir, log)

    # ── WorkbookSuppV2Engine 훅 오버라이드 ────────────────────────────────

    def _load_cfg(self):
        return _load_basic_config()

    def _workbook_type(self, job_dir):
        """플랜 분기는 표준 워크북(모의고사 계열)이다.

        'EBS' 분기는 **완성 내지**(페이지당 2프레임 · C1/C2 프레임 분리)
        전용이라 세종 내지에 걸면 배치가 어긋난다. 기본 원고는 부교재
        워크북과 같은 12스텝 구조 — 부교재 v2로 조판해 온 실물과 같은
        경로를 탄다.
        """
        return "모의고사"

    def _select_template(self, cfg, workbook_type, school, log):
        """내지는 세종 워크북 내지 하나로 고정 (config indd_original)."""
        src = cfg.get("indd_original", "")
        if isinstance(src, dict):
            src = src.get(_SCHOOL, "") or src.get("_default", "")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(f"내지 원본 없음: {src}")
        log(f"[내지] 리딩파워(기본) 전용 내지: {os.path.basename(src)}")
        return src

    def _template_token(self):
        """스텝 카탈로그 판정 — 학교 선택이 아니라 고정 내지 파일명으로.

        (부모는 school 키로 내지를 고르지만 여기선 내지가 고정이다.)
        세종 내지는 '내용 종합'(step1_b2)이 실물에 없어 그 스텝을 미지원
        으로 보고해야 한다 — 원고에 내용종합이 있어도 침묵 유실 대신
        '미지원 스텝'으로 노출된다.
        """
        ctx = getattr(self, "_plan_ctx", None) or {}
        cfg = ctx.get("cfg") or self._load_cfg()
        base = os.path.basename(str(cfg.get("indd_original", "")))
        for token, _smap in _TEMPLATE_STEP_MAPS:
            if token in base:
                return token
        return ""

    def _unit_number(self, job_dir):
        """선택한 단원의 강 번호 ('Unit 20 Example, 1, 2' → '20')."""
        unit = self._read_meta_str(job_dir, "lesson", "")
        return EbsWorkbookBasicEngine.unit_number(unit)

    def _output_name(self, job_dir, grade, year, month, workbook_type,
                     school):
        """세종1_워크북{stem}_내지_v2.indd — 실물 완성본 규칙
        ('세종1_워크북(리딩파워1강)_내지.indd') + _v2 접미."""
        stem = self._read_meta_str(job_dir, "filename_stem", "").strip()
        if not stem:
            num = self._unit_number(job_dir)
            stem = f"(리딩파워{num}강)" if num else "(리딩파워)"
        safe_stem = stem.replace("/", "_").replace("\\", "_").strip()
        prefix = (school or _SCHOOL)
        return f"{prefix}_워크북{safe_stem}_내지_v2.indd"

    def _divider_deco(self, job_dir, content):
        """간지 문구 — 기본값 '리딩파워 / N강' (부교재의 교재유형 자동
        판정은 이 계열에 맞지 않는다: 원고 출처가 항상 리딩파워다).

        세종 내지의 간지는 간지-마스터 페이지라 실행기 매칭 밖(무접촉)
        이지만, 계약은 부교재 v2와 같은 모양으로 실어 둔다 — 내지가
        바뀌어 간지가 잡히게 되면 그때 바로 올바른 문구가 찍힌다.
        """
        line1 = (self._read_meta_str(job_dir, "divider_line1", "")
                 or self._read_meta_str(job_dir, "divider_text", ""))
        line2 = self._read_meta_str(job_dir, "divider_line2", "")
        source = "user" if line1 else "type"
        if not line1:
            line1 = "리딩파워"
        if not line2:
            num = self._unit_number(job_dir)
            stem = self._read_meta_str(job_dir, "filename_stem", "")
            m = re.search(r"(\d+\s*강|Unit\s*\.?\s*\d+)", stem, re.I)
            if num:
                line2 = f"{num}강"
            elif m:
                line2 = re.sub(r"\s+", "", m.group(1))
        return {"divider": {"line1": line1, "line2": line2,
                            "source": source}}
