"""펼침면 압축 엔진 (수동 Slim_Merge.jsx / Slim_Merge2.jsx 웹 흡수).

워크북 전체(C) .indd에서 특정 단원 섹션의 짝(왼쪽)-홀(오른쪽) 페이지를
한 페이지로 병합해 펼침면을 압축한다. 섹션 탐지는 '단원' 스타일
(문자 스타일 그룹 '마스터페이지' > '단원' → 문서 문자 스타일 → 단락
스타일 순 폴백)이 적용된 텍스트의 마커 문자열 포함 여부.

두 가지 모드 (수동 스크립트 2종과 1:1 대응, 기본값 파리티):
  - ox      (Slim_Merge.jsx, 2026-05-26): '본문 O/X' 섹션.
            왼쪽 면적최대 프레임을 상단 절반으로 축소 + 오른쪽 면적최대
            프레임을 왼쪽 하단 절반으로 move → 비워진 오른쪽 페이지 삭제.
  - arrange (Slim_Merge2.jsx, 2026-05-06): '문장 배열' 섹션.
            스레드 스토리 독립화 → 하단(y>100) 프레임 삭제 → 오른쪽
            페이지 프레임을 왼쪽으로 duplicate + 고정 좌표 배치 → 오른쪽
            페이지 삭제.

입력: .indd 업로드 + 모드 선택. 출력: 압축된 .indd (원본 무접촉 —
job_dir 사본을 출력 경로로 복사 후 in-place 수정). PDF export 없음
(수동 스크립트 파리티 — 압축본은 후속 조판 작업의 중간 산출물).
"""

import json
import os
import re
import shutil
import unicodedata

from config import STUDIO_ROOT
from core.base import BaseEngine, safe_copy


def _nfc(s):
    return unicodedata.normalize("NFC", s) if s else s


_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["output_base"])


