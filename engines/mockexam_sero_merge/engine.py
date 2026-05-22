"""모의고사 세로 결합 엔진.

여러 회차 세로버전 모의고사 .indd 에서 지정한 문제 코드(YYMMQQ)에 해당하는
페이지만 추출해서, 빈 템플릿(.indd) 위에 결합하고 PDF 까지 내보낸다.

입력:
  - 학년(고1/고2), 학교, 시험기간 (공통 메타데이터)
  - 문제 코드 리스트 (textarea, 6자리 YYMMQQ)
  - 결과 파일명 (확장자 제외)

소스 .indd 는 GDrive 의 `워크북/모의고사/고{학년}/` 폴더에서 파일명 패턴으로
자동 매칭 (예: G1_22YR_03MO_VERT(C).indd / 고1_25년_3월_전체(C).indd 등 —
실제 매칭 규칙은 JSX 와 동일하게 '세로' + '고{N}' + '{YY}년' + '{M}월'
포함 여부로 판단).
"""

import json
import os
import re
import unicodedata

from config import STUDIO_ROOT
from core.base import BaseEngine, safe_copy_indd


def _nfc(s):
    return unicodedata.normalize("NFC", s)


_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_PATH_KEYS = ["template_path", "gdrive_base", "output_base"]


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class MockexamSeroMergeEngine(BaseEngine):

    @property
    def material_id(self):
        return "mockexam_sero_merge"

    @property
    def display_name(self):
        return "모의고사 세로 결합"

    @property
    def description(self):
        return "여러 회차 세로버전 모의고사에서 문제 코드 기준으로 페이지를 추출·결합 → .indd + PDF"

    @property
    def subject_prefix(self):
        return "세로결합"

    @property
    def template_name(self):
        return "typeset_mockexam_sero_merge.html"

    @property
    def log_filename(self):
        return "merge_log.txt"

    @property
    def jsx_timeout(self):
        return 900  # 15분 — 여러 .indd 열기 + PDF export

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "codes",
                    "label": "문제 코드 (한 줄에 하나, 6자리 YYMMQQ — 예: 260320)",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "key": "result_name",
                    "label": "결과 파일명 (확장자 제외)",
                    "type": "text",
                    "required": True,
                },
            ]
        }

    # ─── 헬퍼 ───────────────────────────────────────────────────────

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    @staticmethod
    def _parse_code(raw):
        code = re.sub(r"\s", "", raw)
        if not re.match(r"^\d{6}$", code):
            return None
        return {
            "raw": code,
            "year": code[0:2],
            "month": code[2:4],
            "qNum": code[4:6],
        }

    @staticmethod
    def _find_vertical_file(folder, grade_num, year, month):
        """GDrive 폴더에서 vertical .indd 매칭 (JSX 와 동일 규칙)."""
        if not os.path.isdir(folder):
            return None
        # 미러 redirect — Drive zombie 시 GDrive listdir EDEADLK 회피
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
            if "세로" not in nfc:
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

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        """코드 → 소스 .indd 매핑 → 로컬 사본 → metadata.json."""
        cfg = _load_config()

        codes_text = uploaded_files.get("codes", "")
        grade = self._get_meta(job_dir, "grade", "고1")
        grade_num = grade.replace("고", "")

        # 코드 파싱
        codes = []
        for line in codes_text.splitlines():
            line = line.strip()
            if not line:
                continue
            p = self._parse_code(line)
            if not p:
                raise ValueError(f"잘못된 코드: {line!r} (6자리 숫자 필요)")
            codes.append(p)
        if not codes:
            raise ValueError("문제 코드가 입력되지 않았습니다.")

        log(f"[코드] {len(codes)}개")

        # GDrive 폴더
        gdrive_folder = os.path.join(cfg["gdrive_base"], grade)
        if not os.path.isdir(gdrive_folder):
            raise FileNotFoundError(f"GDrive 폴더를 찾을 수 없습니다: {gdrive_folder}")
        log(f"[GDrive] {gdrive_folder}")

        # 코드별 소스 파일 매칭
        sources = []
        not_found = []
        for c in codes:
            f = self._find_vertical_file(gdrive_folder, grade_num, c["year"], c["month"])
            if not f:
                not_found.append(
                    f"{c['raw']} ({c['year']}년 {int(c['month'])}월 파일 없음)"
                )
                continue
            sources.append({
                "code": c["raw"],
                "year": c["year"],
                "month": c["month"],
                "qNum": c["qNum"],
                "gdrive_path": f,
            })
            log(f"  - {c['raw']} → {os.path.basename(f)}")

        if not_found:
            raise FileNotFoundError(
                "파일을 찾지 못한 코드:\n  " + "\n  ".join(not_found)
            )

        # GDrive 파일을 로컬 사본으로 — InDesign 세션 안정성 + JSX 동시 열기 대비
        # 같은 GDrive 파일이 여러 코드에 사용될 수 있으므로 path 기준 dedup
        local_by_src = {}
        local_sources = []
        for src in sources:
            gp = src["gdrive_path"]
            if gp not in local_by_src:
                base = os.path.basename(gp)
                # 파일명 그대로 사용 — 같은 회차가 같은 로컬 사본을 공유
                local_path = os.path.join(job_dir, f"src_{base}")
                try:
                    actual = safe_copy_indd(gp, local_path)
                except Exception as e:
                    raise RuntimeError(
                        f"GDrive 파일 복사 실패: {base} — {e}"
                    )
                local_by_src[gp] = actual
                log(f"  로컬 복사: {os.path.basename(actual)}")
            local_sources.append({**src, "local_path": local_by_src[gp]})

        # metadata.json
        meta_path = os.path.join(job_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"codes": codes, "sources": local_sources},
                f, ensure_ascii=False, indent=2
            )
        return meta_path

    # ─── prepare_jsx ───────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        grade = self._get_meta(job_dir, "grade", "고1")
        school = _nfc(self._get_meta(job_dir, "school", "학교미지정"))
        exam_period = self._get_meta(job_dir, "exam_period", "기간미지정")
        result_name = self._get_meta(job_dir, "result_name", "").strip()

        if not result_name:
            raise ValueError("결과 파일명을 입력하세요.")

        # 출력 디렉터리 — 조판/교재/모의고사세로결합/{학년}/{시험기간}/{학교}/
        output_dir = os.path.join(
            STUDIO_ROOT, "조판", "교재", "모의고사세로결합",
            grade, exam_period, school
        )
        os.makedirs(output_dir, exist_ok=True)
        log(f"[출력 폴더] {output_dir}")

        # 결과 파일명 중복 처리
        indd_out = os.path.join(output_dir, f"{result_name}.indd")
        if os.path.exists(indd_out):
            n = 2
            while n < 1000:
                trial = os.path.join(output_dir, f"{result_name}_{n}.indd")
                if not os.path.exists(trial):
                    indd_out = trial
                    break
                n += 1
        pdf_out = os.path.splitext(indd_out)[0] + ".pdf"

        # 메타 로드
        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)

        # settings.json
        settings = {
            "template_path": cfg["template_path"],
            "output_indd": indd_out,
            "output_pdf": pdf_out,
            "output_dir": output_dir,
            "log_path": os.path.join(output_dir, self.log_filename),
            "log_paths": [os.path.join(job_dir, self.log_filename)],
            "keep_head": cfg.get("keep_head", 3),
            "school": school,
            "grade": grade,
            "exam_period": exam_period,
            "sources": meta["sources"],
        }
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        # JSX 사본 + 토큰 치환
        jsx_src = os.path.join(_DIR, "jsx", "run.jsx")
        jsx_dst = os.path.join(job_dir, "run.jsx")
        with open(jsx_src, encoding="utf-8") as f:
            jsx_code = f.read()
        jsx_code = jsx_code.replace("__SETTINGS_PATH__", settings_path)
        with open(jsx_dst, "w", encoding="utf-8") as f:
            f.write(jsx_code)

        log(f"[결과 .indd] {os.path.basename(indd_out)}")
        log(f"[결과 PDF]  {os.path.basename(pdf_out)}")
        return jsx_dst

    # ─── verify ────────────────────────────────────────────────────

    def verify(self, job_dir, log):
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        indd_out = settings["output_indd"]
        pdf_out = settings["output_pdf"]

        warnings = []
        if not os.path.exists(indd_out):
            warnings.append(f".indd 미생성: {os.path.basename(indd_out)}")
        if not os.path.exists(pdf_out):
            warnings.append(f"PDF 미생성: {os.path.basename(pdf_out)}")

        # 로그에서 [경고]/[오류] 카운트
        log_path = settings.get("log_path", "")
        warn_count = 0
        if log_path and os.path.exists(log_path):
            try:
                content = open(log_path, encoding="utf-8", errors="ignore").read()
                warn_count = len(re.findall(r"\[경고\]|\[오류\]", content))
                if warn_count > 0:
                    warnings.append(f"JSX 경고/오류 {warn_count}건 (로그 확인)")
            except OSError:
                pass

        ok = os.path.exists(pdf_out) and len(warnings) == 0

        return {
            "ok": ok,
            "overflow": 0,
            "stories": {},
            "pdf_path": pdf_out if os.path.exists(pdf_out) else None,
            "pdf_paths": [pdf_out] if os.path.exists(pdf_out) else [],
            "warnings": warnings,
        }
