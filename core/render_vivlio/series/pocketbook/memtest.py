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

번호는 **단원(교과서/모의고사)마다 1부터 이어서** 매긴다 — 완성본이 그렇게 돼
있다(강동1 실측: 교과서 1~154 · 모의고사 1~1093). 원고 파일의 번호를 그대로
가져오면 한 권 안에서 1번이 여러 개 생긴다.
"""
import difflib
import hashlib
import json
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
    """**알파벳만** 남긴 지문(指紋). 서식·공백·구두점이 달라도 같아진다.

    ⚠ 숫자를 남기면 안 된다. 분석본 지문에는 **문장 번호**(`1 Dear valued
      players, 2 Recently, …`)가 섞여 있는데 리테 원고에는 없다 — 숫자를 세면
      두 글이 영영 안 만난다(광문1 실측: 교과서·부교재 33지문이 통째로 못
      붙었다). 양쪽에서 똑같이 버리므로 견주는 데는 지장이 없다.
    """
    return "".join(c for c in _LETTERS.findall(text.lower()) if not c.isdigit())


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
    return _quotes(re.sub(r"\s+", " ", "".join(out)).strip()), n + 1


def _quotes(txt):
    """곧은 따옴표 → 활자 따옴표.

    리뷰테스트 원고는 `"own"`·`don't` 처럼 곧은 따옴표를 쓰지만 포켓북 지문면은
    `“own”`·`don’t` 다(코퍼스 실측). 마주 보는 두 면이 서로 다른 활자를 쓰면 안 된다.
    **앞이 빈칸(또는 글 첫머리)일 때만 여는 따옴표**다. 앞 글자로 '낱말인가'를
    따지면 `‘no,’"` 나 `33%"` 의 닫는 따옴표를 여는 것으로 잘못 본다(실측 2건).
    """
    out = []
    for i, ch in enumerate(txt):
        if ch not in "\"'":
            out.append(ch)
            continue
        prev = txt[i - 1] if i else ""
        opening = not prev or prev.isspace() or prev in "([{“‘—–-"
        out.append(("“" if ch == '"' else "‘") if opening
                   else ("”" if ch == '"' else "’"))
    return "".join(out)


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
    # 끝은 길이로 재지 않고 **지문 끝머리를 다시 찾아** 잡는다. 완성본과 원고가
    # 낱말 한둘 다르면(개정판) 길이로 잡은 끝이 문장 중간에서 잘린다.
    tail = hay.rfind(need[-40:], at) if len(need) >= 40 else -1
    end = tail + len(need[-40:]) if tail >= 0 else min(len(hay), at + len(need))
    end = max(end, at + 1)
    a, b = idx[at], idx[end - 1] + 1
    # 글자만으로 잡은 경계는 **문장부호를 잘라 먹는다** — 첫 따옴표와 마지막
    # 마침표가 그렇다. 띄어쓰기를 만날 때까지 양쪽으로 넓힌다.
    while a > 0 and not P[a - 1].isspace() and not _LETTERS.match(P[a - 1].lower()):
        a -= 1
    while b < len(P) and not P[b].isspace() and not _LETTERS.match(P[b].lower()):
        b += 1
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


def _is_answer(lines):
    """정답지인가, `(앞글자)` 판인가 — 굵은 낱말의 길이로 가른다."""
    tot = n = 0
    for line in lines:
        for sp in line["spans"]:
            if sp["flags"] & BOLD_FLAG and sp["size"] < 12:
                for w in sp["text"].split():
                    n += 1
                    tot += len(w)
    return n > 0 and tot / n >= ANSWER_MIN_WORD


def is_answer_pdf(path):
    return _is_answer(list(_pdf_lines(path)))


def read_pdf(path):
    """정답지 pdf → 지문 목록. **굵은 글자가 곧 정답**이다.

    정답지가 아니면(=`(앞글자)`·`(빈칸)` 판) 빈 목록을 돌려준다 — 한 번 읽은
    줄을 두 번 읽지 않으려고 판정도 여기서 한다.
    """
    lines = list(_pdf_lines(path))
    if not _is_answer(lines):
        return []
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
def _files(paths):
    """파일·폴더 목록 → 실제 파일 목록(순서 고정)."""
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
    return sorted(files)


def _stamp(files):
    """원고 폴더의 지문(指紋) — 경로·크기·수정시각.

    내용 해시가 아니라 stat 만 본다. 363개를 다 열면 캐시가 무슨 소용인가
    (여는 데 드는 시간이 파싱 시간이다). 원고는 사람이 새 파일을 떨구는 식으로
    바뀌므로 크기·수정시각이면 충분하다.
    """
    rows = []
    for f in files:
        try:
            st = os.stat(f)
        except OSError:
            continue
        rows.append("%s|%d|%d" % (f, st.st_size, int(st.st_mtime)))
    return hashlib.sha1("\n".join(rows).encode("utf-8")).hexdigest()


def _cache_load(path, stamp=None):
    """캐시 → 지문 목록. `stamp` 를 주면 원고가 그대로일 때만 돌려준다.

    `stamp=None` 은 **원고를 못 읽을 때의 구명줄**이다(아래 `read` 참고).
    """
    try:
        with open(path, encoding="utf-8") as f:
            got = json.load(f)
    except (OSError, ValueError):
        return None
    if stamp is not None and got.get("stamp") != stamp:
        return None
    out = []
    for e in got.get("entries") or ():
        # 표기(`숫자[낱말]`)만 저장해 두고 조각은 여기서 되만든다 — 조각을 통째로
        # 담으면 파일이 열 배가 된다. 번호는 어차피 붙일 때 다시 매긴다.
        parts = _split_marks(e["t"])
        out.append({"header": e.get("h", ""), "src": e.get("s", ""),
                    "parts": parts, "letters": letters(plain(parts))})
    return out or None


def _cache_save(path, stamp, entries):
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"stamp": stamp,
                       "entries": [{"h": e["header"], "s": e["src"],
                                    "t": render(e["parts"], 1)[0]}
                                   for e in entries]},
                      f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass                    # 캐시는 못 써도 조판은 굴러가야 한다


def read(paths, log=None, cache=None):
    """파일·폴더 목록 → 암기테스트 지문 목록.

    같은 내용이 docx 와 pdf 로 둘 다 있으면 **docx 를 남긴다**(표기가 원고에
    직접 적혀 있어 되만들 여지가 없다).

    `cache` 를 주면 그 파일에 결과를 담아 두고, 원고 폴더가 그대로면 다시 안
    읽는다. `리테 모음` 전체가 363개라 한 번 훑는 데 10초가 든다 — 아침에 여러
    학교를 연달아 돌릴 때 권당 10초씩 버릴 이유가 없다.
    """
    log = log or (lambda _m: None)
    files = _files(paths)
    # ⚠ 원고 폴더는 **구글드라이브**다. 안 잡히는 순간 파일이 0개가 되고,
    #   그러면 지문(指紋)이 달라져 캐시까지 버리고 **암기 TEST 가 통째로 빠진
    #   책이 조용히 나간다**(실측: 세종1 204면 → 106면, 게이트는 전부 통과).
    #   폴더를 못 읽었는데 캐시가 있으면 캐시를 쓴다 — 그리고 크게 말한다.
    if paths and not files:
        got = _cache_load(cache) if cache else None
        if got:
            log("  [리테] ⚠ 원고 폴더를 못 읽었다(구글드라이브?) — **지난번에 "
                "읽어 둔 지문 %d개**로 간다. 원고가 바뀌었다면 다시 돌릴 것" % len(got))
            return got
        log("  [리테] ⚠ 원고 폴더를 못 읽었고 캐시도 없다 — 암기 TEST 가 "
            "통째로 빠진다: %s" % ", ".join(str(x) for x in paths[:2]))
        return []
    stamp = _stamp(files)
    if cache:
        got = _cache_load(cache, stamp)
        if got is not None:
            log("  [리테] 원고 폴더(파일 %d개) 그대로 — 지난번에 읽어 둔 "
                "지문 %d개를 쓴다" % (len(files), len(got)))
            return got
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
    if cache and uniq:
        _cache_save(cache, stamp, uniq)
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
    """지문 원문 → 짝이 되는 암기테스트 항목. **내용으로만** 찾는다.

    ⚠ 닮음 비율로 고르면 안 된다. `quick_ratio` 는 글자 개수만 세므로 길이가
      비슷한 영어 글끼리는 아무 사이나 0.8 을 넘는다 — 실제로 **엉뚱한 지문이
      붙었다**(광문1 16강-03 에 다른 지문이 0.22 짜리로 들어왔다). 그래서 문턱은
      **연속 60글자가 그대로 들어 있는가**로 잡는다. 60글자면 사실상 유일하다.
    """
    need = letters(text)
    if len(need) < 60:
        return None
    head = need[:60]
    hits = [e for e in entries if head in e["letters"]]
    if hits:
        # 여러 벌이 있으면(같은 회차 원고가 두 판) 길이가 가장 가까운 것.
        return min(hits, key=lambda e: abs(len(e["letters"]) - len(need)))
    # 지문이 원고보다 긴 경우(두 지문을 한 면에 합친 판) — 원고 머리가 지문 안에.
    part = [e for e in entries
            if len(e["letters"]) >= 60 and e["letters"][:60] in need]
    if not part:
        return None
    best = max(part, key=lambda e: difflib.SequenceMatcher(
        None, need, e["letters"], autojunk=False).ratio())
    r = difflib.SequenceMatcher(None, need, best["letters"],
                                autojunk=False).ratio()
    return best if r >= MATCH_MIN else None


def _pages(row, body):
    """한 지문의 암기 TEST 두 면. **문제면과 정답면은 같은 표기를 쓴다** —
    빈칸·주황은 `data.format_memtest()` 가 `answer` 로 갈라 만든다. 정답을 두 번
    수확하면 둘 다 정답이 보이는 사고가 난다(예전에 그랬다)."""
    key = row.get("key") or row.get("pno") or row.get("label") or ""
    return [{"kind": "memtest", "answer": ans, "key": key,
             "category": row.get("category") or "",
             "body_runs": [{"t": body}]}
            for ans in (False, True)]


def _runs(rows):
    """지문 목록 → 계열(kind)이 같은 이어진 묶음. 완성본의 '단원'이 이것이다.

    코퍼스는 지문마다 `mock`(모의고사) / `label`(교과서·EBS)을 달고 있고,
    완성 포켓북은 그 경계에서 **암기 TEST 번호를 1부터 다시** 매긴다(실측:
    강동1 교과서 1~154 · 모의고사 1~1093).

    ⚠ `kind` 로 묶으면 안 된다 — 지문은 전부 `passage` 라서 책 전체가 한 묶음이
      되고, 그러면 모의고사 암기 TEST 까지 책 끝으로 몰린다. 갈래(교과서·부교재·
      모의고사)와 **단원**으로 묶는다.
    """
    out = []
    for r in rows:
        if r.get("kind") == "memtest":
            k = ("memtest",)
        else:
            k = (r.get("_rank"), r.get("category") or r.get("unit") or "")
        if out and out[-1][0] == k:
            out[-1][1].append(r)
        else:
            out.append((k, [r]))
    return out


def attach(rows, sources, log=None, place="auto", cache=None):
    """지문 목록에 암기 TEST 면을 끼워 넣는다.

    자리는 완성본을 따른다(강동1·명일2·성덕1 실측, 셋이 같다).

        auto     모의고사는 지문 바로 뒤에 두 면, 교과서는 그 단원 끝에 몰아서
        after    언제나 지문 바로 뒤
        section  언제나 단원 끝
        end      책 맨 뒤

    번호는 단원마다 1부터 이어 매긴다 — 한 면이 곧 한 지문이고, 학생은 그 면
    안에서 번호를 찾는다.

    `cache` 는 원고를 다시 안 읽기 위한 파일 자리다(`read` 참고).
    """
    log = log or (lambda _m: None)
    entries = read(sources, log, cache=cache)
    if not entries:
        log("■ 리뷰테스트 원고에서 읽어 낸 지문이 없다")
        return rows
    out, book_tail, hit, miss, total = [], [], 0, [], 0
    # 번호는 계열마다 따로 센다. 묶음(run)마다 세면 지문 순서가 흔들릴 때
    # 같은 단원이 여러 토막으로 갈려 번호가 여러 번 1로 돌아간다.
    seq = {}
    for kind, group in _runs(rows):
        rank = kind[0]
        no, sect_tail = seq.get(rank, 1), []
        for row in group:
            out.append(row)
            if kind == "memtest":
                continue
            text = _row_text(row)
            e = find(entries, text)
            if e is None:
                # ⚠ 짤지문(18·19·25~28)과 장문(43~45)은 **리뷰테스트 원고가
                #   원래 없다**(사용자 지시). 빠진 게 아니라 없는 것이라
                #   「없음」 목록에 올리면 멀쩡한 책이 매번 운다.
                if not (row.get("short") or row.get("split")):
                    miss.append(row.get("key") or row.get("label") or "?")
                continue
            body, no = render(cut(e["parts"], text), no)
            pages = _pages(row, body)
            hit += 1
            if place == "end":
                book_tail += pages
            elif place == "after" or (
                    place == "auto" and kind[0] == 2):   # 모의고사만 지문 바로 뒤
                out += pages
            else:
                sect_tail += pages
        total += no - seq.get(rank, 1)
        seq[rank] = no
        out += sect_tail
    out += book_tail
    log("■ 암기 TEST — 지문 %d개에 붙였다(빈칸 %d개, 원고 %d지문)"
        % (hit, total, len(entries)))
    if miss:
        log("  [암기TEST 없음] %d지문 — %s" % (len(miss), ", ".join(miss[:12])))
    return out
