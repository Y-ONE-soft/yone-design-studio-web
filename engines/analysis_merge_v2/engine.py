"""분석본 결합 v2 엔진 (2026 여름 개편).

v1(engines/analysis_merge)과의 차이 — 사용자 스펙 6건:
  1. 목업 연결 제거 — verify 결과에 pdf_path/pdf_paths를 넣지 않는다.
     (core/pipeline.py의 '목업 IN 폴더 자동 복사'는 result["pdf_path"]가
     있을 때만 발동하므로, v2 흐름에서는 목업 핸드오프가 원천 차단된다.)
  2. 프레임 지오메트리 복원 — page.duplicate가 문서 간 복제에서 콘텐츠
     프레임을 수평 이동시키는 결함(실측: LEFT +2mm / RIGHT +4mm 순수 평행이동,
     data_corpus/analysis_merge_v2/repro1)을 JSX가 소스 좌표로 복원하고,
     verify가 잔여 드리프트를 게이트로 대조한다.
  3. 저장 위치 — GDrive 분석본/고1,고2(공통)/{시험기간}/{학교}/ 아래
     .indd만 저장 (PDF 생성 제거). 로컬(job_dir)에 먼저 쓰고
     shutil.copy2 + 지수 백오프로 복사. 기존 GDrive 파일은 절대 덮어쓰지
     않는다 (동명 존재 시 _2, _3 접미).
  4. 링크 체크+임베드 — 저장 전 JSX가 깨진 링크를 relink_map(파이썬이
     소스 폴더/이미지 폴더에서 사전 스캔)으로 리링크 후 전부 임베드
     (Link.unlink() == 임베드; 실측: 기존 결합본 링크 status가
     LINK_EMBEDDED로 남음). verify 게이트: 미임베드 0 / 깨진 링크 0.
  5. 1페이지·간지 텍스트 — 기존 결합본 실측 스펙(간지 마스터의
     '2026 {학교표기}' 챕터_숫자 프레임 + 순번 프레임, 페이지1 상단 슬러그
     범위/범위_추가내용 프레임, 범위 프레임쌍 오버라이드 위아래 병기)대로
     학교명/순번/범위들을 기재한다.
  6. verify — 기존(파일 생성/로그 경고) + 지오메트리/링크/간지/오버플로우
     게이트. 시각 검수(core.visual_inspect) 연결 지점은 아래 verify 주석 참조.

v1 엔진은 무수정(핸드북 철칙) — 코드 파싱/소스 탐색/복사 로직은 상속으로 재사용.
"""

import json
import os
import re
import shutil
import time
import unicodedata

from core.base import BaseEngine  # noqa: F401  (상속 체인 명시용)
from engines.analysis_merge.engine import AnalysisMergeEngine

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_PATH_KEYS = ["template_path", "gdrive_base", "save_base", "image_dirs"]

# relink 후보로 스캔할 이미지/소재 확장자
_IMAGE_EXTS = (".ai", ".psd", ".jpg", ".jpeg", ".png", ".tif", ".tiff",
               ".eps", ".pdf", ".indd")

# GDrive 복사 지수 백오프 (초) — gdrive_copy_robust 패턴
_COPY_BACKOFF = [1, 3, 8, 15, 30]


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    cfg = resolve_config(cfg, ["template_path", "gdrive_base", "save_base"])
    from core.paths import resolve
    cfg["image_dirs"] = [resolve(p) for p in cfg.get("image_dirs", [])]
    return cfg


