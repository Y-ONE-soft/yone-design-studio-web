# -*- coding: utf-8 -*-
"""빈칸어휘/빈칸어법 — 산출물의 빈칸 개수를 원고와 대조 (검수 G3 항목).

**빈칸은 "글자가 없는 내용"이라 기존 검사 어디에도 안 걸린다.**
오버셋·링크·폰트·프리플라이트는 밑줄이 하나 더 있어도 전부 정상이고,
텍스트 대조는 빈칸에 글자가 없어 대조 대상 자체가 안 된다. 육안으로
20문항 × 13섹션의 밑줄을 세는 것도 비현실적이다.

2026-08-13 한영1 워크북01 실측: 원고에 없는 밑줄 16개가 검수 여러 번을
통과해 살아남았다(p105 4 · p108 3 · p122 6 · p170 3). 이 검사는 그 16건을
전부 검출하고, 수정본에서는 0을 낸다.

빈칸 표기는 경로에 따라 다르지만 둘 다 센다:
    원고 기반 조판 : "160[m    ]"  (텍스트 공백)
    완성본 재사용  : "160[m￼]"     (앵커 도형)
"""
import json
import os
import re
import subprocess
import time
import unicodedata

_DIR = os.path.dirname(os.path.abspath(__file__))
_JSX = os.path.join(_DIR, "jsx", "dump_blanks.jsx")
_DUMP = "/tmp/wbsel_blanks_dump.json"

# 원고의 빈칸: "160[m                    ]"
_MS_SLOT = re.compile(r"\d+\[[A-Za-z]?[  ]{4,}\]")
# 산출물의 빈칸: 도형형 "[m￼]" / 공백형 "[m      ]"
_OUT_SLOT = re.compile(r"\[[A-Za-z]?(?:￼|[  ]{4,})\]")
_OBJ = "￼"

_FILE_MAP = {"어휘": "Step1 C2 빈칸어휘.docx", "어법": "Step2 C1 빈칸어법.docx"}


def _nfc(s):
    return unicodedata.normalize("NFC", s)


def dump(indd, timeout=480):
    """InDesign 에서 빈칸 섹션 단락을 덤프한다 (읽기 전용)."""
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
    for _ in range(timeout // 2):
        time.sleep(2)
        if os.path.exists(_DUMP) and os.path.getsize(_DUMP) > 2:
            time.sleep(2)
            try:
                return json.load(open(_DUMP, encoding="utf-8"))
            except ValueError:
                continue
    return None


def _ms_blanks(path, qq):
    """원고 파일에서 no.qq 블록의 영문 문장별 빈칸 개수 리스트."""
    from engines.workbook.parser import _docx_extract_paragraphs
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


def _manuscript_path(base, grade_num, code, kind):
    yy, mm = int(code[:2]), int(code[2:4])
    gdir = os.path.join(base, "고%s" % grade_num)
    if not os.path.isdir(gdir):
        return None
    ym = None
    want = "고%s %d년 %d월" % (grade_num, yy, mm)
    for raw in os.listdir(gdir):
        if _nfc(raw) == want:
            ym = os.path.join(gdir, raw)
            break
    if not ym:
        return None
    wb = None
    for raw in os.listdir(ym):
        if "워크북" in _nfc(raw) and os.path.isdir(os.path.join(ym, raw)):
            wb = os.path.join(ym, raw)
            break
    if not wb:
        return None
    for raw in os.listdir(wb):
        if _nfc(raw) == _FILE_MAP[kind]:
            return os.path.join(wb, raw)
    return None


def run(indd, num2code, manuscript_base, grade_num="1", log=None):
    """→ (검사한 지문 수, [실패 항목]). 실패 항목은 사람이 읽는 문자열."""
    if log is None:
        log = lambda s: None
    rows = dump(indd)
    if rows is None:
        return 0, ["빈칸 대조: InDesign 덤프 실패 (검사 못 함)"]

    got = {}
    for r in rows:
        lbl, sec = r.get("label") or "", r.get("section") or ""
        t = r.get("text") or ""
        if not lbl or not re.search(r"[A-Za-z]", t):
            continue
        if re.search(r"[가-힣]", t):
            continue
        got.setdefault((lbl, "어법" if "어법" in sec else "어휘"),
                       []).append((r["page"], t))

    base = os.path.expanduser(manuscript_base)
    checked, fails = 0, []
    for (lbl, kind), sentences in sorted(got.items(),
                                         key=lambda x: int(x[0][0])):
        try:
            code = num2code.get(int(lbl))
        except ValueError:
            continue
        if not code:
            continue
        path = _manuscript_path(base, grade_num, code, kind)
        if not path:
            continue
        exp = _ms_blanks(path, int(code[4:6]))
        if exp is None:
            continue
        act = [len(_OUT_SLOT.findall(t)) for _p, t in sentences]
        stray = sum(len(re.findall(_OBJ, _OUT_SLOT.sub("", t)))
                    for _p, t in sentences)
        checked += 1
        page = sentences[0][0]
        if sum(exp) != sum(act) or stray:
            msg = ("빈칸 불일치: p%s 마더텅%s %s — 원고 %d / 산출 %d "
                   "/ 괄호 밖 여분도형 %d"
                   % (page, lbl, kind, sum(exp), sum(act), stray))
            fails.append(msg)
            log("  [빈칸] " + msg)
        else:
            log("  [빈칸] p%-4s 마더텅%-3s %s  %d개 일치"
                % (page, lbl, kind, sum(exp)))
    return checked, fails
