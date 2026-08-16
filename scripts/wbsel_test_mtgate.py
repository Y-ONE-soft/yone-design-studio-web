# -*- coding: utf-8 -*-
"""선택 워크북 — 마더텅 라벨링 게이트 / 보충원고 자동탐색 / fill 하드코딩 회귀 검사.

InDesign·GDrive 원고 복사 없이 engine.parse 의 **앞단(코드 조달·라벨·정렬·
보충원고 선택)** 만 검사한다. 원고 파싱과 병합은 스텁으로 갈아끼운다.

막으려는 사고 (2026-08-13 실측):
  강 번호를 넣지 않은 일반 모의고사 결합 job 인데도 마더텅 엑셀을 조회해,
  231133·240632·250620 이 마더텅 2·6·17 로 라벨되고 순서까지 재정렬됐다.
  마더텅 출처 코드 224개는 일반 기출 코드와 같은 번호라 반드시 일어난다.

사용: python3 scripts/wbsel_test_mtgate.py      (종료코드 0 = 전부 통과)
"""
import json
import os
import shutil
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_ENV = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV):
    for _line in open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from engines.workbook_select import engine as eng_mod        # noqa: E402
from engines.workbook_select.engine import WorkbookSelectEngine  # noqa: E402

# 엑셀 실측: 231133→11강 2번, 240632→11강 6번, 250620→**3강** 17번.
# 이 순서로 넣으면 옛 코드(게이트 없음)는 2·6·17 로 재정렬해 입력 순서를
# 뒤집는다 — 게이트가 살아 있으면 입력 순서 그대로여야 한다.
_MT_CODES = "250620,231133,240632"
_MT_CODES_G11 = ["231133", "240632"]      # 그중 11강에 속하는 것

_results = []


def _check(name, ok, detail=""):
    _results.append((name, ok, detail))
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name,
                        ("  — " + detail) if detail else ""))


class _Stop(Exception):
    """merge 직전에 parse 를 세우고 (codes, labels) 를 꺼내온다."""

    def __init__(self, codes, labels):
        self.codes, self.labels = codes, labels


def _run_parse(codes_text="", gang="", grade="고1"):
    """parse 를 merge 직전까지 돌린다 → (codes, labels, log 줄, 엑셀 조회 횟수)"""
    job = tempfile.mkdtemp(prefix="wbsel_gate_")
    with open(os.path.join(job, "grade.txt"), "w", encoding="utf-8") as f:
        f.write(grade)

    lines = []
    hits = {"load_index": 0, "codes_for_gang": 0}

    orig = {
        "load_index": eng_mod._mt.load_index,
        "codes_for_gang": eng_mod._mt.codes_for_gang,
        "find_ms": WorkbookSelectEngine._find_manuscript_dir,
        "copy_ms": WorkbookSelectEngine._copy_manuscripts,
        "parse_folder": eng_mod.parse_manuscript_folder,
        "merge": eng_mod.merge_selected,
    }

    def _load_index(path, *a, **k):
        hits["load_index"] += 1
        return orig["load_index"](path, *a, **k)

    def _codes_for_gang(path, g, *a, **k):
        hits["codes_for_gang"] += 1
        return orig["codes_for_gang"](path, g, *a, **k)

    def _merge(sources, codes, log=None, labels=None, fill=None):
        raise _Stop(list(codes), dict(labels or {}))

    eng_mod._mt.load_index = _load_index
    eng_mod._mt.codes_for_gang = _codes_for_gang
    WorkbookSelectEngine._find_manuscript_dir = staticmethod(
        lambda base, gn, yy, mm: (os.path.join(job, "fake"), None))
    WorkbookSelectEngine._copy_manuscripts = staticmethod(
        lambda s, d, log: 0)
    eng_mod.parse_manuscript_folder = lambda *a, **k: {"steps": {}}
    eng_mod.merge_selected = _merge
    try:
        WorkbookSelectEngine().parse(
            {"codes": codes_text, "mt_gang": gang}, job, lines.append)
        raise AssertionError("merge 스텁이 호출되지 않았다")
    except _Stop as s:
        return s.codes, s.labels, lines, hits
    finally:
        eng_mod._mt.load_index = orig["load_index"]
        eng_mod._mt.codes_for_gang = orig["codes_for_gang"]
        WorkbookSelectEngine._find_manuscript_dir = staticmethod(
            orig["find_ms"].__func__ if hasattr(orig["find_ms"], "__func__")
            else orig["find_ms"])
        WorkbookSelectEngine._copy_manuscripts = staticmethod(
            orig["copy_ms"].__func__ if hasattr(orig["copy_ms"], "__func__")
            else orig["copy_ms"])
        eng_mod.parse_manuscript_folder = orig["parse_folder"]
        eng_mod.merge_selected = orig["merge"]
        shutil.rmtree(job, ignore_errors=True)


