"""화이트북 v2 엔진 — 새 아키텍처 운영 래퍼 (blackbook_v2/workbook_v2 패턴).

파이프라인: 인-리포 파서(engines/whitebook/external 스냅샷 재사용 +
engines/whitebook_v2/wb_parser 구조 섹션 인식 — W35 배치 C) + v1
practice_parser → wbwt-flows 렌더 플랜(engines/whitebook_v2/plan.py)
→ whitebook_flow JSX(실행만) → 검수 게이트 내장(플랜 단어 보존 + v1
expected_stories 계승 + 오버플로우 + PDF).

W35 배치 C 이전에는 parse 를 v1(WhitebookEngine.parse — 외부
parse_whitebook.py subprocess)에 위임했다. 지금은 리포 스냅샷 + 구조
섹션 분할(침묵 금지)로 직접 파싱한다 — 골든 2케이스 diff 0 계약,
v1 은 종전대로 외부 경로 사용(운영 무변경).

v1(engines/whitebook) 무변경. 출력 파일명 v1 규칙 + _v2 접미로 공존.
템플릿/출력 경로는 v1의 engines/whitebook/config.json을 공유한다.

expected_stories 주의: v1 config의 "D항목(D단어new)": 8은 구버전 템플릿 기준
(현행 [원본] 템플릿은 10개 — 2026-05 v1 실행 로그 실측). v2는 실물 기준으로
보정해 계승하고, 연습문제 스토리(본문/답지 3+3)도 추가 검수한다.
"""
import json
import os
import re
import unicodedata

from core.base import BaseEngine, safe_copy_indd
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "whitebook", "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                            "core", "jsx", "whitebook_flow.body.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")

# 실행기 area → (검수 표시명, 기대 스토리 수) — v1 config expected_stories 계승
# (D_item은 실물 템플릿 실측 10으로 보정 — 모듈 docstring 참조)
EXPECTED_STORIES = {
    "A": ("A어휘", 10),
    "B": ("B문장", 10),
    "C": ("C영영사전", 10),
    "D_box": ("D보기", 10),
    "D_item": ("D항목(D단어new)", 10),
    "E": ("E전치사", 10),
    "ans": ("정답", 10),
    "prac_main": ("연습문제본문", 3),
    "prac_ans": ("연습문제답지", 3),
}


def _norm_typo(s):
    """타이포그래피 정규화 — InDesign 자동 치환(굽은따옴표 등) 흡수."""
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"'))


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["indd_output_dir", "indd_original",
                                "parse_script"])


