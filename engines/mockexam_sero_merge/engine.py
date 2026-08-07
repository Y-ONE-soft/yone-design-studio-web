"""모의고사 세로 결합 엔진.

여러 회차 세로버전 모의고사 .indd 에서 지정한 문제 코드(YYMMQQ)에 해당하는
페이지만 추출해서, 빈 템플릿(.indd) 위에 결합하고 PDF 까지 내보낸다.

입력:
  - 학년(고1/고2), 학교, 시험기간 (공통 메타데이터)
  - 문제 리스트 (textarea) — 6자리 YYMMQQ 또는 자연어 형식 혼합 가능:
      250632 / 25년 6월 32번 / 25년 6월 32,33번 /
      25년 6월 20-23번, 29번 / 25년 6월 20~21, 29~30 /
      25년 6월 33번, 22년 3월 33,34번 (한 줄에 여러 회차)
    범위(20-23)는 개별 번호로 전개되고, 같은 지문이 여러 번호를 덮는
    장문(예: 41~42)은 JSX 단계에서 중복 지문 1회만 삽입된다.
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

# 입력 파싱용 정규식
#   _YM_RE   : "25년 6월" / "2025년 06월" 회차 앵커 (년/월)
#   _QTOK_RE : 문제번호 토큰 — "20-23" 범위 또는 단일 "29"
#              (구분자: 하이픈/물결 및 그 전각·유니코드 변형)
_RANGE_SEP = r"[\-~–—－～∼]"
_YM_RE = re.compile(r"(\d{2,4})\s*년\s*(\d{1,2})\s*월")
_QTOK_RE = re.compile(r"(\d{1,2})\s*" + _RANGE_SEP + r"\s*(\d{1,2})|(\d{1,2})")
_CODE6_RE = re.compile(r"^\d{6}$")


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


def _despace(s):
    return re.sub(r"[\s_]+", "", _nfc(s))


def indd_entries(folder):
    """완성본 폴더의 .indd 목록 — 미러 ∪ GDrive 합집합 [(name_nfc, path)].

    미러만 listdir 하면 안 되는 이유 (2026-08-07 실측): mirror-sync는 주기
    스냅샷이라 GDrive의 rename/신규가 늦게 반영된다. '전체(C)→전체' 일괄
    rename 직후 미러엔 옛 이름 49개가 유령으로 남고 새 이름 44개는 아예
    없어서, 미러만 본 _find_vertical_file이 "찾지 못한 회차" 오류를 냈다.
    읽기 경로는 미러본이 있으면 미러(EDEADLK 회피), 없으면 GDrive 원본 —
    list_manuscript_entries(원고 폴더용)와 동일 계약.
    """
    from engines.final.extractor import list_manuscript_entries
    out = []
    for name, path in (list_manuscript_entries(folder, None) or []):
        n = _nfc(name)
        if not n.lower().endswith(".indd") or n.startswith("~"):
            continue
        out.append((n, path))
    return out


def _numeric_token_indd_fallback(folder, grade_num, year, month,
                                 require=(), forbid=(), entries=None):
    """소스 .indd 2차 매칭 — 숫자 토큰 기반 (W36 배치 F, 감사 §9 F안).

    1차(리터럴: '고{N}' 접두 + '{YY}년' + '{M}월' + 키워드 substring)가
    0건일 때만 호출한다 — 기존 매칭분 무변경 (배치 A `_find_month_folder`
    2차 패턴 확산). 파일명에서 (학년, 년, 월) 숫자 토큰을 구분자·접두
    무관하게 대조하고, 키워드('세로'/'전체')는 공백/언더스코어 제거 후
    substring으로 판정(랭킹 신호 강등이 아닌 필수 유지 — 세로/가로판
    오선택은 결합 결과를 통째로 바꾸므로 안전 우선).

    반환: 후보 리스트 (파일명 최단 우선 정렬 — 1차와 동일 휴리스틱).
    """
    if entries is None:
        if not os.path.isdir(folder):
            return []
        entries = indd_entries(folder)
    month_int = int(month)
    yy = str(year)[-2:]
    out = []
    for nfc, path in entries:
        if "idlk" in nfc.lower():
            continue
        d = _despace(nfc)
        if any(k in d for k in forbid):
            continue
        if not all(k in d for k in require):
            continue
        mg = re.search(r"고\s*(\d)", nfc)
        if not mg or mg.group(1) != str(grade_num):
            continue
        my = re.search(r"(\d{2,4})\s*년", nfc)
        if not my or my.group(1)[-2:] != yy:
            continue
        mm = re.search(r"(\d{1,2})\s*월", nfc)
        if not mm or int(mm.group(1)) != month_int:
            continue
        out.append(path)
    out.sort(key=lambda p: len(os.path.basename(p)))
    return out


def _list_indd_names(folder, limit=12, entries=None):
    """미발견 리포트용 — 폴더 내 .indd 파일명 나열 (침묵 금지, 배치 F).

    미러 ∪ GDrive 합집합(indd_entries) — 에러 메시지가 옛 미러 목록을
    보여주면 진단이 통째로 어긋난다 (2026-08-07 사고).
    """
    try:
        if entries is None:
            entries = indd_entries(folder)
    except OSError:
        return []
    names = sorted(n for n, _ in entries)
    return names[:limit]


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
                    "label": "문제 (6자리 250632 또는 '25년 6월 32번' / '25년 6월 20-23번, 29번')",
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

    # 소스 파일 종별 라벨 (에러 메시지용) — 서브클래스(가로판 결합)가 오버라이드
    _SRC_LABEL = "세로버전"

    def _config(self):
        """엔진 config 로드 훅 — 서브클래스가 자체 config.json으로 교체 가능."""
        return _load_config()

    def _get_meta(self, job_dir, key, default=""):
        path = os.path.join(job_dir, f"{key}.txt")
        if os.path.exists(path):
            return open(path, encoding="utf-8").read().strip()
        return default

    @staticmethod
    def _parse_qnums(segment):
        """문제번호 구간 → [(번호:int, 범위확장분여부:bool)] (입력 순서 유지).

        "32" → [(32,False)] / "32,33" → [(32,F),(33,F)]
        "20-23" → [(20,T),(21,T),(22,T),(23,T)]  (범위 전개분은 True)
        """
        seg = segment.replace("번", " ")
        out = []
        for m in _QTOK_RE.finditer(seg):
            if m.group(1) is not None:            # a~b 범위
                a, b = int(m.group(1)), int(m.group(2))
                step = 1 if a <= b else -1
                for q in range(a, b + step, step):
                    out.append((q, True))
            else:                                 # 단일 번호
                out.append((int(m.group(3)), False))
        return out

    @staticmethod
    def _make_code(year, month, q, from_range):
        """year('25'), month('06'), q(int) → 코드 dict (6자리 raw 포함)."""
        return {
            "raw": f"{year}{month}{int(q):02d}",
            "year": year,
            "month": month,
            "qNum": f"{int(q):02d}",
            "from_range": bool(from_range),
            "display": f"{year}년 {int(month)}월 {int(q)}번",
        }

    @classmethod
    def _split_entries(cls, text):
        """입력 전체를 회차/코드 조각으로 분리.

        줄바꿈뿐 아니라 콤마로도 회차·코드를 구분할 수 있도록,
        회차 앵커(년월)와 단독 6자리 코드 앞에 경계(개행)를 넣고 나눈다.
        그래서 '250632, 25년 6월 33번' 처럼 코드와 자연어를 콤마로 섞어도 된다.
        학년 토큰(고1/고2/고3)은 라디오에서 선택하므로 무시한다.
        """
        text = re.sub(r"고\s*[123]", " ", text)                       # 중복 학년 토큰 제거
        text = _YM_RE.sub(lambda m: "\n" + m.group(0), text)          # 회차 앞 경계
        text = re.sub(r"(?<!\d)\d{6}(?!\d)",
                      lambda m: "\n" + m.group(0), text)              # 6자리 코드 앞 경계
        return text.split("\n")

    @classmethod
    def _parse_line(cls, line):
        """한 줄(조각) 입력 → 코드 dict 리스트.

        지원 형식:
          - 6자리 YYMMQQ (콤마/공백으로 여러 개): 250632  /  250632 250921
          - 자연어 단일/콤마: 25년 6월 32번  /  25년 6월 32,33번
          - 범위: 25년 6월 20-23번, 29번  /  25년 6월 20~21, 29~30
          - 한 줄에 여러 회차: 25년 6월 33번, 22년 3월 33,34번
        """
        # '년/월' 글자가 전혀 없으면 6자리 코드 모드
        if "년" not in line and "월" not in line:
            out = []
            for tok in re.split(r"[,\s]+", line.strip()):
                if not tok:
                    continue
                t = re.sub(r"\s", "", tok)
                if not _CODE6_RE.match(t):
                    raise ValueError(
                        f"잘못된 입력: {tok!r} — 6자리 코드(250632) 또는 "
                        f"'25년 6월 32번' 형식으로 입력하세요."
                    )
                out.append(cls._make_code(t[0:2], t[2:4], int(t[4:6]), False))
            return out

        # 자연어 — '년/월' 앵커로 회차 그룹 분할
        anchors = list(_YM_RE.finditer(line))
        if not anchors:
            raise ValueError(f"년/월을 인식하지 못했습니다: {line!r}")
        out = []
        for i, mt in enumerate(anchors):
            yr = mt.group(1)
            yr = yr[-2:] if len(yr) >= 2 else yr.zfill(2)   # 2025→25
            mo = int(mt.group(2))
            if not (1 <= mo <= 12):
                raise ValueError(f"잘못된 월: {mt.group(2)}월 ({line!r})")
            seg_start = mt.end()
            seg_end = anchors[i + 1].start() if i + 1 < len(anchors) else len(line)
            qnums = cls._parse_qnums(line[seg_start:seg_end])
            if not qnums:
                raise ValueError(f"문제 번호를 인식하지 못했습니다: {line!r}")
            for q, is_range in qnums:
                if not (1 <= q <= 99):
                    raise ValueError(f"문제 번호 범위 오류: {q}번 ({line!r})")
                out.append(cls._make_code(f"{int(yr):02d}", f"{mo:02d}", q, is_range))
        return out

    @staticmethod
    def _find_vertical_file(folder, grade_num, year, month):
        """GDrive 폴더에서 vertical .indd 매칭 (JSX 와 동일 규칙)."""
        if not os.path.isdir(folder):
            return None
        # 미러 ∪ GDrive 합집합 — 미러만 보면 rename/신규가 안 보인다
        entries = indd_entries(folder)

        month_int = int(month)
        month_variants = [str(month_int)]
        if month_int < 10:
            month_variants.append(f"0{month_int}")

        candidates = []
        for nfc, path in entries:
            if "세로" not in nfc:
                continue
            if not nfc.startswith(f"고{grade_num}"):
                continue
            if f"{year}년" not in nfc:
                continue
            if not any(f"{mv}월" in nfc for mv in month_variants):
                continue
            candidates.append(path)

        if not candidates:
            # 2차 (배치 F): 숫자 토큰 매칭 — 구분자('고1_25년')·4자리 연도
            # 표기와 무관. 1차 0건일 때만 진입 (기존 매칭 무변경).
            candidates = _numeric_token_indd_fallback(
                folder, grade_num, year, month, require=("세로",),
                entries=entries)
        if not candidates:
            return None
        candidates.sort(key=lambda p: len(os.path.basename(p)))
        return candidates[0]

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        """코드 → 소스 .indd 매핑 → 로컬 사본 → metadata.json."""
        cfg = self._config()

        codes_text = uploaded_files.get("codes", "")
        grade = self._get_meta(job_dir, "grade", "고1")
        grade_num = grade.replace("고", "")

        # 입력 파싱 — 6자리 코드 / "YY년 M월 Q번" / 범위 / 콤마·줄바꿈 혼합
        parsed = []
        for piece in self._split_entries(codes_text):
            piece = piece.strip().strip(",").strip()
            if not piece:
                continue
            parsed.extend(self._parse_line(piece))
        if not parsed:
            raise ValueError("문제 코드가 입력되지 않았습니다.")

        # 동일 코드 중복 제거 (입력 순서 보존)
        codes = []
        seen = set()
        for c in parsed:
            if c["raw"] in seen:
                continue
            seen.add(c["raw"])
            codes.append(c)

        log(f"[코드] {len(codes)}개")

        # GDrive 폴더
        gdrive_folder = os.path.join(cfg["gdrive_base"], grade)
        if not os.path.isdir(gdrive_folder):
            raise FileNotFoundError(f"GDrive 폴더를 찾을 수 없습니다: {gdrive_folder}")
        log(f"[GDrive] {gdrive_folder}")

        # 회차(년/월)별 세로버전 파일 1회 매칭 — 같은 회차의 여러 문제는 파일 공유
        file_by_ym = {}
        not_found = []
        for c in codes:
            ym = (c["year"], c["month"])
            if ym not in file_by_ym:
                f = self._find_vertical_file(
                    gdrive_folder, grade_num, c["year"], c["month"]
                )
                file_by_ym[ym] = f
                if not f:
                    not_found.append(f"{c['year']}년 {int(c['month'])}월")
        if not_found:
            # 침묵 금지 (배치 F): 폴더 내 .indd 후보를 에러에 동봉 —
            # '왜 못 찾았는지'를 파일명 수준에서 바로 볼 수 있게.
            cands = _list_indd_names(gdrive_folder)
            cand_note = (
                "\n폴더 내 .indd 후보:\n  " + "\n  ".join(cands)
                if cands else "\n폴더 내 .indd 후보 없음"
            )
            raise FileNotFoundError(
                f"{self._SRC_LABEL} 파일을 찾지 못한 회차:\n  "
                + "\n  ".join(not_found) + cand_note
            )

        # 코드별 소스 엔트리
        sources = []
        for c in codes:
            f = file_by_ym[(c["year"], c["month"])]
            sources.append({
                "code": c["raw"],
                "year": c["year"],
                "month": c["month"],
                "qNum": c["qNum"],
                "from_range": c["from_range"],
                "display": c["display"],
                "gdrive_path": f,
            })
            log(f"  - {c['display']} ({c['raw']}) → {os.path.basename(f)}")

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

        # 로그에서 [경고]/[오류] 카운트 — job 전용 로그(이번 실행분만) 우선.
        # log_path(출력 폴더 공용 로그)는 과거 실행분이 누적될 수 있어
        # 다른 작업의 경고가 현재 작업 판정을 오염시킨다.
        log_paths = settings.get("log_paths") or []
        log_path = log_paths[0] if log_paths else settings.get("log_path", "")
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
