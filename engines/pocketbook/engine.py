"""포켓북 조판 엔진.

분석본 .indd 폴더 경로 → run.jsx가 InDesign에서 직접 스토리 복제 → 포켓북 .indd + PDF.

run.jsx가 분석본을 직접 열고 영어/한글 스토리를 서식 유지한 채 복제하므로,
parse() 단계에서는 파일 목록과 메타데이터만 준비한다.
"""

import json
import os
import re

from core.base import BaseEngine, safe_copy

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")
_JSX_TEMPLATE = os.path.join(_DIR, "jsx", "run.jsx")
_SETTINGS_MARKER = "__SETTINGS_PATH__"


_PATH_KEYS = [
    "indd_template", "indd_output_dir",
    "first_page_image", "last_page_image",
    "illustrations_base", "review_test_base",
    "existing_pocketbooks",
]


def _load_config():
    from core.paths import resolve_config
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        cfg = json.load(f)
    return resolve_config(cfg, _PATH_KEYS)


class PocketbookEngine(BaseEngine):

    # ── 기본 속성 ─────────────────────────────────────────────────────

    @property
    def material_id(self):
        return "pocketbook"

    @property
    def display_name(self):
        return "포켓북"

    @property
    def description(self):
        return "포켓북 조판 자동화 (분석본 → 포켓북 내지)"

    @property
    def subject_prefix(self):
        return "포켓북"

    @property
    def template_name(self):
        return "typeset_pocketbook.html"

    @property
    def log_filename(self):
        return "typeset_log.txt"

    @property
    def jsx_timeout(self):
        # 광문1 분석본 4개+ 큰 케이스는 12분(720초+) 걸림 — 600은 부족.
        # 1800초(30분)면 _wait_for_completion이 PDF 완료 전 timeout 안 남.
        # stall 감지(STALL_LIMIT=300초)가 따로 있어 진짜 hang은 timeout 늘려도 자동 종료됨.
        return 1800

    @property
    def upload_spec(self):
        return {
            "slots": [
                {
                    "key": "analysis_dir",
                    "label": "분석본 폴더 경로 (학교 폴더)",
                    "required": True,
                    "type": "text",
                    "placeholder": "자동 감지됨 — 학교 선택 시 채워짐",
                },
                {
                    "key": "include_review_test_flag",
                    "label": "리뷰테스트 포함 여부",
                    "required": False,
                    "type": "text",
                },
                {
                    "key": "review_tests",
                    "label": "리뷰테스트 해설지 (.docx)",
                    "required": False,
                    "multiple": True,
                    "accept": ".docx",
                },
                {
                    "key": "include_listening_flag",
                    "label": "듣기 포함 여부",
                    "required": False,
                    "type": "text",
                },
                {
                    "key": "listening_file",
                    "label": "듣기 원고 (.hwpx)",
                    "required": False,
                    "accept": ".hwpx",
                },
            ]
        }

    # ── 유틸 ──────────────────────────────────────────────────────────

    @staticmethod
    def _gdrive_cp(src, dst):
        """구글드라이브 파일 로컬 복사 (ditto -> Finder 폴백)."""
        import subprocess

        # 1차: ditto (macOS 네이티브, FUSE 호환성 우수)
        r = subprocess.run(["ditto", src, dst], capture_output=True)
        if r.returncode == 0 and os.path.exists(dst) and os.path.getsize(dst) > 0:
            return

        # 2차: Finder 복사 (AppleScript)
        osa = (
            'tell application "Finder" to duplicate '
            f'(POSIX file "{src}" as alias) '
            f'to (POSIX file "{os.path.dirname(dst)}" as alias) '
            'with replacing'
        )
        r2 = subprocess.run(["osascript", "-e", osa], capture_output=True)
        if r2.returncode == 0:
            # Finder는 원본 파일명으로 복사 -> dst 이름으로 rename
            finder_copied = os.path.join(
                os.path.dirname(dst), os.path.basename(src)
            )
            if os.path.exists(finder_copied) and finder_copied != dst:
                if os.path.exists(dst):
                    os.remove(dst)
                os.rename(finder_copied, dst)
            if os.path.exists(dst) and os.path.getsize(dst) > 0:
                return

        # 양쪽 다 실패
        err1 = r.stderr.decode("utf-8", errors="replace").strip()
        err2 = r2.stderr.decode("utf-8", errors="replace").strip()
        raise OSError(
            f"파일 복사 실패: {os.path.basename(src)}\n"
            f"  ditto: {err1 or 'empty file'}\n"
            f"  Finder: {err2 or 'empty file'}"
        )

    @staticmethod
    def _get_meta(job_dir, key, default=""):
        p = os.path.join(job_dir, f"{key}.txt")
        return open(p).read().strip() if os.path.exists(p) else default

    @staticmethod
    def _find_analysis_files(folder):
        """폴더에서 분석본 .indd 파일 목록 (번호순 정렬)."""
        import unicodedata
        if not folder or not os.path.isdir(folder):
            return []
        files = []
        for raw in os.listdir(folder):
            nfc = unicodedata.normalize("NFC", raw)
            if nfc.endswith(".indd") and "분석본" in nfc:
                files.append(os.path.join(folder, raw))
        # "분석본" 뒤 숫자로 정렬 (분석본01, 분석본02, 분석본02-2...)
        def _sort_key(f):
            nfc = unicodedata.normalize("NFC", os.path.basename(f))
            m = re.search(r"분석본(\d+)(?:-(\d+))?", nfc)
            if m:
                major = int(m.group(1))
                minor = int(m.group(2)) if m.group(2) else 0
                return (major, minor)
            return (0, 0)
        files.sort(key=_sort_key)
        return files

    @staticmethod
    def _detect_source_type(filepath):
        """파일명에서 소스 유형 감지. macOS NFD 대응.

        한 분석본에 교과서(N과)와 모의고사(YY년M월)가 함께 들어 있으면 'mixed'.
        (예: '동아박4과,21년11월' / '26년6월,YBM박2과')
        run.jsx가 지문별 챕터 라벨로 교과서/모의고사를 다시 가른다.
        EBS(올림포스/리딩파워)+교과서 혼합은 기존 ebs 경로(미래엔 DL 등)를 유지한다.
        """
        import unicodedata
        name = unicodedata.normalize("NFC", os.path.basename(filepath))
        is_ebs = ("올포" in name or "올림" in name or "리딩파워" in name or "리파" in name)
        # 괄호 안 카테고리에 과/강(교과서)과 날짜(모의고사)가 동시에 있으면 혼합
        paren_m = re.search(r"\(([^)]+)\)", name)
        paren = paren_m.group(1) if paren_m else ""
        has_lesson = bool(re.search(r"\d+\s*(?:과|강)", paren))
        has_date = bool(re.search(r"\d{2}년\s*\d{1,2}월", name))
        if has_lesson and has_date and not is_ebs:
            return "mixed"
        if "모의" in name or "마더텅" in name or has_date:
            return "mockexam"
<<<<<<< Updated upstream
        if is_ebs:
=======
        if "올포" in name or "올림" in name or "리딩파워" in name or "리파" in name:
