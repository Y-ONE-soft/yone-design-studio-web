"""세서특필 v2 엔진 — 새 아키텍처 운영 래퍼 (whitebook_v2/blackbook_v2 패턴).

파이프라인: v1 파서 완전 재사용(SeseoSpecialEngine.parse 위임)
→ ss-flows 렌더 플랜(engines/seseospecial_v2/plan.py)
→ seseospecial_flow JSX(실행만) → 검수 게이트 내장(플랜 단어 보존 +
영역별 스토리 시퀀스 1:1 대조 + 실행기 로그 배치 수 + 오버플로우 + PDF).

v1(engines/seseospecial) 무변경. 출력 파일명 v1 규칙 + _v2 접미로 공존.
템플릿/출력 경로는 v1의 engines/seseospecial/config.json을 공유한다.

템플릿 주의 (2026-07-04 실물 조사): [원본]광문2/광문3 템플릿은 v1 JSX가
기대하는 "A ver > 실전문제" 스타일 트리를 가진 현행 세대이나,
[원본]광문1 템플릿은 구세대(C ver 트리 — 새형식 스타일 자체가 없음)라
v1도 스타일 적용이 침묵 실패했다. 실운영은 광문1 원고를 광문2 계열 문서에
조판했음(job 41198133 .settings.json 실증). v2는 스타일 부재를 [경고]와
verify 실패로 드러낸다 (침묵 실패 없음).
"""
import json
import os
import re
import unicodedata

from core.base import BaseEngine, safe_copy_indd
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "seseospecial", "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                            "core", "jsx", "seseospecial_flow.body.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def _norm_typo(s):
    """타이포그래피 정규화 — InDesign 자동 치환(굽은따옴표 등) 흡수."""
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"'))


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["templates"])


def _school_key(school):
    """v1 _school_key 동일 — 템플릿 키 추출."""
    for key in ("광문1", "광문2", "광문3"):
        if key in school:
            return key
    return school


def _dump_style_name(full_path):
    """플랜 전체 경로 → dump_stories의 1단계 부모 표기.

    dump_stories.jsx styleFullName은 '직계 그룹 > 이름'만 기록한다
    ("A ver > 실전문제 > 정답 사본" → "실전문제 > 정답 사본").
    """
    parts = [p.strip() for p in (full_path or "").split(">")]
    if len(parts) >= 2:
        return f"{parts[-2]} > {parts[-1]}"
    return parts[-1] if parts else ""


