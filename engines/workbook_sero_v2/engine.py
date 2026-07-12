"""워크북 세로 v2 엔진 — 사이클(문제) 단위 새 아키텍처 래퍼.

파이프라인: v1 세로 파서 재사용(engines/workbook_sero/parser — 사이클 분할)
→ 사이클 플랜(engines/workbook_sero_v2/plan.py — workbook_v2 스텝 빌더 재사용)
→ workbook_sero_flow JSX(사이클 복제/삭제 + 슬롯 배치 실행만)
→ 검수 게이트 내장(사이클×슬롯 단어 보존/오버플로우/PDF).

v1(engines/workbook_sero) 무변경. 출력 파일명 v1 규칙 + _v2 접미로 공존.
템플릿/출력 경로는 v1의 engines/workbook_sero/config.json을 공유한다.
"""
import json
import os
import re
import unicodedata

from core.base import BaseEngine, safe_copy_indd, safe_copy
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "workbook_sero",
                          "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                            "core", "jsx", "workbook_sero_flow.body.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def _norm_typo(s):
    """타이포그래피 정규화 — workbook_v2와 동일 (곧은↔굽은 따옴표)."""
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"'))


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["indd_output_dir", "indd_original",
                                "indd_original_gdrive_fallback",
                                "manuscript_base"])


