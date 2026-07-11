"""교과서 워크북 v2 엔진 — WorkbookV2Engine 상속 (workbook_supp_v2 패턴).

v1(engines/textbook_workbook)과의 차이는 전부 훅으로 표현:
  - parse: v1 완전 위임 (GDrive 워크북 폴더 복사 + workbook 파서 재사용 —
    교과서 메타 subject/publisher/lesson 포함 content.json 산출)
  - _load_cfg: v1 textbook config (indd_original 학교키/_default,
    textbook_base, subject_grade_map)
  - _workbook_type: "교과서" 고정 (plan의 C1 교과서 분기 — 《제목》 하단 구조)
  - _step_map: None = 모의고사 기본 STEP_MAP (v1 textbook은 settings에
    stepStoryMap을 안 넣어 run.jsx 기본 매핑 사용 — 내지도 동일 [원본]워크북_C)
  - _output_name: {subject}_{pub}_{lesson}_전체(C)(학교)_v2.indd
  - _select_template: 학교 키 → "_default" 폴백 (구버전 문자열 config 호환)
  - _plan_decorations: 간지(subject+publisher / lesson — v1 run.jsx 16.7)
    + 교과서 후처리(빈 페이지 마스터 재할당 — v1 16.8)

v1 무변경. 출력 파일명 _v2 접미로 공존. run/verify는 WorkbookV2Engine
(플랜 단어 보존 검수 게이트 + 오버플로우 지목 + PDF).
"""
import json
import os

from core.paths import resolve_config
from engines.workbook_v2.engine import WorkbookV2Engine

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "textbook_workbook",
                          "config.json")
_PATH_KEYS = ["indd_output_dir", "indd_original", "textbook_base"]

# 독립 지문번호 텍스트 프레임을 가진 섹션 (supp W11과 동일 —
# [원본]워크북_C 실물: 빈칸 어휘 p94~ / 어법 O/X p132~ / 빈칸 어법 p150~
# 페이지 좌측의 단일 프레임 번호 스토리. 교과서 내지도 같은 원본이다)
_NUMBER_FRAME_STEPS = ["step1_c2", "step2_b1", "step2_c1"]


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class TextbookWorkbookV2Engine(WorkbookV2Engine):

    @property
    def material_id(self):
        return "textbook_workbook_v2"

    @property
    def display_name(self):
        return "교과서 워크북 v2 (베타)"

    @property
    def description(self):
        return ("교과서 워크북 조판 v2 — 데이터 플랜 + 자동 검수 "
                "(과목/출판사/과 선택, 워크북 v2 로직 공유)")

    @property
    def subject_prefix(self):
        return "교과서워크북"

    @property
    def template_name(self):
        return "typeset_textbook_workbook_v2.html"

    @property
    def upload_spec(self):
        from engines.textbook_workbook.engine import TextbookWorkbookEngine
        return TextbookWorkbookEngine().upload_spec

    # ── 교과서 메타 (v1 prepare_jsx와 동일 규칙) ────────────────────────────

    def _textbook_meta(self, job_dir):
        subject = self._read_meta_str(job_dir, "subject", "")
        publisher = self._read_meta_str(job_dir, "publisher", "")
        lesson = self._read_meta_str(job_dir, "lesson", "")
        pub_short = publisher
        if subject and publisher.startswith(subject):
            pub_short = publisher[len(subject):].strip()
        return subject, pub_short, lesson

    # ── 1단계: parse — v1 완전 위임 (GDrive 복사 + 파서) ────────────────────

    def parse(self, uploaded_files, job_dir, log):
        from engines.textbook_workbook.engine import TextbookWorkbookEngine
        return TextbookWorkbookEngine().parse(uploaded_files, job_dir, log)

    # ── WorkbookV2Engine 훅 오버라이드 ──────────────────────────────────────

    def _load_cfg(self):
        return _load_v1_config()

    def _workbook_type(self, job_dir):
        return "교과서"

    def _output_name(self, job_dir, grade, year, month, workbook_type,
                     school):
        """v1 규칙({subject}_{pub}_{lesson}_전체(C)(학교)) + _v2 접미."""
        subject, pub_short, lesson = self._textbook_meta(job_dir)
        school_suffix = f"({school})" if school else ""
        return f"{subject}_{pub_short}_{lesson}_전체(C){school_suffix}_v2.indd"

    def _select_template(self, cfg, workbook_type, school, log):
        """학교 키 → "_default" 폴백 (v1 동일, 구버전 문자열 config 호환)."""
        indd_orig = cfg.get("indd_original", "")
        if isinstance(indd_orig, dict):
            src = ""
            if school:
                src = indd_orig.get(school, "")
                if src:
                    log(f"[내지] 학교 전용 템플릿: {school}")
            if not src:
                src = (indd_orig.get("_default", "")
                       or indd_orig.get("모의고사", ""))
        else:
            src = indd_orig
        if not src or not os.path.exists(src):
            raise FileNotFoundError(f"내지 원본 없음: {src}")
        return src

    def _plan_decorations(self, job_dir, cfg):
        """v1 run.jsx 16.7(간지) + 16.8(빈 페이지 마스터 재할당) opt-in
        + 완제품 후처리 op 2종 (W13 — c13/c15 실조판 실증).

        교과서 원고는 지문 2~5개인데 내지([원본]워크북_C)는 모의고사 18지문
        규격이라, 실기에서 모의고사 잔재 지문번호 프레임 17종(20~45)과
        내용 없는 스텝 페이지 200개+가 잔존했다 (게이트 G3/G4 warning 실증).
        supp(W11)/ebs(W12)와 동일하게 page_cleanup(잔여 페이지 삭제 + 빈
        STEP3 페이지 M 마스터)과 passage_numbers(독립 지문번호 프레임을
        원고 지문번호로 갱신)를 opt-in한다. 간지 페이지는 단일 프레임이라
        page_cleanup 삭제 판정(다중 프레임 스토리 전부 빈)에 걸리지 않고,
        textbook_postprocess(16.8)는 잔존 빈 페이지에만 동작한다."""
        from engines.workbook_v2.plan import passage_labels
        subject, pub_short, lesson = self._textbook_meta(job_dir)
        deco = {
            "divider": {"line1": f"{subject} {pub_short}".strip(),
                        "line2": lesson},
            "textbook_postprocess": True,
            "page_cleanup": {"empty_master": "M"},
        }
        try:
            content = json.load(open(os.path.join(job_dir, "content.json"),
                                     encoding="utf-8"))
            labels = passage_labels(content.get("steps", {}))
        except (OSError, ValueError):
            labels = []
        # W14 D3: 교과서 step3(textbook 항목)는 지문번호 라벨 개념이 없다 —
        # step3 콘텐츠 페이지에 남는 모의고사 문항번호 잔재 프레임('20' 등)을
        # 삭제한다 (c03 서술형 step3 단독 실증). 라벨이 있으면 기존 갱신도
        # 그대로 수행 (실행기는 labels/steps가 비면 갱신을 생략하고
        # clear_steps만 처리).
        deco["passage_numbers"] = {"labels": labels,
                                   "steps": list(_NUMBER_FRAME_STEPS),
                                   "clear_steps": ["step3"]}
        return deco
