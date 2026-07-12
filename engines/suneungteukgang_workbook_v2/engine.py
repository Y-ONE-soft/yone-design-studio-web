"""수능특강 워크북 v2 엔진 — 분석본/문제본 2단계 순차 조판 (v1 구조 보존).

v1(engines/suneungteukgang_workbook)과 동일하게 두 원본 .indd를 사용:
  - 분석본([원본]고3_수능특강(분석)): step1_a1/a2/c1/c2 + step2_a1/a1_btm/c2
  - 문제본([원본]고3_수능특강(문제)): step3 (실전문제 — 마스터 D)
prepare_jsx가 스테이지별 플랜 2개 + settings/run.jsx 2세트를 만들고,
run_indesign이 순차 실행한다 (v1 run_indesign 오버라이드 구조 그대로).

파이프라인 부품은 전부 workbook_v2 재사용:
  - parse: v1 완전 위임 (GDrive 단원 폴더 + workbook 파서, "EBS" 유형)
  - 플랜: steps_to_plan(workbook_type="EBS", step_map=스테이지별 매핑 —
    engines/suneungteukgang_workbook_v2/step_map.json = v1의
    _ANALYSIS_STEP_STORY_MAP/_PROBLEM_STEP_STORY_MAP 데이터화)
  - 렌더: core/jsx/workbook_flow.body.jsx (스테이지당 1회)
  - verify: 두 indd를 각각 dump — 스테이지별 플랜 단어 보존 + 오버플로우
    지목 + PDF 2개

v1 무변경. 출력 파일명 v1 규칙(EBS_수능특강_{강}_분석/문제) + _v2 접미 공존.

다중 강 통합(merge_lessons)도 v2 자체 구현 — v1 merge_lessons와 동일 의미론
(첫 강 indd를 saveAs 후 나머지 강의 spread를 AT_END duplicate)이되,
  - 대상/산출 파일명이 _v2 규칙 (v1 산출물과 절대 안 섞임)
  - lib.jsxinc 기반 core/jsx/merge_spreads.body.jsx (절대경로/ES3 철칙)
  - 머지 후 검수 게이트: 통합본을 dump_indd로 재오픈해 강별 단어셋 보존
    + 스프레드 수(=소스 합) 정합 확인 (_gate_merge — 오프라인 테스트 대상)
"""
import json
import os
import re

from core.base import safe_copy_indd
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config
from engines.workbook_v2.engine import WorkbookV2Engine, _RE_WORD, _norm_typo

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "suneungteukgang_workbook",
                          "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                            "core", "jsx", "workbook_flow.body.jsx")
_MERGE_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                           "core", "jsx", "merge_spreads.body.jsx")
_MERGE_MARKER = "스프레드 머지 완료"   # merge_spreads.body.jsx의 완료 wlog와 일치
_PATH_KEYS = ["indd_output_dir", "indd_original", "ebs_base"]

_STAGE_MAPS = json.load(open(os.path.join(_DIR, "step_map.json"),
                             encoding="utf-8"))
_STAGE_MAPS.pop("_doc", None)

# (스테이지 라벨, 한글, 파일명 토큰, 원본 키)
_STAGES = [
    ("analysis", "분석본", "분석", "analysis"),
    ("problem", "문제본", "문제", "problem"),
]


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


# ── 다중 강 통합(merge) 헬퍼 — 오프라인 테스트 대상 ─────────────────────────

def _strip_ws(label):
    return re.sub(r"\s+", "", label)


def _merged_label(lesson_labels):
    """통합 파일명 라벨 — v1 merge_lessons 규칙 그대로.
    (한글+~ 조합이 InDesign saveAs에서 가끔 silent fail → `-` 결합)"""
    first = _strip_ws(lesson_labels[0])
    last = _strip_ws(lesson_labels[-1])
    if first == last:
        return first
    if len(lesson_labels) <= 4:
        return "-".join(_strip_ws(l) for l in lesson_labels)
    return f"{first}-{last}"


