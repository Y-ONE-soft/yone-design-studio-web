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
import re
import unicodedata

from core.paths import resolve_config
from engines.workbook_v2.engine import WorkbookV2Engine

# ── 15개정 구6스텝 워크북 파일명 선라우팅 (W17 c11) ─────────────────────────
# 구교과서(15개정) 워크북 폴더는 "StepN <콘텐츠토큰>[ 정답지]" 네이밍
# (Step2 문장배열 / Step3 어법수정 / Step4 빈칸내용 / Step5 영작배열 /
# Step6 실전문제)이라 현행 file_map(스텝 문자코드 포함)과 어긋난다.
# 실증(영어 독해와 작문 비상(김) 1과): Step4 빈칸내용·Step5 영작배열·
# Step6 실전문제가 침묵 미사용되고, 'Step3 어법수정'은 Step3 토큰 때문에
# 실전문제(step3)로 오라우팅됐다. 콘텐츠 토큰 기준으로 현행 규격명으로
# 스테이징한 뒤 v1 parse에 위임한다 (v1 무변경 — W12 ebs_v2 선라우팅 전례).
_RE_LEGACY_STEP = re.compile(
    r"^Step\s*(\d)\s+([가-힣]+)(\s*정답지)?\.(docx|hwpx|hwp)$", re.I)
# 콘텐츠 토큰 → 현행 규격 base 이름. 빈칸내용(어휘완성)은 현행 step1_c2가
# '정답지'를 소비하는 스텝이라 정답지가 소비본이 된다 (N[답] 괄호 표기
# 형식 동일 — c11 실물 대조). 나머지는 문제본 소비.
_LEGACY_CONTENT_MAP = {
    "문장배열": "Step1 C1 문장배열",
    "빈칸내용": "Step1 C2 빈칸어휘",
    "영작배열": "Step2 C2 영작배열(서술형)",
    "실전문제": "Step3 실전문제",
    # 어법수정: 현행 교과서 워크북에 대응 스텝 없음 — 매핑하지 않고
    # Step3 토큰 오라우팅만 차단 (G9 미사용 보고로 운영 판단에 위임)
}
_LEGACY_UNMAPPED_SUFFIX = " (구6스텝 미대응)"

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "textbook_workbook",
                          "config.json")
_PATH_KEYS = ["indd_output_dir", "indd_original", "textbook_base"]

# W24 r14: 교과서 전용 step_map — 기본 STEP_MAP과 동일 마커/pos에
# master_pair(섹션 시작 좌/우 마스터 쌍 — 내지가 supp와 같은 [원본]
# 워크북_C라 supp W21 실측 계약 재사용)만 추가 (step_map.json _doc 참조).
_STEP_MAP = json.load(open(os.path.join(_DIR, "step_map.json"),
                           encoding="utf-8"))
