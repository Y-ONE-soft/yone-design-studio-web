# -*- coding: utf-8 -*-
"""리뷰테스트 원고 → 지문별 암기 TEST 본문(`숫자[낱말]` 표기).

암기 TEST 는 지문과 **같은 글**이고, 외워야 할 낱말 자리에 번호가 붙어 있을
뿐이다. 정답면은 그 낱말이 주황으로 보이고 문제면은 같은 자리가 빈칸이다.
조판이 받는 것은 `숫자[낱말]` 표기 하나뿐이고, 색·빈칸은 `data.format_memtest()`
가 그 표기에서 되만든다. 그래서 여기서 할 일은 **표기의 본문을 지문별로 만드는
것**뿐이다.

원고는 두 갈래로 온다.

① **해설지 .docx** — 본문에 이미 `1[understanding]` 이라고 찍혀 있다. 그대로 쓴다.
② **정답지 .pdf** — 표기가 없다. 대신 정답 낱말만 **굵게** 조판돼 있다
   (`NotoSansCJKkr-Bold`, 나머지는 Regular). 굵기가 곧 정답 표시다.

②를 쓰는 이유가 있다. 원고 폴더(`리테 모음`)에는 363개 중 docx 가 12개뿐이고
나머지는 전부 PDF 다. 짝을 이루는 `(앞글자)` PDF 와 글자를 맞대어 빼는 길도
있지만, 굵기 하나만 보면 **파일 한 개로** 끝나고 줄바꿈·자간이 달라도 흔들리지
않는다. 실측: 정답지 175개 중 굵은 글자가 없는 파일은 0개였다.

형식(파일명·헤더 표기)에는 기대지 않는다.

* **어느 파일이 정답지인가** — 이름이 아니라 굵은 낱말의 평균 길이로 가른다.
  정답지는 낱말 통째(평균 6~8자), `(앞글자)` 판은 첫 글자 한 개(평균 1자)다.
  실측 363개에서 2.5자를 경계로 175/188 로 깨끗이 갈렸고 경계 근처가 없었다.
* **어느 줄이 본문인가** — 한글 비율로 해석줄을 걷어내고, 글자 크기가 본문보다
  1.25배 이상 큰 줄을 지문 헤더로 본다(헤더 표기는 `고1 250920`·`RP기본 13강
  Example`·`영어I 동아(박) 1과 본문1` 처럼 제각각이라 글자로는 못 가른다).
* **어느 지문에 붙는가** — 헤더 글자가 아니라 **내용**으로 맞춘다. 암기테스트
  본문은 지문과 같은 글이므로 알파벳만 남긴 지문(signature)이 그대로 열쇠다
  (`idml.split_memtest` 가 쓰는 방법과 같다).

번호는 **책 단위로 1부터 이어서** 매긴다. 한 권이 회차 여럿에서 지문을 모아 오면
파일별 번호를 그대로 쓸 때 1번이 여러 개 생겨 학생이 답을 적을 수 없다.
"""
import difflib
import os
import re
import zipfile

_MARK = re.compile(r"(\d+)\s*\[([^\]]*)\]")
_HAN = re.compile(r"[가-힣]")
_LAT = re.compile(r"[A-Za-z]")
_LETTERS = re.compile(r"[a-z0-9]")
_WP = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

BOLD_FLAG = 1 << 4          # PyMuPDF span flags 의 굵기 비트
ANSWER_MIN_WORD = 2.5       # 굵은 낱말 평균 길이 — 이보다 짧으면 (앞글자) 판이다
MATCH_MIN = 0.80            # 지문 ↔ 암기테스트 본문 최소 닮음


# ══════════════════════════════════════════════════════════════════
# 1. 조각(part) — [글자, 정답인가]
#    표기 문자열이 아니라 조각 목록으로 들고 다닌다. 그래야 번호를 나중에
#    (책 단위로) 다시 매길 수 있고, 지문 경계로 자르기도 쉽다.
# ══════════════════════════════════════════════════════════════════
def plain(parts):
    """조각 → 표기 없는 맨 글자."""
    return "".join(t for t, _b in parts)


def letters(text):
    """알파벳·숫자만 남긴 지문(指紋). 서식·공백·구두점이 달라도 같아진다."""
    return "".join(_LETTERS.findall(text.lower()))