def _latest_lesson_indd(out_dir, short, tok):
    """강별 v2 산출물 중 가장 최신(mtime) 것 — v1과 동일하게 _N 사본 포함."""
    exact = os.path.join(out_dir, f"EBS_수능특강_{short}_{tok}_v2.indd")
    candidates = [exact] if os.path.exists(exact) else []
    base = os.path.join(out_dir, f"EBS_수능특강_{short}_{tok}_v2")
    n = 2
    while os.path.exists(f"{base}_{n}.indd"):
        candidates.append(f"{base}_{n}.indd")
        n += 1
    if not candidates:
        return None
    candidates.sort(key=os.path.getmtime, reverse=True)
    return candidates[0]


def _dedupe_path(path):
    if not os.path.exists(path):
        return path
    base, ext = os.path.splitext(path)
    k = 2
    while os.path.exists(f"{base}_{k}{ext}"):
        k += 1
    return f"{base}_{k}{ext}"


def _text_words(texts):
    got = set()
    for t in texts:
        for w in _RE_WORD.findall(_norm_typo(t)):
            got.add(w.lower())
    return got


def _gate_merge(stats, dump, src_paths):
    """머지 검수 게이트 (순수 함수).

    stats: merge JSX가 남긴 게이트 입력 — 소스별 spread/pages/paras(전체
           단락 텍스트) + 통합본 spread/pages + dup_fail
    dump:  통합본 .indd를 dump_indd로 재오픈한 결과 (저장 파일 기준 진실)
    검사: (a) 소스 수 정합 (b) 통합본 스프레드 수 = 소스 합 + duplicate
          실패 0 (c) 강별 단어셋이 통합본 dump에 모두 존재
    반환: (ok, warnings, info)
    """
    warnings = []
    ok = True
    sources = stats.get("sources", [])
    merged = stats.get("merged", {}) or {}

    # (a) 소스 수 정합
    if len(sources) != len(src_paths):
        ok = False
        warnings.append(f"❌ 머지 소스 수 불일치: stats {len(sources)}개 ≠ "
                        f"요청 {len(src_paths)}개")

    # (b) 스프레드 수 정합 + duplicate 실패
    want_spreads = sum(s.get("spreads", 0) for s in sources)
    got_spreads = merged.get("spreads", -1)
    if got_spreads != want_spreads:
        ok = False
        warnings.append(f"❌ 통합본 스프레드 수 불일치: {got_spreads} ≠ "
                        f"소스 합 {want_spreads}")
    if stats.get("dup_fail"):
        ok = False
        warnings.append(f"❌ spread duplicate 실패 {stats['dup_fail']}건")

    # (c) 강별 단어셋 보존 (통합본 재오픈 dump 기준)
    got_words = set()
    overflow = 0
    for story in dump.get("stories", []):
        for pp in story.get("paragraphs", []):
            for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                got_words.add(w.lower())
        if story.get("overflow"):
            overflow += 1
    for s_stat in sources:
        want = _text_words(s_stat.get("paras", []))
        missing = want - got_words
        if missing:
            ok = False
            warnings.append(
                f"❌ {os.path.basename(s_stat.get('path', '?'))} 내용누락 "
                f"{len(missing)}단어: " + ", ".join(sorted(missing)[:8]))

    # 오버플로우는 강별 결과에서 이월된 것 — v2 규칙대로 경고(수동 처리)
    if overflow:
        warnings.append(f"⚠️ 통합본 오버플로우 스토리 {overflow}개 "
                        f"(강별 결과에서 이월 — 수동 처리)")

    info = {"spreads": got_spreads, "pages": merged.get("pages"),
            "overflow": overflow, "lessons": len(sources)}
    return ok, warnings, info


