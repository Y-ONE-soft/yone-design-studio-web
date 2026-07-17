"""모의고사 가로판 결합 엔진 (수동 MergeMockExam.jsx 웹 흡수).

여러 회차 가로판('전체(C)') 모의고사 워크북 .indd에서 지정한 문제 코드
(YYMMQQ)에 해당하는 페이지 구간을 추출해 하나의 PDF로 결합하고,
(옵션) 결합 .indd도 함께 저장한다.

수동본과의 구조 대응 (파리티 — 기본값 동일):
  - 구간 감지: A마스터 페이지 + 6자리 코드 (수동 findAllMarkers 동일)
  - PDF: 코드별 페이지 범위를 섹션 번호 임시 재설정(순차 폴리오) 후
    개별 export → CoreGraphics(python3)로 결합 (수동 방식 그대로 —
    page.move() 없음, 원본 무수정)
  - .indd: 첫 코드 문서 saveACopy → 범위 외 삭제 → 나머지 duplicate
    (수동 saveAsIndd 동일, 기본 저장 ON = 수동 체크박스 기본값)
수동본과 달리 파일 선택 다이얼로그 대신 GDrive에서 회차별 가로판을
자동 매칭하고(mockexam_sero_merge와 동일 입력 스펙), /tmp 하드코딩은
job_dir로 외부화했다.

입력 스펙/코드 파싱/소스 매칭 파이프는 MockexamSeroMergeEngine 상속 —
파일 매칭 키워드('세로' → '전체')와 출력/JSX만 교체.
"""

import json
import os
import re
import unicodedata

from engines.mockexam_sero_merge.engine import MockexamSeroMergeEngine


def _nfc(s):
    return unicodedata.normalize("NFC", s)


_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, ["gdrive_base", "output_base"])