def test_gate_off():
    """강 번호 없는 job — 엑셀 미조회 · 라벨 없음 · 입력 순서 유지."""
    codes, labels, lines, hits = _run_parse(codes_text=_MT_CODES)
    want = _MT_CODES.split(",")
    _check("강 미지정: 입력 순서 유지 (재정렬 안 함)", codes == want,
           "기대 %s / 실제 %s" % (want, codes))
    _check("강 미지정: 마더텅 라벨 0건", not labels,
           "라벨 %s" % labels)
    _check("강 미지정: 엑셀 조회 0회", hits["load_index"] == 0,
           "load_index %d회" % hits["load_index"])


def test_gate_on():
    """강 번호를 넣은 job — 마더텅 번호로 라벨·정렬 (기존 기능 보존)."""
    codes, labels, lines, hits = _run_parse(codes_text=_MT_CODES, gang="11")
    _check("11강 지정: 11강 코드만 라벨됨",
           sorted(labels) == _MT_CODES_G11, "라벨 %s" % labels)
    _check("11강 지정: 타 강(250620) 라벨 안 붙음",
           "250620" not in labels, "라벨 %s" % labels)
    if labels:
        nums = [int(labels[c]) for c in codes if c in labels]
        _check("11강 지정: 번호 오름차순 정렬", nums == sorted(nums),
               "번호 %s" % nums)
    _check("11강 지정: 엑셀 조회함", hits["load_index"] >= 1)


def test_gang_only():
    """코드 없이 강 번호만 — 엑셀에서 코드 조달 (기존 기능 보존)."""
    codes, labels, lines, hits = _run_parse(gang="11")
    _check("11강만 입력: 코드 조달됨", len(codes) >= 10,
           "%d개" % len(codes))
    _check("11강만 입력: 라벨 = 코드 수", len(labels) == len(codes),
           "라벨 %d / 코드 %d" % (len(labels), len(codes)))


def test_no_input():
    """코드도 강도 없으면 명확히 실패해야 한다."""
    try:
        _run_parse()
        _check("입력 없음: ValueError", False, "예외가 안 났다")
    except ValueError as e:
        _check("입력 없음: ValueError", True, str(e)[:40])
    except Exception as e:                                  # noqa: BLE001
        _check("입력 없음: ValueError", False,
               "%s: %s" % (type(e).__name__, e))


def test_supplement_lookup():
    """마더텅 N강 워크북 폴더 자동 탐색 — 로컬 하드코딩 없이 GDrive 에서."""
    cfg = eng_mod._load_config()
    base = cfg["manuscript_base"]
    dirs, err = WorkbookSelectEngine._find_gang_manuscript_dirs(base, "1", 11)
    _check("11강 워크북 폴더 자동탐색", bool(dirs), err or (dirs and dirs[0]))
    if dirs:
        names = set()
        for raw in os.listdir(dirs[0]):
            names.add(eng_mod._nfc(raw))
        has_a1 = any(n.startswith("Step1 A1") for n in names)
        has_step3 = any(n.startswith("Step3") for n in names)
        _check("11강 워크북에 Step1 A1 어휘선택 있음", has_a1,
               "파일 %d개" % len(names))
        _check("11강 워크북에 Step3 있음", has_step3)
    for g in (3, 13, 15):
        d, e = WorkbookSelectEngine._find_gang_manuscript_dirs(base, "1", g)
        _check("%d강 워크북 폴더 자동탐색" % g, bool(d), e or "")
    d, e = WorkbookSelectEngine._find_gang_manuscript_dirs(base, "1", 99)
    _check("없는 강(99)은 사유와 함께 실패", not d and bool(e), e or "")


def test_config_clean():
    """config 에 강/파일 하드코딩이 남아 있지 않아야 한다."""
    raw = json.load(open(os.path.join(
        _ROOT, "engines", "workbook_select", "config.json"), encoding="utf-8"))
    _check("config 에 mt_gang 기본값 없음", not raw.get("mt_gang"),
           "mt_gang=%r" % raw.get("mt_gang"))
    _check("config 에 fill_json 하드코딩 없음", not raw.get("fill_json"),
           "fill_json=%r" % raw.get("fill_json"))
    _check("config 에 supplement_dir 로컬 하드코딩 없음",
           not raw.get("supplement_dir"),
           "supplement_dir=%r" % raw.get("supplement_dir"))


def main():
    test_config_clean()
    test_gate_off()
    test_gate_on()
    test_gang_only()
    test_no_input()
    test_supplement_lookup()
    bad = [n for n, ok, _ in _results if not ok]
    print("\n%d/%d 통과" % (len(_results) - len(bad), len(_results)))
    if bad:
        print("실패: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