class WhitebookV2Engine(BaseEngine):

    jsx_timeout = 1500

    @property
    def material_id(self):
        return "whitebook_v2"

    @property
    def display_name(self):
        return "화이트북 워크북 v2 (베타)"

    @property
    def description(self):
        return "화이트북 조판 v2 — 데이터 플랜 + 자동 검수 (신규 아키텍처)"

    @property
    def subject_prefix(self):
        return "화이트북"

    @property
    def upload_spec(self):
        # v1과 동일 슬롯 (공용 typeset.html 폼 자동 생성)
        from engines.whitebook.engine import WhitebookEngine
        return WhitebookEngine().upload_spec

    def _get_meta(self, job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p, encoding="utf-8").read().strip() \
            if os.path.exists(p) else default

    # ── 1단계: parse — 인-리포 파서 (스냅샷 재사용 + 구조 섹션 인식) ─────────

    def parse(self, uploaded_files, job_dir, log):
        """v1 parse 와 동일 파이프라인 (골든 파리티 계약) — 차이 2가지:
        외부 subprocess 대신 리포 스냅샷 import, 섹션 분할은 wb_parser 의
        구조 신호 1선 + 발문 프라이어 + 결손/중복 [오류] (침묵 소멸 금지)."""
        from engines.whitebook.practice_parser import (
            parse_practice_docx, parse_practice_answer_docx)
        from engines.whitebook_v2 import wb_parser

        hwpx = [uploaded_files[k] for k in ("w1_main", "w2_main", "w3_main")
                if k in uploaded_files]
        main_ans = [uploaded_files[k]
                    for k in ("w1_main_ans", "w2_main_ans", "w3_main_ans")
                    if k in uploaded_files]
        if not hwpx:
            raise ValueError("원고 hwpx 파일이 없습니다.")

        # 1) 워크북 파서 (인-리포) → Day별 A~E (+정답)
        data = wb_parser.parse_workbook_files(
            hwpx, main_ans or None, log=lambda m: log(f"[파서] {m}"))

        # 2) 연습문제(.docx) → 'practices' (v1 parse 블록과 동일)
        practices = []
        for week_idx, (pkey, akey) in enumerate(
            [("w1_practice", "w1_prac_ans"),
             ("w2_practice", "w2_prac_ans"),
             ("w3_practice", "w3_prac_ans")], start=1
        ):
            entry = {"week": week_idx, "questions": [], "answers": []}
            if pkey in uploaded_files:
                try:
                    entry["questions"] = parse_practice_docx(
                        uploaded_files[pkey])
                    log(f"[연습] WEEK{week_idx} 문제: "
                        f"{len(entry['questions'])}개")
                except Exception as e:
                    log(f"[연습] WEEK{week_idx} 문제 파싱 실패: {e}")
            if akey in uploaded_files:
                try:
                    entry["answers"] = parse_practice_answer_docx(
                        uploaded_files[akey])
                    log(f"[연습] WEEK{week_idx} 답지: {len(entry['answers'])}개")
                except Exception as e:
                    log(f"[연습] WEEK{week_idx} 답지 파싱 실패: {e}")
            practices.append(entry)
        data["practices"] = practices

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"[파서] content.json 생성 완료 "
            f"({os.path.getsize(json_path):,} bytes)")
        return json_path

    # ── 2단계: prepare_jsx — 플랜 빌드 + 템플릿 복사 + JSX 생성 ─────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.whitebook_v2.plan import content_to_plan

        cfg = _load_v1_config()
        issue_num = _nfc(self._get_meta(job_dir, "issue_num", "01"))
        school = _nfc(self._get_meta(job_dir, "school", "학교미선택"))

        content = json.load(open(json_path, encoding="utf-8"))
        plan = content_to_plan(content, issue_num=issue_num)
        plan_path = os.path.abspath(os.path.join(job_dir, "render_plan.json"))
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)
        log("[v2] 플랜: " + ", ".join(
            f"{fl['area']} {sum(1 for u in fl['units'] if not u.get('skip'))}"
            f"/{len(fl['units'])}유닛" for fl in plan["flows"]))

        # 출력 파일명: v1 규칙({학교}_화이트북{NN}_내지) + _v2 접미
        num = issue_num.zfill(2)
        prefix = cfg.get("indd_name_prefix", "화이트북")
        out_name = f"{school}_{prefix}{num}_내지_v2.indd"
        out_dir = cfg["indd_output_dir"]
        os.makedirs(out_dir, exist_ok=True)

        src = cfg.get("indd_original", "")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(f"내지 원본 없음: {src}")
        indd_path = safe_copy_indd(src, os.path.join(out_dir, out_name))
        log(f"[내지] 원본 복사: {os.path.basename(indd_path)}")

        pdf_path = indd_path.replace(".indd", ".pdf")
        jsx_log = os.path.abspath(os.path.join(job_dir, "조판_로그.txt"))
        jsx_path = build_jsx(
            _RENDER_BODY,
            {"__TEMPLATE_PATH__": indd_path, "__PLAN_PATH__": plan_path,
             "__OUT_INDD__": indd_path, "__OUT_PDF__": pdf_path},
            log_path=jsx_log,
            out_path=os.path.join(job_dir, "run.jsx"))

        settings = {"engine": "whitebook_v2", "indd_path": indd_path,
                    "pdf_path": pdf_path, "jsx_path": jsx_path,
                    "log_path": jsx_log, "json_path": json_path,
                    "plan_path": plan_path, "issue_num": issue_num,
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
        # stall_limit 900: 100p+ 문서의 doc.save + PDF export가 로그 무갱신으로
        # 기본 300초 행 판정에 오탐될 수 있음 (workbook_v2 W4 실측 교훈)
        run_jsx(settings["jsx_path"], log, poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="화이트북 v2 조판 완료",
                stall_limit=900)

    # ── 4단계: verify — 검수 게이트 내장 ────────────────────────────────────

    @staticmethod
    def _norm_para(t):
        """단락 대조 정규화 — 앵커문자(￼)/개행 제거 + 타이포 통일 + NFC."""
        t = (t or "").replace("￼", "").replace("\r", "").replace("\n", "")
        return _nfc(_norm_typo(t))

    def verify(self, job_dir, log):
        from core.inspect import dump_indd
        from engines.whitebook_v2.plan import unit_paras
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        plan = json.load(open(settings["plan_path"], encoding="utf-8"))

        dump = dump_indd(settings["indd_path"],
                         os.path.join(job_dir, "typeset_dump.json"), log)
        got = set()
        overflow = 0
        overflow_heads = []
        dump_keys = set()
        for st in dump["stories"]:
            paras = st["paragraphs"]
            for pp in paras:
                for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                    got.add(w.lower())
            dump_keys.add(tuple((self._norm_para(p["t"]), p["s"])
                                for p in paras))
            if st.get("overflow"):
                # 섹션 아이콘(앵커된 6.3mm 소형 프레임, A~E 한 글자)의 의사
                # 오버플로우 제외 — v1 실물 출력에도 동일하게 존재(수용된 상태)
                is_icon = (len(paras) == 1 and
                           self._norm_para(paras[0]["t"]).strip()
                           in ("A", "B", "C", "D", "E"))
                if not is_icon:
                    overflow += 1
                    if paras:
                        overflow_heads.append(paras[0]["t"][:40])

        warnings = []
        ok = True

        # (a) 영역별 플랜 단어 보존 (검수 게이트 — 내용 누락 0)
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
                    f"❌ {flow['area']} 내용누락 {len(missing)}단어: "
                    + ", ".join(sorted(missing)[:8]))

        # (a2) 유닛 1:1 대조 — 각 유닛(단락 텍스트+스타일 열)이 실제 스토리로
        # 존재하는지 (스타일 미적용/정렬 어긋남 검출 — 검수 강화)
        for flow in plan["flows"]:
            bad = 0
            for u in flow["units"]:
                paras = unit_paras(u)
                if not paras:
                    continue
                key = tuple((self._norm_para(p["t"]), p["s"]) for p in paras)
                if key not in dump_keys:
                    bad += 1
            if bad:
                ok = False
                warnings.append(f"❌ {flow['area']} 유닛-스토리 불일치 {bad}건 "
                                "(텍스트/스타일 열 대조 실패)")

        # (b) 스토리 수 검수 — v1 expected_stories 계승 (실행기 로그 파싱)
        jsx_log_txt = ""
        if os.path.exists(settings["log_path"]):
            jsx_log_txt = open(settings["log_path"], encoding="utf-8",
                               errors="ignore").read()
        stories = {}
        for area, (label, exp) in EXPECTED_STORIES.items():
            m = re.search(rf"^스토리수 {re.escape(area)}: (\d+)$",
                          jsx_log_txt, re.M)
            actual = int(m.group(1)) if m else None
            stories[label] = {"actual": actual, "expected": exp}
            if actual is None:
                ok = False
                warnings.append(f"❌ {label} 스토리 수 확인 불가")
            elif actual != exp:
                ok = False
                warnings.append(f"❌ {label}: {actual}개 (예상 {exp}개)")

        # (b2) 배치 수 검수 — 비-skip 유닛 전부 배치됐는지 (실행기 로그 파싱)
        for flow in plan["flows"]:
            expected_placed = sum(1 for u in flow["units"]
                                  if not u.get("skip"))
            m = re.search(
                rf"^배치완료 {re.escape(flow['area'])}: (\d+)유닛",
                jsx_log_txt, re.M)
            placed = int(m.group(1)) if m else None
            if placed != expected_placed:
                ok = False
                warnings.append(f"❌ {flow['area']} 배치 {placed}유닛 "
                                f"(기대 {expected_placed})")

        # (b3) 섹션 아이콘 수 검수
        want_icons = sum(len((u.get("ops") or {}).get("icons", []))
                         for fl in plan["flows"] for u in fl["units"]
                         if not u.get("skip"))
        if want_icons:
            got_icons = sum(int(n) for n in re.findall(
                r"^아이콘삽입 \S+: (\d+)$", jsx_log_txt, re.M))
            if got_icons != want_icons:
                ok = False
                warnings.append(f"❌ 섹션 아이콘 {got_icons}/{want_icons}개")

        # (c) 오버플로우 — v2 시리즈 규칙: 경고(검수가 지목, 수동 처리)
        if overflow:
            warnings.append(f"⚠️ 오버플로우 스토리 {overflow}개 (수동 처리): "
                            + " | ".join(overflow_heads[:5]))

        # (d) PDF
        pdf_ok = os.path.exists(settings["pdf_path"])
        if not pdf_ok:
            ok = False
            warnings.append("❌ PDF 미생성")

        render_warns = [l.strip() for l in jsx_log_txt.splitlines()
                        if "[경고]" in l]
        warnings.extend(f"⚠️ {w}" for w in render_warns[:5])

        log(f"[검수] 플랜 {len(plan['flows'])}영역 / 누락 {total_missing} / "
            f"오버플로우 {overflow} / PDF {'OK' if pdf_ok else '실패'}")
        return {
            "ok": ok,
            "overflow": overflow,
            "stories": stories,
            "pdf_path": settings["pdf_path"] if pdf_ok else None,
            "indd_path": settings["indd_path"],
            "warnings": warnings,
        }
