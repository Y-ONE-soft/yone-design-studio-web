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
다중 강 통합(merge_lessons)은 v1의 것을 그대로 사용한다 — v1 파일명 규칙
(_v2 없음) 대상이므로 v2 출력 통합은 미지원 (전용 템플릿에서 다중 선택 제거,
로드맵 미해결 참조).
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

        stages_meta = []
        for stage_label, stage_kor, name_tok, orig_key in _STAGES:
            stage_map = _STAGE_MAPS[stage_label]
            stage_steps = {k: v for k, v in steps.items() if k in stage_map}
            plan = steps_to_plan(stage_steps, exclude=exclude,
                                 workbook_type="EBS", step_map=stage_map)
            plan_path = os.path.abspath(
                os.path.join(job_dir, f"render_plan_{stage_label}.json"))
            with open(plan_path, "w", encoding="utf-8") as f:
                json.dump(plan, f, ensure_ascii=False)
            log(f"[v2] {stage_kor} 플랜: " + (", ".join(
                f"{fl['step']} {len(fl['units'])}유닛"
                for fl in plan["flows"]) or "(플로우 없음)"))

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
