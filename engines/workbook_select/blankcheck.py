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

# 빈칸 표기는 **어느 원고로 조판했느냐**에 따라 형태가 다르다.
#   해설지 조판(기본)  : "177[focusing]"      번호 + 정답 (스타일이 첫 글자만
#                        남기고 밑줄로 렌더한다)
#   문제지 조판(옛 회차): "521[s          ]"   번호 + 첫 글자 + 공백
#                        (해설지가 없는 옛 원고는 문제지로 조판하고 도형 획을 넣는다)
#   완성본 재사용      : "[m￼]"               앵커 도형
# 셋 다 "번호 + 대괄호 한 덩어리"이므로 괄호 그룹으로 센다. 형태를 특정해서
# 세면 다른 형태를 0개로 읽어 **가짜 불일치**가 난다 (2026-08-17: 해설지로
# 조판된 지문 8개가 전부 "산출 0"으로 실패 처리됐다).
_MS_SLOT = re.compile(r"\d+\[[^\]]*\]")
_OUT_SLOT = re.compile(r"\d*\[[^\]]*\]")
_OBJ = "￼"

# 대조 대상 원고 후보 — 조판이 쓴 원고와 같은 것으로 비교해야 한다.
# 파일명은 회차마다 흔들린다("Step1 C2 빈칸어휘 정답지(개정).docx" /
# "Step1 C2빈칸어휘 정답지(개정).docx" — 띄어쓰기 유무). 이름을 못박으면
# 그 회차만 대조에서 빠진다 → **공백 제거 후 키워드 포함**으로 찾는다.
_FILE_KEY = {"어휘": "빈칸어휘", "어법": "빈칸어법"}


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
    # ⚠ "크기 > 2" 로 기다리면 빈 결과 "[]"(정확히 2바이트)를 영영 못 받아
    #    8분을 다 쓰고 타임아웃한다 — 검사가 안 돈 것과 구분도 안 된다
    #    (실측 2026-08-17). 빈 배열도 **정상 응답**으로 받고, 0건이라는 사실을
    #    호출부가 판단하게 한다.
    for _ in range(timeout // 2):
        time.sleep(2)
        if os.path.exists(_DUMP) and os.path.getsize(_DUMP) >= 2:
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


def _manuscript_paths(base, grade_num, code, kind):
    """그 회차 워크북 폴더의 대조 후보 원고들 — 해설지·개정·문제지 전부.

    조판이 어느 쪽을 썼는지는 회차마다 다르므로 후보를 다 모아 두고,
    호출부가 **빈칸 개수가 맞는 원고**를 채택한다.
    """
    wb = _workbook_dir(base, grade_num, code)
    if not wb:
        return []
    key = _FILE_KEY[kind]
    out = []
    for raw in os.listdir(wb):
        n = _nfc(raw)
        if not n.lower().endswith(".docx"):
            continue
        if key not in n.replace(" ", ""):
            continue
        out.append(os.path.join(wb, raw))
    # 해설지(개정) → 해설지 → 문제지 순으로 시도하면 로그가 읽기 쉽다
    out.sort(key=lambda p: (0 if "개정" in _nfc(os.path.basename(p)) else
                            1 if "정답" in _nfc(os.path.basename(p)) else 2))
    return out


def _workbook_dir(base, grade_num, code):
    yy, mm = int(code[:2]), int(code[2:4])
    gdir = os.path.join(base, "고%s" % grade_num)
    if not os.path.isdir(gdir):
        return None
    want = "고%s %d년 %d월" % (grade_num, yy, mm)
    ym = None
    for raw in os.listdir(gdir):
        if _nfc(raw) == want:
            ym = os.path.join(gdir, raw)
            break
    if not ym:
        return None
    for raw in os.listdir(ym):
        if "워크북" in _nfc(raw) and os.path.isdir(os.path.join(ym, raw)):
            return os.path.join(ym, raw)
    return None


def _manuscript_path(base, grade_num, code, kind, filename=None):
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
    if not filename:
        cands = _manuscript_paths(base, grade_num, code, kind)
        return cands[0] if cands else None
    for raw in os.listdir(wb):
        if _nfc(raw) == filename:
            return os.path.join(wb, raw)
    return None


def run(indd, num2code, manuscript_base, grade_num="1", log=None):
    """→ (검사한 지문 수, [실패 항목]). 실패 항목은 사람이 읽는 문자열."""
    if log is None:
        log = lambda s: None
    rows = dump(indd)
    if rows is None:
        return 0, ["빈칸 대조: InDesign 덤프 실패 (검사 못 함)"]
    if not rows:
        # 빈칸 섹션을 한 페이지도 못 찾았다 = 대상 문서를 잘못 잡았거나
        # 러닝 라벨이 없다. "0건 일치"로 통과시키면 안 된다.
        return 0, ["빈칸 대조: 빈칸 섹션을 찾지 못함 — 대상 문서/러닝 라벨 확인 "
                   "(검사 못 함)"]

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
        # 조판이 해설지로 갔는지 문제지로 갔는지는 회차마다 다르다
        # (해설지가 기본, 없는 옛 회차는 문제지 + 도형 획). 대조본을 하나로
        # 못박으면 다른 쪽으로 조판된 문항이 통째로 가짜 불일치가 된다.
        # → 후보 원고를 모두 세어 **개수가 맞는 원고가 있으면 통과**.
        cands = _manuscript_paths(base, grade_num, code, kind)
        if not cands:
            continue
        act = [len(_OUT_SLOT.findall(t)) for _p, t in sentences]
        stray = sum(len(re.findall(_OBJ, _OUT_SLOT.sub("", t)))
                    for _p, t in sentences)
        tried = []
        matched = None
        for cand in cands:
            exp = _ms_blanks(cand, int(code[4:6]))
            if exp is None:
                continue
            tried.append((os.path.basename(cand), sum(exp)))
            if sum(exp) == sum(act):
                matched = (os.path.basename(cand), sum(exp))
                break
        if not tried:
            continue
        checked += 1
        page = sentences[0][0]
        if matched is None or stray:
            msg = ("빈칸 불일치: p%s 마더텅%s %s — 산출 %d / 원고 후보 %s "
                   "/ 괄호 밖 여분도형 %d"
                   % (page, lbl, kind, sum(act),
                      ", ".join("%s=%d" % t for t in tried), stray))
            fails.append(msg)
            log("  [빈칸] " + msg)
        else:
            log("  [빈칸] p%-4s 마더텅%-3s %s  %d개 일치  (%s)"
                % (page, lbl, kind, matched[1], matched[0]))
    return checked, fails
