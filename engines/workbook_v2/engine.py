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

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "workbook", "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                            "core", "jsx", "workbook_flow.body.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")

# 변형문제 문제모음 파일명 (W12): "리딩파워 유형 (기본)-Unit 15- 123문제
# [변형문제]-.hwp" 류 — Step3(변형문제) 원고로 라우팅한다. 정답/해설/답지
# 본은 제외 (Step3 본문에 endnote로 합쳐져 있는 관행).
_RE_VARIANT_POOL = re.compile(r"변형\s*문제")
_RE_ANSWER_TOKEN = re.compile(r"정답|해설|답지|답안")


def _is_variant_pool_filename(fname_nfc):
    return (bool(_RE_VARIANT_POOL.search(fname_nfc))
            and not _RE_ANSWER_TOKEN.search(fname_nfc))


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


class WorkbookV2Engine(BaseEngine):

    jsx_timeout = 1800

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
                    "label": "원고 파일 (Step1~3 전체)",
                    "required": True,
                    "multiple": True,
                    "accept": ".docx,.hwp,.hwpx",
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

        # 업로드 파일 분류 — v1 WorkbookEngine.parse와 동일 (Step3 판정 포함)
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
                fname_nfc = _nfc(fname).strip()
                # STEP3 식별 (v1 주석 참조: Step 3/Step_3/Step-3 + "N번" 패턴
                # + 변형문제 문제모음(W12))
                is_step3 = (
                    bool(re.search(r"(?:스텝|step)[\s_-]*3(?!\d)",
                                   fname_nfc, re.I))
                    or bool(re.search(r"\d+(?:\s*~\s*\d+)?\s*번", fname_nfc))
                    or _is_variant_pool_filename(fname_nfc)
                )
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

        log(f"[v2 파서] 시작 (v1 파서 재사용): 고{grade} {year}년 {month}월")
        data = parse_manuscript_folder(manuscript_dir, cfg, grade, year,
                                       month, log)

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log(f"[v2 파서] 완료: {len(data.get('steps', {}))}개 STEP")
        return json_path

    # ── 파생 엔진 훅 (workbook_supp_v2 등이 오버라이드 — 기본은 v1 규칙) ────

    def _output_name(self, job_dir, grade, year, month, workbook_type,
                     school):
        """출력 .indd 파일명 — v1 워크북 규칙 + _v2 접미."""
        yy = str(year)[-2:]
        mm = str(month).zfill(2)
        return f"고{grade}_{yy}년_{mm}월_전체(C)_v2.indd"

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

    def _workbook_type(self, job_dir):
        """원고 유형 — 기본은 v1 워크북 메타 규칙. 파생 엔진은 고정값."""
        return self._read_meta_str(job_dir, "workbook_type", "모의고사")

    def _step_map(self):
        """스텝→스토리 매핑 override — None이면 모의고사 기본 STEP_MAP.
        EBS/수능특강 파생 엔진이 내지 구조에 맞는 매핑을 반환한다."""
        return None

    def _plan_decorations(self, job_dir, cfg):
        """플랜 최상위에 병합할 선택 키 (실행기 opt-in op) — 기본 없음.
        교과서 파생 엔진이 {"divider": ..., "textbook_postprocess": True}
        를 반환한다 (v1 run.jsx 16.7/16.8)."""
        return {}

    # ── 2단계: prepare_jsx — 플랜 빌드 + 템플릿 복사 + JSX 생성 ─────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.workbook_v2.plan import steps_to_plan, ensure_step3_kinds

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
        plan = steps_to_plan(content.get("steps", {}), exclude=exclude,
                             workbook_type=workbook_type,
                             step_map=self._step_map())
        plan.update(self._plan_decorations(job_dir, cfg))
        plan_path = os.path.abspath(os.path.join(job_dir, "render_plan.json"))
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)
        log("[v2] 플랜: " + ", ".join(
            f"{fl['step']} {len(fl['units'])}유닛" for fl in plan["flows"]))
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
        # stall_limit 900: 워크북 전체(C) 문서(250p+)의 doc.save + PDF export가
        # 로그 무갱신으로 5분을 초과 (기본 300초 행 판정이 export 중 오탐 —
        # W4 실측: 정상 export 중 InDesign이 강제 종료됨)
        run_jsx(settings["jsx_path"], log, poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="워크북 v2 조판 완료",
                stall_limit=900)

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
            rep = inspect_workbook_finish(content, plan, dump)
            if rep["critical"]:
                ok = False
                warnings.extend(f"❌ {c}" for c in rep["critical"])
            warnings.extend(f"⚠️ {w}" for w in rep["warnings"])
            log(f"[검수] 완제품 게이트: critical {len(rep['critical'])} / "
                f"warning {len(rep['warnings'])}")
        except Exception as e:                                  # noqa: BLE001
            warnings.append(f"⚠️ 완제품 게이트 실행 실패: {e}")

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