class AnalysisMergeV2Engine(AnalysisMergeEngine):

    @property
    def material_id(self):
        return "analysis_merge_v2"

    @property
    def display_name(self):
        return "분석본 결합 v2 (베타)"

    @property
    def description(self):
        return ("문제 코드 기준 페이지 추출·결합 → 지오메트리/링크/간지 검수 후 "
                "GDrive 분석본 폴더에 .indd 저장")

    @property
    def template_name(self):
        return "typeset_analysis_merge_v2.html"

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "codes",
                    "label": "문제 (6자리 250632 또는 '25년 6월 32번' / '25년 6월 20-23번, 29번')",
                    "type": "textarea",
                    "required": True,
                },
                {
                    "key": "ranges",
                    "label": "범위 목록 (교재명/회차 + 상세 — 비우면 문제 코드에서 자동 유도)",
                    "type": "text",
                    "required": False,
                },
                {
                    "key": "ganji_school",
                    "label": "간지 학교 표기 (예: 2026 강동고2)",
                    "type": "text",
                    "required": True,
                },
                {
                    "key": "result_name",
                    "label": "결과 파일명 (확장자 제외 — 비우면 자동 생성)",
                    "type": "text",
                    "required": False,
                },
            ]
        }

    # ─── 범위 입력 파싱 ─────────────────────────────────────────────

    @staticmethod
    def parse_ranges(raw):
        """범위 입력 → [{"title": 교재명/회차, "detail": 상세}] (순서 보존).

        지원 형식:
          - JSON: [{"title":"고1 25년 3월 모의고사","detail":"39번, 40번"}, ...]
          - 줄 단위 "제목 | 상세" (상세 생략 가능)
        """
        raw = (raw or "").strip()
        if not raw:
            return []
        out = []
        if raw.startswith("["):
            try:
                data = json.loads(raw)
            except ValueError:
                raise ValueError(f"범위 JSON 파싱 실패: {raw[:80]!r}")
            for item in data:
                if not isinstance(item, dict):
                    raise ValueError(f"범위 항목 형식 오류: {item!r}")
                title = _nfc(str(item.get("title", "")).strip())
                detail = _nfc(str(item.get("detail", "")).strip())
                if title:
                    out.append({"title": title, "detail": detail})
        else:
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                if "|" in line:
                    title, detail = line.split("|", 1)
                else:
                    title, detail = line, ""
                title = _nfc(title.strip())
                detail = _nfc(detail.strip())
                if title:
                    out.append({"title": title, "detail": detail})
        return out

    # ─── 문제 코드 → 범위 자동 유도 (사용자 피드백 2026-07-19) ──────

    @staticmethod
    def _format_qnums(qnums):
        """문항 번호 리스트 → 상세 표기 (연속 구간은 "a~b번"으로 압축).

        [39, 40] → "39~40번" / [20, 21, 22, 23, 29] → "20~23번, 29번"
        (기존 손마무리 실물·수동 입력 관례: "39~40번", "20번")
        """
        parts = []
        i = 0
        while i < len(qnums):
            j = i
            while j + 1 < len(qnums) and qnums[j + 1] == qnums[j] + 1:
                j += 1
            if j > i:
                parts.append(f"{qnums[i]}~{qnums[j]}번")
            else:
                parts.append(f"{qnums[i]}번")
            i = j + 1
        return ", ".join(parts)

    @classmethod
    def derive_ranges_from_codes(cls, codes, grade):
        """범위 미입력 시 문제 코드(YYMMNN)에서 간지 범위 목록 자동 유도.

        규칙 (사용자 스펙): 250320 → "고1 25년 3월 모의고사 / 20번"
          - title  = "{학년} {YY}년 {M}월 모의고사"  (학년은 폼의 학년 필드)
          - detail = 같은 회차 문항 번호들 ("20번", "39~40번" — 연속 압축)
        여러 회차면 입력 순서(첫 등장 순)대로 범위 목록에 병기 —
        기존 다중 범위 병기 로직(범위쌍 복제)이 그대로 소비한다.
        """
        grade = (grade or "").strip() or "고1"
        order = []
        by_ym = {}
        for c in codes or []:
            key = (c["year"], c["month"])
            if key not in by_ym:
                by_ym[key] = []
                order.append(key)
            q = int(c["qNum"])
            if q not in by_ym[key]:
                by_ym[key].append(q)
        out = []
        for year, month in order:
            title = f"{grade} {int(year)}년 {int(month)}월 모의고사"
            out.append({"title": title,
                        "detail": cls._format_qnums(by_ym[(year, month)])})
        return out

    # ─── relink 맵 (링크 파일명 → 절대경로) [스펙4에서 사용] ────────

    @staticmethod
    def _scan_dir_for_files(root, mapping):
        """root 아래 이미지/소재 파일을 파일명(NFC) → 경로로 수집.

        os.walk는 숨김 dot-디렉토리를 가지치기한다
        (development-guide 2026-06-26: .rsync-partial 불완전 파일 사고 예방).
        """
        if not root or not os.path.isdir(root):
            return
        for cur, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fn in files:
                if fn.startswith(".") or fn.startswith("~"):
                    continue
                nfc = _nfc(fn)
                if not nfc.lower().endswith(_IMAGE_EXTS):
                    continue
                # 먼저 발견된 경로 우선 (image_dirs가 소스 폴더보다 먼저)
                mapping.setdefault(nfc, os.path.join(cur, fn))

    def build_relink_map(self, cfg, month_folders):
        """깨진 링크 리링크용 파일명 → 절대경로 맵.

        탐색 순서: ① config image_dirs(분석본 이미지 폴더)
                   ② 각 소스 강(월) 폴더와 그 하위(Links 등)
        """
        mapping = {}
        for d in cfg.get("image_dirs", []):
            self._scan_dir_for_files(d, mapping)
        for folder in month_folders:
            self._scan_dir_for_files(folder, mapping)
        # JSX의 link.name은 NFD(HFS)일 수 있음 — 양쪽 정규화 키를 모두 제공
        for name in list(mapping.keys()):
            nfd = unicodedata.normalize("NFD", name)
            if nfd != name:
                mapping.setdefault(nfd, mapping[name])
        return mapping

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        """v1 parse(코드→소스 로컬 복사) + 템플릿 로컬 확보 + 범위/relink 맵."""
        meta_path = super().parse(uploaded_files, job_dir, log)
        cfg = _load_config()

        with open(meta_path, encoding="utf-8") as f:
            meta = json.load(f)

        # 범위 목록 (간지/1페이지 기재용) — 수동 입력 우선, 비우면 문제
        # 코드(YYMMNN)에서 자동 유도 (사용자 피드백 2026-07-19)
        ranges = self.parse_ranges(self._get_meta(job_dir, "ranges", ""))
        if ranges:
            log(f"[범위] {len(ranges)}개: "
                + " / ".join(r["title"] for r in ranges))
        else:
            grade = self._get_meta(job_dir, "grade", "고1")
            ranges = self.derive_ranges_from_codes(meta.get("codes"), grade)
            if not ranges:
                raise ValueError(
                    "범위 목록이 입력되지 않았고 코드에서 유도할 수도 없습니다. "
                    "(예: 고1 25년 3월 모의고사 | 39번, 40번)")
            log(f"[범위 자동 유도] {len(ranges)}개: "
                + " / ".join(f"{r['title']} / {r['detail']}" for r in ranges))

        # 템플릿: GDrive 원본 → job_dir 로컬 사본 (GDrive 원본 무수정 원칙)
        tpl_src = cfg["template_path"]
        if not os.path.isfile(tpl_src):
            raise FileNotFoundError(f"분석본 마스터 템플릿 없음: {tpl_src}")
        tpl_local = os.path.join(job_dir, "template_" + _nfc(os.path.basename(tpl_src)))
        from engines.final.extractor import _gdrive_safe_copy
        ok, err = _gdrive_safe_copy(tpl_src, tpl_local, log=log)
        if not ok:
            raise RuntimeError(f"템플릿 복사 실패: {err}")
        log(f"[템플릿] 로컬 사본: {os.path.basename(tpl_local)}")

        # relink 맵 — 소스 월 폴더 + 이미지 폴더 사전 스캔
        month_folders = []
        for s in meta.get("sources", []):
            mf = s.get("month_folder")
            if mf and mf not in month_folders:
                month_folders.append(mf)
        relink_map = self.build_relink_map(cfg, month_folders)
        log(f"[링크맵] 후보 {len(relink_map)}개 파일")

        meta["template_local"] = tpl_local
        meta["ranges"] = ranges
        meta["relink_map"] = relink_map
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, ensure_ascii=False, indent=2)
        return meta_path

    # ─── prepare_jsx ───────────────────────────────────────────────

    # 범위 제목의 년·월 추출 ("고1 25년 3월 모의고사" → 25년3월)
    _RE_YEAR_MONTH = re.compile(r"(\d{1,2})\s*년\s*(\d{1,2})\s*월")

    @classmethod
    def summarize_range_title(cls, title):
        """범위 제목 → 파일명용 축약 (사용자 피드백 2026-07-19).

        년·월만 남긴다: "고1 25년 3월 모의고사" → "25년3월".
        년·월이 없는 제목(교과서 단원 등)은 공백만 제거해 그대로 —
        기존 형식 입력 하위호환.
        """
        title = (title or "").strip()
        m = cls._RE_YEAR_MONTH.search(title)
        if m:
            return f"{int(m.group(1))}년{int(m.group(2))}월"
        return re.sub(r"\s+", "", title)

    @staticmethod
    def sanitize_filename(name):
        """파일명 규칙: 부적합 문자 제거 + 띄어쓰기 금지 (피드백 2026-07-19)."""
        name = re.sub(r'[/\\:*?"<>|]', "", name or "")
        return re.sub(r"\s+", "", name)

    def default_result_name(self, school, issue_num, ranges):
        """명명 규칙: {학교}_분석본{NN}({년월 축약,…})_내지 — 공백 없음.

        예: 배재1_분석본01(25년3월,22년9월)_내지
        """
        try:
            nn = f"{int(issue_num):02d}"
        except (TypeError, ValueError):
            nn = "01"
        parts = []
        for r in ranges:
            s = self.summarize_range_title(r.get("title", ""))
            if s and s not in parts:        # 같은 년월 중복 기재 방지
                parts.append(s)
        summary = ",".join(parts)[:40] or "결합"
        return self.sanitize_filename(f"{school}_분석본{nn}({summary})_내지")

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        grade = self._get_meta(job_dir, "grade", "고1")
        school = _nfc(self._get_meta(job_dir, "school", "").strip())
        exam_period = _nfc(self._get_meta(job_dir, "exam_period", "").strip())
        issue_num = self._get_meta(job_dir, "issue_num", "1").strip()
        ganji_school = _nfc(self._get_meta(job_dir, "ganji_school", "").strip())
        result_name = _nfc(self._get_meta(job_dir, "result_name", "").strip())

        if not school:
            raise ValueError("학교를 선택하세요 (저장 폴더: 학교명+학년).")
        if not exam_period:
            raise ValueError("시험 기간을 선택하세요.")
        if not ganji_school:
            raise ValueError("간지 학교 표기를 입력하세요. (예: 2026 강동고2)")

        with open(json_path, encoding="utf-8") as f:
            meta = json.load(f)
        ranges = meta.get("ranges") or []
        if not result_name:
            result_name = self.default_result_name(school, issue_num, ranges)
            log(f"[파일명 자동 생성] {result_name}")
        else:
            # 직접 입력한 파일명도 파일명 규칙 적용 (띄어쓰기 금지)
            cleaned = self.sanitize_filename(result_name)
            if cleaned != result_name:
                log(f"[파일명 정규화] {result_name!r} → {cleaned!r}")
                result_name = cleaned
            if not result_name:
                result_name = self.default_result_name(school, issue_num, ranges)
                log(f"[파일명 자동 생성] {result_name}")

        # 로컬 스테이징 출력 (검수 게이트 통과 후 verify가 GDrive로 복사)
        output_dir = os.path.join(job_dir, "out")
        os.makedirs(output_dir, exist_ok=True)
        indd_out = os.path.join(output_dir, f"{result_name}.indd")

        settings = {
            "template_path": meta.get("template_local") or cfg["template_path"],
            "output_indd": indd_out,
            "output_dir": output_dir,
            # 로그는 job 전용만 사용 — 공용 누적 로그를 판정에 쓰지 않는다
            # (development-guide 2026-07-17 ②).
            "log_path": os.path.join(job_dir, self.log_filename),
            "log_paths": [],
            "report_path": os.path.join(job_dir, "v2_report.json"),
            "keep_head": cfg.get("keep_head", 1),
            "school": school,
            "grade": grade,
            "exam_period": exam_period,
            "issue_num": issue_num,
            "ganji_school": ganji_school,
            "ranges": ranges,
            "relink_map": meta.get("relink_map") or {},
            "sources": meta["sources"],
            # GDrive 최종 저장 정보 (파이썬 verify 전용 — JSX는 GDrive 무접촉)
            "gdrive_save": {
                "base": cfg["save_base"],
                "exam_period": exam_period,
                "school_dir": school,
            },
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

        log(f"[결과 .indd] {os.path.basename(indd_out)} (로컬 스테이징)")
        log(f"[GDrive 저장 예정] {cfg['save_base']}/{exam_period}/{school}/")
        return jsx_dst

    # ─── run_indesign ──────────────────────────────────────────────

    def run_indesign(self, job_dir, log):
        """runner 기본 완료 판정은 'PDF:'/'조판 완료' 마커 의존 — v2는 PDF가
        없으므로 명시적 완료 마커('===== 완료 =====')를 전달한다."""
        from core.indesign.runner import run_jsx
        jsx_path = os.path.join(job_dir, "run.jsx")
        log_file = os.path.join(job_dir, self.log_filename)
        run_jsx(jsx_path, log, poll_log_path=log_file,
                timeout=self.jsx_timeout,
                completion_marker="===== 완료 =====")

    # ─── GDrive 저장 (검수 통과 후) ────────────────────────────────

    @staticmethod
    def _copy_to_gdrive(local_path, base, exam_period, school_dir, log):
        """로컬 스테이징 .indd → GDrive 분석본 폴더 복사.

        - 신규 폴더/파일 생성만 한다. 기존 파일은 절대 덮어쓰지 않는다
          (동명 존재 시 _2, _3 접미로 새 파일 생성).
        - shutil.copy2 + 지수 백오프 (EDEADLK 등 일시 오류 재시도,
          gdrive_copy_robust 패턴).
        반환: (gdrive_path or None, error or None)
        """
        if not os.path.isdir(base):
            return None, f"GDrive 저장 기준 폴더 없음: {base}"
        target_dir = os.path.join(base, exam_period, school_dir)
        try:
            os.makedirs(target_dir, exist_ok=True)
        except OSError as e:
            return None, f"폴더 생성 실패: {target_dir} — {e}"

        name = os.path.basename(local_path)
        stem, ext = os.path.splitext(name)
        dst = os.path.join(target_dir, name)
        n = 2
        while os.path.exists(dst):
            dst = os.path.join(target_dir, f"{stem}_{n}{ext}")
            n += 1

        last_err = None
        for i, delay in enumerate([0] + _COPY_BACKOFF):
            if delay:
                time.sleep(delay)
            try:
                shutil.copy2(local_path, dst)
                if (os.path.isfile(dst)
                        and os.path.getsize(dst) == os.path.getsize(local_path)):
                    return dst, None
                last_err = "복사본 크기 불일치"
            except OSError as e:
                last_err = str(e)
                if log:
                    log(f"  [GDrive 복사 재시도 {i}] {last_err}")
        return None, f"GDrive 복사 실패: {last_err}"

    # ─── verify ────────────────────────────────────────────────────

    # 지오메트리 게이트 허용 오차 (mm) — 복원 후 잔여 드리프트
    GEO_TOL_MM = 0.1

    def verify(self, job_dir, log):
        settings_path = os.path.join(job_dir, ".settings.json")
        with open(settings_path, encoding="utf-8") as f:
            settings = json.load(f)

        indd_out = settings["output_indd"]
        report_path = settings.get("report_path", "")

        warnings = []
        gates = {}

        if not os.path.exists(indd_out):
            warnings.append(f".indd 미생성: {os.path.basename(indd_out)}")

        report = {}
        if report_path and os.path.exists(report_path):
            try:
                with open(report_path, encoding="utf-8") as f:
                    report = json.load(f)
            except ValueError as e:
                warnings.append(f"검수 리포트 파싱 실패: {e}")
        else:
            warnings.append("검수 리포트(v2_report.json) 미생성")

        # ── 게이트 1: 코드 매칭 (v1 기존 검수 계승) ─────────────────
        unresolved = report.get("unresolved") or []
        gates["codes_ok"] = not unresolved
        if unresolved:
            warnings.append(f"마커 매칭 실패 코드 {len(unresolved)}개: "
                            + ", ".join(unresolved))

        # ── 게이트 2: 프레임 지오메트리 (스펙 2) ────────────────────
        geo = report.get("geometry") or {}
        max_drift = geo.get("max_residual_mm")
        mismatch = geo.get("count_mismatch_pages") or []
        geo_ok = (max_drift is not None and max_drift <= self.GEO_TOL_MM
                  and not mismatch)
        gates["geometry_ok"] = geo_ok
        if max_drift is None:
            warnings.append("지오메트리 리포트 없음")
        elif max_drift > self.GEO_TOL_MM:
            warnings.append(
                f"프레임 잔여 드리프트 {max_drift}mm > 허용 {self.GEO_TOL_MM}mm "
                f"(교정 전 최대 {geo.get('max_drift_before_mm')}mm)")
        if mismatch:
            warnings.append(f"페이지 아이템 수 불일치: {mismatch}")

        # ── 게이트 3: 링크 (스펙 4) ─────────────────────────────────
        links = report.get("links") or {}
        n_missing = links.get("missing_after", -1)
        n_unembedded = links.get("unembedded_after", -1)
        links_ok = (n_missing == 0 and n_unembedded == 0)
        gates["links_ok"] = links_ok
        if not links_ok:
            warnings.append(
                f"링크 게이트 실패 — 깨진 링크 {n_missing}개, "
                f"미임베드 {n_unembedded}개 "
                f"(리링크 {links.get('relinked', 0)}건, 임베드 {links.get('embedded', 0)}건)")

        # ── 게이트 4: 간지/1페이지 텍스트 (스펙 5) ──────────────────
        ganji = report.get("ganji") or {}
        ganji_ok = bool(ganji.get("ok"))
        # 간지 프레임 속성 대조 (W28-피드백2): 학교명 기재 전 캡처(기대)와
        # 기재 후 실측의 색/밑줄/크기 스냅샷이 다르면 실패 — JSX가 ok에
        # 반영하지만, verify에서도 독립적으로 재검한다 (이중 봉합).
        attr_mismatches = ganji.get("attr_mismatches") or []
        if attr_mismatches:
            ganji_ok = False
            warnings.append("간지 학교명 서식 불일치(기대→실측): "
                            + ", ".join(str(m) for m in attr_mismatches))
        gates["ganji_ok"] = ganji_ok
        if not bool(ganji.get("ok")):
            warnings.append("간지/1페이지 기재 실패: "
                            + (ganji.get("error") or "리포트 없음"))

        # ── 게이트 5: 오버플로우 (콘텐츠 페이지) ────────────────────
        overflow_pages = report.get("overflow_pages") or []
        gates["overflow_ok"] = not overflow_pages
        if overflow_pages:
            warnings.append(f"오버플로우 프레임 페이지: {overflow_pages}")

        # ── 시각 검수 1층 (스펙 6 — opt-in: YONE_VISUAL_INSPECT=1) ──
        # v2는 PDF가 없어 .indd 렌더(allow_indesign=True)로 실행. W29 판정
        # 철학 준수: fail-open, critical도 warning만 붙이고 게이트는 불변.
        visual = None
        if (os.environ.get("YONE_VISUAL_INSPECT") == "1"
                and os.path.exists(indd_out)):
            try:
                from core.visual_inspect import inspect_job_visual
                log("[시각검수] 페이지 렌더 + 기계 검사 중...")
                vr = inspect_job_visual(job_dir, log,
                                        result={"indd_path": indd_out},
                                        allow_indesign=True)
                if vr is not None:
                    visual = {"report_path": vr["report_path"],
                              "summary": vr["summary"]}
                    if vr["summary"]["critical"]:
                        warnings.append(
                            f"[시각검수] critical {vr['summary']['critical']}건 "
                            f"(페이지 {vr['summary']['flagged_pages'][:8]}) — "
                            f"visual_report.json 확인")
            except Exception as _ve:
                log(f"[시각검수] 건너뜀 (fail-open): {_ve}")

        all_gates_ok = all(gates.values()) and os.path.exists(indd_out)

        # ── GDrive 저장 (스펙 3) — 게이트 전부 통과 시에만 ──────────
        gdrive_path = None
        if all_gates_ok:
            gs = settings.get("gdrive_save") or {}
            gdrive_path, err = self._copy_to_gdrive(
                indd_out, gs.get("base", ""), gs.get("exam_period", ""),
                gs.get("school_dir", ""), log)
            if gdrive_path:
                log(f"[GDrive 저장] {gdrive_path}")
            else:
                warnings.append(
                    f"[GDrive 저장 실패 — 로컬 보존: {indd_out}] {err}")
        elif os.path.exists(indd_out):
            warnings.append(
                f"검수 게이트 미통과 — GDrive 저장 보류, 로컬 보존: {indd_out}")

        ok = all_gates_ok and gdrive_path is not None

        # 스펙 1: pdf_path/pdf_paths를 결과에 넣지 않는다 → core/pipeline.py의
        # 목업 IN 폴더 자동 복사(result["pdf_path"] 조건)가 발동하지 않는다.
        return {
            "ok": ok,
            "overflow": len(overflow_pages),
            "stories": {},
            "warnings": warnings,
            "gates": gates,
            "indd_path": gdrive_path or (indd_out if os.path.exists(indd_out) else None),
            "local_indd": indd_out if os.path.exists(indd_out) else None,
            "gdrive_path": gdrive_path,
            "visual": visual,
            "geometry": {
                "max_drift_before_mm": geo.get("max_drift_before_mm"),
                "max_residual_mm": max_drift,
            },
            "links": links,
            "ganji": ganji,
        }
