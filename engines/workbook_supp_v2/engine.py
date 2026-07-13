"""부교재 워크북 v2 엔진 — WorkbookV2Engine 상속 (v1 supp의 상속 구조 그대로).

v1 workbook_supp가 WorkbookEngine을 100% 상속하고 내지 lookup(학교명 키,
"_default" 폴백)과 출력 파일명(filename_stem)만 바꾸듯, v2도
WorkbookV2Engine의 훅만 오버라이드한다. 파서/렌더/검수 게이트는
workbook_v2와 동일.

W11 (job 06f4b2c2 결함 수리 — 완제품 기준):
  - _step_map: supp 전용 step_map.json — step2_a1/btm에 pos(top/bottom)
    기하 힌트 (상/하단 뒤바뀜 회귀 교정)
  - _plan_decorations: page_cleanup(잔여 사이클/제외 스텝 페이지 삭제 +
    빈 STEP3 페이지 M 마스터) + passage_numbers(독립 지문번호 프레임 갱신)

v1(engines/workbook_supp) 무변경. 출력 파일명 v1 규칙 + _v2 접미로 공존.
"""
import json
import os

from engines.workbook_v2.engine import WorkbookV2Engine

_DIR = os.path.dirname(os.path.abspath(__file__))
_STEP_MAP = json.load(open(os.path.join(_DIR, "step_map.json"),
                           encoding="utf-8"))
_STEP_MAP.pop("_doc", None)

# 학교 전용 내지의 스텝 카탈로그 (W19 c19 실증): 세종 내지(42p)에는 '내용
# 종합'(step1_b2) 섹션이 실물에 없다 — 마커 텍스트/페이지 58 모두 부재
# (v1 실물 세종1_워크북리딩파워20강_내지.indd 42p도 동일). 매핑에 없는
# 스텝은 steps_to_plan이 unsupported로 보고 → 렌더 제외 + verify 지목.
# (미지원 매핑 없이 렌더하면 '스토리 못 찾음' 경고 후 원고가 침묵 유실돼
# 단어 게이트 ok=False — c19 1차 조판 실증.)
_SEJONG_STEP_MAP = {k: v for k, v in _STEP_MAP.items() if k != "step1_b2"}

# 내지 파일명 토큰 → 스텝 카탈로그. _select_template이 고를 원본의
# basename으로 판정 (경로/사본 이름이 달라도 토큰은 보존된다).
_TEMPLATE_STEP_MAPS = [("세종", _SEJONG_STEP_MAP)]

# 독립 지문번호 텍스트 프레임을 가진 섹션 (템플릿 스펙
# tests/fixtures/template_spec_workbookC.json 실물 확인: 빈칸 어휘 p94~ /
# 어법 O/X p132~ / 빈칸 어법 p150~ 페이지 좌측의 단일 프레임 번호 스토리)
_NUMBER_FRAME_STEPS = ["step1_c2", "step2_b1", "step2_c1"]


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

    # ── W11 훅: 스토리 매핑 + 완제품 후처리 op ──────────────────────────────

    def _step_map(self):
        """supp 전용 step_map — step2_a1/btm pos(top/bottom) 기하 힌트.

        학교 전용 내지가 선택되는 경우(base prepare_jsx가 _plan_ctx로
        제공하는 컨텍스트로 _select_template과 동일하게 판정) 해당 내지의
        스텝 카탈로그를 적용한다 — 세종 내지는 step1_b2 미지원 (W19)."""
        ctx = getattr(self, "_plan_ctx", None) or {}
        cfg, school = ctx.get("cfg"), ctx.get("school", "")
        if cfg and school:
            try:
                src = self._select_template(
                    cfg, ctx.get("workbook_type", "모의고사"), school,
                    lambda m: None)
            except FileNotFoundError:
                src = ""
            base = os.path.basename(src)
            for token, smap in _TEMPLATE_STEP_MAPS:
                if token in base:
                    return smap
        return _STEP_MAP

    def _plan_decorations(self, job_dir, cfg):
        """완제품 후처리 op 2종 (실행기 opt-in — 다른 엔진 플랜 무변경).

        page_cleanup: 원고에 없는 스텝/남는 사이클 페이지 삭제 + 빈 STEP3
            페이지 M 마스터 재할당 (v1 run.jsx 16.5 + adjustStep3Pages 이식).
        passage_numbers: 빈칸어휘/어법OX/빈칸어법 섹션의 독립 지문번호
            프레임을 원고 지문번호로 갱신 (v1 미지원 — 완제품 기준 신설).
        """
        from engines.workbook_v2.plan import passage_labels
        from engines.workbook_v2.engine import _mockexam_divider
        # divider (W19 D4): v1 supp는 run.jsx 16.7을 그대로 상속해 간지
        # '고N 모의고사 / YY년 M월'을 갱신한다 — v2도 동일 opt-in.
        # 세종 내지의 간지('세종고 …')는 간지-마스터 페이지라 updateDivider
        # 매칭 조건(마스터 [None]) 밖 — 무접촉 (c19 실측 pg=['간지']).
        deco = {"page_cleanup": {"empty_master": "M"}}
        deco.update(_mockexam_divider(job_dir))
        try:
            content = json.load(open(os.path.join(job_dir, "content.json"),
                                     encoding="utf-8"))
            labels = passage_labels(content.get("steps", {}))
        except (OSError, ValueError):
            labels = []
        if labels:
            deco["passage_numbers"] = {"labels": labels,
                                       "steps": list(_NUMBER_FRAME_STEPS)}
        return deco

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
