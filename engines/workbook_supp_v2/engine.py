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
import re
import unicodedata

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

# 외부지문 무-p형 헤더 "1. no.1" (W22 r12 — 간지 교재유형 판정용.
# 게이트 _RE_NOP_HEADER와 동일 패턴이나 독립 정의 — 게이트는 출력 검사용
# 정의를 따로 유지한다: 생산 코드가 틀리면 게이트도 같이 틀리는 순환 방지)
_RE_NOP_HEADER = re.compile(r"^\s*\d+\s*[.)]\s*no\.?\s*\d+(?:~\d+)?\s*$",
                            re.I)
# W23 r13 F1 — 교재유형 판정 강화 (job 6c1430c3 실증: '[N과 추가지문]'
# bracket 헤더 원고가 무-p형 감지에 안 잡혀 간지가 메타 기본 '모의고사'로
# 추락). 추가지문형 헤더("[3과 추가지문]" 단독 단락, p형 "p1-no.3과
# 추가지문" 꼬리 포함)와 업로드 파일/폴더명의 '외부지문' 토큰을 감지한다.
_RE_ADDU_HEADER = re.compile(
    r"^\[?\s*\d+\s*과\s*추가\s*지문\s*\]?$")
_RE_ADDU_TAIL = re.compile(r"\d+\s*과\s*추가\s*지문\s*(?:\([^)]*\))?\]?\s*$")
_RE_EXT_TOKEN = re.compile(r"외부\s*지문")


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

    @property
    def upload_spec(self):
        """W24 r14 (사용자 확정 스펙): 간지 두 줄 분리 입력 —
        line1(교재유형) + line2(디테일 범위), 둘 다 선택. 미입력이면
        교재유형만 자동 표기 (W22 단일 divider_text의 확장 — 기존 필드는
        하위호환으로 유지: 값이 오면 line1로 소비). 텍스트 슬롯은
        routes/typeset.py가 job_dir/{key}.txt로 저장한다 (새 라우트 없음
        — 기존 슬롯 처리 재사용)."""
        spec = dict(super().upload_spec)
        spec["slots"] = list(spec["slots"]) + [{
            "key": "divider_line1",
            "label": "간지 첫 줄 — 교재유형 (선택, 미입력 시 자동 판정)",
            "type": "text",
            "required": False,
        }, {
            "key": "divider_line2",
            "label": "간지 둘째 줄 — 디테일 범위 (선택)",
            "type": "text",
            "required": False,
        }, {
            # W22 단일 입력 하위호환 (구 폼/캐시 페이지가 divider_text로
            # 보내면 line1로 소비 — UI에는 노출하지 않는다)
            "key": "divider_text",
            "label": "간지 문구 (구버전 하위호환 — line1로 소비)",
            "type": "text",
            "required": False,
        }]
        return spec

    # ── W11 훅: 스토리 매핑 + 완제품 후처리 op ──────────────────────────────

    def _template_token(self):
        """선택될 내지의 학교 토큰 ("세종" 등) — 없으면 "" (기본 내지).

        base prepare_jsx가 _plan_ctx로 제공하는 컨텍스트로 _select_template과
        동일하게 판정한다 (경로/사본 이름이 달라도 토큰은 보존)."""
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
            for token, _smap in _TEMPLATE_STEP_MAPS:
                if token in base:
                    return token
        return ""

    def _step_map(self):
        """supp 전용 step_map — step2_a1/btm pos(top/bottom) 기하 힌트.

        학교 전용 내지가 선택되는 경우 해당 내지의 스텝 카탈로그를 적용한다
        — 세종 내지는 step1_b2 미지원 (W19)."""
        token = self._template_token()
        for tk, smap in _TEMPLATE_STEP_MAPS:
            if tk == token:
                return smap
        return _STEP_MAP

    def _divider_deco(self, job_dir, content):
        """간지 divider op — W24 r14 두 줄 분리 입력 + W23 r13 판정 강화.

        간지는 line1(교재유형) + line2(디테일 범위) 구조 (사용자 확정
        스펙). 업로드 시 divider_line1/divider_line2 슬롯(둘 다 선택)을
        입력하면 그 문구로 간지를 갱신하고, line1 미입력이면 교재유형을
        자동 판정해 표기한다 (line2는 입력값 그대로 — 미입력 시 비움).
        W22 단일 divider_text는 하위호환: 값이 있으면 line1로 소비.
        교재유형 판정 사다리 (r13 F1 — job 6c1430c3 실증: '[N과 추가지문]'
        원고가 무-p형 감지에 안 잡혀 메타 기본 '모의고사'가 인쇄된 결함):
          ① 업로드 파일/폴더명 '외부지문' 토큰 → '외부지문'
          ② 무-p형 'N. no.M' 헤더 → '외부지문' (W22 기존)
          ③ 'N과 추가지문' 헤더(bracket 단독/p형 꼬리) → '외부지문'
             (r14 사용자 확정: 자동 판정 표기는 '추가지문'이 아니라
             '외부지문' — 게이트 G27이 '추가지문' 자동 표기 잔존을 감시)
          ④ workbook_type 메타가 '모의고사'가 아니면 그 값 (사용자가 폼
             에서 교과서/EBS 내지를 고른 신호)
          ⑤ 판정 불가 → 중립 '부교재' — supp에서 '모의고사'는 어떤 경우
             에도 자동으로 나가면 안 된다 (사용자 확정 스펙, 게이트 G27
             계약: source=type + '모의고사' = critical).
        source(user|type)는 line1의 출처 계약 — 게이트 G27이 소비한다
        (실행기는 line1/line2만 읽는다 — additive). line2는 source와
        무관한 사용자 입력 (자동 판정 line1 + 사용자 line2 조합 허용)."""
        line1 = (self._read_meta_str(job_dir, "divider_line1", "")
                 or self._read_meta_str(job_dir, "divider_text", ""))
        line2 = self._read_meta_str(job_dir, "divider_line2", "")
        if line1:
            return {"divider": {"line1": line1, "line2": line2,
                                "source": "user"}}
        return {"divider": {"line1": self._detect_supp_type(job_dir,
                                                            content),
                            "line2": line2, "source": "type"}}

    def _detect_supp_type(self, job_dir, content):
        """교재유형 실측 판정 — _divider_deco 사다리 ①~⑤ (docstring 참조)."""
        uploads = os.path.join(job_dir, "uploads")
        names = []
        if os.path.isdir(uploads):
            for root, dirs, files in os.walk(uploads):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                names.append(os.path.basename(root))
                names.extend(f for f in files if not f.startswith("."))
        if any(_RE_EXT_TOKEN.search(unicodedata.normalize("NFC", n))
               for n in names):
            return "외부지문"
        from engines.workbook_v2.plan import _norm_header
        steps = (content or {}).get("steps") or {}
        texts = [_norm_header(p.get("text") or "")
                 for sd in steps.values() if isinstance(sd, dict)
                 for p in (sd.get("paragraphs") or [])]
        if any(_RE_NOP_HEADER.match(t) for t in texts):
            return "외부지문"
        if any(_RE_ADDU_HEADER.match(t) or _RE_ADDU_TAIL.search(t)
               for t in texts):
            # r14 사용자 확정: 'N과 추가지문' 원고도 자동 표기는 '외부지문'
            return "외부지문"
        wt = self._workbook_type(job_dir)
        if wt and wt != "모의고사":
            return wt
        return "부교재"

    def _plan_decorations(self, job_dir, cfg):
        """완제품 후처리 op (실행기 opt-in — 다른 엔진 플랜 무변경).

        page_cleanup: 원고에 없는 스텝/남는 사이클 페이지 삭제 + 빈 STEP3
            페이지 M 마스터 재할당 (v1 run.jsx 16.5 + adjustStep3Pages 이식).
        passage_numbers: 빈칸어휘/어법OX/빈칸어법 섹션의 독립 지문번호
            프레임을 원고 지문번호로 갱신 (v1 미지원 — 완제품 기준 신설).
        divider: 간지 문구 — W22 r12 스펙 (_divider_deco 참조. v1 상속의
            '고N 모의고사/YY년 M월'(W19 D4)은 r12 피드백 3으로 폐기).
        """
        from engines.workbook_v2.plan import passage_labels
        # 세종 내지의 간지('세종고 …')는 간지-마스터 페이지라 updateDivider
        # 매칭 조건(마스터 [None]) 밖 — 무접촉 (c19 실측 pg=['간지']).
        # W21 r11 (실사용 0e3108fd 결함 전체-1/전체-2): 기본 내지([원본]
        # 워크북_C)는 ① 빈 STEP3 페이지를 M 마스터 보존 대신 삭제(delete
        # 모드 — 'M 보존' v1 관행은 완제품 기준으로 폐기 확정), ② 페이지
        # 정리 후 섹션 시작 페이지의 좌/우 마스터 변형 정합(section_masters
        # — 쌍 데이터는 step_map.json master_pair 계약). 학교 전용 내지
        # (세종 등)는 마스터 구성이 미실측이라 기존 동작 유지 (무접촉).
        if self._template_token():
            deco = {"page_cleanup": {"empty_master": "M"}}
        else:
            deco = {"page_cleanup": {"empty": "delete"},
                    "section_masters": True}
        # W23 r13 F4 — 문제 단위 펼침면 킵 (opt-in, base prepare_jsx가
        # True 센티널을 question_keep_op 계약으로 확장. W40 결함 2 —
        # question_keep_op가 stem_keep(발문 고아 방지 프레임판)을 포함)
        deco["question_keep"] = True
        # W40 결함 1 — 다열 선지 열 정렬 (v1 실물 실측: 기본 12.7mm 탭
        # 그리드 관행 — 실행기 applyChoiceTabs가 그룹별 최장 열 실측으로
        # 명시 탭스톱 부여). step3 실전문제 한정.
        deco["choice_tabs"] = {"steps": ["step3"], "style_contains": "선지",
                               "grid": 12.7, "min_gap": 2}
        try:
            content = json.load(open(os.path.join(job_dir, "content.json"),
                                     encoding="utf-8"))
        except (OSError, ValueError):
            content = {}
        deco.update(self._divider_deco(job_dir, content))
        labels = passage_labels(content.get("steps", {}) or {})
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
