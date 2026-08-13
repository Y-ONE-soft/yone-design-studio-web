# -*- coding: utf-8 -*-
"""빈칸어휘/빈칸어법 — 산출물의 빈칸 개수를 **원고와 대조** (검수 필수 항목).

왜 필요한가
-----------
2026-08-13 검수에서 빈칸어휘/빈칸어법에 **원고에 없는 밑줄 16개**가 발견됐다.
그때까지 검수를 여러 번 했는데 전부 통과했다. 이유:

  - 오버셋·링크·폰트·프리플라이트: 밑줄이 하나 더 있어도 전부 정상
  - 지문 중복/누락 검사: 지문은 다 있으니 정상
  - 텍스트 대조: 빈칸은 글자가 없으니 대조 대상에 안 잡힘
  - 육안: 밑줄 한 칸 더 있는 것을 20문항 × 13섹션에서 눈으로 세기는 비현실적

**빈칸은 "글자가 없는 내용"이라 기존 검사 어디에도 안 걸린다.**
그래서 개수를 원고와 직접 세서 대조하는 검사가 따로 필요하다.

무엇을 잡는가
-------------
  - 원고에 없는 여분 밑줄 (이번 사고)
  - 원고에 있는데 빠진 밑줄
  - 빈칸 표기가 도형(￼)이든 텍스트 공백이든 동일하게 판정

사용:
    python3 scripts/wbsel_check_blanks.py --gang 11 --indd <경로>
    python3 scripts/wbsel_check_blanks.py --gang 11        (열려 있는 문서)
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

_ENV = os.path.join(_ROOT, ".env")
if os.path.exists(_ENV):
    for _line in open(_ENV, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

from engines.workbook.engine import _load_config as _wb_config  # noqa: E402
from engines.workbook.parser import _docx_extract_paragraphs  # noqa: E402
from engines.workbook_select import motherteng as _mt  # noqa: E402
from engines.workbook_select.engine import _load_config as _sel_config  # noqa: E402

_JSX = os.path.join(_ROOT, "engines", "workbook_select", "jsx",
                    "dump_blanks.jsx")
_DUMP = "/tmp/wbsel_blanks_dump.json"

# 원고의 빈칸: "160[m                    ]" — 번호 + 대괄호 + (첫글자) + 공백런
_MS_SLOT = re.compile(r"\d+\[[A-Za-z]?[  ]{4,}\]")
# 산출물의 빈칸: 도형형 "[m￼]" / 공백형 "[m      ]"
_OUT_SLOT = re.compile(r"\[[A-Za-z]?(?:￼|[  ]{4,})\]")
_OBJ = "￼"
_EN = re.compile(r"[A-Za-z']+")


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def _run_dump(indd):
    src = open(_JSX, encoding="utf-8").read()
    src = src.replace("__INDD_PATH__", indd or "").replace("__OUT_PATH__", _DUMP)
    run = "/tmp/wbsel_dump_blanks_run.jsx"
    with open(run, "w", encoding="utf-8") as f:
        f.write(src)
    try:
        os.remove(_DUMP)
    except OSError:
        pass
    subprocess.Popen([
        "osascript", "-e",
        'tell application id "com.adobe.InDesign" to do script '
        '(POSIX file "%s") language javascript' % run,
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(240):
        time.sleep(2)
        if os.path.exists(_DUMP) and os.path.getsize(_DUMP) > 2:
            time.sleep(2)
            return json.load(open(_DUMP, encoding="utf-8"))
    return None


def _ms_blanks_by_sentence(path, qq):
    """원고 파일에서 no.qq 블록의 영문 문장별 빈칸 개수."""
    paras = _docx_extract_paragraphs(path, False)
    txt = [(p.get("text") if isinstance(p, dict) else str(p)) or ""
           for p in paras]
    hdr = re.compile(r"^\s*\d+\.\s*p\S*-no\.%d\s*$" % qq)
    any_hdr = re.compile(r"^\s*\d+\.\s*p\S*-no\.\d+")
    start = None
    for i, t in enumerate(txt):
        if hdr.match(t.strip()):
            start = i + 1
            break
    if start is None:
        return None
    out = []
    for t in txt[start:]:
        if any_hdr.match(t.strip()):
            break
        if not t.strip() or re.search(r"[가-힣]", t):
            continue
        out.append(len(_MS_SLOT.findall(t)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gang", required=True)
    ap.add_argument("--grade", default="고1")
    ap.add_argument("--indd", default="", help="비우면 열려 있는 문서")
    args = ap.parse_args()

    sel = _sel_config()
    codes, numbers, col = _mt.codes_for_gang(sel.get("motherteng_xlsx"),
                                             int(args.gang))
    if not codes:
        print("엑셀에서 %s강을 찾지 못했습니다" % args.gang)
        return 2
    num2code = {numbers[c]: c for c in codes if c in numbers}
    print("마더텅 %s강 — %d문항 (엑셀 '%s')" % (args.gang, len(codes), col))

    print("InDesign 덤프 중…")
    rows = _run_dump(args.indd)
    if rows is None:
        print("덤프 실패 — InDesign 로그 확인")
        return 2
    print("빈칸 섹션 단락 %d개 수집" % len(rows))

    # 지문번호 → 섹션 → 문장별 빈칸 수
    got = {}
    for r in rows:
        lbl, sec = r.get("label") or "", r.get("section") or ""
        t = r.get("text") or ""
        if not lbl or not re.search(r"[A-Za-z]", t):
            continue
        if re.search(r"[가-힣]", t):
            continue
        key = (lbl, "어법" if "어법" in sec else "어휘")
        got.setdefault(key, []).append((r["page"], t))

    cfg = _wb_config()
    base = os.path.expanduser(sel["manuscript_base"])
    grade_num = args.grade.replace("고", "").strip() or "1"
    fmap = {"어휘": "Step1 C2 빈칸어휘.docx", "어법": "Step2 C1 빈칸어법.docx"}

    fails, checked = [], 0
    for (lbl, kind), sentences in sorted(got.items(),
                                         key=lambda x: int(x[0][0])):
        code = num2code.get(int(lbl))
        if not code:
            continue
        yy, mm, qq = int(code[:2]), int(code[2:4]), int(code[4:6])
        # 회차 폴더
        gdir = os.path.join(base, "고%s" % grade_num)
        ym = None
        for raw in os.listdir(gdir):
            if _nfc(raw) in ("고%s %d년 %d월" % (grade_num, yy, mm),):
                ym = os.path.join(gdir, raw)
                break
        if not ym:
            continue
        wb = None
        for raw in os.listdir(ym):
            if "워크북" in _nfc(raw) and os.path.isdir(os.path.join(ym, raw)):
                wb = os.path.join(ym, raw)
                break
        if not wb:
            continue
        want = fmap[kind]
        path = None
        for raw in os.listdir(wb):
            if _nfc(raw) == want:
                path = os.path.join(wb, raw)
                break
        if not path:
            continue

        exp = _ms_blanks_by_sentence(path, qq)
        if exp is None:
            continue
        act = [len(_OUT_SLOT.findall(t)) for _p, t in sentences]
        stray = sum(
            1 for _p, t in sentences
            for m in re.finditer(_OBJ, _OUT_SLOT.sub("", t))
        )
        checked += 1
        page = sentences[0][0]
        n_exp, n_act = sum(exp), sum(act)
        mark = "OK"
        if n_exp != n_act or stray:
            mark = "*** 불일치"
            fails.append((page, lbl, kind, n_exp, n_act, stray))
        print("  p%-4s 마더텅%-3s %s  원고 %3d / 산출 %3d  여분도형 %d  %s"
              % (page, lbl, kind, n_exp, n_act, stray, mark))
        if mark != "OK":
            for i in range(max(len(exp), len(act))):
                e = exp[i] if i < len(exp) else "-"
                a = act[i] if i < len(act) else "-"
                if e != a:
                    txt = sentences[i][1] if i < len(sentences) else ""
                    print("        문장%-2d 원고 %s / 산출 %s  %s"
                          % (i + 1, e, a, txt[:70]))

    print("\n===== 판정 =====")
    print("  지문 %d개 대조" % checked)
    if fails:
        for p, lbl, kind, e, a, s in fails:
            print("  실패: p%s 마더텅%s %s — 원고 %d vs 산출 %d (여분도형 %d)"
                  % (p, lbl, kind, e, a, s))
        return 1
    print("  빈칸 개수 전부 원고와 일치")
    return 0


if __name__ == "__main__":
    sys.exit(main())
