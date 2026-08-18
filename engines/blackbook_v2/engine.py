"""블랙북 v2 엔진 — 새 아키텍처 두 번째 운영 래퍼 (mockexam_v2 패턴).

파이프라인: 하이브리드 파서(문제=구조 인식 IR, 어휘/정답=v1 파서 재사용)
→ bb-flows 렌더 플랜(데이터) → blackbook_flow JSX(실행만) → 검수 게이트 내장.

v1(engines/blackbook) 무변경. 출력 파일명 _v2 접미로 공존.
배치 의미론·한계는 v1과 대등 (초장문 문항 오버플로우 = 수동 처리 — 단,
v2는 어느 문항인지 검수가 자동 지목).
"""
import glob
import json
import os
import re
import unicodedata

from core.base import BaseEngine, safe_copy_indd
from core.indesign.jsxbuild import build_jsx
from core.paths import resolve_config

_DIR = os.path.dirname(os.path.abspath(__file__))
_V1_CONFIG = os.path.join(os.path.dirname(_DIR), "blackbook", "config.json")
_RENDER_BODY = os.path.join(os.path.dirname(os.path.dirname(_DIR)),
                            "core", "jsx", "blackbook_flow.body.jsx")

_RE_WORD = re.compile(r"[A-Za-z][A-Za-z'\-]{3,}")


def _norm_typo(s):
    return (s.replace("’", "'").replace("‘", "'")
             .replace("“", '"').replace("”", '"'))


def _nfc(s):
    return unicodedata.normalize("NFC", s or "")


def _load_v1_config():
    with open(_V1_CONFIG, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["indd_output_dir", "indd_original"])


