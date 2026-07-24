"""HWPX -> rich paragraph IR.

기존 core.extract 는 run 단위로 밑줄(ul)만 보존한다. 시험지 조판은 그것만으로
부족하다 — 원고의 네모(글자 테두리), 굵게, 위/아래 첨자, 글자 크기까지 살려야
'사람 손 없이' 재현이 성립한다. 여기서는 charPr 를 전부 해석해 run 속성으로 내린다.

핵심 신호 (q35 원고 실측):
  - underline type != NONE                 -> 밑줄
  - borderFillIDRef 가 '테두리 있는' 것     -> 네모 (어휘 (A)/(B)/(C) 선택지)
  - bold / italic / offset(첨자) / height   -> 그대로
"""
import re
import unicodedata
import zipfile

NS_T = re.compile(r"<hp:t>(.*?)</hp:t>", re.S)
# <hp:t> 안에는 탭 같은 요소가 중첩된다: <hp:t><hp:tab .../>(A) ...</hp:t>
# 걷어내지 않으면 원시 마크업이 그대로 본문에 인쇄된다.
_TAB_EL = re.compile(r"<hp:tab\b[^>]*/?>")
_ANY_EL = re.compile(r"<[^>]+>")

# 원고에 섞여 들어오는 이형 문자 -> 표준 문자.
# (소프트하이픈/수정자 마이너스가 단어 중간에 박혀 있는 사례가 실제로 있음)
CHAR_FIX = {
    "\u00ad": "-",   # SOFT HYPHEN   (multi\u00addimensional -> multi-dimensional)
    "\u02d7": "-",   # MODIFIER LETTER MINUS (self\u02d7expression)
    "\u2010": "-", "\u2011": "-", "\u2012": "-",   # hyphen / nb-hyphen / figure dash
    "\u2043": "-",   # HYPHEN BULLET
    "\u2717": "\u00d7",       # \u2717 -> \u00d7 (Noto Sans CJK KR \uae00\ub9ac\ud504 \uc5c6\uc74c)
    "\U000f003b": "\u2b07",   # HWP \uc0ac\uc124\uc601\uc5ed \uc694\uc57d \ud654\uc0b4\ud45c
}
_FIX_RE = re.compile("|".join(re.escape(k) for k in CHAR_FIX))


def fix_chars(s):
    return _FIX_RE.sub(lambda m: CHAR_FIX[m.group(0)], s)


# HWP 페이지 푸터가 본문 흐름에 유출된 조각 (원고 결함) — 지문 중간에 박힌다.
# 예: "2022학년도 6월 전국연합학력평가 정답 및 해설 고2 11"
_RUNNING_FOOTER = re.compile(
    r"\s*\d{4}학년도\s*\d{1,2}월\s*전국연합학력평가\s*정답\s*및\s*해설\s*고\d\s*\d*\s*")


def strip_footer(s):
    return _RUNNING_FOOTER.sub(" ", s)


def _unescape(s):
    return (s.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'")
             .replace("&amp;", "&"))


def _parse_char_props(header_xml):
    """charPr id -> {ul, box, bold, italic, sup, sub, height}"""
    # 테두리 없는 borderFill id 집합을 먼저 구한다.
    plain_bf = set()
    for bf in re.findall(r"<hh:borderFill\b.*?</hh:borderFill>", header_xml, re.S):
        bid = re.search(r'id="(\d+)"', bf)
        if not bid:
            continue
        strokes = re.findall(r'<hh:(?:leftBorder|rightBorder|topBorder|bottomBorder)'
                             r'[^>]*type="([A-Z]+)"', bf)
        if not strokes or all(s == "NONE" for s in strokes):
            plain_bf.add(bid.group(1))

    props = {}
    for c in re.findall(r"<hh:charPr\b.*?</hh:charPr>", header_xml, re.S):
        cid = re.search(r'id="(\d+)"', c).group(1)
        ul = re.search(r'<hh:underline[^>]*type="([A-Z]+)"', c)
        bf = re.search(r'borderFillIDRef="(\d+)"', c)
        off = re.search(r'<hh:offset[^>]*hangul="(-?\d+)"', c)
        h = re.search(r'height="(\d+)"', c)
        o = int(off.group(1)) if off else 0
        props[cid] = {
            "ul": bool(ul and ul.group(1) != "NONE"),
            "box": bool(bf and bf.group(1) not in plain_bf),
            "bold": "<hh:bold" in c,
            "italic": "<hh:italic" in c,
            "sup": o > 0,
            "sub": o < 0,
            "height": int(h.group(1)) / 100.0 if h else 10.0,
        }
    return props


def extract(path):
    """HWPX -> [{"text", "runs":[{"t", ...attrs}]}] (문서 순서, 표/각주 포함 안 함)"""
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        header = z.read("Contents/header.xml").decode("utf-8")
        secs = sorted(n for n in names
                      if re.match(r"Contents/section\d+\.xml$", n))
        body = "".join(z.read(n).decode("utf-8") for n in secs)

    props = _parse_char_props(header)
    base = {"ul": False, "box": False, "bold": False, "italic": False,
            "sup": False, "sub": False, "height": 10.0}

    out = []
    for p in re.findall(r"<hp:p\b.*?</hp:p>", body, re.S):
        p = re.sub(r"<hp:linesegarray>.*?</hp:linesegarray>", "", p, flags=re.S)
        runs = []
        for m in re.finditer(r'<hp:run charPrIDRef="(\d+)".*?</hp:run>', p, re.S):
            cid, chunk = m.group(1), m.group(0)
            attrs = props.get(cid, base)
            # 중첩 요소 제거는 반드시 _unescape 앞에서 (원고의 &lt; 를 태그로
            # 오인하지 않도록). 탭은 공백으로 살린다.
            txt = "".join(
                _unescape(_ANY_EL.sub("", _TAB_EL.sub(" ", t)))
                for t in NS_T.findall(chunk))
            if not txt:
                continue
            txt = strip_footer(fix_chars(unicodedata.normalize("NFC", txt)))
            if runs and all(runs[-1][k] == attrs[k] for k in base):
                runs[-1]["t"] += txt
            else:
                r = dict(attrs)
                r["t"] = txt
                runs.append(r)
        out.append({"text": "".join(r["t"] for r in runs), "runs": runs})
    return out


if __name__ == "__main__":
    import sys, json
    paras = extract(sys.argv[1])
    print(json.dumps(paras, ensure_ascii=False, indent=1))