def render(parts, start=1):
    """조각 → `숫자[낱말]` 표기. 다음에 쓸 번호를 함께 돌려준다."""
    out, n = [], start - 1
    for t, blank in _merge(parts):
        if not blank:
            out.append(t)
            continue
        for w in re.split(r"(\s+)", t):
            if w.strip():
                n += 1
                out.append("%d[%s]" % (n, w))
            else:
                out.append(w)
    txt = re.sub(r"\s+", " ", "".join(out)).strip()
    # 본문(지문면)은 활자 따옴표를 쓴다 — 마주 보는 면과 글자가 달라 보이면 안 된다.
    txt = re.sub(r"(?<=[A-Za-z])'(?=[A-Za-z])", "’", txt)
    return txt, n + 1


def count_blanks(parts):
    return sum(len(t.split()) for t, b in _merge(parts) if b)


def _merge(parts):
    """이어 붙은 같은 종류의 조각을 하나로. 한 낱말이 조각 둘로 쪼개져 있으면
    번호가 둘 붙는다(`[ho]` `[w]`) — 실제로 그렇게 됐다."""
    out = []
    for t, b in parts:
        if not t:
            continue
        if out and out[-1][1] == b:
            out[-1][0] += t
        else:
            out.append([t, b])
    return out


def cut(parts, want):
    """조각 목록에서 `want`(지문 원문)에 해당하는 구간만 잘라 낸다.

    한 지문이 아니라 여러 지문이 한 덩이로 들어오는 원고가 있다(헤더를 못 가른
    경우). 잘라 내지 않으면 옆 지문 글까지 암기테스트에 인쇄된다.
    """
    P = plain(parts)
    idx = [i for i, ch in enumerate(P) if _LETTERS.match(ch.lower())]
    hay = letters(P)
    need = letters(want)
    if not need or not hay:
        return parts
    at = hay.find(need[:60])
    if at < 0:
        at = hay.find(need[:30])
    if at < 0:
        return parts
    end = min(len(hay), at + len(need))
    a, b = idx[at], idx[end - 1] + 1
    out, pos = [], 0
    for t, blank in parts:
        s, e = pos, pos + len(t)
        pos = e
        if e <= a or s >= b:
            continue
        out.append((t[max(0, a - s):len(t) - max(0, e - b)], blank))
    return out or parts


# ══════════════════════════════════════════════════════════════════
# 2. 원고 읽기
# ══════════════════════════════════════════════════════════════════
def _kind(path):
    """확장자가 아니라 **내용**으로 갈래를 본다.

    구글 드라이브가 받아 놓은 사본은 이름이 `…docx의 사본` 이라 확장자가 없다.
    """
    try:
        with open(path, "rb") as f:
            head = f.read(4)
    except OSError:
        return None
    if head[:4] == b"%PDF":
        return "pdf"
    if head[:2] == b"PK":
        try:
            with zipfile.ZipFile(path) as z:
                if "word/document.xml" in z.namelist():
                    return "docx"
        except Exception:
            return None
    return None


# ── ① 해설지 docx ──────────────────────────────────────────────
def _docx_paragraphs(path):
    from xml.etree import ElementTree as ET
    with zipfile.ZipFile(path) as z:
        with z.open("word/document.xml") as f:
            root = ET.parse(f).getroot()
    ns = {"w": _WP}
    out = []
    for p in root.findall(".//w:p", ns):
        out.append("".join(t.text or "" for t in p.findall(".//w:t", ns)).strip())
    return out


def _split_marks(line):
    """`A 1[missing] hiker` → [('A ',False), ('missing',True), (' hiker',False)]"""
    parts, pos = [], 0
    for m in _MARK.finditer(line):
        if m.start() > pos:
            parts.append((line[pos:m.start()], False))
        parts.append((m.group(2), True))
        pos = m.end()
    if pos < len(line):
        parts.append((line[pos:], False))
    return parts


def read_docx(path):
    """해설지 docx → 지문 목록.

    헤더는 `1. p74-no.01`·`1. L2-p. 37 본문 1`·`3. L1-본문9` 처럼 제각각이지만
    **차례 번호가 1씩 는다**는 것은 같다. 그 뼈대로 가른다(짧고, 표기가 없고,
    번호가 이어지는 줄).
    """
    out, cur, seq = [], None, 0
    for line in _docx_paragraphs(path):
        if not line:
            continue
        m = re.match(r"\s*(\d+)\s*[.)]", line)
        if (m and int(m.group(1)) == seq + 1 and len(line) <= 40
                and not _MARK.search(line)):
            seq = int(m.group(1))
            cur = {"header": line, "parts": [], "src": path}
            out.append(cur)
            continue
        if cur is None:
            continue
        if len(_HAN.findall(line)) / max(1, len(line)) > 0.30:
            continue                      # 한글 해석줄
        if cur["parts"]:
            cur["parts"].append((" ", False))
        cur["parts"] += _split_marks(line)
    if not out:
        # 번호 뼈대가 없는 원고 — 통째로 하나로 두고 내용으로 자른다.
        body = []
        for line in _docx_paragraphs(path):
            if line and len(_HAN.findall(line)) / max(1, len(line)) <= 0.30:
                if body:
                    body.append((" ", False))
                body += _split_marks(line)
        if body:
            out = [{"header": os.path.basename(path), "parts": body, "src": path}]
    return out