_STEP_MAP.pop("_doc", None)

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

    # ── 1단계: parse — 구6스텝 선라우팅 + v1 완전 위임 (GDrive 복사 + 파서) ──

    def parse(self, uploaded_files, job_dir, log):
        self._prestage_legacy_folder(job_dir, log)
        from engines.textbook_workbook.engine import TextbookWorkbookEngine
        json_path = TextbookWorkbookEngine().parse(uploaded_files, job_dir,
                                                   log)
        # 배치 A (W33): Step3 쌍방 대조 — 침묵 누락 [오류] (v1 무변경,
        # 교과서 config는 mockexam 비어 있어 number_matching=False)
        from engines.workbook_v2 import routing as _routing
        content = json.load(open(json_path, encoding="utf-8"))
        _routing.reconcile_step3(
            os.path.join(job_dir, "uploads", "Step3"),
            (content.get("steps") or {}).get("step3"), log,
            number_matching=False)
        return json_path

    @staticmethod
    def _legacy_dest_name(name_nfc, entry_names):
        """구6스텝 파일명 → 현행 규격명 (해당 없으면 None = 원명 유지)."""
        m = _RE_LEGACY_STEP.match(name_nfc)
        if not m:
            return None
        token, ans, ext = m.group(2), (m.group(3) or "").strip(), m.group(4)
        base = _LEGACY_CONTENT_MAP.get(token)
        if base is None:
            # 미대응 토큰(어법수정 등): StepN 접두를 떼어 오라우팅(Step3
            # 토큰 → step3 폴더 흡수)을 차단하고 미사용 보고로 남긴다.
            dest = f"{token}{_LEGACY_UNMAPPED_SUFFIX}"
        else:
            dest = base
        if ans:
            dest += " 정답지"
        dest += f".{ext}"
        # 폴더에 이미 현행 규격명 파일이 실재하면 rename하지 않는다 (충돌 방지)
        if dest in entry_names:
            return None
        return dest

    def _prestage_legacy_folder(self, job_dir, log):
        """구6스텝 워크북 폴더를 현행 규격명으로 스테이징 (없으면 no-op).

        manuscript_folder 메타의 폴더에서 구6스텝 파일명이 발견되면
        job_dir/원고_구6스텝/ 에 현행 규격명으로 사전 복사하고 메타를
        스테이징 경로로 재작성한다 (원경로는 manuscript_folder_original.txt
        보존). GDrive 원본 무접촉 — 읽기 전용 복사만 수행."""
        folder = self._read_meta_str(job_dir, "manuscript_folder", "")
        if not folder or not os.path.isdir(folder):
            return
        from engines.final.extractor import (_gdrive_safe_copy,
                                             list_manuscript_entries)
        entries = list_manuscript_entries(folder, log)
        entry_names = {unicodedata.normalize("NFC", n) for n, _ in entries}
        renames = {}
        for name, _src in entries:
            nfc = unicodedata.normalize("NFC", name)
            dest = self._legacy_dest_name(nfc, entry_names)
            if dest and dest != nfc:
                renames[nfc] = dest
        if not renames:
            return
        staged = os.path.join(job_dir, "원고_구6스텝")
        os.makedirs(staged, exist_ok=True)
        log(f"[구6스텝] 15개정 구스텝 파일명 감지 — 현행 규격명으로 "
            f"선라우팅 ({len(renames)}건)")

        def _copy(src_path, dst_path):
            ok, err = _gdrive_safe_copy(src_path, dst_path, log=log)
            if not ok:
                raise RuntimeError(
                    f"구6스텝 스테이징 복사 실패: "
                    f"{os.path.basename(src_path)} ({str(err)[:200]})")

        for name, src in entries:
            nfc = unicodedata.normalize("NFC", name)
            if os.path.isdir(src):
                # 서브폴더(Step3 등)는 구조 그대로 복사
                for root, dirs, files in os.walk(src):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    rel = os.path.relpath(root, src)
                    dst_dir = os.path.join(staged, nfc,
                                           "" if rel == "." else rel)
                    os.makedirs(dst_dir, exist_ok=True)
                    for f in files:
                        if f.startswith("."):
                            continue
                        _copy(os.path.join(root, f),
                              os.path.join(dst_dir, f))
                continue
            dest = renames.get(nfc, nfc)
            if dest != nfc:
                log(f"[구6스텝] {nfc} → {dest}")
            _copy(src, os.path.join(staged, dest))
        orig_meta = os.path.join(job_dir, "manuscript_folder_original.txt")
        with open(orig_meta, "w", encoding="utf-8") as f:
            f.write(folder)
        with open(os.path.join(job_dir, "manuscript_folder.txt"), "w",
                  encoding="utf-8") as f:
            f.write(staged)

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

    def _step_map(self):
        """W24 r14: 교과서 전용 step_map — master_pair 계약 추가 (기본
        STEP_MAP과 같은 마커/페이지/pos, section_masters op가 소비)."""
        return dict(_STEP_MAP)

    def _plan_decorations(self, job_dir, cfg):
        """v1 run.jsx 16.7(간지) + 16.8(빈 페이지 마스터 재할당) opt-in
        + 완제품 후처리 op (W13 — c13/c15 실조판 실증 + W24 r14 확산).

        교과서 원고는 지문 2~5개인데 내지([원본]워크북_C)는 모의고사 18지문
        규격이라, 실기에서 모의고사 잔재 지문번호 프레임 17종(20~45)과
        내용 없는 스텝 페이지 200개+가 잔존했다 (게이트 G3/G4 warning 실증).
        supp(W11)/ebs(W12)와 동일하게 page_cleanup과 passage_numbers(독립
        지문번호 프레임을 원고 지문번호로 갱신)를 opt-in한다.

        W24 r14 (supp 검증 3종 op 확산 — 내지가 supp와 같은 [원본]워크북_C):
          - page_cleanup delete 모드: 빈 페이지 완전 삭제 + 고아 간지
            스프레드 삭제 + 파트 경계 M 채움 (W21~W23 supp 실증. 'M 보존'
            v1 관행은 완제품 기준으로 폐기 — W21 사용자 확정)
          - section_masters: 섹션 시작 좌/우 마스터 정합 (쌍 데이터는
            step_map.json master_pair — supp W21 실측 계약 재사용)
          - question_keep: 문제 단위 펼침면 킵 (W23 r13 F4 스펙, True
            센티널을 base prepare_jsx가 계약으로 확장)
        간지 라벨 페이지는 delete 판정(다중 프레임 스토리 전부 빈)에
        걸리지 않고 divider op가 정리 이후 문구를 갱신한다 (실행기 순서:
        page_cleanup → question_keep → section_masters → divider —
        간지 텍스트 op와 delete의 상호작용은 r14 c13 실기로 검증).
        textbook_postprocess(16.8)는 잔존 빈 페이지에만 동작 — delete
        모드에선 사실상 no-op이나 밀기 공백 페이지 방어로 유지."""
        from engines.workbook_v2.plan import passage_labels
        subject, pub_short, lesson = self._textbook_meta(job_dir)
        deco = {
            "divider": {"line1": f"{subject} {pub_short}".strip(),
                        "line2": lesson},
            "textbook_postprocess": True,
            "page_cleanup": {"empty": "delete"},
            "section_masters": True,
            "question_keep": True,
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
