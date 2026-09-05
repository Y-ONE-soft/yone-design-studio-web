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
  - _output_name: EBS_리딩파워_{단원}_전체_v2.indd
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

    # ── 1단계: parse — v1 위임 + 변형문제 문제모음 Step3 선라우팅 (W12) ─────

    def parse(self, uploaded_files, job_dir, log):
        from engines.ebs_workbook.engine import EbsWorkbookEngine
        return parse_with_step3_routing(EbsWorkbookEngine(), uploaded_files,
                                        job_dir, log)

    # ── WorkbookV2Engine 훅 오버라이드 ──────────────────────────────────────

    def _load_cfg(self):
        return _load_v1_config()

    def _workbook_type(self, job_dir):
        return "EBS"

    def _plan_decorations(self, job_dir, cfg):
        """완제품 후처리 op — page_cleanup opt-in (W12) + question_keep
        (W24 r14 확산).

        변형문제 문제모음(STEP3 단독) 실조판에서 원고 없는 STEP1/2 섹션
        페이지 24개 + 섹션 지문번호 프레임(01~04)이 잔존(게이트 warning)
        → 잔여 페이지 삭제 + 빈 STEP3 페이지 M 마스터(내지 실물에 M-마스터
        존재 확인). passage_numbers는 EBS 내지의 독립 번호 프레임 실물
        근거가 없어 미적용 (섹션 페이지 삭제로 함께 정리됨).

        W24 r14 확산 판정 (EBS리딩파워_내지 46p 실측 —
        data_corpus/round14/template_masters/ebs_dump.json + c16 재조판
        프로브 data_corpus/round14/c16_ebs_probe/):
          - question_keep 활성: step3 문제 단위 펼침면 킵 (r14 c16 실기
            밀기 5건, 게이트 G30 critical 0 — True 센티널은 base
            prepare_jsx가 계약으로 확장).
          - page_cleanup delete 활성: r14 c16 delete 프로브 critical 0/
            warning 0 (기지 overset 1 유지). delete가 기존 M-모드와
            다른 구간은 STEP3 영역(마지막 간지 이후)+장식-빈/꼬리
            페이지뿐이라 간지 정렬(내장 M p19 채움)이 구조적으로 보존
            — M-모드의 빈 M 페이지 2장이 삭제돼 24p→23p. 한계: EBS
            간지 라벨은 라틴 표기("EBS Reading Power")라 고아 간지/파트
            경계 자동 정렬의 판정 밖 — 빈 섹션 간지 잔존은 기존 동작
            그대로(무회귀)이고, 정렬 붕괴는 G28(delete critical)이 감시.
          - section_masters 보류: 섹션 시작 좌/우 쌍은 STEP1 = A/B로
            실측됐으나(우측 시작 p7/p13 = B-마스터) EBS v2 코퍼스가 전부
            STEP3 단독이라 실기 검증 불가 — step_map.json에 master_pair
            계약만 등재해 G26 warning 감시로 두고 op는 켜지 않는다."""
        return {"page_cleanup": {"empty": "delete"},
                "question_keep": True}

    def _step_map(self):
        return dict(_STEP_MAP)

    def _output_name(self, job_dir, grade, year, month, workbook_type,
                     school):
        """v1 규칙(EBS_리딩파워_{단원}_전체) + _v2 접미."""
        unit = self._read_meta_str(job_dir, "lesson", "")
        unit_short = re.sub(r"\s+", "", unit) if unit else "단원"
        return f"EBS_리딩파워_{unit_short}_전체_v2.indd"

    def _select_template(self, cfg, workbook_type, school, log):
        """단일 원본 indd (구버전 dict config 호환 — v1 동일)."""
        src = cfg.get("indd_original", "")
        if isinstance(src, dict):
            src = src.get("모의고사", "")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(f"내지 원본 없음: {src}")
        return src


def parse_with_step3_routing(v1_engine, uploaded_files, job_dir, log):
    """v1 파서 위임 전에 Step3 원고 업로드를 공용 라우터로 선라우팅.

    v1의 추가 업로드 Step3 판정은 파일명 "step3/스텝3/N번"만 인식해
    "…123문제 [변형문제]….hwp" 류 문제모음이 일반 폴더로 들어가 어느
    스텝에도 매핑되지 않고 조용히 유실된다 (W12 실증 — 게이트 G7).
    배치 A (W33): 판정을 공용 라우터(workbook_v2/routing.py)로 확장 —
    'STEP 03'·'177 문제'·'변형 문항' 토씨 변형 수용 + 정답/답지류가
    'N번.<ext>' 표기로 v1의 Step3 라우팅('번.hwp' in)에 오라우팅되는
    것 차단(루트 스테이징 — W18 D3 부류). 파싱 후 Step3 쌍방 대조로
    침묵 누락 [오류] 차단. v1 무변경.

    v1_engine: 원고 수집을 위임할 v1 엔진 인스턴스 (완성=EbsWorkbookEngine,
    기본=EbsWorkbookBasicEngine) — 시리즈가 달라도 선라우팅은 같다.
    """
    import unicodedata
    from core.base import safe_copy
    from engines.workbook_v2 import routing as _routing

    manuscripts = uploaded_files.get("manuscripts")
    if isinstance(manuscripts, list):
        rest = []
        uploads_dir = os.path.join(job_dir, "uploads")
        step3_dir = os.path.join(uploads_dir, "Step3")
        for fpath in manuscripts:
            fname = os.path.basename(fpath)
            if fname.startswith("manuscripts_"):
                fname = fname[len("manuscripts_"):]
            fname_nfc = unicodedata.normalize("NFC", fname).strip()
            if _routing.route_step3(fname_nfc):
                os.makedirs(step3_dir, exist_ok=True)
                staged = _routing.stage_step3_name(step3_dir, fname_nfc, log)
                safe_copy(fpath, os.path.join(step3_dir, staged))
                log(f"[v2] Step3 원고 선라우팅: {fname_nfc}")
            elif (_routing.RE_QNUM.search(fname_nfc)
                  and _routing.RE_ANSWER_TOKEN.search(fname_nfc)):
                # 'NN번_정답.hwp' — v1 추가 업로드 라우팅('번.hwp' in)이
                # Step3로 오라우팅하는 것 차단: 루트에 스테이징 (미사용
                # 정답본은 G9 stats로 보고)
                os.makedirs(uploads_dir, exist_ok=True)
                safe_copy(fpath, os.path.join(uploads_dir, fname_nfc))
                log(f"[v2] 정답/답지류 루트 스테이징 (Step3 오라우팅 "
                    f"차단): {fname_nfc}")
            else:
                rest.append(fpath)
        if len(rest) != len(manuscripts):
            uploaded_files = dict(uploaded_files, manuscripts=rest)
    json_path = v1_engine.parse(uploaded_files, job_dir, log)
    content = json.load(open(json_path, encoding="utf-8"))
    _routing.reconcile_step3(
        os.path.join(job_dir, "uploads", "Step3"),
        (content.get("steps") or {}).get("step3"), log,
        number_matching=False)
    return json_path