# ── ② 정답지 pdf ───────────────────────────────────────────────
def _pdf_lines(path):
    import fitz
    doc = fitz.open(path)
    try:
        for page in doc:
            for blk in page.get_text("dict")["blocks"]:
                if blk["type"]:
                    continue
                for line in blk["lines"]:
                    yield line
    finally:
        doc.close()


def is_answer_pdf(path):
    """정답지인가, `(앞글자)` 판인가 — 굵은 낱말의 길이로 가른다."""
    tot = n = 0
    for line in _pdf_lines(path):
        for sp in line["spans"]:
            if sp["flags"] & BOLD_FLAG and sp["size"] < 12:
                for w in sp["text"].split():
                    n += 1
                    tot += len(w)
    return n > 0 and tot / n >= ANSWER_MIN_WORD


def read_pdf(path):
    """정답지 pdf → 지문 목록. **굵은 글자가 곧 정답**이다."""
    lines = list(_pdf_lines(path))
    size = {}
    for line in lines:
        for sp in line["spans"]:
            k = round(sp["size"], 1)
            size[k] = size.get(k, 0) + len(_LAT.findall(sp["text"]))
    if not size:
        return []
    body = max(size, key=lambda k: size[k])          # 라틴 글자가 가장 많은 크기
    out, cur, prev_y = [], None, None
    for line in lines:
        text = "".join(sp["text"] for sp in line["spans"])
        if not text.strip():
            continue
        if max(round(sp["size"], 1) for sp in line["spans"]) >= body * 1.25:
            cur = {"header": text.strip(), "parts": [], "src": path}
            out.append(cur)
            prev_y = None
            continue
        if len(_HAN.findall(text)) / max(1, len(text)) > 0.30:
            continue                                  # 한글 해석줄
        if cur is None:
            continue
        y = round(line["bbox"][1], 1)
        if prev_y is not None and abs(y - prev_y) > 0.6 and cur["parts"]:
            # 줄바꿈은 보통 낱말 사이지만, 정답 낱말이 줄 끝에서 잘려 넘어가기도
            # 한다(`…understand ho` / `w long things…`). 정답 조각끼리 맞닿은
            # 자리는 낱말 **안**이다 — 정답 둘 사이에는 언제나 보통 굵기의 공백
            # 조각이 끼어 있기 때문이다. 여기에 공백을 넣으면 낱말이 갈라진다.
            head = next((sp for sp in line["spans"] if sp["text"]), None)
            glued = (head is not None and bool(head["flags"] & BOLD_FLAG)
                     and cur["parts"][-1][1]
                     and cur["parts"][-1][0][-1:].isalpha()
                     and head["text"][:1].isalpha())
            if not glued:
                cur["parts"].append((" ", False))
        prev_y = y
        for sp in line["spans"]:
            if sp["text"]:
                cur["parts"].append((sp["text"], bool(sp["flags"] & BOLD_FLAG)))
    return out