class SeseoSpecialV2Engine(BaseEngine):

    jsx_timeout = 1500

    @property
    def material_id(self):
        return "seseospecial_v2"

    @property
    def display_name(self):
        return "세서특필 v2 (베타)"

    @property
    def description(self):
        return "특강교재 세서특필 조판 v2 — 데이터 플랜 + 자동 검수 (신규 아키텍처)"

    @property
    def subject_prefix(self):
        return "세서특필"

    @property
    def upload_spec(self):
        # v1과 동일 슬롯 (공용 typeset.html 폼 자동 생성)
        from engines.seseospecial.engine import SeseoSpecialEngine
        return SeseoSpecialEngine().upload_spec

    def _get_meta(self, job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p, encoding="utf-8").read().strip() \
            if os.path.exists(p) else default

    # ── 1단계: parse — v1 완전 재사용 ────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        from engines.seseospecial.engine import SeseoSpecialEngine
        return SeseoSpecialEngine().parse(uploaded_files, job_dir, log)

    # ── 2단계: prepare_jsx — 플랜 빌드 + 템플릿 복사 + JSX 생성 ─────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.seseospecial_v2.plan import content_to_plan

        cfg = _load_v1_config()
        school = _nfc(self._get_meta(job_dir, "school", "학교미선택"))
        issue_num = _nfc(self._get_meta(job_dir, "issue_num", "01"))

        content = json.load(open(json_path, encoding="utf-8"))
        plan = content_to_plan(content,
                               part1_page=cfg.get("part1_story_page", 6))
        plan_path = os.path.abspath(os.path.join(job_dir, "render_plan.json"))
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)
        log("[v2] 플랜: " + ", ".join(
            f"{fl['area']} {sum(len(u.get('paras') or []) for u in fl['units'])}"
            f"단락/{len(fl['units'])}유닛" for fl in plan["flows"]))

        # 출력 파일명: v1 규칙({학교}_세서특필{NN}_내지) + _v2 접미
        num = issue_num.zfill(2)
        prefix = cfg.get("indd_name_prefix", "세서특필")
        out_name = f"{school}_{prefix}{num}_내지_v2.indd"
        out_dir = cfg["indd_output_dir"]
        os.makedirs(out_dir, exist_ok=True)
        indd_path = os.path.join(out_dir, out_name)

        # 재실행 충돌 방지 (v1 동일): 열려 있으면 덮어쓰기 전에 닫기
        try:
            from core.indesign.runner import close_open_indd
            close_open_indd(indd_path, log)
        except Exception:
            pass

        key = _school_key(school)
        template_path = cfg["templates"].get(key, "")
        if template_path and os.path.exists(template_path):
            indd_path = safe_copy_indd(template_path, indd_path)
            log(f"[내지] 원본 복사: {os.path.basename(template_path)} "
                f"-> {os.path.basename(indd_path)}")
        elif not os.path.exists(indd_path):
            # v1 파리티: 템플릿이 없으면 기존 출력본 재사용, 그것도 없으면 실패
            raise FileNotFoundError(
                f"템플릿 없음: {template_path}\n내지 파일 없음: {indd_path}")

        pdf_path = indd_path.replace(".indd", ".pdf")
        jsx_log = os.path.abspath(os.path.join(job_dir, "조판_로그.txt"))
        jsx_path = build_jsx(
            _RENDER_BODY,
            {"__TEMPLATE_PATH__": indd_path, "__PLAN_PATH__": plan_path,
             "__OUT_INDD__": indd_path, "__OUT_PDF__": pdf_path},
            log_path=jsx_log,
            out_path=os.path.join(job_dir, "run.jsx"))

        settings = {"engine": "seseospecial_v2", "indd_path": indd_path,
                    "pdf_path": pdf_path, "jsx_path": jsx_path,
                    "log_path": jsx_log, "json_path": json_path,
                    "plan_path": plan_path, "school": school,
                    "school_key": key, "issue_num": issue_num,
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
        # 재실행 안전: 이전 실행의 조판_로그(완료 마커 포함)가 남아 있으면
        # 러너가 그 마커를 보고 렌더를 조기 완료로 오판 → 다음 단계(dump)
        # 제출 실패 → 재시도 pkill이 렌더 중인 InDesign을 죽인다 (E2E 실증).
        # 러너는 1차 시도에서 poll 로그를 지우지 않으므로 여기서 제거한다.
        try:
            os.remove(settings["log_path"])
        except OSError:
            pass
        # stall_limit 900: 150~220p 문서의 doc.save + PDF export가 로그 무갱신
        # 으로 기본 300초 행 판정에 오탐될 수 있음 (workbook_v2 W4 교훈)
        run_jsx(settings["jsx_path"], log, poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="세서특필 v2 조판 완료",
                stall_limit=900)

    # ── 4단계: verify — 검수 게이트 내장 ────────────────────────────────────

    @staticmethod
    def _norm_para(t):
        """단락 대조 정규화 — 앵커(￼)/개행/제어문자 제거 + 타이포 + NFC."""
        t = re.sub(u"[\u0000-\u001f\ufffc]", "", t or "")
        return _nfc(_norm_typo(t)).rstrip()

    def verify(self, job_dir, log):
        from core.inspect import dump_indd
        from engines.seseospecial_v2.plan import flow_paras
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        plan = json.load(open(settings["plan_path"], encoding="utf-8"))

        dump = dump_indd(settings["indd_path"],
                         os.path.join(job_dir, "typeset_dump.json"), log)
        got = set()
        overflow = 0
        overflow_heads = []
        story_seqs = []       # 스토리별 (norm_text, dump 스타일명) 시퀀스
        for st in dump["stories"]:
            paras = st["paragraphs"]
            for pp in paras:
                for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                    got.add(w.lower())
            story_seqs.append([(self._norm_para(p["t"]), p["s"])
                               for p in paras])
            if st.get("overflow"):
                overflow += 1
                if paras:
                    overflow_heads.append(paras[0]["t"][:40])

        warnings = []
        ok = True
        stories = {}

        jsx_log_txt = ""
        if os.path.exists(settings["log_path"]):
            jsx_log_txt = open(settings["log_path"], encoding="utf-8",
                               errors="ignore").read()

        total_missing = 0
        for flow in plan["flows"]:
            paras = flow_paras(flow)
            area = flow["area"]

            # (a) 플랜 단어 보존 (검수 게이트 — 내용 누락 0)
            want = set()
            for p in paras:
                for w in _RE_WORD.findall(_norm_typo(p["t"])):
                    want.add(w.lower())
            missing = want - got
            total_missing += len(missing)
            if missing:
                ok = False
                warnings.append(f"❌ {area} 내용누락 {len(missing)}단어: "
                                + ", ".join(sorted(missing)[:8]))

            # (b) 스토리 시퀀스 1:1 — 영역 전체 (텍스트, 스타일) 열이 실제
            # 스토리와 정확히 일치 (템플릿=조판물이라 단어 게이트만으론 무력
            # — whitebook W6 교훈. v2는 브레이크 문자 미삽입이라 정확 대조 가능)
            expected = [(self._norm_para(p["t"]),
                         _dump_style_name(p["s"]) if p["s"] else None)
                        for p in paras]
            matched = False
            for seq in story_seqs:
                if len(seq) != len(expected):
                    continue
                same = True
                for (et, es), (at, ast) in zip(expected, seq):
                    if et != at or (es is not None and es != ast):
                        same = False
                        break
                if same:
                    matched = True
                    break
            if not matched:
                ok = False
                warnings.append(f"❌ {area} 스토리 시퀀스 불일치 "
                                f"({len(expected)}단락 열 대조 실패)")

            # (c) 실행기 로그 배치 수
            m = re.search(rf"^배치완료 {re.escape(area)}: (\d+)단락",
                          jsx_log_txt, re.M)
            placed = int(m.group(1)) if m else None
            stories[area] = {"actual": placed, "expected": len(paras)}
            if placed != len(paras):
                ok = False
                warnings.append(f"❌ {area} 배치 {placed}단락 "
                                f"(기대 {len(paras)})")

        # (d) 오버플로우 — v2 시리즈 규칙: 경고(검수가 지목, 수동 처리)
        if overflow:
            warnings.append(f"⚠️ 오버플로우 스토리 {overflow}개 (수동 처리): "
                            + " | ".join(overflow_heads[:5]))

        # (e) PDF
        pdf_ok = os.path.exists(settings["pdf_path"])
        if not pdf_ok:
            ok = False
            warnings.append("❌ PDF 미생성")

        render_warns = [l.strip() for l in jsx_log_txt.splitlines()
                        if "[경고]" in l]
        warnings.extend(f"⚠️ {w}" for w in render_warns[:5])
        if render_warns:
            ok = False   # 스타일 부재/스토리 미발견은 침묵 실패 대신 검수 실패

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
