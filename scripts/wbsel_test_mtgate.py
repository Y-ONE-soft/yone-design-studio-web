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
    """코드 조달 단계에서 실패를 잡아내기 위한 표식 (입력 없음 검사용)."""


def _run_parse(codes_text="", gang="", grade="고1"):
    """parse 를 끝까지 돌린다 (원고 파싱·병합만 스텁).

    → (조판 순서 코드, {코드: 최종 표기}, log 줄, 엑셀 조회 횟수)

    병합을 스텁으로 갈되 **라벨 경로는 진짜를 태운다** — 스텁이 코드마다
    `[코드]` 마커 단락을 만들고, parse 의 마지막 단계인 _apply_final_labels
    가 그것을 최종 표기로 바꾼다. 즉 이 테스트는 "무엇을 merge 에
    넘겼는가"가 아니라 **산출물에 실제로 찍힌 표기**를 본다."""
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

    order = {}

    def _merge(sources, codes, log=None, labels=None, fill=None):
        order["codes"] = list(codes)
        paras = []
        for c in codes:
            paras.append({"text": "[%s]" % c,
                          "runs": [{"t": "[%s]" % c, "ul": False}]})
            paras.append({"text": "Body text for %s." % c,
                          "runs": [{"t": "Body.", "ul": False}]})
        return ({"steps": {"step1_a1": {"paragraphs": paras}}}, {}, [])

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
        out = json.load(open(os.path.join(job, "content.json"),
                             encoding="utf-8"))
        marks = [p["text"][1:-1]
                 for p in out["steps"]["step1_a1"]["paragraphs"]
                 if p["text"].startswith("[")]
        codes_in_order = order.get("codes") or []
        printed = dict(zip(codes_in_order, marks))
        # 코드가 그대로 찍혔으면 "표기 안 바뀜" — 라벨 없음으로 본다
        labels = {c: v for c, v in printed.items() if v != c}
        return codes_in_order, labels, lines, hits
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


def _para(t):
    return {"text": t, "runs": [{"t": t, "ul": False}]}


def test_final_labels():
    """지문번호 표기는 **마지막 단계에서만** 바뀐다 + 프레임 라벨이 항상 채워진다.

    막으려는 것 ①: 마더텅 번호가 병합·검수 중간 단계에 섞여 원고 대조가 깨짐
    막으려는 것 ②: `_passage_labels` 가 비면 passage_numbers op 이 스킵돼
                   프레임에 템플릿 잔재 번호(20·21·22…)가 그대로 인쇄됨
                   (2026-08-17 실측: 단일 회차 job 250620·250631·250632)
    """
    eng = WorkbookSelectEngine()
    lines = []

    def mk():
        return {"steps": {
            "step1_a1": {"paragraphs": [
                _para("[161131]"), _para("Some English body text here."),
                _para("[240632]"), _para("More body text."),
            ]},
            "step2_a1": {"paragraphs": [
                _para("10. p0-no.161131"), _para("Body."),
                _para("11. p0-no.240632"), _para("Body."),
            ]},
        }}

    # (1) 마더텅 job — 코드 → 마더텅 번호로 교체
    m = mk()
    eng._apply_final_labels(m, {"161131": "20", "240632": "6"}, lines.append)
    a1 = [p["text"] for p in m["steps"]["step1_a1"]["paragraphs"]]
    a2 = [p["text"] for p in m["steps"]["step2_a1"]["paragraphs"]]
    _check("마더텅: 브래킷 라벨 교체", a1[0] == "[20]" and a1[2] == "[6]",
           "%s / %s" % (a1[0], a1[2]))
    _check("마더텅: 헤더 no. 교체",
           a2[0] == "10. p0-no.20" and a2[2] == "11. p0-no.6",
           "%s / %s" % (a2[0], a2[2]))
    _check("마더텅: 본문은 안 건드림",
           a1[1] == "Some English body text here.", a1[1])
    _check("마더텅: runs 동기화",
           m["steps"]["step1_a1"]["paragraphs"][0]["runs"][0]["t"] == "[20]")
    _check("마더텅: 프레임 라벨 = 마더텅 번호",
           m.get("_passage_labels") == ["20", "6"],
           str(m.get("_passage_labels")))

    # (2) 코드 job — 표기 유지 + 프레임 라벨은 문항번호(QQ)
    m = mk()
    eng._apply_final_labels(m, {}, lines.append)
    a1 = [p["text"] for p in m["steps"]["step1_a1"]["paragraphs"]]
    _check("코드job: 라벨 그대로(YYMMQQ)", a1[0] == "[161131]", a1[0])
    _check("코드job: 프레임 라벨 = QQ",
           m.get("_passage_labels") == ["31", "32"],
           str(m.get("_passage_labels")))

    # (3) 회차가 하나뿐이어도 프레임 라벨이 채워져야 한다 (옛 구멍)
    m = {"steps": {"step1_a1": {"paragraphs": [
        _para("[250620]"), _para("Body."),
        _para("[250631]"), _para("Body."),
        _para("[250632]"), _para("Body.")]}}}
    eng._apply_final_labels(m, {}, lines.append)
    _check("단일 회차 job 도 프레임 라벨 채움",
           m.get("_passage_labels") == ["20", "31", "32"],
           str(m.get("_passage_labels")))


