"""분석본 결합 엔진.

여러 회차 분석본 .indd 에서 지정한 문제 코드(YYMMQQ)에 해당하는
페이지만 추출해서, 분석본 마스터 템플릿 위에 결합하고 PDF 까지 내보낸다.

입력:
  - 학년(고1/고2), 학교, 시험기간 (공통 메타데이터)
  - 문제 코드 리스트 (textarea, 6자리 YYMMQQ)
  - 결과 파일명 (확장자 제외)

소스 .indd 는 GDrive 의 `모의고사 작업/고{학년}/고{학년} {YY}년 {M}월/`
폴더에서 파일명에 "분석본"이 포함된 모든 .indd 파일을 후보로 두고
코드의 페이지를 찾아 추출한다. (메인 / 보조2 / 짤지문 등 변형 자동 매칭)

페이지 매칭 규칙은 JSX 와 동일하게
"(고N) {YY}년 {M}월 {QQ}번" Korean 마커 텍스트로 한다.
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


class AnalysisMergeEngine(BaseEngine):

    @property
    def material_id(self):
        return "analysis_merge"

    @property
    def display_name(self):
        return "분석본 결합"

    @property
    def description(self):
        return "여러 회차 분석본에서 문제 코드 기준으로 페이지를 추출·결합 → .indd + PDF"

    @property
    def subject_prefix(self):
        return "분석본결합"

    @property
    def template_name(self):
        return "typeset_analysis_merge.html"

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
                    "label": "문제 코드 (한 줄에 하나, 6자리 YYMMQQ — 예: 250320)",
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
    def _find_month_folder(gdrive_base, grade_num, year, month):
        """모의고사 작업/고{N}/ 안에서 (year, month)에 해당하는 월 폴더 찾기.

        폴더명 패턴: `고{N} {YY}년 {M}월` (또는 0-padded M)
        """
        grade_dir = os.path.join(gdrive_base, f"고{grade_num}")
        # 미러 redirect — Drive zombie 시 GDrive listdir EDEADLK 회피
        from engines.final.extractor import _resolve_local_mirror as _rlm
        grade_dir = _rlm(grade_dir, None)
        if not os.path.isdir(grade_dir):
            return None

        month_int = int(month)
        month_variants = [str(month_int)]
        if month_int < 10:
            month_variants.append(f"0{month_int}")

        prefix = f"고{grade_num} "
        for raw in os.listdir(grade_dir):
            nfc = _nfc(raw)
            if not nfc.startswith(prefix):
                continue
            if f"{year}년" not in nfc:
                continue
            if not any(f"{mv}월" in nfc for mv in month_variants):
                continue
            full = os.path.join(grade_dir, raw)
            if os.path.isdir(full):
                return full
        return None

    @staticmethod
    def _find_analysis_files(month_folder, patterns=None):
        """월 폴더 안에서 '분석본'이 들어간 모든 .indd 후보 반환.

        반환 순서: 짧은 파일명이 먼저 (메인 → 보조 → 짤지문 등).
        """
        if not month_folder or not os.path.isdir(month_folder):
            return []
        # 미러 redirect — Drive zombie 시 GDrive listdir EDEADLK 회피
        from engines.final.extractor import _resolve_local_mirror as _rlm
        month_folder = _rlm(month_folder, None)
        patterns = patterns or ["분석본"]
        results = []
        for raw in os.listdir(month_folder):
            nfc = _nfc(raw)
            if not nfc.lower().endswith(".indd"):
                continue
            if not any(pat in nfc for pat in patterns):
                continue
            # ~$ / lock files 제외
            if nfc.startswith("~") or "idlk" in nfc.lower():
                continue
            results.append(os.path.join(month_folder, raw))
        # 짧은 파일명이 우선 (e.g., "분석본.indd" → "분석본 2.indd" → "분석본 짤지문.indd")
        results.sort(key=lambda p: (len(os.path.basename(p)), os.path.basename(p)))
        return results

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        """코드 → 월 폴더 → 후보 분석본 .indd 로컬 복사 → metadata.json."""
        cfg = _load_config()
        patterns = cfg.get("file_patterns", ["분석본"])

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

        gdrive_base = cfg["gdrive_base"]
        if not os.path.isdir(gdrive_base):
            raise FileNotFoundError(f"GDrive 기준 폴더 없음: {gdrive_base}")
        log(f"[GDrive] {gdrive_base}")

        # GDrive 파일은 EDEADLK 회피를 위해 8-경로 폴백 + 지수 백오프 사용
        # (.claude/rules/gdrive_copy_robust.md 참조)
        from engines.final.extractor import _gdrive_safe_copy

        def _robust_copy(src_path, dst_path):
            """같은 dst 충돌 시 _2, _3 suffix → _gdrive_safe_copy 로 복사."""
            if (os.path.isfile(dst_path) and os.path.getsize(dst_path) > 0):
                b, ext = os.path.splitext(dst_path)
                n = 2
                while (os.path.isfile(f"{b}_{n}{ext}") and
                       os.path.getsize(f"{b}_{n}{ext}") > 0):
                    n += 1
                dst_path = f"{b}_{n}{ext}"
            ok, err = _gdrive_safe_copy(src_path, dst_path, log=log)
            if not ok:
                raise RuntimeError(
                    f"GDrive 파일 복사 실패: {os.path.basename(src_path)} — {err}"
                )
            return dst_path

        # 코드별로 월 폴더와 후보 파일들을 찾기 (year, month) 단위로 캐시
        ym_to_folder = {}       # (year, month) → folder path
        ym_to_sources = {}      # (year, month) → list of local file paths
        local_copied = {}       # gdrive_path → local_path

        sources_meta = []       # 최종 metadata.json 에 저장될 항목
        not_found_folders = []
        for c in codes:
            key = (c["year"], c["month"])
            if key not in ym_to_folder:
                folder = self._find_month_folder(
                    gdrive_base, grade_num, c["year"], c["month"]
                )
                ym_to_folder[key] = folder
                if not folder:
                    ym_to_sources[key] = []
                    log(f"  - {c['raw']} → [폴더 없음] {c['year']}년 {int(c['month'])}월")
                else:
                    files = self._find_analysis_files(folder, patterns)
                    log(f"  - {c['year']}년 {int(c['month'])}월 폴더: "
                        f"{os.path.basename(folder)} → 분석본 {len(files)}개")
                    locals_ = []
                    for f in files:
                        if f in local_copied:
                            locals_.append(local_copied[f])
                            continue
                        base = os.path.basename(f)
                        local_path = os.path.join(job_dir, f"src_{base}")
                        actual = _robust_copy(f, local_path)
                        local_copied[f] = actual
                        locals_.append(actual)
                        log(f"    로컬 복사: {os.path.basename(actual)}")
                    ym_to_sources[key] = locals_

            folder = ym_to_folder[key]
            local_files = ym_to_sources[key]
            if not folder:
                not_found_folders.append(
                    f"{c['raw']} ({c['year']}년 {int(c['month'])}월 폴더 없음)"
                )
                continue
            if not local_files:
                not_found_folders.append(
                    f"{c['raw']} ({c['year']}년 {int(c['month'])}월 폴더에 분석본 파일 없음)"
                )
                continue
            sources_meta.append({
                "code": c["raw"],
                "year": c["year"],
                "month": c["month"],
                "qNum": c["qNum"],
                "month_folder": folder,
                "candidates": local_files,  # 후보들 — JSX 가 마커 매칭 후 선택
            })

        if not_found_folders:
            raise FileNotFoundError(
                "해결되지 않은 코드:\n  " + "\n  ".join(not_found_folders)
            )

        # metadata.json
        meta_path = os.path.join(job_dir, "metadata.json")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(
                {"codes": codes, "sources": sources_meta},
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

        # 출력 디렉터리 — 조판/교재/분석본결합/{학년}/{시험기간}/{학교}/
        output_dir = os.path.join(
            STUDIO_ROOT, "조판", "교재", "분석본결합",
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
            "keep_head": cfg.get("keep_head", 1),
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
