"""워크북 v2 엔진 — 새 아키텍처 세 번째 운영 래퍼 (blackbook_v2 패턴).

파이프라인: v1 파서 재사용(parse_manuscript_folder — kind 주석 포함 산출)
→ wb-flows 렌더 플랜(engines/workbook_v2/plan.py — 12스텝 전부 파이썬 빌더)
→ workbook_flow JSX(실행만) → 검수 게이트 내장(플랜 단어 보존/미지원 스텝/
오버플로우/PDF).

v1(engines/workbook) 무변경. 출력 파일명 v1 규칙 + _v2 접미로 공존.
템플릿/출력 경로는 v1의 engines/workbook/config.json을 공유한다.
"""
import glob
import json
import os
import re
import unicodedata

from core.base import BaseEngine, safe_copy_indd, safe_copy
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config
from engines.workbook_v2 import routing as _routing

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "workbook", "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                            "core", "jsx", "workbook_flow.body.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def _is_variant_pool_filename(fname_nfc):
    """변형문제 문제모음 (W12/W14) — 공용 라우터(routing.py)로 위임 (배치 A)."""
    return _routing.is_variant_pool_filename(fname_nfc)


def _routes_to_step3(fname_nfc):
    """업로드 파일명 → Step3 폴더 라우팅 여부.

    배치 A (W33): 판정을 공용 라우터(engines/workbook_v2/routing.py)로 위임 —
    토큰 정규화(공백/언더스코어/0패딩/NFC) 후 판정해 'STEP 03'·'177 문제'·
    '변형 문항' 같은 토씨 변형에 견딘다 (감사 실증 #4 해소). 정답/답지류
    (W13 c05)와 스텝1/2 접두(W18 D3)는 차단. 판정 이력 주석은 routing.py 참조."""
    return _routing.route_step3(fname_nfc)


def _norm_typo(s):
    """타이포그래피 정규화 — InDesign이 곧은따옴표를 굽은따옴표(’“”),
    하이픈을 대시로 자동 치환하므로 단어 대조 전에 통일한다."""
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"'))


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["indd_output_dir", "indd_original",
                                "manuscript_base", "completed_base"])


def _mockexam_divider(job_dir):
    """모의고사 간지 divider op (W19 D4 — v1 run.jsx 16.7 파리티).

    content.json의 grade/year/month로 '고N 모의고사 / YY년 M월' 라인을
    만든다 (v1과 동일 포맷 — 월 zero-pad 없음). 값이 없으면 미적용."""
    try:
        content = json.load(open(os.path.join(job_dir, "content.json"),
                                 encoding="utf-8"))
        g, y, m = (content.get("grade"), content.get("year"),
                   content.get("month"))
    except (OSError, ValueError):
        return {}
    if not (g and y and m):
        return {}
    # 선택 워크북(여러 회차 문항 병합)은 회차 한 개로 표기할 수 없다.
    # merge_select 가 넣은 표식이 있으면 2행(회차)을 비운다 — 첫 코드의
    # year/month 를 그대로 쓰면 "23년 11월" 처럼 실제와 다른 회차가
    # 간지에 찍힌다 (2026-08-06 실측: 10개 회차 혼합본).
    if content.get("_mixed_rounds"):
        return {"divider": {"line1": f"고{g} 모의고사", "line2": ""}}
    return {"divider": {"line1": f"고{g} 모의고사",
                        "line2": f"{y}년 {m}월"}}