>>>>>>> Stashed changes
            return "ebs"
        return "textbook"

    @staticmethod
    def _detect_category(filepath):
        """파일명에서 카테고리 추출. 모의고사(YY년M월)는 괄호보다 우선.

        혼합(mixed) 파일은 괄호 안 전체(교과서+모의고사)를 그대로 반환한다
        (예: '동아박4과,21년11월'). run.jsx/리뷰테스트 탐색이 하위로 분리한다.
        """
        import unicodedata
        name = unicodedata.normalize("NFC", os.path.basename(filepath))
        # 혼합: 괄호 안 전체 보존 (모의고사 우선 규칙보다 먼저 처리)
        if PocketbookEngine._detect_source_type(filepath) == "mixed":
            pm = re.search(r"\(([^)]+)\)", name)
            if pm:
                return pm.group(1).strip()
        # 모의고사: "26년 3월" or "26년3월" -> "26년3월" (괄호보다 우선)
        m2 = re.search(r"(\d{2}년)\s*(\d{1,2}월)", name)
        if m2:
            return m2.group(1) + m2.group(2)
        # 교과서/EBS: 괄호 안 카테고리. 단 "(1)" 같은 단순 숫자(중복 파일 마커)는 제외.
        m = re.search(r"\(([^)]+)\)", name)
        if m:
            paren = m.group(1).strip()
            if re.search(r"[^\d\s,~\-]", paren):  # 강·과·한글 등 카테고리성 문자 포함
                return paren
        # 괄호 없는 올림포스/올포 EBS: 본문에서 "올림포스N강" 추출
        # (예 "분석본01_올림포스 독해기본1 15강" -> "올림포스15강",
        #  "...16강 (1)"의 (1)은 위에서 걸러지고 여기서 "올림포스16강")
        if "올림" in name or "올포" in name:
            gm = re.search(r"(\d+)\s*강", name)
            if gm:
                return "올림포스" + gm.group(1) + "강"
        return ""

    @staticmethod
    def _split_mixed_category(cat):
        """혼합 카테고리를 (하위카테고리, 타입) 목록으로 분리.

        '동아박4과,21년11월' → [('동아박4과','textbook'), ('21년11월','mockexam')]
        '26년6월,YBM박2과'  → [('YBM박2과','textbook'), ('26년6월','mockexam')]
        교과서 토큰이 여러 개면 하나로 합친다('능률민3과,4과' → '능률민3과,4과').
        """
        import unicodedata
        nfc = unicodedata.normalize("NFC", cat) if cat else ""
        tb_parts, mock_parts = [], []
        for part in nfc.split(","):
            part = part.strip()
            if not part:
                continue
            if re.search(r"\d{2}년\s*\d{1,2}월", part) or "마더텅" in part:
                mock_parts.append(part)
            else:
                tb_parts.append(part)
        result = []
        if tb_parts:
            result.append((",".join(tb_parts), "textbook"))
        for mp in mock_parts:
            result.append((mp, "mockexam"))
        return result

    @staticmethod
    def _resolve_subject_folder(folder):
        """완성 포켓북 과목 폴더의 로마/아라비아 숫자 표기 차이 흡수.

        config의 existing_pocketbooks는 '영어1'/'영어2'(아라비아)인데 실제 폴더는
        '영어Ⅰ'/'영어Ⅱ'(로마)일 수 있다. 이 경우 완성본을 못 찾아 교과서 지문이
        전부 신규조판되던 버그가 있었다(리뷰테스트 탐색은 norm_subj.replace로 이미
        흡수하지만 완성 포켓북 경로만 누락). 실제 폴더가 있으면 그대로, 없으면
        표기를 바꿔 존재하는 폴더를 찾는다."""
        import unicodedata
        if not folder or os.path.isdir(folder):
            return folder
        base, name = os.path.split(folder)
        nfc = unicodedata.normalize("NFC", name)
        for ar, ro in (("영어1", "영어Ⅰ"), ("영어2", "영어Ⅱ")):
            if ar in nfc:
                cand = os.path.join(base, nfc.replace(ar, ro))
                if os.path.isdir(cand):
                    return cand
        return folder

    @staticmethod
    def _expand_category(cat):
        """카테고리 문자열을 개별 항목으로 확장.
        'YBM김1,2과' → ['YBM김1과', 'YBM김2과']
        '교과서1,2과,SL' → ['교과서1과', '교과서2과', 'SL']
        '25년3월' → ['25년3월']
        '올포14,15,16강' → ['올포14강', '올포15강', '올포16강']
        """
        if not cat:
            return []
        # 숫자,숫자 + 접미사(과/강) 패턴: "YBM김1,2과" or "올포14,15강"
        m = re.match(r'^(.+?)(\d+(?:,\d+)+)(과|강)(.*)$', cat)
        if m:
            prefix, nums_str, suffix, rest = m.groups()
            nums = nums_str.split(',')
            result = [prefix + n + suffix for n in nums]
            # 나머지 부분 (예: ",SL")
            if rest:
                for extra in rest.split(','):
                    extra = extra.strip()
                    if extra:
                        result.append(extra)
            return result
        # 콤마 구분된 단순 목록
        if ',' in cat:
            return [c.strip() for c in cat.split(',') if c.strip()]
        return [cat]

    @staticmethod
    def _parse_gang_spec(cat):
        """올림포스 카테고리에서 강 번호 목록 추출 (범위 포함, 등장 순서 유지).
        '올림포스10,11,12,14강' → [10,11,12,14]
        '올림포스10-12,14-16강' → [10,11,12,14,15,16]
        '올림포스15,16,17,18강,미래앤3,4과DL' → [15,16,17,18]
        """
        import unicodedata
        nfc = unicodedata.normalize("NFC", cat) if cat else ""
<<<<<<< Updated upstream
        m = re.search(r"(?:올림포스|올포|리딩파워|리파)\s*([\d,\-~]+)강", nfc)
=======
        m = re.search(r"(?:올림포스|올포)\s*([\d,\-~]+)강", nfc)
>>>>>>> Stashed changes
        if not m:
            return []
        spec = m.group(1)
        nums = []
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            rng = re.match(r"^(\d+)\s*[-~]\s*(\d+)$", part)
            if rng:
                a, b = int(rng.group(1)), int(rng.group(2))
                if a <= b:
                    nums.extend(range(a, b + 1))
            elif part.isdigit():
                nums.append(int(part))
        # 중복 제거 (등장 순서 유지)
        seen = set()
        result = []
        for n in nums:
            if n not in seen:
                seen.add(n)
                result.append(n)
        return result

    @staticmethod
    def _review_canon_type(header):
        """리뷰테스트 header에서 유형 추출 → olymposCanonKey와 같은 표기.
        '1. p68-수능 대비 ANALYSIS' → '분석', '2. p70-no.01' → '01',
        '2. p116-no.01~02' → '01'(범위 첫 번호), '서술형 Practice' → '서술'.
        """
        if not header:
            return None
        if "ANALYSIS" in header or "분석" in header:
            return "분석"
        if "서술" in header:
            return "서술"
        if "논술" in header:
            return "논술"
<<<<<<< Updated upstream
        # 리딩파워: "...Example" → "Ex" (지문 라벨 "Unit N Ex"와 canon 매칭)
        if "Example" in header or re.search(r"(?<![A-Za-z])Ex(?![A-Za-z])", header):
            return "Ex"
=======
>>>>>>> Stashed changes
        nm = re.search(r"no\.?\s*(\d+)", header, re.IGNORECASE)
        if nm:
            n = int(nm.group(1))
            return ("0" if n < 10 else "") + str(n)
        return None

    @staticmethod
    def _assign_olpo_review_canon(passages, gang_list):
        """올림포스 리뷰 passages에 canon 키('강-유형') 부여.
        강 번호는 header에 없으므로 'ANALYSIS(분석)'마다 새 강으로 보고
        gang_list(등장 순서)에서 순차 할당한다.
        """
        if not gang_list:
            return
        gang_idx = -1
        for p in passages:
            t = PocketbookEngine._review_canon_type(p.get("header", ""))
            if t == "분석":
                gang_idx += 1
            if gang_idx < 0:
                gang_idx = 0
            if t and gang_idx < len(gang_list):
                p["canon"] = str(gang_list[gang_idx]) + "-" + t

    @staticmethod
<<<<<<< Updated upstream
    def _find_rp_review_docx(unit_dir):
        """리딩파워 Unit 폴더에서 리뷰테스트 해설지(없으면 정답지) .docx 경로.
        "... 리뷰테스트"/"리테" 하위 폴더를 우선 탐색한다.
        """
        import unicodedata
        dirs = [unit_dir]
        try:
            for raw in os.listdir(unit_dir):
                full = os.path.join(unit_dir, raw)
                if os.path.isdir(full):
                    nfc = unicodedata.normalize("NFC", raw)
                    if "리뷰" in nfc or "리테" in nfc:
                        dirs.insert(0, full)
        except Exception:
            return None
        for d in dirs:
            try:
                files = [unicodedata.normalize("NFC", f) for f in os.listdir(d)]
            except Exception:
                continue
            for kw in ["해설지", "정답지"]:
                for f in files:
                    if f.startswith("~$"):
                        continue
                    if f.endswith(".docx") and kw in f:
                        return os.path.join(d, f)
        return None

    def _discover_rp_review(self, rt_base, lesson_nums, job_dir, log):
        """리딩파워 리뷰테스트 탐색 + 파싱 + Unit 기준 canon 부여.

        올림포스는 "올림포스 독해기본N 〉 N강", 리딩파워는
        "Reading Power 유형편(기본) 〉 Unit N 〉 ... 리뷰테스트 〉 ...해설지.docx" 구조이고
        폴더가 "Unit N"으로 명명돼 올림포스 경로가 전혀 못 잡았다.
        파일명 강번호 오타(예 "13,14,16,16강")를 흡수하려고 min~max 범위 Unit을 모두 본다.
        canon은 "Unit번호-유형"(예 "17-Ex", "17-01") — run.jsx가 지문 "Unit 17 Ex"와 매칭.
        """
        import unicodedata
        from engines.pocketbook.parser import parse_review_test
        passages = []
        ebs_base = os.path.join(rt_base, "EBS 작업")
        if not os.path.isdir(ebs_base) or not lesson_nums:
            return passages
        # "Reading Power 유형편(기본)" 폴더 (완성편 제외)
        rp_root = None
        for raw in os.listdir(ebs_base):
            nfc = unicodedata.normalize("NFC", raw)
            if ("Reading Power" in nfc or "리딩파워" in nfc) and "완성" not in nfc:
                full = os.path.join(ebs_base, raw)
                if os.path.isdir(full):
                    rp_root = full
                    break
        if not rp_root:
            log("  [리뷰테스트] 리딩파워 폴더(EBS 작업) 못 찾음")
            return passages
        lo, hi = min(lesson_nums), max(lesson_nums)
        gdrive_markers = ("GoogleDrive", "Google Drive", "CloudStorage")
        local_rt_dir = os.path.join(job_dir, "review_test_local")
        os.makedirs(local_rt_dir, exist_ok=True)
        units = []
        for raw in os.listdir(rp_root):
            full = os.path.join(rp_root, raw)
            if not os.path.isdir(full):
                continue
            um = re.search(r"Unit\s*(\d+)", unicodedata.normalize("NFC", raw))
            if um and lo <= int(um.group(1)) <= hi:
                units.append((int(um.group(1)), full))
        units.sort()
        for unum, udir in units:
            docx = self._find_rp_review_docx(udir)
            if not docx:
                continue
            parse_path = docx
            if any(m in docx for m in gdrive_markers):
                local_copy = os.path.join(local_rt_dir, os.path.basename(docx))
                if not os.path.exists(local_copy):
                    try:
                        self._gdrive_cp(docx, local_copy)
                    except Exception as e:
                        log(f"  [리뷰테스트] 복사 실패: {e}")
                        continue
                parse_path = local_copy
            try:
                rt = parse_review_test(parse_path)
            except Exception as e:
                log(f"  [리뷰테스트] 파싱 실패 ({os.path.basename(docx)}): {e}")
                continue
            for rp in rt.get("passages", []):
                t = PocketbookEngine._review_canon_type(rp["header"])
                passages.append({
                    "header": rp["header"],
                    "answer_text": "\r".join(rp["lines_answer"]),
                    "blank_text": "\r".join(rp["lines_blank"]),
                    "word_count": rp["word_count"],
                    "canon": (str(unum) + "-" + t) if t else None,
                })
        return passages

    @staticmethod
