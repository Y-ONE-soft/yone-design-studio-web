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

# 입력 파싱용 정규식 (모의고사 세로 결합과 동일)
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


# 월 폴더에 섞여 있을 수 있는 '분석본이 아닌' .indd 갈래 (3차 폴백용).
# 리뷰테스트/워크북 등은 보통 하위 폴더에 있지만, 마스터 템플릿·변형 원고가
# 월 폴더에 놓인 사례가 있어 이름으로 배제한다.
_OTHER_KIND_RE = re.compile(
    "리뷰테스트|리테|워크북|직전보충|포켓북|변형|정답|해설|"
    "마스터|내지|템플릿|원본"
)


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
    def _find_month_folder(gdrive_base, grade_num, year, month):
        """모의고사 작업/고{N}/ 안에서 (year, month)에 해당하는 월 폴더 찾기.

        폴더명 패턴: `고{N} {YY}년 {M}월` (또는 0-padded M)

        회차 폴더는 학년 폴더 바로 밑에 있기도 하고(고2 전체·고1 20년 이전·
        고1 26년), 연도 묶음 폴더 안으로 한 단계 내려가 있기도 하다
        (`고1 25년(3,6,9,10,11월)/고1 25년 3월` — 실측 2026-08-25). 두 배치를
        `month_dir_entries` 가 하나의 평면 목록으로 돌려준다. 묶음 폴더 자체는
        목록에서 빠지므로 1차 substring 매칭이 "11월" 을 품은 묶음 이름을
        11월 회차로 오인하던 사고도 함께 막힌다.
        """
        grade_dir = os.path.join(gdrive_base, f"고{grade_num}")
        # 미러 ∪ GDrive 합집합 — 미러가 stale해도(월 폴더가 GDrive에만 있어도)
        # 누락 방지. 읽기는 미러 우선이라 EDEADLK 회피 유지.
        from engines.final.extractor import list_manuscript_entries
        from core.mock_folders import month_dir_entries
        entries = month_dir_entries(
            grade_dir, lambda d: list_manuscript_entries(d, None))
        if not entries:
            return None

        month_int = int(month)
        month_variants = [str(month_int)]
        if month_int < 10:
            month_variants.append(f"0{month_int}")

        prefix = f"고{grade_num} "
        for nfc, full in entries:
            if not nfc.startswith(prefix):
                continue
            if f"{year}년" not in nfc:
                continue
            if not any(f"{mv}월" in nfc for mv in month_variants):
                continue
            if os.path.isdir(full):
                return full

        # 2차 (배치 A W33, 감사 실증 #6): 숫자 토큰 매칭 — 구분자(언더스코어
        # 등)·연도 4자리 표기와 무관하게 (학년, 년, 월) 토큰 집합으로 대조.
        # 1차(기존 규칙)가 못 찾은 경우에만 진입 — 기존 인식분 무변경.
        yy = str(year)[-2:]
        for nfc, full in entries:
            if not os.path.isdir(full):
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
            return full
        return None

    @staticmethod
    def _find_analysis_files(month_folder, patterns=None):
        """월 폴더 안에서 '분석본'이 들어간 모든 .indd 후보 반환.

        반환 순서: 짧은 파일명이 먼저 (메인 → 보조 → 짤지문 등).
        """
        if not month_folder:
            return []
        # 미러 ∪ GDrive 합집합 — 미러가 stale해도 분석본 .indd 누락 방지
        from engines.final.extractor import list_manuscript_entries
        patterns = patterns or ["분석본"]
        entries = [
            (nfc, full)
            for nfc, full in list_manuscript_entries(month_folder, None)
            if nfc.lower().endswith(".indd")
            # ~$ / lock files 제외
            and not nfc.startswith("~") and "idlk" not in nfc.lower()
        ]
        results = [full for nfc, full in entries
                   if any(pat in nfc for pat in patterns)]
        if not results:
            # 2차 (배치 F, 감사 실증 #6 후반 — 배치 A 미해결 (4)): 공백/
            # 언더스코어 제거 후 패턴 대조 → 그래도 0건이면 '분석' 토큰
            # 축약형('분석.indd' 등) 허용. 1차 0건일 때만 진입 (기존 무변경).
            def _ds(s):
                return re.sub(r"[\s_]+", "", s)
            ds_pats = [_ds(p) for p in patterns]
            results = [full for nfc, full in entries
                       if any(p in _ds(nfc) for p in ds_pats)]
            if not results and any("분석" in p for p in patterns):
                results = [full for nfc, full in entries
                           if "분석" in _ds(nfc)]
        if not results:
            # 3차 (2026-09-01): 명칭이 '분석본'으로 굳기 전(고1·고2 23년 이전)
            # 회차는 같은 물건을 `고1 23년 6월 모의고사(New).indd` /
            # `고1 23년 11월 짤지문.indd` 로 부른다. 파일명 화이트리스트 대신
            # **구조**로 판정한다 — 월 폴더 바로 아래의 .indd 는 그 회차의
            # 분석본이고, 리뷰테스트·워크북 등 다른 산출물은 하위 폴더에
            # 따로 산다(비재귀 열거라 애초에 안 잡힌다). 폴더 안에 섞여 있는
            # 다른 갈래만 이름으로 걸러낸다. 1·2차가 0건일 때만 진입하므로
            # 지금 잘 도는 폴더(24년~)의 동작은 그대로다.
            results = [full for nfc, full in entries
                       if not _OTHER_KIND_RE.search(_ds(nfc))]
        # '짤지문'(본편에서 잘려 나온 지문)본은 분석본 세트의 일부인데,
        # 이름에 '분석본'이 없는 회차(`고1 25년 10월 짤지문.indd`)가 있어
        # 1차에서 통째로 빠졌다. 항상 후보에 합류시키되 **맨 뒤**로 보내
        # 본편이 먼저 매칭되게 한다(기존 폴더들은 이미 이 순서 — 무변경).
        jjal = [full for nfc, full in entries if "짤" in nfc]
        for f in jjal:
            if f not in results:
                results.append(f)
        # 짧은 파일명이 우선 (e.g., "분석본.indd" → "분석본 2.indd" → "분석본 짤지문.indd")
        # GDrive 원본 경로는 NFD 라 basename 을 그대로 비교하면 한글이
        # 안 맞는다 — 정렬 키도 NFC 로 정규화한 뒤 본다.
        def _sk(p):
            b = _nfc(os.path.basename(p))
            return ("짤" in b, len(b), b)
        results.sort(key=_sk)
        return results

    # ─── parse ─────────────────────────────────────────────────────

    def parse(self, uploaded_files, job_dir, log):
        """코드 → 월 폴더 → 후보 분석본 .indd 로컬 복사 → metadata.json."""
        cfg = _load_config()
        patterns = cfg.get("file_patterns", ["분석본"])

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
            # 침묵 금지 (배치 F): '왜 못 찾았는지'를 후보 수준에서 동봉 —
            # 월 폴더 미발견이면 학년 폴더의 하위 폴더 목록을, 분석본 미발견이면
            # 해당 월 폴더의 .indd 목록을 에러 메시지에 나열.
            from engines.final.extractor import list_manuscript_entries
            notes = []
            if any(ym_to_folder[k] is None for k in ym_to_folder):
                grade_dir = os.path.join(gdrive_base, f"고{grade_num}")
                # 연도 묶음 폴더를 펼친 평면 목록 — 후보 목록에 묶음 이름만
                # 뜨면 "왜 못 찾았는지"가 아니라 오답을 보여주게 된다.
                from core.mock_folders import month_dir_entries
                folder_names = sorted(
                    nfc for nfc, full in month_dir_entries(
                        grade_dir, lambda d: list_manuscript_entries(d, None))
                )[:12]
                if folder_names:
                    notes.append("학년 폴더 하위 후보:\n  "
                                 + "\n  ".join(folder_names))
            for key, folder in ym_to_folder.items():
                if folder and not ym_to_sources.get(key):
                    indd_names = sorted(
                        nfc for nfc, full in
                        (list_manuscript_entries(folder, None) or [])
                        if nfc.lower().endswith(".indd")
                        and not nfc.startswith("~")
                    )[:12]
                    notes.append(
                        f"{os.path.basename(folder)} 내 .indd 후보:\n  "
                        + ("\n  ".join(indd_names) if indd_names else "(없음)")
                    )
            raise FileNotFoundError(
                "해결되지 않은 코드:\n  " + "\n  ".join(not_found_folders)
                + ("\n" + "\n".join(notes) if notes else "")
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