def test_header_dialect_order():
    """보충 원고 방언 헤더 정리가 라벨 길이에 상관없이 동작해야 한다.

    정리를 번호 치환 **뒤에** 하면 `\\d{1,3}` 이 6자리 라벨에 걸려 실패해
    "no.161131번 161131" 꼬리가 지면에 인쇄된다 (2026-08-17 실측).
    """
    import re as _re

    def transform(btxt, ordinal, lab):
        t = _re.sub(r"^\s*\d+\.", "%d." % ordinal, btxt, count=1)
        t = _re.sub(r"^(\s*\d+\.\s*)p\.?\s*\d+\s*강", r"\1p0", t, count=1)
        t = _re.sub(r"(no\.?\s*\d{1,3})\s*번\s*\d{6}", r"\1", t, count=1,
                    flags=_re.I)
        t = _re.sub(r"(no\.?\s*)\d{1,3}(?:\s*[~\-]\s*\d{1,3})?",
                    lambda m: m.group(1) + lab, t, count=1, flags=_re.I)
        return t

    src = os.path.join(_ROOT, "engines", "workbook_select", "merge_select.py")
    body = open(src, encoding="utf-8").read()
    i_clean = body.find('r"(no\\.?\\s*\\d{1,3})\\s*번\\s*\\d{6}"')
    i_swap = body.find('lambda mm: mm.group(1) + _lab(pc["code"])')
    _check("merge_select: 방언 정리가 번호 치환보다 앞", 0 < i_clean < i_swap,
           "clean=%d swap=%d" % (i_clean, i_swap))

    for lab, want in (("161131", "10. p0-no.161131"), ("20", "10. p0-no.20")):
        got = transform("1. p11강-no.20번 161131", 10, lab)
        _check("방언 헤더 정리 (라벨 %s)" % lab, got == want, got)
    got = transform("5. p22-no.33", 3, "231133")
    _check("표준 헤더 치환", got == "3. p22-no.231133", got)


def test_fill_resolution():
    """보충 데이터(fill) 조달 — 학년·강이 **정확히** 맞을 때만 자동 조달.

    막으려는 것: 저장해 둔 fill 파일이 다른 강 job 에 섞이는 것
    (2026-08-13 사고의 재발). 우선순위는 업로드 > job > 보관소 > config.
    """
    eng = WorkbookSelectEngine()
    cfg = eng_mod._load_config()
    job = tempfile.mkdtemp(prefix="wbsel_fill_")
    lines = []
    try:
        p = eng._resolve_fill_path({}, job, "1", 11, cfg, lines.append)
        _check("fill: 고1 11강 → 보관소 자동 조달",
               p.endswith("hanyoung1_gang11.json"), p or "(없음)")
        _check("fill: 보관소 항목 없는 강(13)은 조달 안 함",
               eng._resolve_fill_path({}, job, "1", 13, cfg, lines.append) == "")
        _check("fill: 강 없는 코드 job 은 조달 안 함",
               eng._resolve_fill_path({}, job, "1", None, cfg,
                                      lines.append) == "")
        _check("fill: 학년 다르면 조달 안 함 (고2 11강)",
               eng._resolve_fill_path({}, job, "2", 11, cfg,
                                      lines.append) == "")
        up = os.path.join(job, "uploaded_fill.json")
        with open(up, "w", encoding="utf-8") as f:
            f.write("{}")
        _check("fill: 업로드가 보관소보다 우선",
               eng._resolve_fill_path({"fill": up}, job, "1", 11, cfg,
                                      lines.append) == up)
        jf = os.path.join(job, "fill.json")
        with open(jf, "w", encoding="utf-8") as f:
            f.write("{}")
        _check("fill: job 폴더 fill.json 이 보관소보다 우선",
               eng._resolve_fill_path({}, job, "1", 11, cfg,
                                      lines.append) == jf)
        # 보관소 색인 정합 — 적힌 파일이 실제로 있어야 한다
        idx = json.load(open(eng._FILL_INDEX, encoding="utf-8"))
        bad = [e["file"] for e in idx.get("entries") or []
               if not os.path.exists(os.path.join(eng._FILL_DIR, e["file"]))]
        _check("fill: 보관소 색인의 파일이 전부 존재", not bad, str(bad))
        # 업로드 슬롯이 실제로 노출되는가
        keys = [s["key"] for s in eng.upload_spec["slots"]]
        _check("fill: 웹 업로드 슬롯 존재", "fill" in keys, str(keys))
    finally:
        shutil.rmtree(job, ignore_errors=True)


def main():
    test_config_clean()
    test_gate_off()
    test_gate_on()
    test_gang_only()
    test_no_input()
    test_final_labels()
    test_header_dialect_order()
    test_fill_resolution()
    test_supplement_lookup()
    bad = [n for n, ok, _ in _results if not ok]
    print("\n%d/%d 통과" % (len(_results) - len(bad), len(_results)))
    if bad:
        print("실패: " + ", ".join(bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