class WorkbookV2Engine(BaseEngine):

    # W13 c05 실측(고1 25-10 전체 업로드 — 284p 전량 콘텐츠): PDF export가
    # 로그 무갱신 20분+, 전체 렌더 40분+. 기존 timeout 1800/stall 900이면
    # 정상 export 중 행 오탐 강제종료(유령 모달 사고 재발 경로) — 워크북
    # 계열만 상향 (다른 엔진 기본값 무변경, 진짜 행은 최종 timeout이 차단).
    jsx_timeout = 3600

    @property
    def material_id(self):
        return "workbook_v2"

    @property
    def display_name(self):
        return "워크북 v2 (베타)"

    @property
    def description(self):
        return "워크북 조판 v2 — 데이터 플랜 + 자동 검수 (신규 아키텍처)"

    @property
    def subject_prefix(self):
        return "워크북"

    @property
    def template_name(self):
        return "typeset_workbook_v2.html"

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "manuscripts",
                    "label": "원고 파일 (Step1~3 전체 · PDF는 Step3만)",
                    "required": True,
                    "multiple": True,
                    "accept": ".docx,.hwp,.hwpx,.pdf",
                },
            ]
        }

    # ── 유틸리티 (v1 WorkbookEngine과 동일 메타 규칙) ───────────────────────

    def _read_meta(self, job_dir, key, default=None):
        p = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(p):
            val = open(p).read().strip()
            digits = re.sub(r"[^0-9]", "", val)
            if digits:
                return int(digits)
            try:
                return int(val)
            except ValueError:
                return default
        return default

    def _read_meta_str(self, job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p).read().strip() if os.path.exists(p) else default

    def _read_exclude(self, job_dir):
        exclude_path = os.path.join(job_dir, "exclude.txt")
        if not os.path.exists(exclude_path):
            return []
        raw = open(exclude_path, encoding="utf-8").read().strip()
        return [s.strip() for s in raw.split(",") if s.strip()]

    # ── 1단계: 원고 폴더 → content.json (v1 파서 재사용) ────────────────────

    def parse(self, uploaded_files, job_dir, log):
        from engines.workbook.parser import parse_manuscript_folder

        staged_root = None
        # 업로드 파일 분류 — v1 WorkbookEngine.parse와 동일 (Step3 판정 포함)
        manuscripts = uploaded_files.get("manuscripts")
        if isinstance(manuscripts, list):
            manuscript_dir = os.path.join(job_dir, "uploads")
            os.makedirs(manuscript_dir, exist_ok=True)
            step3_dir = os.path.join(manuscript_dir, "Step3")
            os.makedirs(step3_dir, exist_ok=True)
            staged_root = set()
            for fpath in manuscripts:
                fname = os.path.basename(fpath)
                if fname.startswith("manuscripts_"):
                    fname = fname[len("manuscripts_"):]
                fname_nfc = _nfc(fname).strip()
                if _routes_to_step3(fname_nfc):
                    # 배치 A: v1 소비 규칙('N번.<ext>')에 맞는 규격명으로
                    # 스테이징 ('20번 (수정).docx' 침묵 누락 — 감사 실증 #1)
                    fname_nfc = _routing.stage_step3_name(step3_dir,
                                                          fname_nfc, log)
                    dest = os.path.join(step3_dir, fname_nfc)
                else:
                    dest = os.path.join(manuscript_dir, fname_nfc)
                    staged_root.add(fname_nfc)
                if fpath != dest:
                    safe_copy(fpath, dest)
        elif isinstance(manuscripts, str) and os.path.isdir(manuscripts):
            manuscript_dir = manuscripts
        else:
            manuscript_dir = uploaded_files.get("manuscript_folder", "")

        if not manuscript_dir or not os.path.isdir(manuscript_dir):
            raise ValueError(f"원고 폴더를 찾을 수 없습니다: {manuscript_dir}")

        grade = self._read_meta(job_dir, "grade", 1)
        year = self._read_meta(job_dir, "year", 25)
        month = self._read_meta(job_dir, "month", 10)
        cfg = self._parse_config(_load_v1_config(), log)

        log(f"[v2 파서] 시작 (v1 파서 재사용): 고{grade} {year}년 {month}월")
        # W77 (사용자 지시 2026-08-27): 원고 본문 그림(도표/그래프) 추출.
        # **잡 폴더 안**으로만 뽑는다 — 원고 폴더는 구글 드라이브일 수 있고
        # 드라이브 파일에는 절대 쓰지 않는다.
        image_dir = os.path.join(job_dir, "assets")
        data = parse_manuscript_folder(manuscript_dir, cfg, grade, year,
                                       month, log, image_dir=image_dir)
        _n_img = sum(1 for _it in ((data.get("steps") or {})
                                   .get("step3") or {}).get("normal", []) or []
                     for _p in _it.get("paragraphs", []) or []
                     if _p.get("image"))
        if _n_img:
            log(f"[v2 파서] 원고 그림 {_n_img}개 추출 → {image_dir}")

        # W82: 스텝1/2 어디에도 안 실린 루트 원고를 구조로 재판정 → Step3 구제.
        # 부교재 Step3 원고는 책 제목으로 이름이 붙어(‘수능만만 기본문법 PART1
        # 09 관계사.docx’ — job 4b8b05f8) 파일명 라우터가 못 잡고, 스텝1/2
        # 매칭에도 안 걸려 Step3가 통째로 0유닛이 됐다. 파싱 **결과**를 기준
        # 으로 미소비 파일을 가려 '문항 모음' 구조면 Step3로 옮기고 재파싱한다.
        # 원고 폴더를 **직접** 가리킨 경우(staged_root is None)에는 구제하지
        # 않는다 — 그 폴더는 구글 드라이브일 수 있고 드라이브 파일에는 절대
        # 쓰지 않는다. 폴더 입력은 Step3 하위 폴더가 실물로 있으므로 구제할
        # 이유도 없다 (구제는 폴더 구조를 잃는 업로드 경로의 문제다).
        rescued = (_routing.rescue_unrouted_step3(
            manuscript_dir, data, log, candidates=staged_root)
            if staged_root is not None else [])
        if rescued:
            data = parse_manuscript_folder(manuscript_dir, cfg, grade, year,
                                           month, log, image_dir=image_dir)
            log(f"[v2 파서] Step3 구제 후 재파싱: {len(rescued)}개 "
                f"({', '.join(rescued)})")

        # 배치 A (W33): Step3 '입력 파일 전수 ↔ 라우팅 결과' 쌍방 대조 —
        # 어느 문항에도 실리지 않은 원고가 남으면 [오류] 조판 중단 (침묵 금지)
        mock = cfg.get("mockexam") or {}
        _routing.reconcile_step3(
            os.path.join(manuscript_dir, "Step3"),
            (data.get("steps") or {}).get("step3"), log,
            number_matching=bool(mock.get("normal_questions")
                                 or mock.get("short_questions")))

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"[v2 파서] 완료: {len(data.get('steps', {}))}개 STEP")
        # W68: 원고 자체의 정합성을 조판 '전에' 본다 — 잘못된 파일/다른 강
        # 원고가 섞이면 여기서 [원고이상]으로 뜬다 (사용자 육안 검수 대체)
        try:
            from engines.workbook_v2.gate import (
                inspect_manuscript_consistency)
            inspect_manuscript_consistency(data, log=log)
        except Exception as e:                                 # noqa: BLE001
            log(f"[교차검증] 원고 검사 실패(무시하고 진행): {e}")
        return json_path

    # ── 파생 엔진 훅 (workbook_supp_v2 등이 오버라이드 — 기본은 v1 규칙) ────

    def _output_name(self, job_dir, grade, year, month, workbook_type,
                     school):
        """출력 .indd 파일명 — v1 워크북 규칙 + _v2 접미."""
        yy = str(year)[-2:]
        mm = str(month).zfill(2)
        return f"고{grade}_{yy}년_{mm}월_전체_v2.indd"

    def _select_template(self, cfg, workbook_type, school, log):
        """원본 indd 선택 — v1과 동일: 학교 전용 템플릿 우선 → 유형 기본."""
        indd_map = cfg.get("indd_original", {})
        src = ""
        if school:
            src = indd_map.get(f"{workbook_type}_{school}", "")
            if src:
                log(f"[내지] 학교 전용 템플릿: {school}")
        if not src:
            src = indd_map.get(workbook_type, "")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(
                f"내지 원본 없음: {src or workbook_type} "
                f"(workbook_type={workbook_type}, school={school})")
        return src

    def _load_cfg(self):
        """엔진 config 로드 — 파생 엔진(교과서/EBS/수능특강)이 오버라이드."""
        return _load_v1_config()

    def _parse_config(self, cfg, log):
        """파싱에 쓸 config — 파생 엔진이 조정할 수 있는 훅 (기본 무변경).

        parse()는 종전부터 _load_v1_config()(모의고사 config)를 직접 써
        왔고 _load_cfg 훅을 타지 않는다. 그 규칙 자체는 유지하되(파생
        엔진의 파싱 동작을 통째로 바꾸면 회귀 범위가 너무 넓다), 계열별로
        분명히 틀린 항목만 이 훅에서 좁게 고칠 수 있게 한다.
        부교재(workbook_supp_v2)가 mockexam.short_questions를 비우는 것이
        첫 사용처 — 2026-09-08 사용자 실증."""
        return cfg

    def _workbook_type(self, job_dir):
        """원고 유형 — 기본은 v1 워크북 메타 규칙. 파생 엔진은 고정값."""
        return self._read_meta_str(job_dir, "workbook_type", "모의고사")

    def _step_map(self):
        """스텝→스토리 매핑 override — None이면 모의고사 기본 STEP_MAP.
        EBS/수능특강 파생 엔진이 내지 구조에 맞는 매핑을 반환한다."""
        return None

    def _plan_decorations(self, job_dir, cfg):
        """플랜 최상위에 병합할 선택 키 (실행기 opt-in op).

        본가(모의고사)는 page_cleanup — c05(고1 25-10) 실기에서 내용
        없는 스텝 페이지 22개 잔존 (게이트 G4 warning 실증, W13).
        passage_numbers는 미적용: 모의고사 내지의 번호 프레임(20~45)이
        원고 문항번호와 정합이라 갱신 이득이 없다 (G3 clean 실측).
        divider(W19 D4): v1 run.jsx 16.7은 간지 '고N 모의고사 / YY년 M월'
        을 원고 값으로 갱신하는데 v2 본가는 미적용이라 [원본] 템플릿
        잔재('고2 모의고사 / 26년 3월')가 그대로 납품됐다 (c20 실증 +
        c04/c05 소급 검출 — 게이트 G22). 파생 엔진(supp/교과서/EBS)은
        이 훅을 전부 오버라이드하고 수능특강/세로는 자체 prepare라
        미호출 — 이 변경은 본가 전용.
        question_keep(W23 r13 F4): 문제 단위 펼침면 킵 — step3 문제가
        오른쪽 페이지에서 잘려 다음 장으로 이어지면 다음 페이지로 밀기.
        True 센티널은 prepare_jsx가 플랜 완성 후 question_keep_op로
        확장한다 (opt-in — supp+본가만 활성, 파생 엔진 플랜 무변경)."""
        deco = {"page_cleanup": {"empty_master": "M"},
                "question_keep": True}
        deco.update(_mockexam_divider(job_dir))
        # W40 결함 7 — 지문번호 프레임 갱신. 본가는 "내지 번호 프레임(20~45)이
        # 원고 문항번호와 정합"이라 미적용이었는데, 그 전제는 단일 회차
        # 워크북에서만 성립한다. 다회차 선택 워크북(workbook_select)은 라벨이
        # YYMMQQ 6자리라 템플릿의 20~40이 그대로 남아 인쇄됐다 (게이트 G3
        # v15 실증: p89~105/125~141/142~158 에 17개씩 3구간 잔존).
        # 라벨이 평문 문항번호(3자리 이하 숫자)면 기존대로 미적용 — 단일 회차
        # 동작 무변경.
        from engines.workbook_v2.plan import passage_labels
        try:
            content = json.load(open(os.path.join(job_dir, "content.json"),
                                     encoding="utf-8"))
        except (OSError, ValueError):
            content = {}
        # 조건은 반드시 "다회차 선택 워크북"으로 좁힌다. 라벨 모양으로
        # 판정하면(숫자/자릿수) 평범한 회차 워크북도 '41~42' 같은 묶음 라벨
        # 하나 때문에 발동해 18개 실측 job 중 16개가 걸렸다 — 프레임과
        # 원고가 이미 정합인 문서까지 갱신하게 되는 광범위 동작 변경.
        # 상위 엔진(workbook_select)이 확정한 지문번호가 있으면 그대로 쓴다 —
        # 마더텅 워크북은 엑셀의 강별 행번호가 지문번호이며, 코드에서 유도할
        # 수 없다 (짝수만 뽑힌 워크북이면 2,4,6…).
        labels = list(content.get("_passage_labels") or [])
        if labels:
            deco["passage_numbers"] = {"labels": labels,
                                       "steps": ["step1_c2", "step2_b1",
                                                 "step2_c1"]}
            return deco
        labels = passage_labels(content.get("steps", {}) or {})
        if labels:
            # 사용자 확정 스펙: 프레임에는 문항번호만 남긴다 — 모의고사
            # 코드 YYMMQQ 의 뒤 2자리(QQ). 250621 -> 21, 240340 -> 40.
            # 6자리라 프레임(2자리 폭)이 넘치던 문제도 이걸로 해소된다.
            # 마더텅(비 6자리)은 대상 아님 — 추후 마더텅 번호로 별도 처리.
            # 2026-09-08: 축약을 _mixed_rounds 밖으로 뺀다. 단일 회차
            # 선택 워크북(job 9b542423)도 라벨이 6자리 코드('260632')인데,
            # 아래 갱신이 상시가 되면서 그대로 2자리 폭 프레임에 들어가게
            # 됐다 — 축약 조건이 갱신 조건과 어긋나 있던 것.
            labels = [s[-2:] if re.fullmatch(r"\d{6}", s) else s
                      for s in labels]
            # 2026-09-08 (사용자 지적 "통합웹 워크북 중 지문번호 프레임이
            # 안 바뀌는 게 있다"): 단일 회차 워크북도 **항상** 갱신한다.
            # 위 '정합이라 갱신 이득이 없다'는 전제가 틀렸다 — 모의고사
            # 워크북은 회차마다 뽑는 문항이 달라서 템플릿 기본값(20,21,
            # 22,23)과 어긋난다. 실측: job 58f334d0(고1 26년 9월) 원고
            # 지문번호 30·33·34·38 인데 프레임 4개가 20~23 그대로 인쇄,
            # job 42e0bf1f(고2 26년 9월) 원고 21~24 에 '20' 잔존.
            # 갱신이 정합인 문서에서는 같은 값을 다시 쓰므로 무해하고,
            # 같은 내지([원본]워크북(모의고사)_내지)·같은 실행기를 쓰는
            # 부교재(workbook_supp_v2)가 이 op를 상시 켠 채 정상 동작해
            # 왔다는 것이 근거다. 범위 라벨('41~42')도 실행기
            # RE_BARE_NUM/템플릿 프레임('41-42')이 이미 수용한다.
            deco["passage_numbers"] = {"labels": labels,
                                       "steps": ["step1_c2", "step2_b1",
                                                 "step2_c1"]}
        return deco

    # ── 2단계: prepare_jsx — 플랜 빌드 + 템플릿 복사 + JSX 생성 ─────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.workbook_v2.plan import (steps_to_plan,
                                              ensure_step3_kinds,
                                              question_keep_op,
                                              choice_tabs_op,
                                              normalize_choice_tabs)

        cfg = self._load_cfg()
        grade = self._read_meta(job_dir, "grade", 1)
        year = self._read_meta(job_dir, "year", 25)
        month = self._read_meta(job_dir, "month", 10)
        workbook_type = self._workbook_type(job_dir)
        school = self._read_meta_str(job_dir, "school", "")
        exclude = self._read_exclude(job_dir)
        if exclude:
            log(f"[v2] 제외 섹션: {', '.join(exclude)}")

        content = json.load(open(json_path, encoding="utf-8"))
        ensure_step3_kinds(content.get("steps", {}).get("step3"), log)
        # 훅 컨텍스트 (W19): _step_map이 선택될 내지(학교 전용 템플릿)에 따라
        # 매핑을 달리할 수 있도록 스냅샷 제공 (예: supp 세종 내지는 '내용
        # 종합' 섹션이 없어 step1_b2를 미지원 보고해야 한다). 기본 구현은
        # 미사용 — 기존 엔진 동작 무변경.
        self._plan_ctx = {"cfg": cfg, "school": school,
                          "workbook_type": workbook_type, "job_dir": job_dir}
        plan = steps_to_plan(content.get("steps", {}), exclude=exclude,
                             workbook_type=workbook_type,
                             step_map=self._step_map())
        plan.update(self._plan_decorations(job_dir, cfg))
        # W51 (job 0645d4a7 실증): 제외/미지원 스텝의 섹션 마커 텍스트를
        # page_cleanup에 전달 — 제외 섹션 첫 페이지의 러닝헤더 마커 프레임
        # ('내용 종합' 등)이 '텍스트 있는 프레임'으로 삭제 판정을 비껴가
        # 빈 섹션 페이지가 잔존했다. 실행기는 이 텍스트와 일치하는 단일
        # 프레임을 빈 프레임으로 취급한다 (플로우 콘텐츠 페이지의 같은
        # 마커는 페이지에 콘텐츠가 있어 삭제 판정 자체가 안 걸린다).
        if isinstance(plan.get("page_cleanup"), dict):
            from engines.workbook_v2.plan import STEP_MAP as _DEFAULT_STEP_MAP
            placed = {fl["step"] for fl in plan.get("flows", [])}
            smap = self._step_map() or _DEFAULT_STEP_MAP
            ex_markers = sorted({
                (v.get("marker") or "").strip()
                for k, v in smap.items()
                if k not in placed and isinstance(v, dict) and v.get("marker")})
            ex_markers = [m for m in ex_markers if m]
            if ex_markers:
                plan["page_cleanup"]["excluded_markers"] = ex_markers
                log("[v2] 제외 섹션 마커 정리 대상: " + ", ".join(ex_markers))
        # W23 r13 F4 — question_keep 센티널(True) 확장: 데코 훅은 플랜
        # (flows)을 못 보므로 여기서 문제 시작 인덱스/스타일 계약을 계산해
        # 치환한다 (대상 스텝에 시작점이 없으면 키 제거 — 실행기 no-op).
        if plan.get("question_keep") is True:
            qk = question_keep_op(plan)
            if qk:
                plan["question_keep"] = qk
                log("[v2] 문제단위킵: step3 문제 시작 "
                    + str(sum(len(v.get("starts") or [])
                              for v in qk["flows"].values())) + "개 계약")
            else:
                plan.pop("question_keep", None)
        # W40 결함 1 — 다열 선지 열 정렬 계약. question_keep 과 같은 이유로
        # 데코 훅이 flows 를 못 보므로 여기서 계산해 얹는다.
        nz = normalize_choice_tabs(plan)
        if nz:
            log(f"[v2] 선지탭정규화: {nz}단락 (연속탭/선행공백 접기)")
        ct = choice_tabs_op(plan)
        if ct:
            plan["choice_tabs"] = ct
            log("[v2] 선지열정렬: " + ", ".join(ct["steps"])
                + " 탭 선지 " + str(ct.pop("_rows")) + "단락 계약")
        plan_path = os.path.abspath(os.path.join(job_dir, "render_plan.json"))
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)
        log("[v2] 플랜: " + ", ".join(
            f"{fl['step']} {len(fl['units'])}유닛" for fl in plan["flows"]))
        # W74: 지문 수 교차검증(M3)을 **조판 전에** 본다. 예전에는 verify
        # (완제품 게이트)에서만 돌아, 지문번호 인식이 깨진 채로 InDesign이
        # 40분을 돌고 나서야 알 수 있었다. 여기서는 중단하지 않고 알린다 —
        # 스텝별 지문 수가 다를 수 있는 원고도 있기 때문 (판단은 사람).
        try:
            from engines.workbook_v2.gate import inspect_plan_units
            _pc, _pw, _ps = inspect_plan_units(plan)
            for _m in _pc:
                log("⚠️ [조판전검수] " + _m)
        except Exception as _e:                                # noqa: BLE001
            log(f"[조판전검수] 유닛 수 교차검증 실패(무시): {_e}")
        if plan["unsupported"]:
            log(f"[v2] ⚠️ 미지원 스텝(렌더 제외): "
                + ", ".join(plan["unsupported"]))
        # 빈 플랜 조기 차단 (W12 — 게이트 G7과 동일 기준): 원고가 어느
        # 스텝에도 매핑되지 않았는데 InDesign을 돌려 '빈 완제품'이 성공으로
        # 남는 침묵 유실 방지.
        if not any(fl["units"] for fl in plan["flows"]):
            raise ValueError(
                "렌더할 유닛이 0개입니다 — 업로드 원고가 어느 스텝에도 "
                "매핑되지 않았습니다 (파일명/폴더 규칙 확인)")

        # 출력 파일명: v1 규칙 + _v2 접미 (파생 엔진은 _output_name 오버라이드)
        out_name = self._output_name(job_dir, grade, year, month,
                                     workbook_type, school)
        indd_path = os.path.join(cfg["indd_output_dir"], out_name)

        # 원본 indd 선택 (파생 엔진은 _select_template 오버라이드)
        src = self._select_template(cfg, workbook_type, school, log)
        os.makedirs(os.path.dirname(indd_path), exist_ok=True)
        indd_path = safe_copy_indd(src, indd_path)
        log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")

        pdf_path = indd_path.replace(".indd", ".pdf")
        jsx_log = os.path.abspath(os.path.join(job_dir, "조판_로그.txt"))
        jsx_path = build_jsx(
            _RENDER_BODY,
            {"__TEMPLATE_PATH__": indd_path, "__PLAN_PATH__": plan_path,
             "__OUT_INDD__": indd_path, "__OUT_PDF__": pdf_path},
            log_path=jsx_log,
            out_path=os.path.join(job_dir, "run.jsx"))

        settings = {"engine": self.material_id, "indd_path": indd_path,
                    "pdf_path": pdf_path, "jsx_path": jsx_path,
                    "log_path": jsx_log, "json_path": json_path,
                    "plan_path": plan_path,
                    "unsupported": plan["unsupported"],
                    "workbook_type": workbook_type,
                    "output_dir": job_dir}
        with open(os.path.join(job_dir, ".settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return os.path.join(job_dir, ".settings.json")

    # ── 3단계: run_indesign ─────────────────────────────────────────────────

    def run_indesign(self, job_dir, log):
        from core.indesign.runner import run_jsx
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        # 재실행 안전 (seseospecial_v2 W7 교훈): 이전 실행의 조판_로그에 완료
        # 마커가 남아 있으면 러너가 렌더 시작 직후 조기 완료로 오판 → 이후
        # dump 제출 실패 → 재시도 pkill이 렌더 중인 InDesign을 죽인다.
        # 러너는 1차 시도에서 poll 로그를 지우지 않으므로 여기서 제거한다.
        # (실서비스는 job_dir가 매번 새로 생성돼 no-op — E2E 재실행용 안전망)
        try:
            os.remove(settings["log_path"])
        except OSError:
            pass
        # stall_limit 2700: 워크북 전체(C) 문서의 doc.save + PDF export가
        # 로그 무갱신으로 길게 이어진다 (W4 실측 5분+ → 900, W13 c05 실측
        # 20분+ — 900이면 정상 export 중 행 오탐 강제종료 = 유령 모달 사고
        # 재발 경로). JSX가 저장/export 직전 하트비트를 남기므로 무갱신
        # 구간은 해당 단계 소요만큼이다. 진짜 행은 timeout(3600)이 차단
        # (timeout 경로는 InDesign을 죽이지 않는다 — 킬 루프 금지).
        run_jsx(settings["jsx_path"], log, poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="워크북 v2 조판 완료",
                stall_limit=2700)

    # ── 4단계: verify — 검수 게이트 내장 ────────────────────────────────────

    def verify(self, job_dir, log):
        from core.inspect import dump_indd
        from engines.workbook_v2.plan import unit_paras
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        plan = json.load(open(settings["plan_path"], encoding="utf-8"))

        dump = dump_indd(settings["indd_path"],
                         os.path.join(job_dir, "typeset_dump.json"), log)
        got = set()
        overflow = 0
        for st in dump["stories"]:
            for pp in st["paragraphs"]:
                for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                    got.add(w.lower())
            if st.get("overflow"):
                overflow += 1

        # (a) 스텝별 플랜 단어 보존
        warnings = []
        ok = True
        total_missing = 0
        for flow in plan["flows"]:
            want = set()
            for u in flow["units"]:
                for p in unit_paras(u):
                    for w in _RE_WORD.findall(_norm_typo(p["t"])):
                        want.add(w.lower())
            missing = want - got
            total_missing += len(missing)
            if missing:
                ok = False
                warnings.append(
                    f"❌ {flow['step']} 내용누락 {len(missing)}단어: "
                    + ", ".join(sorted(missing)[:8]))

        # (b) 미지원 스텝 보고
        if settings.get("unsupported"):
            warnings.append("⚠️ 미지원 스텝(렌더 제외): "
                            + ", ".join(settings["unsupported"]))

        # (c) 오버플로우 — v2 시리즈 규칙: 경고(검수가 위치 지목, 수동 처리)
        if overflow:
            warnings.append(f"⚠️ 오버플로우 스토리 {overflow}개 (수동 처리)")

        # (d) PDF
        pdf_ok = os.path.exists(settings["pdf_path"])
        if not pdf_ok:
            ok = False
            warnings.append("❌ PDF 미생성")

        # (e) 완제품 게이트 (W11 — 헤더/정답 잔존, 지문번호 프레임,
        #     잔여 페이지, 상/하단 배치, 파싱 계층 경고). 게이트 자체 오류는
        #     경고로 강등 (조판을 막지 않는다 — fail-open).
        try:
            from engines.workbook_v2.gate import inspect_workbook_finish
            content = json.load(open(settings["json_path"],
                                     encoding="utf-8"))
            rep = inspect_workbook_finish(
                content, plan, dump,
                uploads_dir=os.path.join(job_dir, "uploads"))
            for fn in rep["stats"].get("unused_uploads_expected") or []:
                log(f"[검수] 미사용 원고(정답/답지류 — 의도된 제외): {fn}")
            if rep["critical"]:
                ok = False
                warnings.extend(f"❌ {c}" for c in rep["critical"])
            warnings.extend(f"⚠️ {w}" for w in rep["warnings"])
            log(f"[검수] 완제품 게이트: critical {len(rep['critical'])} / "
                f"warning {len(rep['warnings'])}")
        except Exception as e:                                  # noqa: BLE001
            warnings.append(f"⚠️ 완제품 게이트 실행 실패: {e}")

        # (f) 기준 완성본 대조 — 파생 엔진이 훅을 구현하면 실행 (기본 no-op).
        #     "기존 파일을 보고 거기에 맞추면 된다"(사용자 반복 지침)를
        #     육안이 아니라 검수 단계에서 자동으로 수행한다.
        try:
            hook = getattr(self, "_reference_findings", None)
            if hook:
                warnings.extend(hook(job_dir, dump, log))
        except Exception as e:                                  # noqa: BLE001
            warnings.append(f"⚠️ 기준대조 실행 실패: {e}")

        # 플랜 빌더 경고 (헤더 미인식 등 — steps_to_plan이 수집)
        warnings.extend(f"⚠️ 플랜: {w}"
                        for w in (plan.get("warnings") or [])[:5])

        render_warns = [l.strip() for l in open(settings["log_path"],
                                                encoding="utf-8")
                        if "[경고]" in l]
        warnings.extend(f"⚠️ {w}" for w in render_warns[:5])

        log(f"[검수] 플랜 {len(plan['flows'])}스텝 / 누락 {total_missing} / "
            f"오버플로우 {overflow} / PDF {'OK' if pdf_ok else '실패'}")
        return {
            "ok": ok,
            "overflow": overflow,
            "stories": {},
            "pdf_path": settings["pdf_path"] if pdf_ok else None,
            "indd_path": settings["indd_path"],
            "warnings": warnings,
        }
