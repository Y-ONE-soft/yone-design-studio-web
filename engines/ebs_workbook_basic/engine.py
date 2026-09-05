"""리딩파워 유형편(기본) 원고 수집 엔진 — EbsWorkbookEngine 상속.

완성 시리즈(engines/ebs_workbook)와 다른 점은 딱 둘, 둘 다 훅으로 표현:
  1. CONFIG_PATH        — 기본 시리즈 config (fixed_series/내지/스텝 맵)
  2. 단원 폴더 구조      — 완성은 단원 폴더 자신이 원고 폴더
     ('Unit 15 워크북/Step1 …'), 기본은 단원 폴더 **아래** '워크북'
     폴더가 원고 폴더 ('Unit 20 Example, 1, 2/Unit 20 Example, 1, 2
     워크북/Step1 …' · 'Unit 10 Practice 3, 4/워크북/Step1 …' — 실물
     GDrive 두 표기 모두 존재).

조판(prepare_jsx)은 상속받은 완성용 EBS 스토리 맵을 그대로 쓰면 내지가
어긋나므로 **이 v1 엔진은 registry에 등록하지 않는다** — 원고 수집(parse)
과 폴더 탐색 API 전용이고, 조판은 v2(EbsWorkbookBasicV2Engine)가 세종
워크북 내지 플랜으로 수행한다.
"""
import os
import re
import unicodedata

from engines.ebs_workbook.engine import EbsWorkbookEngine

_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_DIR, "config.json")

# 단원 폴더 아래에서 원고 폴더로 인정할 이름 (실물: '워크북',
# '<단원명> 워크북'). 이름이 아니라 '워크북으로 끝나는 폴더' 구조로 본다 —
# 토씨가 바뀌어도 잡히게 (원고 파서 구조판정 원칙과 같은 이유).
_RE_WORKBOOK_DIR = re.compile(r"워크북\s*$")


def _nfc(s):
    return unicodedata.normalize("NFC", s)


class EbsWorkbookBasicEngine(EbsWorkbookEngine):

    CONFIG_PATH = _CONFIG_PATH

    @property
    def material_id(self) -> str:
        return "ebs_workbook_basic"

    @property
    def display_name(self) -> str:
        return "리딩파워(기본) 워크북"

    @property
    def description(self) -> str:
        return "EBS 리딩파워(유형편 기본) 워크북 원고 수집"

    @property
    def subject_prefix(self) -> str:
        return "리딩파워기본워크북"

    # ── 원고 이름 방언 ──────────────────────────────────────────────────

    @classmethod
    def _is_step3_manuscript(cls, name_nfc: str) -> bool:
        """기본 시리즈의 Step3 원고는 'Step3.hwpx'만이 아니다 — 실물에
        '리딩파워 변형문제 발췌 Unit 09 (Practice 3·4).docx'처럼 Step3
        토큰이 없는 변형문제 모음이 단원 폴더에 그냥 놓여 있다
        (Unit 9 실측). 이름 규칙 대신 v2 공용 라우터의 변형문제 토큰까지
        인정한다 — 안 그러면 STEP3 원고가 조용히 유실된다.
        """
        from engines.workbook_v2.routing import RE_VARIANT_POOL
        return (EbsWorkbookEngine._is_step3_manuscript(name_nfc)
                or bool(RE_VARIANT_POOL.search(_nfc(name_nfc))))

    # ── 단원 폴더 구조 ──────────────────────────────────────────────────

    @classmethod
    def _resolve_workbook_dir(cls, unit_path: str) -> str:
        """단원 폴더 → 그 아래 '워크북' 폴더 (없으면 단원 폴더 자신).

        미러 ∪ GDrive 합집합으로 본다 — 미러 단독 listdir 금지
        (2026-08-07 사고). 실측: 미러에 'Unit 10 Practice 3, 4'가 빈
        폴더로 남아 있어 미러만 보면 워크북 원고가 통째로 사라진다.
        """
        from engines.final.extractor import list_manuscript_entries
        try:
            entries = list_manuscript_entries(unit_path, None)
        except OSError:
            return unit_path
        for name, src in sorted(entries):
            if name.startswith(".") or not _RE_WORKBOOK_DIR.search(_nfc(name)):
                continue
            # **목록은 GDrive(정본)에서** — list_manuscript_entries가 주는
            # src는 같은 이름이 미러에 있으면 미러 경로다. 그 경로를 그대로
            # 돌려주면 이 폴더를 listdir하는 쪽(list_files/파서)이 30분 주기
            # 스냅샷을 정본으로 착각한다. 실제 사고: 미러 동기화가 도중이라
            # 'Unit 10 …/워크북'에 Step3와 .rsync-partial만 들어와 있어
            # 원고 19개가 통째로 '없음'으로 보였다 (2026-09-05).
            # 미러 경로는 GDrive를 못 읽을 때(좀비 Drive)만 폴백으로 쓴다.
            gdrive = os.path.join(unit_path, name)
            if os.path.isdir(gdrive):
                return gdrive
            if os.path.isdir(src):
                return src
        return unit_path

    @classmethod
    def list_units(cls):
        """기본 시리즈의 단원 목록 — '워크북' 하위폴더를 가진 폴더만.

        완성 시리즈는 폴더 **이름**에 '워크북'이 있는지로 걸렀지만(부모가
        곧 원고 폴더), 기본은 단원 폴더 이름에 '워크북'이 없다
        ('Unit 20 Example, 1, 2'). 이름 규칙 대신 **구조**(워크북 하위폴더
        보유)로 판정한다.
        """
        cfg = cls._cfg()
        base = cls._series_path()
        # 미러 ∪ GDrive 합집합 — 미러 단독 listdir 금지 (2026-08-07 사고).
        from engines.final.extractor import list_manuscript_entries
        excludes = set(cfg.get("exclude_folders", []))

        def _unit_sort_key(folder):
            nums = [int(n) for n in re.findall(r"\d+", folder)]
            return (nums[0] if nums else 9999, folder)

        result = []
        for name, full in list_manuscript_entries(base, None):
            stripped = _nfc(name).strip()
            if stripped.startswith(".") or stripped in excludes:
                continue
            if not os.path.isdir(full):
                continue
            # 하위 탐색은 **GDrive 경로**로 — entries의 src는 미러일 수
            # 있고, 미러가 stale이면 워크북 폴더를 못 본다 (실측 Unit 10).
            # 경로에는 **실제 폴더명 그대로** 쓴다 (trim 금지 — 실물에
            # 'Unit 19 Example, 1, 2 '처럼 끝에 공백이 붙은 폴더가 있다).
            unit_gdrive = os.path.join(base, _nfc(name))
            if cls._resolve_workbook_dir(unit_gdrive) == unit_gdrive:
                continue        # 워크북 폴더가 없는 단원 (원고 미작업)
            result.append({"folder": _nfc(name), "label": stripped})
        result.sort(key=lambda x: _unit_sort_key(x["folder"]))
        return result

    @staticmethod
    def unit_number(unit_label: str) -> str:
        """단원 라벨 → 강 번호 ('Unit 20 Example, 1, 2' → '20').

        파일명/간지의 '리딩파워N강' 표기에 쓴다. Chapter 표기가 앞에 붙는
        폴더('Chapter1 Unit1 Practice 3,4')가 있어 'Unit' 뒤 숫자를 본다.
        """
        m = re.search(r"Unit\s*\.?\s*(\d+)", _nfc(unit_label), re.I)
        if m:
            return m.group(1)
        m = re.search(r"\d+", _nfc(unit_label))
        return m.group() if m else ""