class SlimMergeEngine(BaseEngine):

    @property
    def material_id(self):
        return "slim_merge"

    @property
    def display_name(self):
        return "펼침면 압축"

    @property
    def description(self):
        return ("본문 O/X · 문장 배열 섹션의 짝-홀 페이지를 병합해 "
                "펼침면을 압축한 .indd 생성")

    @property
    def subject_prefix(self):
        return "펼침면압축"

    @property
    def template_name(self):
        return "typeset_slim_merge.html"

    @property
    def log_filename(self):
        return "slim_log.txt"

    @property
    def jsx_timeout(self):
        # 대형 전체(C) 문서: 열기+findText ~3분 + page.remove() 페이지당
        # 수십 초 (256p 실측 총 10분) — 여유 있게 30분
        return 1800

    def run_indesign(self, job_dir, log):
        """전용 실행기 — 대형 문서의 무로그 구간(open/save) 스톨 오탐 방지.

        기본 stall_limit 300초는 27MB 전체(C) 문서의 열기+findText(실측
        175초)나 저장 구간에서 오탐 위험 — workbook_v2 전례(W4)대로 900초.
        """
        import json as _json
        from core.indesign import runner
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = _json.load(f)
        # 폴링 로그 = job 전용 로그 (이번 실행분만) — 출력 폴더 공용 로그는
        # 과거 실행의 완료 마커/[오류]가 누적돼 오판정 (merge 계열 감사 패턴)
        log_paths = settings.get("log_paths") or []
        log_file = (log_paths[0] if log_paths
                    else os.path.join(job_dir, self.log_filename))
        # completion_marker 필수: 이 엔진은 PDF export가 없어 runner의
        # 기본 완료 휴리스틱("PDF:"/"조판 완료")에 걸리지 않는다 (E2E 실측)
        runner.run_jsx(os.path.join(job_dir, "run.jsx"), log,
                       poll_log_path=log_file, timeout=self.jsx_timeout,
                       stall_limit=900,
                       completion_marker="===== 완료 =====")

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "src_indd",
                    "label": "대상 .indd (워크북 전체)",
                    "type": "file",
                    "accept": ".indd",
                    "required": True,
                },
                {
                    "key": "merge_mode",
                    "label": "병합 대상 섹션 (ox=본문 O/X, arrange=문장 배열)",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "result_name",
                    "label": "결과 파일명 (확장자 제외)",
                    "type": "text",
                    "required": False,
                    "placeholder": "비워두면 원본 파일명_압축 으로 자동",
                },
            ]
        }

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        cfg = _load_config()

        src = uploaded_files.get("src_indd")
        if not src or not os.path.exists(src):
            raise FileNotFoundError(".indd 파일이 업로드되지 않았습니다")

        mode = (uploaded_files.get("merge_mode") or "ox").strip().lower()
        if mode not in cfg["modes"]:
            raise ValueError(
                f"알 수 없는 모드: {mode!r} — "
                f"{', '.join(sorted(cfg['modes']))} 중 선택"
            )
        mode_cfg = cfg["modes"][mode]
        log(f"[모드] {mode} ({mode_cfg['label']} 섹션)")

        # 업로드 사본 → job_dir (원본 무접촉)
        src_base = _nfc(os.path.basename(src))
        local_path = os.path.join(job_dir, f"src_{src_base}")
        try:
            safe_copy(src, local_path, log=log)
        except Exception as e:
            raise RuntimeError(f".indd 복사 실패: {e}")
        log(f"[복사] {os.path.basename(local_path)}")

        # 결과 파일명 — 사용자 입력 > 원본 파일명 기반 자동
        result_name = (uploaded_files.get("result_name") or "").strip()
        if not result_name:
            base = src_base
            if base.lower().endswith(".indd"):
                base = base[:-5]
            result_name = f"{base}_압축"
        log(f"[결과 파일명] {result_name}")

        meta = {
            "src_path": local_path,
            "src_original_name": src_base,
            "mode": mode,
            "result_name": result_name,
        }
        meta_path = os.path.join(job_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta_path

    # ─── prepare_jsx ───────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()

        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)

        output_dir = cfg["output_base"]
        os.makedirs(output_dir, exist_ok=True)

        base = meta["result_name"]
        if base.lower().endswith(".indd"):
            base = base[:-5]
        indd_out = os.path.join(output_dir, f"{base}.indd")
        n = 2
        while os.path.exists(indd_out) and n < 1000:
            indd_out = os.path.join(output_dir, f"{base}_{n}.indd")
            n += 1
        log(f"[출력] {indd_out}")

        # 사본을 출력 경로로 미리 복사 — JSX는 output_indd를 열어 in-place 처리
        shutil.copy2(meta["src_path"], indd_out)

        mode_cfg = cfg["modes"][meta["mode"]]
        settings = {
            "output_indd": indd_out,
            "output_dir": output_dir,
            "mode": meta["mode"],
            "marker_text": mode_cfg["marker"],
            "unit_style_name": cfg.get("unit_style_name", "단원"),
            "unit_style_group": cfg.get("unit_style_group", "마스터페이지"),
            # arrange 모드 파라미터 (수동 Slim_Merge2.jsx 하드코딩 값과 동일)
            "arrange_left_bounds": mode_cfg.get("left_bounds"),
            "arrange_right_bounds": mode_cfg.get("right_bounds"),
            "arrange_bottom_y": mode_cfg.get("bottom_y_threshold", 100),
            "log_path": os.path.join(output_dir, self.log_filename),
            "log_paths": [os.path.join(job_dir, self.log_filename)],
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        jsx_src = os.path.join(_DIR, "jsx", "run.jsx")
        jsx_dst = os.path.join(job_dir, "run.jsx")
        with open(jsx_src, encoding="utf-8") as f:
            jsx_code = f.read()
        jsx_code = jsx_code.replace("__SETTINGS_PATH__", settings_path)
        with open(jsx_dst, "w", encoding="utf-8") as f:
            f.write(jsx_code)
        return jsx_dst

    # ─── verify ────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        indd_out = settings["output_indd"]
        warnings = []
        if not os.path.exists(indd_out):
            warnings.append(f".indd 미생성: {os.path.basename(indd_out)}")

        # job 전용 로그만 판정 — 출력 폴더 공용 로그(log_path)는 과거 실행분
        # 누적으로 다른 작업 경고가 계상된다 (2026-07-17 merge 계열 감사).
        log_paths = settings.get("log_paths") or []
        log_path = log_paths[0] if log_paths else settings.get("log_path", "")
        merged = 0
        if log_path and os.path.exists(log_path):
            try:
                content = open(log_path, encoding="utf-8",
                               errors="ignore").read()
                warn_count = len(re.findall(r"\[경고\]|\[오류\]", content))
                if warn_count > 0:
                    warnings.append(f"JSX 경고/오류 {warn_count}건 (로그 확인)")
                m = re.search(r"병합 그룹: (\d+)개", content)
                if m:
                    merged = int(m.group(1))
                    if merged == 0:
                        warnings.append("병합된 섹션 그룹 0개 — 마커 미탐지 확인")
        # 병합 완료 마커가 아예 없으면 JSX가 끝까지 못 간 것
                if "===== 완료 =====" not in content:
                    warnings.append("완료 마커 없음 — JSX 중단 의심")
            except OSError:
                pass
        else:
            warnings.append("job 로그 없음 — JSX 미실행 의심")

        ok = os.path.exists(indd_out) and len(warnings) == 0

        return {
            "ok": ok,
            "overflow": 0,
            "stories": {"merged_groups": merged},
            "pdf_path": None,
            "pdf_paths": [],
            "indd_path": indd_out if os.path.exists(indd_out) else None,
            "warnings": warnings,
        }