# ── 원고 모으기 ───────────────────────────────────────────────
def read(paths, log=None):
    """파일·폴더 목록 → 암기테스트 지문 목록.

    같은 내용이 docx 와 pdf 로 둘 다 있으면 **docx 를 남긴다**(표기가 원고에
    직접 적혀 있어 되만들 여지가 없다).
    """
    log = log or (lambda _m: None)
    if isinstance(paths, str):
        paths = [paths]
    files = []
    for p in paths or ():
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            for root, _d, fs in os.walk(p):
                files += [os.path.join(root, f) for f in sorted(fs)
                          if not f.startswith(".")]
        elif os.path.exists(p):
            files.append(p)
    docs, pdfs, other = [], [], []
    for f in files:
        k = _kind(f)
        (docs if k == "docx" else pdfs if k == "pdf" else other).append(f)
    out, used, skipped, failed = [], [0, 0], 0, []
    for f in docs:
        try:
            got = [e for e in read_docx(f) if count_blanks(e["parts"])]
        except Exception as exc:                      # 원고 한 개가 전체를 막지 않게
            failed.append("%s(%s)" % (os.path.basename(f), exc))
            continue
        if got:
            out += got
            used[0] += 1
        else:
            skipped += 1                              # 문제지·정답 목록
    for f in pdfs:
        try:
            if not is_answer_pdf(f):
                skipped += 1                          # (앞글자)·(빈칸) 판
                continue
            got = [e for e in read_pdf(f) if count_blanks(e["parts"])]
        except Exception as exc:
            failed.append("%s(%s)" % (os.path.basename(f), exc))
            continue
        if got:
            out += got
            used[1] += 1
        else:
            skipped += 1
    log("  [리테] 원고 %d개에서 지문 %d — 해설지 %d · 정답지 %d "
        "(정답본이 아니라 건너뜀 %d)"
        % (used[0] + used[1], len(out), used[0], used[1], skipped))
    if failed:
        log("  [리테] 읽기 실패 %d개 — %s" % (len(failed), ", ".join(failed[:5])))
    if other:
        log("  [리테] 원고가 아닌 파일 %d개는 지나쳤다 — %s"
            % (len(other), ", ".join(os.path.basename(x) for x in other[:3])))
    seen, uniq = set(), []
    for e in out:
        sig = letters(plain(e["parts"]))
        if sig in seen:
            continue                                  # docx 가 먼저 들어와 이긴다
        seen.add(sig)
        e["letters"] = sig
        uniq.append(e)
    return uniq


# ══════════════════════════════════════════════════════════════════
# 3. 지문에 붙이기
# ══════════════════════════════════════════════════════════════════
def _row_text(row):
    """지문 원문 — 코퍼스·분석본·수확기 어느 모양이든 받는다."""
    if row.get("passage_text"):
        return row["passage_text"]
    paras = row.get("passage") or []
    if isinstance(paras, str):
        return paras
    out = []
    for p in paras:
        if isinstance(p, dict) and "runs" in p:
            out.append("".join(r.get("t", "") for r in p["runs"]))
        elif isinstance(p, dict):
            out.append(p.get("t", ""))
    return " ".join(out)


def find(entries, text):
    """지문 원문 → 짝이 되는 암기테스트 항목. **내용으로만** 찾는다."""
    need = letters(text)
    if len(need) < 60:
        return None
    head = need[:60]
    best, score = None, 0.0
    for e in entries:
        hay = e["letters"]
        if head not in hay and hay[:60] not in need:
            continue
        r = difflib.SequenceMatcher(None, need, hay, autojunk=False).quick_ratio()
        if head in hay:
            r = max(r, MATCH_MIN)          # 긴 덩이 안에 들어 있으면 잘라 쓰면 된다
        if r > score:
            best, score = e, r
    return best if score >= MATCH_MIN else None


def attach(rows, sources, log=None, place="after"):
    """지문 목록에 암기 TEST 면을 끼워 넣는다.

    `place="after"` 는 지문 다음에 문제·정답 두 면(모의고사 포켓북 관행),
    `place="end"` 는 책 끝에 몰아 놓는다(교과서 포켓북이 그렇게 돼 있다).
    번호는 어느 쪽이든 **책 안에서 1부터 이어서** 매긴다.
    """
    log = log or (lambda _m: None)
    entries = read(sources, log)
    if not entries:
        log("■ 리뷰테스트 원고에서 읽어 낸 지문이 없다")
        return rows
    out, tail, no, hit, miss = [], [], 1, 0, []
    for row in rows:
        out.append(row)
        if row.get("kind") == "memtest":
            continue
        text = _row_text(row)
        e = find(entries, text)
        if e is None:
            miss.append(row.get("key") or row.get("label") or "?")
            continue
        parts = cut(e["parts"], text)
        body, no = render(parts, no)
        key = row.get("key") or row.get("pno") or row.get("label") or ""
        pages = [{"kind": "memtest", "answer": ans, "key": key,
                  "category": row.get("category") or "",
                  "body_runs": [{"t": body}]}
                 for ans in (False, True)]
        (tail if place == "end" else out).extend(pages)
        hit += 1
    out += tail
    log("■ 암기 TEST — 지문 %d개에 붙였다(빈칸 %d개, 원고 %d지문)"
        % (hit, no - 1, len(entries)))
    if miss:
        log("  [암기TEST 없음] %d지문 — %s" % (len(miss), ", ".join(miss[:12])))
    return out