class WorkbookSeroV2Engine(BaseEngine):

    jsx_timeout = 1800

    @property
    def material_id(self):
        return "workbook_sero_v2"

    @property
    def display_name(self):
        return "워크북 세로 v2 (베타)"

    @property
    def description(self):
        return ("세로 워크북 조판 v2 — 문제별 사이클 플랜 + 자동 검수 "
                "(신규 아키텍처)")

    @property
    def subject_prefix(self):
        return "워크북세로"

    @property
    def template_name(self):
        return "typeset_workbook_sero_v2.html"

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "manuscripts",
                    "label": "원고 파일 (Step1~3 전체)",
                    "required": True,
                    "multiple": True,
                    "accept": ".docx,.hwp,.hwpx",
                },
            ]
        }

    # ── 유틸리티 (v1 세로 엔진과 동일 메타 규칙) ────────────────────────────

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

    # ── 1단계: 원고 폴더 → content.json (v2 오케스트레이션 — v1 helpers) ────

    # W18 c17 (D3) — Step3 라우팅 가드: 스텝1/2 접두 파일("Step1 A1 어휘선택
    # (2단계 34번).docx"의 'NN번')과 정답/답지/해설 파일("고1 23년 11월
    # NN번_정답.hwp", "…워크북step3_정답지.hwpx")이 Step3로 흘러 중복/정답
    # 사이클을 만들던 것 차단 (W13 본가 오라우팅 차단의 세로 확장).
    _RE_STEP12_PREFIX = re.compile(r"^\s*(?:스텝|step)\s*[12]\b", re.I)
    _RE_ANSWERISH = re.compile(r"정답|답지|답안|해설", re.I)
    # W18 c17 (D6) — 정규 워크북의 'Step2 B2 문법 기본 문제 정답' 네이밍은
    # 가로 file_map(step2_a1_btm 기대명 '어법선택(객관식)')이 못 잡는다 —
    # 내용은 0a5da924가 소비한 '어법선택(문법 기본 문제) 정답지'와 동일
    # 형식(틀린어법 정답지: 원문자 + [정답해설]). 기대명으로 rename 스테이징.
    _GRAMMAR_BASIC_RENAME = "Step2 A1 어법선택(객관식).docx"

    def _stage_fname(self, fname_nfc, log):
        norm = re.sub(r"[^0-9a-z가-힣]", "", fname_nfc.lower())
        if ("문법기본문제" in norm and "어법선택" not in norm
                and self._RE_ANSWERISH.search(fname_nfc)):
            log(f"[스테이징] {fname_nfc} → {self._GRAMMAR_BASIC_RENAME} "
                f"(문법 기본 문제 정답 → step2_a1_btm 소비)")
            return self._GRAMMAR_BASIC_RENAME
        return fname_nfc

    def parse(self, uploaded_files, job_dir, log):
        from engines.workbook_sero_v2.parser_ext import (
            parse_manuscript_folder_v2)

        # 업로드 파일 분류 — v1 세로 엔진 규칙 + D3 라우팅 가드
        manuscripts = uploaded_files.get("manuscripts")
        if isinstance(manuscripts, list):
            manuscript_dir = os.path.join(job_dir, "uploads")
            os.makedirs(manuscript_dir, exist_ok=True)
            step3_dir = os.path.join(manuscript_dir, "Step3")
            os.makedirs(step3_dir, exist_ok=True)
            for fpath in manuscripts:
                fname = os.path.basename(fpath)
                if fname.startswith("manuscripts_"):
                    fname = fname[len("manuscripts_"):]
                fname_nfc = self._stage_fname(_nfc(fname).strip(), log)
                is_step3 = (
                    bool(re.search(r"(?:스텝|step)[\s_-]*3(?!\d)",
                                   fname_nfc, re.I))
                    or bool(re.search(r"\d+(?:\s*~\s*\d+)?\s*번", fname_nfc))
                )
                if self._RE_STEP12_PREFIX.match(fname_nfc):
                    is_step3 = False    # D3 — 스텝1/2 원고의 'NN번' 오인 차단
                if is_step3 and self._RE_ANSWERISH.search(fname_nfc):
                    is_step3 = False    # D3 — 정답/답지 파일은 문제가 아님
                if is_step3:
                    dest = os.path.join(step3_dir, fname_nfc)
                else:
                    dest = os.path.join(manuscript_dir, fname_nfc)
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
        cfg = _load_v1_config()

        log(f"[v2 파서] 시작 (v2 오케스트레이션 — v1 helpers 재사용): "
            f"고{grade} {year}년 {month}월")
        data = parse_manuscript_folder_v2(manuscript_dir, cfg, grade, year,
                                          month, log)

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"[v2 파서] 완료: {len(data.get('cycles', []))}개 사이클")
        return json_path

    # ── 2단계: prepare_jsx — 사이클 플랜 + 템플릿 복사 + JSX 생성 ───────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.workbook_sero_v2.plan import content_to_plan

        cfg = _load_v1_config()
        grade = self._read_meta(job_dir, "grade", 1)
        year = self._read_meta(job_dir, "year", 25)
        month = self._read_meta(job_dir, "month", 10)
        workbook_type = self._read_meta_str(job_dir, "workbook_type",
                                            "모의고사")
        exclude = self._read_exclude(job_dir)
        if exclude:
            log(f"[v2] 제외 섹션: {', '.join(exclude)}")

        content = json.load(open(json_path, encoding="utf-8"))
        plan = content_to_plan(content, exclude=exclude,
                               workbook_type=workbook_type)

        # 사이클별 분할 저장 — ExtendScript eval() 1MB 제한 회피 (v1과 동일)
        meta = {"format": plan["format"], "cycle_count": plan["cycle_count"],
                "unsupported": plan["unsupported"], "cycles": []}
        n_warn = 0
        for idx, cyc in enumerate(plan["cycles"]):
            cyc_path = os.path.abspath(
                os.path.join(job_dir, f"cycle_plan_{idx:02d}.json"))
            with open(cyc_path, "w", encoding="utf-8") as f:
                json.dump(cyc, f, ensure_ascii=False)
            meta["cycles"].append({
                "index": idx, "q_num": cyc["q_num"],
                "q_num_end": cyc.get("q_num_end"), "code": cyc.get("code"),
                "path": cyc_path,
            })
            for w in cyc.get("warnings", []):
                if n_warn < 10:
                    log(f"[v2] ⚠️ {w}")
                n_warn += 1
            log(f"[v2] 사이클 Q{cyc['q_num']}: "
                + ", ".join(f"{s['step']}"
                            + ("(비움)" if s.get("clear")
                               else f" {len(s['units'])}유닛")
                            for s in cyc["slots"]))
        plan_path = os.path.abspath(os.path.join(job_dir, "render_plan.json"))
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False)

        # 출력 파일명: v1 규칙 + _v2 접미
        yy = str(year)[-2:]
        mm = str(month).zfill(2)
        out_name = f"고{grade}_{yy}년_{mm}월_전체(C세로)_v2.indd"
        indd_path = os.path.join(cfg["indd_output_dir"], out_name)

        # 원본 indd — v1과 동일: 로컬 원본 우선, 없으면 GDrive 폴백
        src = cfg.get("indd_original", {}).get(workbook_type, "")
        if not src or not os.path.exists(src):
            src = cfg.get("indd_original_gdrive_fallback",
                          {}).get(workbook_type, "")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(
                f"세로 원본 .indd 를 찾을 수 없습니다: {workbook_type}")
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

        settings = {"engine": "workbook_sero_v2", "indd_path": indd_path,
                    "pdf_path": pdf_path, "jsx_path": jsx_path,
                    "log_path": jsx_log, "json_path": json_path,
                    "plan_path": plan_path,
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
        # stall_limit 900: 240p+ 문서의 doc.save + PDF export 무로그 구간이
        # 기본 300초 행 판정에 오탐됨 (workbook_v2 W4 실증과 동일)
        run_jsx(settings["jsx_path"], log, poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="워크북 세로 v2 조판 완료",
                stall_limit=900)

    # ── 4단계: verify — 검수 게이트 내장 ────────────────────────────────────

    def verify(self, job_dir, log):
        from core.inspect import dump_indd
        from engines.workbook_v2.plan import unit_paras
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        meta = json.load(open(settings["plan_path"], encoding="utf-8"))

        dump = dump_indd(settings["indd_path"],
                         os.path.join(job_dir, "typeset_dump.json"), log)
        got = set()
        overflow = 0
        overflow_heads = []
        for st in dump["stories"]:
            for pp in st["paragraphs"]:
                for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                    got.add(w.lower())
            if st.get("overflow"):
                overflow += 1
                head = next((pp["t"].strip() for pp in st["paragraphs"]
                             if pp["t"].strip()), "")
                overflow_heads.append(head[:30] or "(빈 스토리)")

        # (a) 사이클×슬롯별 플랜 단어 보존
        warnings = []
        ok = True
        total_missing = 0
        for cyc_ref in meta["cycles"]:
            cyc = json.load(open(cyc_ref["path"], encoding="utf-8"))
            for slot in cyc["slots"]:
                if slot.get("clear"):
                    continue
                want = set()
                for u in slot["units"]:
                    for p in unit_paras(u):
                        for w in _RE_WORD.findall(_norm_typo(p["t"])):
                            want.add(w.lower())
                missing = want - got
                total_missing += len(missing)
                if missing:
                    ok = False
                    warnings.append(
                        f"❌ Q{cyc['q_num']} {slot['step']} 내용누락 "
                        f"{len(missing)}단어: "
                        + ", ".join(sorted(missing)[:8]))

        # (b) 오버플로우 — v2 시리즈 규칙: 경고(위치 지목, 수동 처리)
        if overflow:
            warnings.append(
                f"⚠️ 오버플로우 스토리 {overflow}개 (수동 처리): "
                + " / ".join(f"「{h}…」" for h in overflow_heads[:5]))

        # (c) PDF
        pdf_ok = os.path.exists(settings["pdf_path"])
        if not pdf_ok:
            ok = False
            warnings.append("❌ PDF 미생성")

        render_warns = [l.strip() for l in open(settings["log_path"],
                                                encoding="utf-8")
                        if "[경고]" in l]
        warnings.extend(f"⚠️ {w}" for w in render_warns[:5])

        # (d) 완제품 게이트 (W18 D5 — 세로에도 전 계열 공통 게이트 통합.
        # W18 c17 실증: 전 스텝 0분할 침묵 유실이 verify ok=True로 통과)
        gate_report = None
        try:
            from engines.workbook_v2.gate import inspect_workbook_finish
            flow_map = {}
            for cyc_ref in meta["cycles"]:
                cyc = json.load(open(cyc_ref["path"], encoding="utf-8"))
                for slot in cyc["slots"]:
                    if slot.get("clear"):
                        continue
                    fl = flow_map.setdefault(
                        slot["step"],
                        {"step": slot["step"], "target": {}, "units": []})
                    fl["units"].extend(slot.get("units") or [])
            pseudo_plan = {"flows": list(flow_map.values())}
            content_path = os.path.join(job_dir, "content.json")
            content = (json.load(open(content_path, encoding="utf-8"))
                       if os.path.exists(content_path) else {})
            uploads_dir = os.path.join(job_dir, "uploads")
            gate_report = inspect_workbook_finish(
                content, pseudo_plan, dump,
                uploads_dir if os.path.isdir(uploads_dir) else None)
            for c in gate_report["critical"]:
                ok = False
                warnings.append(f"❌ {c}")
            for w in gate_report["warnings"]:
                warnings.append(f"⚠️ {w}")
            log(f"[게이트] critical {len(gate_report['critical'])} / "
                f"warning {len(gate_report['warnings'])}")
        except Exception as e:                        # noqa: BLE001
            ok = False
            warnings.append(f"❌ 게이트 검사 실패: {e}")

        log(f"[검수] 사이클 {len(meta['cycles'])}개 / 누락 {total_missing} / "
            f"오버플로우 {overflow} / PDF {'OK' if pdf_ok else '실패'}")
        return {
            "ok": ok,
            "gate": gate_report,
            "overflow": overflow,
            "cycles_completed": len(meta["cycles"]),
            "stories": {},
            "pdf_path": settings["pdf_path"] if pdf_ok else None,
            "indd_path": settings["indd_path"],
            "warnings": warnings,
        }
