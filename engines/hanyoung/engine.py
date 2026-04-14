import json
import os
import re
import shutil

from core.base import BaseEngine, safe_copy_indd
from core.paths import resolve, resolve_config
from engines.hanyoung.parser import parse_multiple_files

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(_DIR, "jsx", "run.jsx")
_SETTINGS_MARKER = '__SETTINGS_PATH__'


def _load_config():
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    resolve_config(cfg, ["indd_output_dir"])
    # layouts 내부 indd_original도 resolve
    for layout in cfg.get("layouts", {}).values():
        if "indd_original" in layout:
            layout["indd_original"] = resolve(layout["indd_original"])
    return cfg


class HanyoungEngine(BaseEngine):

    @property
    def material_id(self):
        return "hanyoung"

    @property
    def display_name(self):
        return "한영보카"

    @property
    def description(self):
        return "한영보카 단어장 조판 자동화"

    @property
    def subject_prefix(self):
        return "한영보카"

    @property
    def template_name(self):
        return "typeset_hanyoung.html"

    @property
    def log_filename(self):
        return "typeset_log.txt"

    @property
    def jsx_timeout(self):
        return 600  # 세로+가로 2개 내지 처리 시 최대 10분

    @property
    def skip_indesign(self):
        cfg = _load_config()
        for lay in cfg.get("layouts", {}).values():
            if lay.get("indd_original") and os.path.exists(lay["indd_original"]):
                return False
        return True

    @property
    def upload_spec(self):
        return {
            "slots": [{
                "key": "manuscripts",
                "label": "원고 파일 (.xlsx, .hwp, .docx, .pdf, .csv, .txt)",
                "required": True,
                "multiple": True,
                "accept": ".xlsx,.xls,.csv,.tsv,.txt,.hwp,.hwpx,.docx,.pdf",
            }]
        }

    # ── 1단계: 파싱 + 세로/가로 분리 ─────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        file_paths = uploaded_files.get("manuscripts", [])
        if isinstance(file_paths, str):
            file_paths = [file_paths]
        if not file_paths:
            raise ValueError("업로드된 원고 파일이 없습니다.")

        # 전체 파싱
        json_path = os.path.join(job_dir, "content.json")
        result = parse_multiple_files(file_paths, json_path, log)

        # 영영풀이 유무로 단원 분리
        sero = [ch for ch in result["chapters"] if not ch.get("has_definition")]
        garo = [ch for ch in result["chapters"] if ch.get("has_definition")]

        layouts_used = []
        if sero:
            sero_path = os.path.join(job_dir, "content_sero.json")
            with open(sero_path, "w", encoding="utf-8") as f:
                json.dump({"layout": "세로형", "chapters": sero,
                           "total_entries": sum(c["total"] for c in sero)},
                          f, ensure_ascii=False, indent=2)
            layouts_used.append("세로형")
            sero_total = sum(c["total"] for c in sero)
            log(f"[분리] 세로형: {len(sero)}개 단원, {sero_total}개 단어")

        if garo:
            garo_path = os.path.join(job_dir, "content_garo.json")
            with open(garo_path, "w", encoding="utf-8") as f:
                json.dump({"layout": "가로형", "chapters": garo,
                           "total_entries": sum(c["total"] for c in garo)},
                          f, ensure_ascii=False, indent=2)
            layouts_used.append("가로형")
            garo_total = sum(c["total"] for c in garo)
            log(f"[분리] 가로형: {len(garo)}개 단원, {garo_total}개 단어")

        # 사용할 레이아웃 저장
        open(os.path.join(job_dir, "layouts.txt"), "w").write(",".join(layouts_used))

        return json_path

    # ── 2단계: JSX 준비 (세로+가로 순차 처리) ─────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        school = self._get_meta(job_dir, "school", "학교미선택")
        layouts_used = self._get_meta(job_dir, "layouts", "세로형").split(",")
        output_dir = cfg.get("indd_output_dir", job_dir)
        os.makedirs(output_dir, exist_ok=True)

        # 각 레이아웃별 작업 정보 생성
        jobs = []
        for layout in layouts_used:
            layout_cfg = cfg["layouts"].get(layout)
            if not layout_cfg:
                continue

            indd_src = layout_cfg.get("indd_original", "")
            if not indd_src or not os.path.exists(indd_src):
                log(f"[경고] {layout} 원본 없음: {indd_src}")
                continue

            # 레이아웃별 파일명: 배재1_한영보카(세로형)_내지.indd
            suffix = f"({layout})" if len(layouts_used) > 1 else ""
            indd_name = f"{school}_{self.subject_prefix}{suffix}_내지.indd"
            indd_path = os.path.join(output_dir, indd_name)

            # 원본 복사 (동명 파일 보호)
            indd_path = safe_copy_indd(indd_src, indd_path)
            log(f"[내지] {layout}: {os.path.basename(indd_path)} ({layout_cfg['cols']}열, {layout_cfg['capacity']}행)")

            content_file = "content_sero.json" if layout == "세로형" else "content_garo.json"
            content_path = os.path.join(job_dir, content_file)
            if not os.path.exists(content_path):
                # 레이아웃 1개인 경우 content.json 그대로 사용
                content_path = json_path

            jobs.append({
                "json_path": content_path,
                "indd_path": indd_path,
                "layout": layout,
            })

        if not jobs:
            raise FileNotFoundError("사용 가능한 InDesign 원본이 없습니다.")

        # .settings.json — jobs 배열로 저장
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump({"jobs": jobs, "output_dir": job_dir}, f, ensure_ascii=False)

        # run.jsx 사본
        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()
        jsx_copy = os.path.join(job_dir, "run.jsx")
        with open(jsx_copy, "w", encoding="utf-8") as f:
            f.write(jsx_src.replace(_SETTINGS_MARKER, settings_path))

        return jsx_copy

    # ── 2.5단계: InDesign 단계별 실행 (AppleEvents -609 회피) ─────────────

    def run_indesign(self, job_dir, log):
        """JSX 대신 Python에서 InDesign을 단계별로 직접 제어."""
        from engines.hanyoung.indesign_stepper import run_typeset
        settings_path = os.path.join(job_dir, ".settings.json")
        run_typeset(settings_path, log)

    # ── 3단계: 검수 ───────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        cfg = _load_config()
        log_path = os.path.join(job_dir, cfg["log_filename"])

        # content.json에서 전체 정보
        json_path = os.path.join(job_dir, "content.json")
        content = {}
        if os.path.exists(json_path):
            with open(json_path, encoding="utf-8") as f:
                content = json.load(f)

        total = content.get("total_entries", 0)

        sources_summary = {}
        for ch in content.get("chapters", []):
            ch_name = ch.get("name", "?")
            layout_tag = "가로" if ch.get("has_definition") else "세로"
            for sec in ch.get("sections", []):
                name = f"[{layout_tag}] {ch_name} — {sec['name']}"
                sources_summary[name] = {"actual": sec["count"], "expected": sec["count"]}

        warnings = []
        overflow = 0
        pdf_paths = []

        if os.path.exists(log_path):
            lc = open(log_path, encoding="utf-8", errors="ignore").read()

            # 오버플로우 합계
            for m in re.finditer(r"오버플로우:\s*(\d+)개", lc):
                overflow += int(m.group(1))

            # PDF 성공 횟수
            pdf_count = lc.count("PDF: 성공")

            # 모든 PDF 수집
            for f in os.listdir(job_dir):
                if f.lower().endswith(".pdf"):
                    pdf_paths.append(os.path.join(job_dir, f))

            if "용량 초과" in lc:
                warnings.append("표 용량 초과 — 일부 단어 미배치")
            if overflow > 0:
                warnings.append(f"오버플로우 {overflow}개")

            # 총 채우기 수 합산
            filled_total = 0
            for m in re.finditer(r"채우기 완료:\s*(\d+)개", lc):
                filled_total += int(m.group(1))
            if filled_total > 0 and filled_total < total:
                warnings.append(f"배치: {filled_total}/{total}개")

        ok = len(pdf_paths) > 0 and overflow == 0 and not warnings

        # 첫 번째 PDF를 메인으로 (다운로드용)
        pdf_path = pdf_paths[0] if pdf_paths else None

        result = {
            "ok": ok,
            "total_entries": total,
            "grade": "",
            "grade_label": f"PDF {len(pdf_paths)}개",
            "overflow": overflow,
            "stories": sources_summary,
            "pdf_path": pdf_path,
            "pdf_paths": pdf_paths,  # 모든 PDF
            "warnings": warnings,
        }

        status = "✅ 완료" if ok else f"⚠️ 확인 필요 ({len(warnings)}건)"
        log(f"[검수] {status} | {total}개 | PDF {len(pdf_paths)}개 | 오버플로우: {overflow}")
        return result

    @staticmethod
    def _get_meta(job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p).read().strip() if os.path.exists(p) else default