class BlackbookV2Engine(BaseEngine):

    jsx_timeout = 1500

    @property
    def material_id(self):
        return "blackbook_v2"

    @property
    def display_name(self):
        return "블랙북 v2 (베타)"

    @property
    def description(self):
        return "블랙북 조판 v2 — 구조 인식 + 자동 검수 (신규 아키텍처)"

    @property
    def subject_prefix(self):
        return "블랙북"

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "manuscript",
                    "label": "문제 원고 (PART1 문제·어휘, PART2 문제 — 여러 파일)",
                    "required": True,
                    "multiple": True,
                    "accept": ".docx,.hwpx,.hwp",
                },
                {
                    "key": "answers",
                    "label": "해설 원고 (PART1·PART2 해설 — 여러 파일)",
                    "required": False,
                    "multiple": True,
                    "accept": ".docx,.hwpx,.hwp",
                },
            ]
        }

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    # ── 1단계: parse ────────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        from engines.blackbook_v2.parser import parse_files

        files = list(uploaded_files.get("manuscript") or [])
        files += list(uploaded_files.get("answers") or [])
        if not files:
            raise ValueError("업로드된 원고가 없습니다.")

        sections = parse_files(files, log=log)
        for w in sections["warnings"]:
            log(f"[v2] ⚠️ {w}")
        n1 = len(sections["problems_p1"]["items"]) if sections["problems_p1"] else 0
        n2 = len(sections["problems_p2"]["items"]) if sections["problems_p2"] else 0
        log(f"[v2] PART1 문제 {n1} / 어휘 {len(sections['vocab'])} / "
            f"PART2 문제 {n2} / 해설 {len(sections['answers_p1'])}+{len(sections['answers_p2'])}")

        json_path = os.path.join(job_dir, "content.json")
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump({"version": 2, "sections": sections}, f,
                      ensure_ascii=False, indent=1)
        return json_path

    # ── 2단계: prepare_jsx ──────────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        from engines.blackbook_v2.render import sections_to_plan

        cfg = _load_v1_config()
        content = json.load(open(json_path, encoding="utf-8"))
        plan = sections_to_plan(content["sections"])
        plan_path = os.path.abspath(os.path.join(job_dir, "render_plan.json"))
        with open(plan_path, "w", encoding="utf-8") as f:
            json.dump(plan, f, ensure_ascii=False)
        if plan.get("lessons") is not None:
            log("[v2] 플랜(과 단위): " + ", ".join(
                f"{les['label'] or '(과 미표기)'} 어휘{len(les['vocab'])}"
                f"/문제{len(les['problems'])}/해설{len(les['answers'])}"
                for les in plan["lessons"]))
        else:
            log("[v2] 플랜: " + ", ".join(
                f"{fl['area']} {len(fl['units'])}" for fl in plan["flows"]))

        issue_num = _nfc(self._get_meta(job_dir, "issue_num", ""))
        out_name = (f"{cfg.get('indd_name_prefix', '블랙북')}"
                    + (f"_{issue_num}" if issue_num else "") + "_v2.indd")
        out_dir = cfg["indd_output_dir"]
        os.makedirs(out_dir, exist_ok=True)
        indd_path = safe_copy_indd(cfg["indd_original"],
                                   os.path.join(out_dir, out_name))
        pdf_path = indd_path.replace(".indd", ".pdf")
        jsx_log = os.path.abspath(os.path.join(job_dir, "조판_로그.txt"))
        jsx_path = build_jsx(
            _RENDER_BODY,
            {"__TEMPLATE_PATH__": indd_path, "__PLAN_PATH__": plan_path,
             "__OUT_INDD__": indd_path, "__OUT_PDF__": pdf_path},
            log_path=jsx_log,
            out_path=os.path.join(job_dir, "run.jsx"))
        log(f"[내지] {os.path.basename(indd_path)}")

        settings = {"engine": "blackbook_v2", "indd_path": indd_path,
                    "pdf_path": pdf_path, "jsx_path": jsx_path,
                    "log_path": jsx_log, "json_path": json_path,
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
        run_jsx(settings["jsx_path"], log, poll_log_path=settings["log_path"],
                timeout=self.jsx_timeout,
                completion_marker="블랙북 v2 조판 완료")

    # ── 4단계: verify — 검수 게이트 내장 ────────────────────────────────────

    def verify(self, job_dir, log):
        from core.inspect import dump_indd, _dump_paragraphs
        settings = json.load(open(os.path.join(job_dir, ".settings.json"),
                                  encoding="utf-8"))
        from engines.mockexam_v2.parser import extract_file_paragraphs

        # 원고 원본 단어셋 (검수 기준)
        src_words = set()
        for f in glob.glob(os.path.join(job_dir, "uploads", "*")):
            if not os.path.isfile(f):
                continue
            try:
                for para in extract_file_paragraphs(f):
                    for w in _RE_WORD.findall(_norm_typo(para["text"])):
                        src_words.add(w.lower())
            except Exception as e:
                log(f"[검수] 원본 추출 실패({os.path.basename(f)}): {e}")

        dump = dump_indd(settings["indd_path"],
                         os.path.join(job_dir, "typeset_dump.json"), log)
        got = set()
        overflow_heads = []
        for st in dump["stories"]:
            for pp in st["paragraphs"]:
                for w in _RE_WORD.findall(_norm_typo(pp["t"])):
                    got.add(w.lower())
            if st.get("overflow") and st["paragraphs"]:
                overflow_heads.append(st["paragraphs"][0]["t"][:40])
        missing = src_words - got
        pdf_ok = os.path.exists(settings["pdf_path"])

        warnings = []
        ok = True
        if missing:
            ok = False
            warnings.append(f"❌ 내용누락 {len(missing)}단어: "
                            + ", ".join(sorted(missing)[:8]))
        if overflow_heads:
            warnings.append("⚠️ 오버플로우(수동 처리 필요) "
                            f"{len(overflow_heads)}건: "
                            + " | ".join(overflow_heads[:5]))
        if not pdf_ok:
            ok = False
            warnings.append("❌ PDF 미생성")
        render_warns = [l.strip() for l in open(settings["log_path"],
                                                encoding="utf-8")
                        if "[경고]" in l]
        warnings.extend(f"⚠️ {w}" for w in render_warns[:5])

        log(f"[검수] 원고 {len(src_words)}단어 중 누락 {len(missing)} / "
            f"오버플로우 {len(overflow_heads)} / PDF {'OK' if pdf_ok else '실패'}")
        return {
            "ok": ok,
            "overflow": len(overflow_heads),
            "stories": {},
            "pdf_path": settings["pdf_path"] if pdf_ok else None,
            "indd_path": settings["indd_path"],
            "warnings": warnings,
        }