class MockexamHorizMergeEngine(MockexamSeroMergeEngine):

    _SRC_LABEL = "가로판(전체)"

    @property
    def material_id(self):
        return "mockexam_horiz_merge"

    @property
    def display_name(self):
        return "모의고사 가로판 결합"

    @property
    def description(self):
        return ("여러 회차 가로판(전체 C) 모의고사에서 문제 코드 기준으로 "
                "페이지를 추출·결합 → PDF (+.indd)")

    @property
    def subject_prefix(self):
        return "가로판결합"

    @property
    def template_name(self):
        return "typeset_mockexam_horiz_merge.html"

    def _config(self):
        return _load_config()

    @property
    def jsx_timeout(self):
        return 1800  # 대형 가로판(전체 C) 여러 개 열기 + 부분 export + saveACopy

    def run_indesign(self, job_dir, log):
        """전용 실행기 — 대형 소스 열기/saveACopy의 무로그 구간 스톨 오탐 방지
        (slim_merge와 동일 근거 — 27MB 전체(C) 열기 실측 ~3분)."""
        from core.indesign import runner
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)
        # 폴링 로그 = job 전용 로그 — 출력 폴더 공용 로그는 과거 실행의
        # 완료 마커/[오류]가 누적돼 오판정 (merge 계열 감사 패턴)
        log_paths = settings.get("log_paths") or []
        log_file = (log_paths[0] if log_paths
                    else os.path.join(job_dir, self.log_filename))
        runner.run_jsx(os.path.join(job_dir, "run.jsx"), log,
                       poll_log_path=log_file, timeout=self.jsx_timeout,
                       stall_limit=900,
                       completion_marker="===== 완료 =====")

    @property
    def upload_spec(self):
        spec = super().upload_spec
        spec["slots"].append({
            "key": "save_indd",
            "label": "결합 .indd 함께 저장 (on/off, 기본 on)",
            "type": "text",
            "required": False,
        })
        return spec

    # ─── 소스 매칭: 세로 대신 가로판('전체') ────────────────────────

    @staticmethod
    def _find_vertical_file(folder, grade_num, year, month):
        """GDrive 폴더에서 가로판(전체) .indd 매칭.

        규칙: '전체' 포함 + '세로' 미포함 + '고{N}' 접두 + '{YY}년' +
        '{M}월'(0패딩 변형 허용). 후보 여러 개면 파일명 최단
        (— ' 사본'/'[작업중]' 파생본 배제, sero와 동일 휴리스틱).
        """
        if not os.path.isdir(folder):
            return None
        from engines.final.extractor import _resolve_local_mirror as _rlm
        folder = _rlm(folder, None)

        month_int = int(month)
        month_variants = [str(month_int)]
        if month_int < 10:
            month_variants.append(f"0{month_int}")

        candidates = []
        for raw in os.listdir(folder):
            nfc = _nfc(raw)
            if not nfc.lower().endswith(".indd"):
                continue
            if "전체" not in nfc or "세로" in nfc:
                continue
            if not nfc.startswith(f"고{grade_num}"):
                continue
            if f"{year}년" not in nfc:
                continue
            if not any(f"{mv}월" in nfc for mv in month_variants):
                continue
            candidates.append(os.path.join(folder, raw))

        if not candidates:
            return None
        candidates.sort(key=lambda p: len(os.path.basename(p)))
        return candidates[0]

    # ─── prepare_jsx ───────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = self._config()
        grade = self._get_meta(job_dir, "grade", "고1")
        school = _nfc(self._get_meta(job_dir, "school", "학교미지정"))
        exam_period = self._get_meta(job_dir, "exam_period", "기간미지정")
        result_name = self._get_meta(job_dir, "result_name", "").strip()
        save_indd_raw = self._get_meta(job_dir, "save_indd", "on").lower()
        save_indd = save_indd_raw in ("", "on", "true", "1", "yes")

        if not result_name:
            raise ValueError("결과 파일명을 입력하세요.")

        output_dir = os.path.join(
            cfg["output_base"], grade, exam_period, school
        )
        os.makedirs(output_dir, exist_ok=True)
        log(f"[출력 폴더] {output_dir}")

        pdf_out = os.path.join(output_dir, f"{result_name}.pdf")
        if os.path.exists(pdf_out):
            n = 2
            while n < 1000:
                trial = os.path.join(output_dir, f"{result_name}_{n}.pdf")
                if not os.path.exists(trial):
                    pdf_out = trial
                    break
                n += 1
        indd_out = os.path.splitext(pdf_out)[0] + ".indd"

        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)

        pdf_parts_dir = os.path.join(job_dir, "pdf_parts")
        os.makedirs(pdf_parts_dir, exist_ok=True)

        settings = {
            "output_pdf": pdf_out,
            "output_indd": indd_out,
            "output_dir": output_dir,
            "save_indd": save_indd,
            "pdf_preset": cfg.get("pdf_preset", ""),
            "pdf_parts_dir": pdf_parts_dir,
            "paths_txt": os.path.join(job_dir, "pdf_paths.txt"),
            "combine_py": os.path.join(job_dir, "combine_pdf.py"),
            "log_path": os.path.join(output_dir, self.log_filename),
            "log_paths": [os.path.join(job_dir, self.log_filename)],
            "sources": meta["sources"],
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

        log(f"[결과 PDF]  {os.path.basename(pdf_out)}")
        if save_indd:
            log(f"[결과 .indd] {os.path.basename(indd_out)}")
        return jsx_dst

    # ─── verify ────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        pdf_out = settings["output_pdf"]
        indd_out = settings["output_indd"]
        save_indd = settings.get("save_indd", True)

        warnings = []
        if not os.path.exists(pdf_out):
            warnings.append(f"PDF 미생성: {os.path.basename(pdf_out)}")
        if save_indd and not os.path.exists(indd_out):
            warnings.append(f".indd 미생성: {os.path.basename(indd_out)}")

        # job 전용 로그만 판정 (공용 로그 누적 오염 방지 — merge 계열 감사)
        log_paths = settings.get("log_paths") or []
        log_path = log_paths[0] if log_paths else settings.get("log_path", "")
        if log_path and os.path.exists(log_path):
            try:
                content = open(log_path, encoding="utf-8",
                               errors="ignore").read()
                warn_count = len(re.findall(r"\[경고\]|\[오류\]", content))
                if warn_count > 0:
                    warnings.append(f"JSX 경고/오류 {warn_count}건 (로그 확인)")
                if "===== 완료 =====" not in content:
                    warnings.append("완료 마커 없음 — JSX 중단 의심")
            except OSError:
                pass
        else:
            warnings.append("job 로그 없음 — JSX 미실행 의심")

        ok = os.path.exists(pdf_out) and len(warnings) == 0

        return {
            "ok": ok,
            "overflow": 0,
            "stories": {},
            "pdf_path": pdf_out if os.path.exists(pdf_out) else None,
            "pdf_paths": [pdf_out] if os.path.exists(pdf_out) else [],
            "indd_path": (indd_out if (save_indd and os.path.exists(indd_out))
                          else None),
            "warnings": warnings,
        }