=======
>>>>>>> Stashed changes
    def _match_categories_to_files(categories, completed_files):
        """카테고리 목록과 완성 포켓북 파일 매칭.
        Returns: [{"category": str, "file": str, "lesson": int|None}, ...]
        범위 파일명 (예: "(1-5강)") 매칭 지원.
        """
        import unicodedata
        matches = []
        for sub_cat in categories:
            found = None
            lesson_num = None
            for cf in completed_files:
                nfc = unicodedata.normalize("NFC", os.path.basename(cf))
                # 완성 파일명의 괄호 안 카테고리에서 매칭
                fm = re.search(r'\(([^)]+)\)', nfc)
                if fm and sub_cat == fm.group(1):
                    found = cf
                    break
                # 부분 매칭 (sub_cat이 파일명에 포함)
                if sub_cat in nfc:
                    found = cf
                    break
            # 범위 매칭: "올포14강" → 14, "(10-16강)" 파일과 매칭
            if not found:
                lm = re.search(r'(\d+)강', sub_cat)
                if lm:
                    lesson_num = int(lm.group(1))
                    for cf in completed_files:
                        nfc = unicodedata.normalize("NFC", os.path.basename(cf))
                        fm = re.search(r'\((\d+)-(\d+)강\)', nfc)
                        if fm:
                            rng_start = int(fm.group(1))
                            rng_end = int(fm.group(2))
                            if rng_start <= lesson_num <= rng_end:
                                found = cf
                                break
            if found:
                matches.append({"category": sub_cat, "file": found, "lesson": lesson_num})
        return matches

    @staticmethod
    def _sync_rt_map_keys(rt_map, old_categories, new_categories):
        """settings.json의 categories가 content.json과 다를 때 review_test_map에 alias 추가.
        예: content "동아박1,2과" → settings "동아박2과"이면, rt_map["동아박2과"] = rt_map["동아박1,2과"]
        """
        for idx, new_cat in enumerate(new_categories):
            old_cat = old_categories[idx] if idx < len(old_categories) else ""
            if new_cat != old_cat and old_cat in rt_map and new_cat not in rt_map:
                rt_map[new_cat] = rt_map[old_cat]
        return rt_map

    def _discover_review_tests(self, categories, file_types, grade, job_dir, log, semester="", analysis_files=None):
        """카테고리 기반으로 구글드라이브에서 리뷰테스트 해설지 자동 탐색.
        Returns: (rt_map, missing_tb_cats)
          rt_map: { "2503": { "passages": [...] }, ... }
          missing_tb_cats: 탐색 실패한 교과서 카테고리 목록
        """
        import unicodedata
        cfg = _load_config()
        rt_base = cfg.get("review_test_base", "")
        if not rt_base or not os.path.isdir(rt_base):
            missing = [c for i, c in enumerate(categories) if i < len(file_types) and file_types[i] == "textbook"]
            return {}, missing

        # 분석본 파일명에서 출판사 추출 (예: "영어1 분석본 YBM(박)" → "YBM")
        publisher = ""
        if analysis_files:
            for af in analysis_files:
                nfc_af = unicodedata.normalize("NFC", os.path.basename(af))
                pub_m = re.search(r"(YBM|능률|동아|미래엔|비상|지학사|천재)", nfc_af, re.IGNORECASE)
                if pub_m:
                    publisher = pub_m.group(1).upper()
                    break

        from engines.pocketbook.parser import parse_review_test

        rt_map = {}
        seen_keys = set()
        missing_tb_cats = []

        # 혼합(mixed) 파일은 교과서/모의고사 하위 카테고리로 분리해 각각 탐색.
        # 멀티날짜 모의고사(예: 분석본04(25년6월,22년6월,22년3월))는 _detect_category가
        # 첫 날짜만 반환하므로, 파일명의 모든 YY년M월을 각각 탐색해야 secondary 날짜
        # 리뷰테스트(22년6월/22년3월 등)가 누락되지 않는다. (날짜 없는 마더텅은 그대로 유지)
        expanded_entries = []  # [(cat, ft), ...]
        for idx, cat in enumerate(categories):
            ft = file_types[idx] if idx < len(file_types) else "textbook"
            if ft == "mixed":
                expanded_entries.extend(self._split_mixed_category(cat))
            elif ft == "mockexam" and analysis_files and idx < len(analysis_files):
                nfc_name = unicodedata.normalize("NFC", os.path.basename(analysis_files[idx]))
                dates = re.findall(r"\d{2}년\s*\d{1,2}월", nfc_name)
                if dates:
                    for d in dates:
                        expanded_entries.append((re.sub(r"\s+", "", d), "mockexam"))
                else:
                    expanded_entries.append((cat, ft))
            else:
                expanded_entries.append((cat, ft))

        for cat, ft in expanded_entries:
            nfc_cat = unicodedata.normalize("NFC", cat) if cat else ""
            if not nfc_cat:
                continue

            rt_key = None
            search_dirs = []

            if ft == "mockexam":
                # 마더텅 카테고리: "마더텅3" → 마더텅 예전 기출 폴더에서 해설지 탐색
                mt_match = re.match(r"마더텅(\d+)", nfc_cat)
                if mt_match:
                    mt_num = mt_match.group(1)
                    rt_key = "마더텅" + mt_num
                    if rt_key in seen_keys:
                        continue
                    seen_keys.add(rt_key)
                    # 검색 경로: 모의고사 작업/{grade}/한영{grade} 마더텅 예전 기출/{N강 ...}/
                    mock_base = os.path.join(rt_base, "모의고사 작업", grade)
                    if os.path.isdir(mock_base):
                        for raw in os.listdir(mock_base):
                            nfc_raw = unicodedata.normalize("NFC", raw)
                            if "마더텅" in nfc_raw and "예전" in nfc_raw:
                                mt_dir = os.path.join(mock_base, raw)
                                if os.path.isdir(mt_dir):
                                    for sub_raw in os.listdir(mt_dir):
                                        nfc_sub = unicodedata.normalize("NFC", sub_raw)
                                        sub_full = os.path.join(mt_dir, sub_raw)
                                        if os.path.isdir(sub_full) and nfc_sub.startswith(mt_num + "강"):
                                            search_dirs.append(sub_full)
                else:
                    # 일반 모의고사: "25년3월" or "25년10월" -> yy=25, mm=3 or 10
                    ym = re.search(r"(\d{2})년\s*(\d{1,2})월", nfc_cat)
                    if not ym:
                        continue
                    yy = ym.group(1)
                    mm = ym.group(2)
                    rt_key = yy + mm.zfill(2)
                    if rt_key in seen_keys:
                        continue
                    seen_keys.add(rt_key)
                    # 검색 경로: 모의고사 작업/{grade}/{grade} {YY}년 {M}월/
                    mock_base = os.path.join(rt_base, "모의고사 작업", grade)
                    if os.path.isdir(mock_base):
                        for raw in os.listdir(mock_base):
                            nfc = unicodedata.normalize("NFC", raw)
                            if yy in nfc and str(int(mm)) in nfc:
                                full = os.path.join(mock_base, raw)
                                if os.path.isdir(full):
                                    search_dirs.append(full)

            elif ft == "ebs":
                # 카테고리 "올포3강" or "올포3,4강" -> 강 번호 추출
                # rt_key = 카테고리 그대로 (예: "올포3,4강")
                rt_key = nfc_cat
                if rt_key in seen_keys:
                    continue
                seen_keys.add(rt_key)
                # 강 번호 목록 추출 (범위 "10-12,14-16강" 포함)
                lesson_nums = self._parse_gang_spec(nfc_cat)
                if not lesson_nums:
                    continue
                # 리딩파워: 올림포스와 폴더 구조/명명("Unit N")이 달라 별도 처리
                if "리딩파워" in nfc_cat or "리파" in nfc_cat:
                    rp_passages = self._discover_rp_review(rt_base, lesson_nums, job_dir, log)
                    rt_map[rt_key] = {"passages": rp_passages}
                    log(f"  [리뷰테스트] {nfc_cat} -> {len(rp_passages)}개 (리딩파워)")
                    continue
                # EBS 작업 하위에서 올림포스 폴더 탐색
                ebs_base = os.path.join(rt_base, "EBS 작업")
                if not os.path.isdir(ebs_base):
                    continue
                # 올림포스 독해기본1/2 중 학년에 맞는 폴더만 찾기
                # 고1 → 독해기본1, 고2 → 독해기본2
                olpo_dirs = []
                nfc_grade_local = unicodedata.normalize("NFC", grade) if grade else ""
                gm_local = re.search(r"(\d)", nfc_grade_local)
                grade_digit = gm_local.group(1) if gm_local else ""
                for raw in os.listdir(ebs_base):
                    nfc_raw = unicodedata.normalize("NFC", raw)
                    if "올림포스" in nfc_raw and "독해기본" in nfc_raw:
                        # 학년 필터: "독해기본1" → 고1, "독해기본2" → 고2
                        gm2 = re.search(r"독해기본(\d)", nfc_raw)
                        if gm2 and grade_digit and gm2.group(1) != grade_digit:
                            continue
                        olpo_dirs.append(os.path.join(ebs_base, raw))
                # 각 강별로 리테 폴더 탐색
                for lnum in lesson_nums:
                    for olpo_dir in olpo_dirs:
                        # "올림포스 독해기본1 3강" 또는 "올림포스 독해기본1 1~2강" 패턴
                        for raw in os.listdir(olpo_dir):
                            nfc_raw = unicodedata.normalize("NFC", raw)
                            full = os.path.join(olpo_dir, raw)
                            if not os.path.isdir(full):
                                continue
                            # 정확한 강 매칭 ("3강") 또는 범위 매칭 ("1~2강")
                            exact_m = re.search(r"(\d+)강$", nfc_raw.strip())
                            range_m = re.search(r"(\d+)[~\-](\d+)강", nfc_raw)
                            matched = False
                            if exact_m and int(exact_m.group(1)) == lnum:
                                matched = True
                            elif range_m:
                                rng_s = int(range_m.group(1))
                                rng_e = int(range_m.group(2))
                                if rng_s <= lnum <= rng_e:
                                    matched = True
                            if matched:
                                search_dirs.append(full)

            elif ft == "textbook":
                rt_key = nfc_cat
                if rt_key in seen_keys:
                    continue
                seen_keys.add(rt_key)
                # grade+semester -> 정확한 과목명 매핑
                # 고1+1학기=공통영어1, 고1+2학기=공통영어2, 고2+1학기=영어1(영어Ⅰ), 고2+2학기=영어2(영어Ⅱ)
                subj_exact = ""
                nfc_grade = unicodedata.normalize("NFC", grade) if grade else ""
                grade_num = ""
                gm = re.search(r"(\d)", nfc_grade)
                if gm:
                    grade_num = gm.group(1)
                subj_map = {
                    ("1", "1"): "공통영어1", ("1", "2"): "공통영어2",
                    ("2", "1"): "영어1", ("2", "2"): "영어2",
                }
                subj_exact = subj_map.get((grade_num, semester), "")
                # 검색 경로: 교과서 작업/{과목}/ 하위에서 카테고리 매칭
                tb_base = os.path.join(rt_base, "교과서 작업")
                if os.path.isdir(tb_base):
                    for subj_raw in os.listdir(tb_base):
                        subj_dir = os.path.join(tb_base, subj_raw)
                        if not os.path.isdir(subj_dir):
                            continue
                        # grade+semester로 정확한 과목 폴더만 탐색
                        if subj_exact:
                            nfc_subj = unicodedata.normalize("NFC", subj_raw)
                            # 숫자/로마숫자 정규화: Ⅰ→1, Ⅱ→2
                            norm_subj = nfc_subj.replace("\u2160", "1").replace("\u2161", "2")
                            if subj_exact not in norm_subj:
                                continue
                            # "영어1" 검색 시 "공통영어1" 제외
                            if "공통" not in subj_exact and "공통" in norm_subj:
                                continue
                        # 카테고리에서 출판사와 과 번호 분리: "동아박1,2과" → pub="동아박", lessons=[1,2]
                        cat_pub_m = re.match(r"(.+?)(\d[\d,]*과)$", nfc_cat)
                        if cat_pub_m:
                            cat_pub_core = re.sub(r"[^\w]", "", cat_pub_m.group(1))
                            cat_lesson_nums = [int(n) for n in re.findall(r"\d+", cat_pub_m.group(2))]
                        else:
                            cat_pub_core = re.sub(r"[^\w]", "", nfc_cat)
                            cat_lesson_nums = []
                        for pub_raw in os.listdir(subj_dir):
                            pub_dir = os.path.join(subj_dir, pub_raw)
                            if not os.path.isdir(pub_dir):
                                continue
                            # 출판사 폴더명에 출판사명 포함 여부 확인 (과 번호 제외)
                            nfc_pub = unicodedata.normalize("NFC", pub_raw)
                            pub_core = re.sub(r"[^\w]", "", nfc_pub)
                            if cat_pub_core and cat_pub_core not in pub_core:
                                continue
                            # 출판사명 필터 (분석본에서 추출한 출판사와 일치해야 함)
                            if publisher and publisher.upper() not in nfc_pub.upper():
                                continue
                            for les_raw in os.listdir(pub_dir):
                                full = os.path.join(pub_dir, les_raw)
                                if not os.path.isdir(full):
                                    continue
                                # 과 번호 필터: 카테고리에 과 번호가 있으면 해당 과만 추가
                                if cat_lesson_nums:
                                    nfc_les = unicodedata.normalize("NFC", les_raw)
                                    les_m = re.search(r"(\d+)과", nfc_les)
                                    if les_m and int(les_m.group(1)) in cat_lesson_nums:
                                        search_dirs.append(full)
                                else:
                                    search_dirs.append(full)

            if not rt_key or not search_dirs:
                continue

            # 리뷰테스트 폴더에서 해설지/정답지.docx 찾기
            # 교과서: 과별 폴더마다 해설지가 별도 → 전부 수집
            docx_paths = []
            for sd in search_dirs:
                dirs_to_check = [sd]
                try:
                    for sub_raw in os.listdir(sd):
                        sub_full = os.path.join(sd, sub_raw)
                        if os.path.isdir(sub_full):
                            nfc_sub = unicodedata.normalize("NFC", sub_raw)
                            if "리뷰" in nfc_sub or "리테" in nfc_sub:
                                dirs_to_check.insert(0, sub_full)
                except Exception:
                    continue

                found = None
                for d in dirs_to_check:
                    try:
                        # 리테/리뷰 이름의 하위 폴더 안이면 파일명에 키워드 불필요
                        nfc_dirname = unicodedata.normalize("NFC", os.path.basename(d))
                        is_rt_dir = ("리뷰" in nfc_dirname or "리테" in nfc_dirname)
                        files = [unicodedata.normalize("NFC", f) for f in os.listdir(d)]
                        # 1순위: 해설지, 2순위: 정답지
                        for keyword in ["해설지", "정답지"]:
                            for nfc_f in files:
                                if nfc_f.startswith("~$"):
                                    continue
                                if not nfc_f.endswith(".docx") or keyword not in nfc_f:
                                    continue
                                # 리테/리뷰 폴더 안이면 파일명 키워드 불필요
                                if is_rt_dir or "리뷰" in nfc_f or "리테" in nfc_f:
                                    found = os.path.join(d, nfc_f)
                                    break
                            if found:
                                break
                    except Exception:
                        continue
                    if found:
                        break
                if found:
                    docx_paths.append(found)
                    # 모의고사는 하나만 찾으면 됨
                    if ft == "mockexam":
                        break

            if not docx_paths:
                log(f"  [리뷰테스트] {nfc_cat} -> 해설지/정답지 못 찾음")
                rt_map[rt_key] = {"passages": []}
                if ft == "textbook":
                    missing_tb_cats.append(nfc_cat)
                continue

            # 구글드라이브면 로컬 복사 후 파싱 (모든 docx)
            gdrive_markers = ("GoogleDrive", "Google Drive", "CloudStorage")
            all_passages = []
            local_rt_dir = os.path.join(job_dir, "review_test_local")
            os.makedirs(local_rt_dir, exist_ok=True)
            for docx_path in docx_paths:
                parse_path = docx_path
                if any(m in docx_path for m in gdrive_markers):
                    local_copy = os.path.join(local_rt_dir, os.path.basename(docx_path))
                    if not os.path.exists(local_copy):
                        try:
                            self._gdrive_cp(docx_path, local_copy)
                        except Exception as e:
                            log(f"  [리뷰테스트] 복사 실패: {e}")
                            continue
                    parse_path = local_copy

                try:
                    rt_result = parse_review_test(parse_path)
                    for rp in rt_result.get("passages", []):
                        all_passages.append({
                            "header": rp["header"],
                            "answer_text": "\r".join(rp["lines_answer"]),
                            "blank_text": "\r".join(rp["lines_blank"]),
                            "word_count": rp["word_count"],
                        })
                except Exception as e:
                    log(f"  [리뷰테스트] 파싱 실패 ({os.path.basename(docx_path)}): {e}")

            # 올림포스(EBS): 리뷰에 canon 키('강-유형') 부여 → run.jsx에서 지문과 매칭
            if ft == "ebs":
                self._assign_olpo_review_canon(all_passages, lesson_nums)

            rt_map[rt_key] = {"passages": all_passages}
            fnames = [os.path.basename(p) for p in docx_paths]
            log(f"  [리뷰테스트] {nfc_cat} -> {len(all_passages)}개 ({', '.join(fnames)})")

        return rt_map, missing_tb_cats

    # ── 1단계: 파싱 (파일 목록 + 메타데이터 준비) ────────────────────

    def parse(self, uploaded_files, job_dir, log):
        # 분석본 폴더 경로
        analysis_dir = uploaded_files.get("analysis_dir", "")
        if isinstance(analysis_dir, list):
            analysis_dir = analysis_dir[0] if analysis_dir else ""

        # 분석본 .indd 파일 탐색
        analysis_files = self._find_analysis_files(analysis_dir)
        if not analysis_files:
            raise FileNotFoundError(f"분석본 파일이 없습니다: {analysis_dir}")

        log(f"[분석본] {len(analysis_files)}개 파일 발견")

        # 구글드라이브 파일 → 로컬 복사 (rsync로 fcopyfile 데드락 회피)
        gdrive_markers = ("GoogleDrive", "Google Drive", "CloudStorage")
        if any(m in analysis_dir for m in gdrive_markers):
            local_dir = os.path.join(job_dir, "analysis_local")
            os.makedirs(local_dir, exist_ok=True)
            local_files = []
            for af in analysis_files:
                dst = os.path.join(local_dir, os.path.basename(af))
                self._gdrive_cp(af, dst)
                local_files.append(dst)
            analysis_files = local_files
            log(f"[복사] 구글드라이브 → 로컬 ({len(local_files)}개)")

        # 파일별 유형·카테고리 감지
        file_types = []
        categories = []
        type_label = {"textbook": "교과서", "mockexam": "모의고사", "ebs": "EBS", "mixed": "교과서+모의고사"}
        for af in analysis_files:
            st = self._detect_source_type(af)
            cat = self._detect_category(af)
            file_types.append(st)
            categories.append(cat)
            log(f"  - {os.path.basename(af)} → {type_label.get(st, st)} [{cat}]")

        # 리뷰테스트 해설지 파싱 (암기테스트용)
        review_files = uploaded_files.get("review_tests", [])
        if isinstance(review_files, str):
            review_files = [review_files]

        memtest_data = []
        if review_files:
            from engines.pocketbook.parser import parse_multiple_review_tests
            rt_path = os.path.join(job_dir, "review_test.json")
            rt_result = parse_multiple_review_tests(review_files, rt_path, log)
            for rp in rt_result.get("passages", []):
                memtest_data.append({
                    "header": rp["header"],
                    "answer_text": "\r".join(rp["lines_answer"]),
                    "blank_text": "\r".join(rp["lines_blank"]),
                    "word_count": rp["word_count"],
                })
            log(f"[암기테스트] {len(memtest_data)}개 지문 준비")

        # 듣기 원고 파싱
        listening_text_file = ""
        include_listening = uploaded_files.get("include_listening_flag", "0")
        if isinstance(include_listening, list):
            include_listening = include_listening[0] if include_listening else "0"

        if include_listening == "1":
            listening_files = uploaded_files.get("listening_file", [])
            if isinstance(listening_files, str):
                listening_files = [listening_files]
            if listening_files:
                hwpx_path = listening_files[0]
                listening_text_file = os.path.join(job_dir, "listening_parsed.txt")
                import subprocess
                # 파서는 엔진 패키지 내부(_DIR)에 위치 — git에 포함되고 경로가 일관됨
                parser_script = os.path.join(_DIR, "parse_listening_hwpx.py")
                r = subprocess.run(
                    ["python3", parser_script, hwpx_path, listening_text_file],
                    capture_output=True, text=True
                )
                if r.returncode != 0:
                    log(f"[듣기] 파싱 오류: {r.stderr.strip()}")
                else:
                    for line in r.stderr.strip().split("\n"):
                        if line.strip():
                            log(f"[듣기] {line.strip()}")

        # content.json 저장
        content = {
            "analysis_dir": analysis_dir,
            "analysis_files": analysis_files,
            "file_types": file_types,
            "categories": categories,
            "memtest": memtest_data,
            "total_files": len(analysis_files),
            "total_memtest": len(memtest_data),
            "listening_text_file": listening_text_file,
        }

        content_path = os.path.join(job_dir, "content.json")
        with open(content_path, "w", encoding="utf-8") as f:
            json.dump(content, f, ensure_ascii=False, indent=2)

        log(f"[파싱] 완료: {len(analysis_files)}개 분석본")
        return content_path

    # ── 2단계: JSX 준비 ──────────────────────────────────────────────

    def prepare_jsx(self, json_path, job_dir, log):
        cfg = _load_config()
        school = self._get_meta(job_dir, "school", "학교미선택")

        with open(json_path, encoding="utf-8") as f:
            content = json.load(f)

        # 출력 경로 (구글 드라이브면 로컬 job_dir로 전환)
        analysis_dir = content.get("analysis_dir", "")
        gdrive_markers = ("GoogleDrive", "Google Drive", "CloudStorage")
        if analysis_dir and os.path.isdir(analysis_dir) and not any(m in analysis_dir for m in gdrive_markers):
            output_dir = analysis_dir
        else:
            output_dir = cfg.get("indd_output_dir", job_dir)
        os.makedirs(output_dir, exist_ok=True)

        cats = [c for c in content.get("categories", []) if c]
        category_short = "_".join(cats).replace(",", "_").replace(" ", "") if cats else ""
        if category_short:
            indd_name = f"{school}_포켓북({category_short})_내지.indd"
        else:
            indd_name = f"{school}_포켓북_내지.indd"
        output_path = os.path.join(output_dir, indd_name)

        # 템플릿
        template_path = cfg.get("indd_template", "")
        if not template_path or not os.path.exists(template_path):
            raise FileNotFoundError(f"포켓북 템플릿 없음: {template_path}")

        # settings/JSX — /tmp에 저장 (ExtendScript가 한글/iCloud 경로를 못 읽음)
        import hashlib, shutil
        job_hash = hashlib.md5(job_dir.encode()).hexdigest()[:8]
        jsx_work_dir = f"/tmp/pocketbook_{job_hash}"
        os.makedirs(jsx_work_dir, exist_ok=True)

        # 템플릿을 /tmp로 복사 (iCloud/한글 경로 회피)
        local_template = os.path.join(jsx_work_dir, "template.indd")
        if not os.path.exists(local_template):
            safe_copy(template_path, local_template)
        template_path = local_template

        # 학년 추출 (학교명 끝 숫자: 광문1→고1, 배재2→고2)
        grade = ""
        grade_num = ""
        m = re.search(r"(\d)$", school)
        if m:
            grade_num = m.group(1)
            grade = "고" + grade_num

        # 고2 올림포스/올포 → 모의고사로 재분류
        # 고2 올포 분석본은 "고2 25년 9월 20번" 같은 모의고사 지문으로 구성됨
        # 완성본 검색, 리뷰테스트, 마스터 매핑 모두 모의고사로 처리해야 함
        # (고1 올포는 EBS 그대로 유지)
        if grade_num == "2":
            orig_file_types = content.get("file_types", [])
            converted = False
            for i in range(len(orig_file_types)):
                if orig_file_types[i] == "ebs":
                    orig_file_types[i] = "mockexam"
                    converted = True
            if converted:
                content["file_types"] = orig_file_types
                log("[변환] 고2 올림포스 → 모의고사로 재분류")

        # 학기 추출 (분석본 폴더 경로에서: 26-1-중간 → 1학기, 26-2-기말 → 2학기)
        semester = ""
        sem_match = re.search(r"\d{2}-(\d)-", analysis_dir)
        if sem_match:
            semester = sem_match.group(1)  # "1" or "2"

        # 올림포스 완성본 책 구분: 1학기 → 독해기본1, 2학기 → 독해기본2
        # (올림포스 폴더에 두 책이 섞여 있고 강 범위가 겹치므로, 학기로 책을 골라야
        #  다른 지문이 들어가는 것을 막는다)
        olympos_book = ""
        if semester == "1":
            olympos_book = "독해기본1"
        elif semester == "2":
            olympos_book = "독해기본2"

        # 학년+학기 → 검색할 완성 포켓북 폴더 결정
        # 모의고사: 고1 모의고사 / 고2 모의고사
        # 교과서: 고1+1학기→공통영어1, 고1+2학기→공통영어2, 고2+1학기→영어1, 고2+2학기→영어2
        textbook_folder_map = {
            ("1", "1"): "공통영어1",
            ("1", "2"): "공통영어2",
            ("2", "1"): "영어1",
            ("2", "2"): "영어2",
        }
        mock_folder_key = f"{grade} 모의고사" if grade else ""
        text_folder_key = textbook_folder_map.get((grade_num, semester), "")

        log(f"[설정] {grade} {semester}학기 → 모의고사: {mock_folder_key}, 교과서: {text_folder_key}")

        # 삽화 경로
        illustrations_base = cfg.get("illustrations_base", "")

        # 기존 완성 포켓북 파일 목록 수집 (원본 경로만, 복사는 나중에)
        import unicodedata
        completed_files = []  # 원본 경로 리스트
        seen_paths = set()

        def _collect_completed(folder, recursive=False):
            if not folder or not os.path.isdir(folder):
                return
            for fn in os.listdir(folder):
                full = os.path.join(folder, fn)
                nfc = unicodedata.normalize("NFC", fn)
                if recursive and os.path.isdir(full):
                    if nfc == "기존" or nfc.startswith("기존"):
                        continue
                    _collect_completed(full, recursive=True)
                    continue
                if not nfc.endswith(".indd"):
                    continue
                if "분석본" in nfc or "작업전" in nfc:
                    continue
                if full == output_path or full in seen_paths:
                    continue
                seen_paths.add(full)
                completed_files.append(full)

        # 학년+학기에 해당하는 완성 포켓북 폴더만 검색
        all_pocketbooks = cfg.get("existing_pocketbooks", {})
        # 과목 폴더 로마/아라비아 표기 차이 흡수 (영어1→영어Ⅰ 등). 안 하면 완성본
        # 미발견으로 교과서 지문이 전부 신규조판됨.
        all_pocketbooks = {k: (self._resolve_subject_folder(v) if isinstance(v, str) else v)
                           for k, v in all_pocketbooks.items()}
        search_keys = []
        if mock_folder_key and mock_folder_key in all_pocketbooks:
            search_keys.append(mock_folder_key)
        if text_folder_key and text_folder_key in all_pocketbooks:
            search_keys.append(text_folder_key)

        # EBS 타입이 있으면 학년별 EBS 완성본 폴더도 검색
        # 고1: 올림포스(고1) — config의 "올림포스" 키로 매핑됨
        # 고2: 리딩파워(고2)
        # 분석본 카테고리에 "리딩파워"가 있으면 학년 무관하게 리딩파워 폴더 검색
        file_types_set = set(content.get("file_types", []))
        all_cats_str = " ".join(content.get("categories", []))
        if "ebs" in file_types_set:
            if "올림" in all_cats_str or "올포" in all_cats_str:
                if "올림포스" in all_pocketbooks:
                    search_keys.append("올림포스")
            if "리딩파워" in all_cats_str or "리파" in all_cats_str:
                rp_key = f"리딩파워(고{grade_num})" if grade_num else ""
                if rp_key and rp_key in all_pocketbooks:
                    search_keys.append(rp_key)

        for key in search_keys:
            _collect_completed(all_pocketbooks[key], recursive=True)

        if completed_files:
            log(f"[완성본] {len(completed_files)}개 발견 ({', '.join(search_keys)})")

        # 카테고리 매칭 (원본 경로 기준)
        analysis_files = content.get("analysis_files", [])
        file_categories = content.get("categories", [])
        copy_sources = []
        new_analysis = []
        new_file_types = []
        new_categories = []

        for idx, af in enumerate(analysis_files):
            cat = file_categories[idx] if idx < len(file_categories) else ""
            ft = content.get("file_types", [])[idx] if idx < len(content.get("file_types", [])) else "textbook"
            expanded = self._expand_category(cat)
            matches = self._match_categories_to_files(expanded, completed_files)
            matched_cats = {m["category"] for m in matches}
            unmatched = [c for c in expanded if c not in matched_cats]

            # 모든 타입: copy_sources 대신 pno_lookup_files로 passageNo 단위 복사
            if matches:
                for m in matches:
                    log(f"  [매칭] {m['category']} -> pno 단위 복사 예정")

            # 분석본은 항상 new_analysis에 포함 (매칭 여부 무관)
            # run.jsx에서 passageNo 단위로 중복 스킵하므로,
            # 완성본에 없는 지문만 새로 조판됨
            new_analysis.append(af)
            new_file_types.append(ft)
            # 카테고리는 항상 원본 유지: 매칭된 강을 빼버리면 run.jsx의 복사 경로
            # 트리거(카테고리 내 "올림"/"올포" 등)가 사라져 완성본에 있는 지문까지
            # 전부 신규 조판된다. (예: "올림포스15,16,17,18강,미래앤3,4과DL"에서
            # 15~18강이 매칭되면 "미래앤3,4과DL"만 남아 올림포스 복사가 죽음)
            # 복사 여부는 run.jsx가 passageNo로 판단하므로 원본 유지가 안전하다.
            new_categories.append(cat)
            if unmatched and len(unmatched) != len(expanded):
                log(f"  [부분매칭] {os.path.basename(af)}: 완성본 {len(matched_cats)}개 + 신규 {','.join(unmatched)}")

        # 같은 파일에 매칭된 카테고리 그룹화 (범위 파일 중복 복제 방지)
        grouped_sources = {}
        for cs in copy_sources:
            fpath = cs["file"]
            if fpath not in grouped_sources:
                grouped_sources[fpath] = {
                    "file": fpath,
                    "categories": [],
                    "needed_lessons": [],
                    "analysis_idx": cs.get("analysis_idx", 0),
                }
            grouped_sources[fpath]["categories"].append(cs["category"])
            if cs.get("lesson") is not None:
                grouped_sources[fpath]["needed_lessons"].append(cs["lesson"])
            # 가장 빠른 분석본 순서 유지
            aidx = cs.get("analysis_idx", 0)
            if aidx < grouped_sources[fpath]["analysis_idx"]:
                grouped_sources[fpath]["analysis_idx"] = aidx
        copy_sources = list(grouped_sources.values())
        for cs in copy_sources:
            cs["category"] = ",".join(cs["categories"])
            del cs["categories"]

        # 매칭된 파일만 로컬 복사 (구글드라이브 → 로컬)
        gdrive_markers = ("GoogleDrive", "Google Drive", "CloudStorage")
        local_copy_dir = os.path.join(jsx_work_dir, "completed_local")
        for cs in copy_sources:
            src_path = cs["file"]
            if any(m in src_path for m in gdrive_markers):
                os.makedirs(local_copy_dir, exist_ok=True)
                dst = os.path.join(local_copy_dir, os.path.basename(src_path))
                if not os.path.exists(dst):
                    log(f"  [복사] {os.path.basename(src_path)}")
                    self._gdrive_cp(src_path, dst)
                cs["file"] = dst  # settings.json에 로컬 경로 전달

        # (개별 passageNo 매칭용 completed_files 복사 제거 — 카테고리 매칭으로 충분)

        # 리뷰테스트 자동 탐색 (카테고리 기반)
        all_categories = content.get("categories", [])
        all_file_types = content.get("file_types", [])
        all_analysis = content.get("analysis_files", [])
        review_test_map, missing_tb_cats = self._discover_review_tests(
            all_categories, all_file_types, grade, job_dir, log, semester, all_analysis
        )

        # 리뷰테스트 포함인데 교과서 리뷰테스트 파일 못 찾으면 에러
        # (단, 사용자가 직접 업로드한 memtest가 있으면 허용)
        include_review_test = self._get_meta(job_dir, "include_review_test_flag", "1") == "1"
        has_uploaded_memtest = len(content.get("memtest", [])) > 0
        if include_review_test and missing_tb_cats and not has_uploaded_memtest:
            cats_str = ", ".join(missing_tb_cats)
            raise RuntimeError(
                f"교과서 리뷰테스트 해설지를 찾을 수 없습니다: {cats_str}\n"
                f"리뷰테스트 해설지(.docx)를 직접 업로드하거나, "
                f"리뷰테스트 포함을 해제해 주세요."
            )

        # 고2 올포 → 모의고사 리뷰테스트 전체 수집
        # 올포 카테고리("올포14강")로는 모의고사 년월을 모르므로,
        # 모의고사 작업 폴더의 모든 년월 리뷰테스트를 미리 수집해서
        # run.jsx에서 passageNo 기반(YYMM)으로 매칭하도록 함
        if grade_num == "2" and any(ft == "mockexam" for ft in all_file_types):
            # 원본 카테고리에 올포/올림이 있었는지 확인 (ebs→mockexam 변환된 것)
            orig_categories = content.get("categories", [])
            has_olpo = any("올포" in unicodedata.normalize("NFC", c) or "올림" in unicodedata.normalize("NFC", c) for c in orig_categories if c)
            if has_olpo:
                rt_base = cfg.get("review_test_base", "")
                mock_base = os.path.join(rt_base, "모의고사 작업", grade) if rt_base else ""
                if mock_base and os.path.isdir(mock_base):
                    from engines.pocketbook.parser import parse_review_test
                    added_count = 0
                    for raw in os.listdir(mock_base):
                        nfc_raw = unicodedata.normalize("NFC", raw)
                        ym_m = re.search(r"(\d{2})년?\s*(\d{1,2})월", nfc_raw)
                        if not ym_m:
                            continue
                        rt_key = ym_m.group(1) + ym_m.group(2).zfill(2)
                        if rt_key in review_test_map:
                            continue
                        # 리뷰테스트 해설지 탐색
                        full_dir = os.path.join(mock_base, raw)
                        if not os.path.isdir(full_dir):
                            continue
                        dirs_to_check = [full_dir]
                        for sub in os.listdir(full_dir):
                            sub_full = os.path.join(full_dir, sub)
                            nfc_sub = unicodedata.normalize("NFC", sub)
                            if os.path.isdir(sub_full) and ("리뷰" in nfc_sub or "리테" in nfc_sub):
                                dirs_to_check.insert(0, sub_full)
                        found_docx = None
                        for d in dirs_to_check:
                            nfc_dirname = unicodedata.normalize("NFC", os.path.basename(d))
                            is_rt_dir = ("리뷰" in nfc_dirname or "리테" in nfc_dirname)
                            try:
                                files = [unicodedata.normalize("NFC", f) for f in os.listdir(d)]
                            except Exception:
                                continue
                            for keyword in ["해설지", "정답지"]:
                                for nfc_f in files:
                                    if nfc_f.startswith("~$") or not nfc_f.endswith(".docx"):
                                        continue
                                    if keyword not in nfc_f:
                                        continue
                                    if is_rt_dir or "리뷰" in nfc_f or "리테" in nfc_f:
                                        found_docx = os.path.join(d, nfc_f)
                                        break
                                if found_docx:
                                    break
                            if found_docx:
                                break
                        if not found_docx:
                            review_test_map[rt_key] = {"passages": []}
                            continue
                        # 구글드라이브 복사 후 파싱
                        gdrive_markers_rt = ("GoogleDrive", "Google Drive", "CloudStorage")
                        parse_path = found_docx
                        if any(m in found_docx for m in gdrive_markers_rt):
                            local_rt_dir = os.path.join(job_dir, "review_test_local")
                            os.makedirs(local_rt_dir, exist_ok=True)
                            local_copy = os.path.join(local_rt_dir, os.path.basename(found_docx))
                            if not os.path.exists(local_copy):
                                try:
                                    self._gdrive_cp(found_docx, local_copy)
                                except Exception:
                                    review_test_map[rt_key] = {"passages": []}
                                    continue
                            parse_path = local_copy
                        try:
                            rt_result = parse_review_test(parse_path)
                            rt_passages = []
                            for rp in rt_result.get("passages", []):
                                rt_passages.append({
                                    "header": rp["header"],
                                    "answer_text": "\r".join(rp["lines_answer"]),
                                    "blank_text": "\r".join(rp["lines_blank"]),
                                    "word_count": rp["word_count"],
                                })
                            review_test_map[rt_key] = {"passages": rt_passages}
                            added_count += 1
                        except Exception as e:
                            log(f"  [올포 리테] {rt_key} 파싱 실패: {e}")
                            review_test_map[rt_key] = {"passages": []}
                    if added_count > 0:
                        log(f"[올포 리테] 모의고사 리뷰테스트 {added_count}개 년월 추가 수집")

        # output도 /tmp에서 작업 (iCloud/한글 경로 회피)
        tmp_output_path = os.path.join(jsx_work_dir, indd_name)
        # 최종 복사 대상 경로 기록 (verify에서 사용)
        with open(os.path.join(job_dir, ".final_output_path"), "w") as f:
            f.write(output_path)

        # 모든 .indd 파일을 /tmp로 복사 (ExtendScript iCloud/한글 경로 회피)
        indd_local_dir = os.path.join(jsx_work_dir, "indd")
        os.makedirs(indd_local_dir, exist_ok=True)

        def _to_tmp(src):
            """iCloud/한글 경로의 .indd를 /tmp로 복사. 이미 /tmp면 그대로."""
            if not src or not os.path.exists(src):
                return src
            if src.startswith("/tmp/"):
                return src
            dst = os.path.join(indd_local_dir, os.path.basename(src))
            if not os.path.exists(dst):
                if any(m in src for m in gdrive_markers):
                    self._gdrive_cp(src, dst)
                else:
                    safe_copy(src, dst)
            return dst

        tmp_analysis = [_to_tmp(f) for f in new_analysis]

        # passageNo 기반 완성본 검색용 파일 목록 생성 (모든 타입)
        pno_lookup_files = []
        pno_lookup_seen = set()

        def _add_pno_lookup(src_path, ym_key):
            """완성본 파일을 영문 파일명으로 /tmp에 복사하고 pno_lookup에 추가."""
            if ym_key in pno_lookup_seen:
                return
            pno_lookup_seen.add(ym_key)
            # ExtendScript 한글 파일명 회피: 인덱스 기반 영문 파일명
            eng_name = f"pno_lookup_{len(pno_lookup_seen):03d}.indd"
            eng_dst = os.path.join(indd_local_dir, eng_name)
            if not os.path.exists(eng_dst):
                if any(m in src_path for m in gdrive_markers):
                    self._gdrive_cp(src_path, eng_dst)
                else:
                    safe_copy(src_path, eng_dst)
            pno_lookup_files.append({"file": eng_dst, "ym": ym_key})

        def _olympos_book_ok(nfc_name):
            """올림포스 완성본은 학기에 맞는 독해기본N '포켓북'만 사용 (책 혼입 방지).
            책 구분이 없는 파일(교과서/모의고사 등)은 그대로 통과."""
            if not olympos_book:
                return True
            bm = re.search(r"독해기본\s*(\d)", nfc_name)
            if not bm:
                return True
            # 올림포스 파일: 학기에 맞는 책 + 실제 포켓북 파일만 (analysis/원본 제외)
            if ("독해기본" + bm.group(1)) != olympos_book:
                return False
            return "포켓북" in nfc_name

        # 모든 완성본 폴더에서 파일 수집
        for key in search_keys:
            folder = all_pocketbooks.get(key, "")
            if not folder or not os.path.isdir(folder):
                continue
            for fn in os.listdir(folder):
                nfc = unicodedata.normalize("NFC", fn)
                if not nfc.endswith(".indd") or "분석본" in nfc or "작업전" in nfc:
                    continue
                if not _olympos_book_ok(nfc):
                    continue
                src_path = os.path.join(folder, fn)
                # 파일명에서 식별자 추출
                # 모의고사: (YY년M월) 또는 (YY월M월) 등 → YYMM
                ym_match = re.search(r"\((\d{2})\D+(\d{1,2})월\)", nfc)
                if ym_match:
                    yy = ym_match.group(1)
                    mm = ym_match.group(2).zfill(2)
                    _add_pno_lookup(src_path, yy + mm)
                    continue
                # 교과서/EBS: 괄호 안 카테고리 → 그대로 키
                cat_match = re.search(r"\(([^)]+)\)", nfc)
                if cat_match:
                    _add_pno_lookup(src_path, cat_match.group(1))

        # 하위 폴더 재귀 탐색 (교과서 폴더에 서브폴더 있을 수 있음)
        for key in search_keys:
            folder = all_pocketbooks.get(key, "")
            if not folder or not os.path.isdir(folder):
                continue
            for sub in os.listdir(folder):
                sub_path = os.path.join(folder, sub)
                nfc_sub = unicodedata.normalize("NFC", sub)
                if not os.path.isdir(sub_path) or nfc_sub == "기존" or nfc_sub.startswith("기존"):
                    continue
                for fn in os.listdir(sub_path):
                    nfc = unicodedata.normalize("NFC", fn)
                    if not nfc.endswith(".indd") or "분석본" in nfc or "작업전" in nfc:
                        continue
                    if not _olympos_book_ok(nfc):
                        continue
                    src_path = os.path.join(sub_path, fn)
                    ym_match = re.search(r"\((\d{2})\D+(\d{1,2})월\)", nfc)
                    if ym_match:
                        _add_pno_lookup(src_path, ym_match.group(1) + ym_match.group(2).zfill(2))
                        continue
                    cat_match = re.search(r"\(([^)]+)\)", nfc)
                    if cat_match:
                        _add_pno_lookup(src_path, cat_match.group(1))

        if pno_lookup_files:
            log(f"[완성본] passageNo 검색용 {len(pno_lookup_files)}개 준비")

        tmp_copy_sources = []
        for cs in copy_sources:
            entry = {
                "category": cs["category"],
                "file": _to_tmp(cs["file"]),
                "analysis_idx": cs.get("analysis_idx", 0),
            }
            if cs.get("needed_lessons"):
                entry["needed_lessons"] = cs["needed_lessons"]
            tmp_copy_sources.append(entry)

        log(f"[복사] .indd 파일 {len(tmp_analysis) + len(tmp_copy_sources)}개 → /tmp")

        # 리뷰테스트 포함 여부 (기본값: 포함)
        include_review_test = self._get_meta(job_dir, "include_review_test_flag", "1") == "1"
        if not include_review_test:
            log("[설정] 리뷰테스트 제외 모드")

        # settings.json -- run.jsx가 읽을 설정
        settings = {
            "template_path": template_path,
            "output_path": tmp_output_path,
            "output_dir": jsx_work_dir,
            "copy_sources": tmp_copy_sources,
            "analysis_files": tmp_analysis,
            "file_types": new_file_types,
            "categories": new_categories,
            "memtest": content.get("memtest", []) if include_review_test else [],
            "review_test_map": self._sync_rt_map_keys(review_test_map, all_categories, new_categories) if include_review_test else {},
            "include_review_test": include_review_test,
            "illustrations_base": illustrations_base,
            "grade": grade,
            "completed_files": [],  # 개별 passageNo 매칭 제거됨
            "pno_lookup_files": pno_lookup_files,
            "first_page_image": cfg.get("first_page_image", ""),
            "last_page_image": cfg.get("last_page_image", ""),
            "listening_text_file": content.get("listening_text_file", ""),
        }

        # settings.json -- /tmp에 저장 (ExtendScript 한글 경로 회피)
        settings_path = os.path.join(jsx_work_dir, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False)
        # job_dir에도 사본 보관 (디버그용)
        with open(os.path.join(job_dir, ".settings.json"), "w", encoding="utf-8") as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)

        log(f"[설정] {indd_name}")
        copy_count = len(copy_sources)
        new_count = len(new_analysis)
        log(f"[설정] 복제 {copy_count}개 + 신규 {new_count}개 + 암기테스트 {len(settings['memtest'])}개")

        # run.jsx — /tmp에 저장 (ExtendScript 한글 경로 회피)
        with open(_JSX_TEMPLATE, encoding="utf-8") as f:
            jsx_src = f.read()
        jsx_final = jsx_src.replace(_SETTINGS_MARKER, settings_path)
        jsx_copy = os.path.join(jsx_work_dir, "run.jsx")
        with open(jsx_copy, "w", encoding="utf-8") as f:
            f.write(jsx_final)
        # job_dir에도 사본 보관 (디버그용)
        with open(os.path.join(job_dir, "run.jsx"), "w", encoding="utf-8") as f:
            f.write(jsx_final)

        return jsx_copy

    # ── 3단계: 검수 ──────────────────────────────────────────────────

    def verify(self, job_dir, log):
        import shutil as _shutil
        cfg = _load_config()
        log_filename = cfg["log_filename"]

        # /tmp 작업 경로 복원
        sp = os.path.join(job_dir, ".settings.json")
        tmp_output_dir = ""
        if os.path.exists(sp):
            with open(sp) as f:
                s = json.load(f)
            tmp_output_dir = s.get("output_dir", "")

        # 로그 파일: /tmp 쪽 먼저, 없으면 job_dir
        log_path = os.path.join(tmp_output_dir, log_filename) if tmp_output_dir else ""
        if not log_path or not os.path.exists(log_path):
            log_path = os.path.join(job_dir, log_filename)

        # /tmp 로그를 job_dir에도 복사 (디버그용)
        if tmp_output_dir and os.path.exists(os.path.join(tmp_output_dir, log_filename)):
            safe_copy(os.path.join(tmp_output_dir, log_filename),
                          os.path.join(job_dir, log_filename))

        content = {}
        cp = os.path.join(job_dir, "content.json")
        if os.path.exists(cp):
            with open(cp, encoding="utf-8") as f:
                content = json.load(f)

        total_files = content.get("total_files", 0)
        total_memtest = content.get("total_memtest", 0)

        warnings = []
        overflow = 0
        pdf_path = None
        total_passages = 0
        passage_list = []   # 실제 수록된 지문번호 목록 (순서 보존)

        if os.path.exists(log_path):
            lc = open(log_path, encoding="utf-8", errors="ignore").read()

            # 오버플로우
            m = re.search(r"오버플로우:\s*(\d+)개", lc)
            if m:
                overflow = int(m.group(1))

            # 총 지문 수
            m = re.search(r"총\s*(\d+)개\s*완료", lc)
            if m:
                total_passages = int(m.group(1))

            # 실제 수록된 지문번호 목록
            # run.jsx가 지문마다 찍는 "[pno] <번호>" / "[pno복사] <번호>" 로그를 수집.
            # (신규 조판·pno 복사·완성본 레슨 복사 모두 동일 마커로 기록됨)
            # 순서 보존 + 중복 제거, "(+리뷰)" 같은 접미사 제거.
            _seen_pno = set()
            for _label in re.findall(r"\[pno(?:복사)?\]\s*([^\n\r]+)", lc):
                _lab = re.sub(r"\s*\(\+리뷰\)\s*$", "", _label).strip()
                if _lab and _lab not in _seen_pno:
                    _seen_pno.add(_lab)
                    passage_list.append(_lab)
            # 로그에서 집계한 실제 개수가 있으면 그것을 지문 수로 사용
            # (기존 "총 N개 완료" 문장은 run.jsx가 찍지 않아 항상 0이던 버그 보정)
            if passage_list:
                total_passages = len(passage_list)

            # PDF: /tmp에서 최종 경로로 복사
            final_output = ""
            fop = os.path.join(job_dir, ".final_output_path")
            if os.path.exists(fop):
                final_output = open(fop).read().strip()

            if "PDF:" in lc and "성공" in lc and tmp_output_dir:
                # /tmp의 indd/pdf를 최종 경로로 복사
                for ext in [".indd", ".pdf"]:
                    tmp_candidate = s.get("output_path", "").replace(".indd", ext) if ext == ".pdf" else s.get("output_path", "")
                    final_candidate = final_output.replace(".indd", ext) if ext == ".pdf" else final_output
                    if tmp_candidate and os.path.exists(tmp_candidate) and final_candidate:
                        os.makedirs(os.path.dirname(final_candidate), exist_ok=True)
                        safe_copy(tmp_candidate, final_candidate)
                        if ext == ".pdf":
                            pdf_path = final_candidate
                # /tmp pdf 폴백
                if not pdf_path:
                    tmp_pdf = s.get("output_path", "").replace(".indd", ".pdf")
                    if os.path.exists(tmp_pdf):
                        pdf_path = tmp_pdf
            elif "PDF:" in lc and "성공" in lc:
                if os.path.exists(sp):
                    with open(sp) as f:
                        s = json.load(f)
                    candidate = s.get("output_path", "").replace(".indd", ".pdf")
                    if os.path.exists(candidate):
                        pdf_path = candidate

            if overflow > 0:
                warnings.append(f"오버플로우 {overflow}개 — 수동 확인 필요")
            if "PDF: 실패" in lc:
                warnings.append("PDF 내보내기 실패")

        ok = pdf_path is not None and overflow == 0 and not warnings

        # 조교 공유 폴더(ASSISTANT_SHARE_DIR)로 .indd가 넘어가도록 경로 노출.
        # 다른 엔진은 verify result에 indd_path를 넣지만 포켓북만 빠져 있어,
        # 공유 worker가 복사할 파일을 못 찾고 카테고리 폴더만 생성되던 문제 수정.
        # 포켓북 결과물은 job_dir 밖 최종 경로(/조판/교재/포켓북/)에 있음. PDF는 공유 제외.
        indd_out = None
        _fop = os.path.join(job_dir, ".final_output_path")
        if os.path.exists(_fop):
            _cand = open(_fop, encoding="utf-8").read().strip()
            if _cand and os.path.exists(_cand):
                indd_out = _cand

        result = {
            "ok": ok,
            "overflow": overflow,
            "stories": {
                "지문": {"actual": total_passages, "expected": total_passages},
            },
            "passages": passage_list,
            "pdf_path": pdf_path,
            "indd_path": indd_out,
            "warnings": warnings,
            "grade_label": f"분석본 {total_files}개 → 지문 {total_passages}개",
        }

        status = "완료" if ok else f"확인 필요 ({len(warnings)}건)"
        log(f"[검수] {status}")
        return result