class SuneungteukgangWorkbookV2Engine(WorkbookV2Engine):

    @property
    def material_id(self):
        return "suneungteukgang_workbook_v2"

    @property
    def display_name(self):
        return "수능특강 워크북 v2 (베타)"

    @property
    def description(self):
        return ("EBS 수능특강 영어 워크북 조판 v2 — 분석본+문제본 2단계, "
                "데이터 플랜 + 자동 검수 (워크북 v2 로직 공유)")

    @property
    def subject_prefix(self):
        return "수능특강워크북"

    @property
    def template_name(self):
        return "typeset_suneungteukgang_workbook_v2.html"

    @property
    def upload_spec(self):
        from engines.suneungteukgang_workbook.engine import (
            SuneungteukgangWorkbookEngine)
        return SuneungteukgangWorkbookEngine().upload_spec

    # ── 1단계: parse — v1 완전 위임 (GDrive 복사 + 파서) ────────────────────

    def parse(self, uploaded_files, job_dir, log):
        from engines.suneungteukgang_workbook.engine import (
            SuneungteukgangWorkbookEngine)
        return SuneungteukgangWorkbookEngine().parse(uploaded_files, job_dir,
                                                     log)

    def _load_cfg(self):
        return _load_v1_config()

    def _workbook_type(self, job_dir):
        return "EBS"

    # ── 2단계: prepare_jsx — 스테이지별 플랜/템플릿/JSX 2세트 ───────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds

        cfg = self._load_cfg()
        unit = self._read_meta_str(job_dir, "lesson", "")
        unit_short = re.sub(r"\s+", "", unit) if unit else "단원"
        exclude = self._read_exclude(job_dir)
        if exclude:
            log(f"[v2] 제외 섹션: {', '.join(exclude)}")

        indd_originals = cfg.get("indd_original", {})
        if not isinstance(indd_originals, dict):
            raise ValueError("indd_original은 {analysis, problem} 객체여야 함")
        os.makedirs(cfg["indd_output_dir"], exist_ok=True)

        content = json.load(open(json_path, encoding="utf-8"))
        steps = content.get("steps", {})
        ensure_step3_kinds(steps.get("step3"), log)

        # 어느 스테이지에도 못 실리는 스텝 보고
        placeable = set(_STAGE_MAPS["analysis"]) | set(_STAGE_MAPS["problem"])
        leftover = sorted(set(steps) - placeable - set(exclude))
        if leftover:
            log(f"[v2] ⚠️ 미지원 스텝(렌더 제외): {', '.join(leftover)}")

        # 1차: 스테이지별 플랜 먼저 전부 빌드 — 빈 플랜 조기 차단(W12 G7
        # 기준의 2단계 확장)을 템플릿 복사 전에 수행하기 위함.
        stage_plans = {}
        for stage_label, stage_kor, name_tok, orig_key in _STAGES:
            stage_map = _STAGE_MAPS[stage_label]
            stage_steps = {k: v for k, v in steps.items() if k in stage_map}
            plan = steps_to_plan(stage_steps, exclude=exclude,
                                 workbook_type="EBS", step_map=stage_map)
            if stage_label == "analysis":
                # 완제품 op (W15 c08_ref 실증): 분석 내지의 B-마스터 여분
                # 페이지 3개 + 지문번호('04') 잔재 프레임 페이지가 납품물에
                # 남음 — page_cleanup opt-in (다른 워크북 계열과 동일 의미론,
                # 분석본은 step3 플로우가 없어 M-마스터 경로 미진입).
                # 문제본은 다강(多講) 셸 구조(D-마스터 39p + '2강' 간지 —
                # v1 실물도 50p 동일)라 merge 워크플로 확인 전 보류.
                plan["page_cleanup"] = {}
            plan_path = os.path.abspath(
                os.path.join(job_dir, f"render_plan_{stage_label}.json"))
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False)
            log(f"[v2] {stage_kor} 플랜: " + (", ".join(
                f"{fl['step']} {len(fl['units'])}유닛"
                for fl in plan["flows"]) or "(플로우 없음)"))
            stage_plans[stage_label] = (plan, plan_path)

        # 빈 플랜 조기 차단 (W15 c08 실증: 수능특강 원고 hwpx가 어느 스텝에도
        # 매핑되지 않았는데 빈 템플릿 2개가 verify ok=True로 '성공' — 2단계
        # 경로의 침묵 유실). 두 스테이지 모두 0유닛이면 InDesign 실행 전 차단.
        total_units = sum(len(fl["units"])
                          for plan, _ in stage_plans.values()
                          for fl in plan["flows"])
        if total_units == 0:
            raise ValueError(
                "렌더할 유닛이 0개입니다 — 업로드 원고가 어느 스텝에도 "
                "매핑되지 않았습니다 (파일명/폴더 규칙 확인)")

        stages_meta = []
        for stage_label, stage_kor, name_tok, orig_key in _STAGES:
            plan, plan_path = stage_plans[stage_label]
            src = indd_originals.get(orig_key)
            if not src or not os.path.exists(src):
                raise FileNotFoundError(f"{stage_label} 원본 indd 없음: {src}")
            out_name = f"EBS_수능특강_{unit_short}_{name_tok}_v2.indd"
            indd_path = os.path.join(cfg["indd_output_dir"], out_name)
            indd_path = safe_copy_indd(src, indd_path)
            log(f"[내지] {stage_kor} 원본 복사: "
                f"{os.path.basename(indd_path)}")

            pdf_path = indd_path.replace(".indd", ".pdf")
            jsx_log = os.path.abspath(
                os.path.join(job_dir, f"조판_로그_{stage_label}.txt"))
            jsx_path = build_jsx(
                _RENDER_BODY,
                {"__TEMPLATE_PATH__": indd_path, "__PLAN_PATH__": plan_path,
                 "__OUT_INDD__": indd_path, "__OUT_PDF__": pdf_path},
                log_path=jsx_log,
                out_path=os.path.join(job_dir, f"run_{stage_label}.jsx"))
            stages_meta.append({
                "label": stage_label, "kor": stage_kor,
                "indd_path": indd_path, "pdf_path": pdf_path,
                "jsx_path": jsx_path, "log_path": jsx_log,
                "plan_path": plan_path,
            })

        settings = {"engine": self.material_id, "workbook_type": "EBS",
                    "unit": unit, "json_path": json_path,
                    "stages": stages_meta, "unsupported": leftover,
                    "output_dir": job_dir,
                    # 공용 UI 호환 필드 (대표 = 분석본)
                    "indd_path": stages_meta[0]["indd_path"],
                    "pdf_path": stages_meta[0]["pdf_path"],
                    "log_path": stages_meta[0]["log_path"]}
        with open(os.path.join(job_dir, ".settings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=1)
        return os.path.join(job_dir, ".settings.json")

    # ── 3단계: run_indesign — 분석본 → 문제본 순차 (v1 구조 보존) ───────────

    def run_indesign(self, job_dir, log):
        from core.indesign.runner import run_jsx
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        for st in settings["stages"]:
            log(f"━━━ {st['kor']} 조판 시작 ━━━")
            # 재실행 안전 (seseospecial_v2 W7 교훈): 이전 실행 로그의 완료
            # 마커가 남아 있으면 러너가 조기 완료로 오판 → pkill 사고.
            # 2단계 조판은 스테이지별 로그를 분리해 같은 함정을 원천 차단.
            try:
                os.remove(st["log_path"])
            except OSError:
                pass
            run_jsx(st["jsx_path"], log, poll_log_path=st["log_path"],
                    timeout=self.jsx_timeout,
                    completion_marker="워크북 v2 조판 완료",
                    stall_limit=900)
            log(f"━━━ {st['kor']} 조판 완료 ━━━")

    # ── 4단계: verify — 두 indd 각각 검수 게이트 ────────────────────────────

    def verify(self, job_dir, log):
        from core.inspect import dump_indd
        from engines.workbook_v2.plan import unit_paras
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))

        ok = True
        warnings = []
        overflow_total = 0
        total_missing = 0
        n_flows = 0
        pdf_all = True
        for st in settings["stages"]:
            plan = json.load(open(st["plan_path"], encoding="utf-8"))
            dump = dump_indd(
                st["indd_path"],
                os.path.join(job_dir, f"typeset_dump_{st['label']}.json"),
                log)
            got = set()
            overflow = 0
            overflow_heads = []
            for story in dump["stories"]:
                for pp in story["paragraphs"]:
                    for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                        got.add(w.lower())
                if story.get("overflow"):
                    overflow += 1
                    head = next((pp["t"].strip()
                                 for pp in story["paragraphs"]
                                 if pp["t"].strip()), "")
                    overflow_heads.append(head[:30] or "(빈 스토리)")
            overflow_total += overflow

            # (a) 스테이지별 플랜 단어 보존
            for flow in plan["flows"]:
                n_flows += 1
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
                        f"❌ [{st['kor']}] {flow['step']} 내용누락 "
                        f"{len(missing)}단어: "
                        + ", ".join(sorted(missing)[:8]))

            # (b) 오버플로우 — v2 규칙: 경고(위치 지목, 수동 처리)
            if overflow:
                warnings.append(
                    f"⚠️ [{st['kor']}] 오버플로우 스토리 {overflow}개 "
                    f"(수동 처리): "
                    + " / ".join(f"「{h}…」" for h in overflow_heads[:5]))

            # (c) PDF
            if not os.path.exists(st["pdf_path"]):
                ok = False
                pdf_all = False
                warnings.append(f"❌ [{st['kor']}] PDF 미생성")

            # (c2) 완제품 게이트 — 스테이지별(분석본/문제본 각각) 적용 (W15).
            #     게이트 자체 오류는 경고로 강등 (fail-open — 조판을 막지
            #     않는다). c08 실증: 게이트 부재 시 빈 완제품이 ok=True.
            try:
                from engines.workbook_v2.gate import inspect_workbook_finish
                content = json.load(open(settings["json_path"],
                                         encoding="utf-8"))
                # G9(미사용원고)는 job 단위 검사 — 첫 스테이지에서만 수행해
                # 두 스테이지 중복 경고를 피한다.
                first = (st is settings["stages"][0])
                rep = inspect_workbook_finish(
                    content, plan, dump,
                    uploads_dir=(os.path.join(job_dir, "uploads")
                                 if first else None))
                for fn in rep["stats"].get("unused_uploads_expected") or []:
                    log(f"[검수] [{st['kor']}] 미사용 원고(정답/답지류 — "
                        f"의도된 제외): {fn}")
                if rep["critical"]:
                    ok = False
                    warnings.extend(f"❌ [{st['kor']}] {c}"
                                    for c in rep["critical"])
                warnings.extend(f"⚠️ [{st['kor']}] {w}"
                                for w in rep["warnings"])
                log(f"[검수] [{st['kor']}] 완제품 게이트: critical "
                    f"{len(rep['critical'])} / warning {len(rep['warnings'])}")
            except Exception as e:                          # noqa: BLE001
                warnings.append(f"⚠️ [{st['kor']}] 완제품 게이트 실행 실패: "
                                f"{e}")

            if os.path.exists(st["log_path"]):
                render_warns = [l.strip()
                                for l in open(st["log_path"],
                                              encoding="utf-8")
                                if "[경고]" in l]
                warnings.extend(f"⚠️ [{st['kor']}] {w}"
                                for w in render_warns[:5])

        # (d) 미지원 스텝 보고
        if settings.get("unsupported"):
            warnings.append("⚠️ 미지원 스텝(렌더 제외): "
                            + ", ".join(settings["unsupported"]))

        log(f"[검수] 2단계 {n_flows}스텝 / 누락 {total_missing} / "
            f"오버플로우 {overflow_total} / PDF "
            f"{'OK' if pdf_all else '실패'}")
        return {
            "ok": ok,
            "overflow": overflow_total,
            "stories": {},
            "pdf_path": settings["stages"][0]["pdf_path"] if pdf_all
            else None,
            "indd_path": settings["stages"][0]["indd_path"],
            "stage_outputs": {st["label"]: st["indd_path"]
                              for st in settings["stages"]},
            "warnings": warnings,
        }

    # ── 다중 강 통합 merge (v2) ─────────────────────────────────────────────
    # 강별 _v2 indd가 모두 만들어진 후 호출 (UI가 강별 조판 완료 후 fetch).
    # 첫 강 indd를 통합본으로 saveAs 후 다른 강의 spread를 끝에 duplicate.
    # 분석본/문제본 각각. v1 merge_lessons와 동일 의미론 + 검수 게이트 추가.
    @classmethod
    def merge_lessons(cls, lesson_labels, log):
        """lesson_labels: ['21강', '22강', ...] (UI에서 선택된 순서대로)
        Returns: {'analysis': path|None, 'problem': path|None,
                  'errors': [...], 'verify': {stage: {...}}}
        """
        from core.indesign.runner import run_jsx
        from core.inspect import dump_indd

        results = {"analysis": None, "problem": None, "errors": [],
                   "verify": {}}
        if not isinstance(lesson_labels, list) or len(lesson_labels) < 2:
            results["errors"].append("통합할 강이 2개 미만입니다.")
            return results

        cfg = _load_v1_config()
        out_dir = cfg["indd_output_dir"]
        merged_label = _merged_label(lesson_labels)

        for tok, stage_kor, key in [("분석", "분석본", "analysis"),
                                    ("문제", "문제본", "problem")]:
            # 강별 source indd (_v2 규칙, 가장 최신 사본)
            src_paths = []
            missing = []
            for label in lesson_labels:
                p = _latest_lesson_indd(out_dir, _strip_ws(label), tok)
                if p is None:
                    missing.append(f"{label} {stage_kor}")
                else:
                    src_paths.append(os.path.abspath(p))
            if missing:
                results["errors"].append(
                    f"{stage_kor} 통합 실패 — 원본 indd 누락: "
                    + ", ".join(missing))
                continue

            merged_path = os.path.abspath(_dedupe_path(os.path.join(
                out_dir, f"EBS_수능특강_{merged_label}_{tok}_v2.indd")))
            log(f"[{stage_kor} 통합] {len(src_paths)}개 강 → "
                f"{os.path.basename(merged_path)}")

            # 머지 작업 파일 — 전부 절대경로 (InDesign 철칙)
            settings_path = os.path.abspath(os.path.join(
                out_dir, f"_merge_{tok}_v2.settings.json"))
            stats_path = os.path.abspath(os.path.join(
                out_dir, f"_merge_{tok}_v2_stats.json"))
            merge_log = os.path.abspath(os.path.join(
                out_dir, f"_merge_{tok}_v2_로그.txt"))
            # stale 완료마커/게이트 입력 제거 — 이전 머지의 로그·stats가
            # 남아 있으면 조기 완료 오탐/낡은 stats 검증 사고 (W7 교훈)
            for p in (merge_log, stats_path):
                try:
                    os.remove(p)
                except OSError:
                    pass
            with open(settings_path, "w", encoding="utf-8") as f:
                json.dump({"sources": src_paths, "merged": merged_path,
                           "stats": stats_path}, f, ensure_ascii=False)
            jsx_path = build_jsx(
                _MERGE_BODY, {"__MERGE_SETTINGS_PATH__": settings_path},
                log_path=merge_log,
                out_path=os.path.join(out_dir, f"_merge_{tok}_v2.jsx"))

            try:
                run_jsx(jsx_path, log, poll_log_path=merge_log,
                        timeout=1200, completion_marker=_MERGE_MARKER,
                        stall_limit=900)
            except Exception as e:
                results["errors"].append(
                    f"{stage_kor} 통합 InDesign 실행 실패: {e}")
                continue

            if not os.path.exists(merged_path):
                results["errors"].append(f"{stage_kor} 통합 결과 파일 미생성")
                continue
            if not os.path.exists(stats_path):
                results["errors"].append(
                    f"{stage_kor} 통합 게이트 입력(stats) 미생성 — 검증 불가")
                continue

            # 검수 게이트 — 통합본을 재오픈해 저장 파일 기준으로 대조
            stats = json.load(open(stats_path, encoding="utf-8"))
            try:
                dump = dump_indd(
                    merged_path,
                    os.path.join(out_dir, f"_merge_{tok}_v2_dump.json"), log)
            except Exception as e:
                results["errors"].append(
                    f"{stage_kor} 통합본 덤프 실패 (게이트 검증 불가): {e}")
                continue
            gate_ok, warnings, info = _gate_merge(stats, dump, src_paths)
            for w in warnings:
                log(f"[{stage_kor} 통합] {w}")
            results["verify"][key] = dict(info, ok=gate_ok,
                                          warnings=warnings)
            if gate_ok:
                results[key] = merged_path
                log(f"[{stage_kor} 통합] 완료: "
                    f"{os.path.basename(merged_path)} "
                    f"(강 {info['lessons']}개, 스프레드 {info['spreads']})")
            else:
                results["errors"].append(
                    f"{stage_kor} 통합 검수 게이트 실패: "
                    + " / ".join(warnings[:3]))

        return results
