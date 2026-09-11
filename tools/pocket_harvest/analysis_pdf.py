# -*- coding: utf-8 -*-
"""분석본 **PDF** → [지문]. 반환 모양은 `analysis.read_book()` 과 같다.

일부 분석본은 인디자인이 아니라 **코드 조판**(크롬 → pdf-lib)으로 나온다.
IDML 이 없고 PDF 뿐이다(명일2 `분석본05(추가 읽기자료)` 실측). 글자·색·칠이
PDF 에 그대로 남아 있으므로 **지면에서 되읽는다**:

  본문      가장 흔한 크기의 영어 글자(9pt). 글자 사이 틈으로 낱말을 가른다.
  색        글자색의 **색상각**으로 파랑/빨강을 가른다(값을 외우지 않는다).
  구문분석  본문 줄 바로 아래 작은 글자. **가운데가 맞는 낱말(들)** 에 루비로
            건다 — 분석본은 주석을 낱말 가운데에 건다(인디자인과 같다).
  형광펜    글줄 높이의 칠 이미지 → 덮인 낱말. 색은 이미지 픽셀에서 읽는다.
  물결      글자 밑 가는 이미지 → 그 낱말에 물결.
  해석      본문보다 작은 글자 중 주석 색이 아닌 줄. 문장 번호(흰 숫자) 사이에
            온 것을 그 문장의 해석으로 짝짓는다.
  주제/요약 흰 글자 딱지 오른쪽 글.
  핵심기출  **깨끗한 지문 사본**이 들어 있다 → 수확한 지문과 글자를 대 본다
            (`source.clean_match`). G-P13 도 이 사본으로 잘림을 본다.
  VOCA      머리 칸(`중요어휘|의미`)의 x 로 열을 가른다.

⚠ 인디자인이 만든 PDF 는 여기서 읽지 않는다 — IDML 을 내보내야 한다. 구조가
  스타일 이름에 있어서 IDML 쪽이 정확하다(`is_code_typeset`).
"""
import colorsys
import os
import re
import unicodedata
from collections import Counter

try:
    import fitz
except ImportError:          # pragma: no cover
    fitz = None


def nfc(s):
    return unicodedata.normalize("NFC", s or "")


_WS = re.compile(r"\s+")
_HAN = re.compile("[가-힣]")
_LAT = re.compile("[A-Za-z]")
_ALNUM = re.compile("[A-Za-z0-9]")
_WHITE = 0xFFFFFF

# 코드 조판이 **아닌** 것 — 이런 PDF 는 원본(IDML)이 따로 있다
_NOT_CODE = ("indesign", "illustrator", "photoshop", "distiller", "hancom",
             "hwp", "quark")


def _sq(s):
    return _WS.sub(" ", nfc(s)).strip()


def _rgb(c):
    return ((c >> 16) & 255, (c >> 8) & 255, c & 255)


def _hsv(rgb):
    r, g, b = (v / 255.0 for v in rgb)
    h, s, v = colorsys.rgb_to_hsv(r, g, b)
    return h * 360.0, s, v


# ── 파일 판정 ───────────────────────────────────────────────
def producer(path):
    try:
        m = fitz.open(path).metadata or {}
    except Exception:
        return ""
    return ("%s | %s" % (m.get("producer") or "", m.get("creator") or "")).strip()


def is_code_typeset(path):
    """코드 조판 PDF 인가 — 인디자인·일러스트 등이 만든 PDF 가 아닌가."""
    if fitz is None or not str(path).lower().endswith(".pdf"):
        return False
    p = producer(path).lower()
    if not p.strip(" |"):
        return False
    return not any(k in p for k in _NOT_CODE)


# ── 글자·그림 모으기 ─────────────────────────────────────────
def _chars(page):
    out, sid = [], 0
    raw = page.get_text("rawdict", flags=fitz.TEXT_PRESERVE_WHITESPACE
                        | fitz.TEXT_MEDIABOX_CLIP)
    for b in raw.get("blocks", ()):
        if b.get("type") != 0:
            continue
        for ln in b["lines"]:
            for s in ln["spans"]:
                sid += 1
                for c in s["chars"]:
                    x0, y0, x1, y1 = c["bbox"]
                    out.append({"c": nfc(c["c"]), "x0": x0, "y0": y0,
                                "x1": x1, "y1": y1, "oy": c["origin"][1],
                                "size": round(s["size"], 1),
                                "color": s["color"], "span": sid})
    return out


def _images(page):
    """칠 이미지 → [{x0,y0,x1,y1,rgb}]. 색은 이미지 가운데 픽셀에서 읽는다."""
    out = []
    for b in page.get_text("dict").get("blocks", ()):
        if b.get("type") != 1:
            continue
        x0, y0, x1, y1 = b["bbox"]
        rgb = None
        try:
            pm = fitz.Pixmap(b["image"])
            if pm.colorspace and pm.colorspace.n != 3:
                pm = fitz.Pixmap(fitz.csRGB, pm)
            if pm.width and pm.height:
                rgb = tuple(pm.pixel(pm.width // 2, pm.height // 2)[:3])
        except Exception:
            rgb = None
        out.append({"x0": x0, "y0": y0, "x1": x1, "y1": y1, "rgb": rgb})
    return out


def _lines(cs, tol=1.2):
    """글자 → 기준선이 같은 줄. [{oy, cs}] (위에서 아래로)."""
    out = []
    for c in sorted(cs, key=lambda c: (c["oy"], c["x0"])):
        if out and abs(c["oy"] - out[-1]["oy"]) <= tol:
            out[-1]["cs"].append(c)
        else:
            out.append({"oy": c["oy"], "cs": [c]})
    for ln in out:
        ln["cs"].sort(key=lambda c: c["x0"])
        ln["x0"] = min(c["x0"] for c in ln["cs"])
        ln["x1"] = max(c["x1"] for c in ln["cs"])
    return out


def _gap(a, b):
    """두 글자 사이가 띄어쓰기인가 — 틈이 글자 크기의 12% 를 넘으면."""
    if a["c"] == " " or b["c"] == " ":
        return True
    return b["x0"] - a["x1"] > 0.12 * max(a["size"], b["size"])


def _text(cs):
    out, prev = [], None
    for c in sorted(cs, key=lambda c: c["x0"]):
        if prev is not None and _gap(prev, c) and c["c"] != " ":
            out.append(" ")
        out.append(c["c"])
        prev = c
    return _sq("".join(out))


def _join_lines(texts):
    """줄 → 글. 줄 끝 하이픈은 복합어로 보고 붙인다(띄우지 않는다)."""
    out = ""
    for t in texts:
        t = t.strip()
        if not t:
            continue
        if out and out.endswith("-") and _LAT.match(t[:1] or " "):
            out += t
        else:
            out = (out + " " + t) if out else t
    return out


# ── 한글 줄 잇기 ─────────────────────────────────────────────
# 해석은 **낱말 한가운데서** 줄이 바뀐다(`관심을 기 / 울이는`·`일자 / 리를`).
# 줄 끝에 띄어쓰기 글리프가 안 남아서 PDF 만으로는 `그는 / 이해하기`(띄움)와
# 가를 수 없다(줄 끝 x 도 두 경우가 겹친다 — 실측). 그래서 **우리 코퍼스의
# 해석 글**에서 어느 쪽이 실제로 쓰였는지 본다:
#   ① 어절 빈도 — `기울이는` 이 있고 `기`·`울이는` 이 따로는 드물면 붙인다.
#   ② ①이 비기면 경계 음절쌍 — 그 두 음절이 어절 **안**에서 더 자주 붙어
#      나오는가, 띄어쓰기 **너머**로 더 자주 나오는가.
KO_DIRS = []                 # 포켓북이 코퍼스 폴더를 넣어 준다
_KO = None
_KO_STRIP = re.compile(r"[^가-힣A-Za-z0-9]")


def _ko_eat(text, words, inb, crs):
    ws = [_KO_STRIP.sub("", w) for w in (text or "").split()]
    for k, w in enumerate(ws):
        if not _HAN.search(w):
            continue
        words[w] += 1
        for x, y in zip(w, w[1:]):
            inb[x + y] += 1
        if k + 1 < len(ws) and ws[k + 1]:
            crs[w[-1] + ws[k + 1][0]] += 1


def _ko_dir_model(d):
    """코퍼스 폴더 하나 → (어절, 어절 안 음절쌍, 띄어쓰기 너머 음절쌍).

    ⚠ 코퍼스는 iCloud 폴더라 1,373개를 매번 열면 몇 분 걸린다(실측) — 파일
      목록의 **수·최종 수정 시각**이 같으면 `_cache/ko_model.json` 을 쓴다.
      stat 은 내용을 내려받지 않는다.
    """
    import json
    fs = [e for e in os.scandir(d)
          if e.name.endswith(".json") and not e.name.startswith("_")]
    sig = "%d:%d" % (len(fs), int(max((e.stat().st_mtime for e in fs),
                                      default=0)))
    cache = os.path.join(os.path.dirname(os.path.normpath(d)), "_cache",
                         "ko_model.json")
    try:
        with open(cache, encoding="utf-8") as fh:
            c = json.load(fh)
        if c.get("sig") == sig and c.get("dir") == os.path.normpath(d):
            return Counter(c["words"]), Counter(c["inb"]), Counter(c["crs"])
    except Exception:
        pass
    words, inb, crs = Counter(), Counter(), Counter()
    for e in fs:
        try:
            with open(e.path, encoding="utf-8") as fh:
                j = json.load(fh)
        except Exception:
            continue
        for k in ("translation_text", "topic_ko"):
            if isinstance(j.get(k), str):
                _ko_eat(j[k], words, inb, crs)
    try:
        os.makedirs(os.path.dirname(cache), exist_ok=True)
        with open(cache, "w", encoding="utf-8") as fh:
            json.dump({"sig": sig, "dir": os.path.normpath(d), "words": words,
                       "inb": inb, "crs": crs}, fh, ensure_ascii=False)
    except Exception:
        pass
    return words, inb, crs


def _ko_model():
    global _KO
    if _KO is None:
        words, inb, crs = Counter(), Counter(), Counter()
        dirs = list(KO_DIRS) or [os.path.join(
            os.environ.get("STUDIO") or os.path.expanduser(
                "~/Documents/작업/Y.ONE STUDIO"), "조판", "교재", "포켓북", "_corpus")]
        for d in dirs:
            if os.path.isdir(d):
                w, i, c = _ko_dir_model(d)
                words.update(w)
                inb.update(i)
                crs.update(c)
        _KO = (words, inb, crs)
    return _KO


def _join_ko(lines, notes=None):
    """해석 줄 → 글. 한글끼리 만나는 줄 경계만 판정하고 나머지는 띄운다."""
    words, inb, crs, _eat = _ko_model()
    out = ""
    for t in lines:
        t = t.strip()
        if not t:
            continue
        if not out:
            out = t
            continue
        a = out.split(" ")[-1]
        b = t.split(" ")[0]
        a0, b0 = _KO_STRIP.sub("", a), _KO_STRIP.sub("", b)
        if (not a0 or not b0 or a != a0 + a[len(a0):] or not _HAN.match(a0[-1])
                or not _HAN.match(b0[0]) or a[-1:] != a0[-1:]
                or b[:1] != b0[:1]):
            out += " " + t                # 문장부호가 끼면 띄운다
            continue
        joined = words.get(a0 + b0, 0)
        sep = min(words.get(a0, 0), words.get(b0, 0))
        if joined != sep:
            glue = joined > sep
            how = "어절"
        else:
            pair = a0[-1] + b0[0]
            glue = inb.get(pair, 0) > crs.get(pair, 0)
            how = "음절쌍 %d:%d" % (inb.get(pair, 0), crs.get(pair, 0))
        if notes is not None and how != "어절":
            notes.append("줄 경계 '%s|%s' → %s (%s)"
                         % (a0, b0, "붙임" if glue else "띄움", how))
        out += t if glue else " " + t
    return out


# ── 색 → 뜻 ─────────────────────────────────────────────────
def _mark_of(color):
    """글자색 → blue/red/None. 무채색(먹·회색)은 None. 모르는 색은 'other'."""
    h, s, v = _hsv(_rgb(color))
    if s < 0.25 or v < 0.2:
        return None
    if 180 <= h <= 265:
        return "blue"
    if h >= 320 or h <= 20:
        return "red"
    return "other"


# 형광펜 이름 → 색상각. 이름은 idml.HL_NAME 과 같은 벌이다.
_HL_HUE = {"yellow": 52, "orange": 30, "mint": 165, "sky": 210,
           "violet": 265, "pink": 335}


def _hl_of(rgb):
    if not rgb:
        return None
    h, s, v = _hsv(rgb)
    if s < 0.08:
        return None                      # 흰·회색 — 칠이 아니다

    def d(a, b):
        x = abs(a - b) % 360
        return min(x, 360 - x)
    return min(_HL_HUE, key=lambda k: d(h, _HL_HUE[k]))


# ── 낱말 ────────────────────────────────────────────────────
def _tokens(line_cs):
    """본문 한 줄 → 조각. 틈에서 끊고, 같은 낱말 안이라도 **색이 바뀌면** 끊는다
    (`puzzling` 빨강 + `.` 먹). 조각마다 앞이 띄어쓰기였는지(`sp`)를 둔다."""
    out, prev = [], None
    for c in line_cs:
        if c["c"] == " ":
            prev = c
            continue
        gap = prev is not None and _gap(prev, c)
        if (out and not gap and prev is not None and prev["c"] != " "
                and _mark_of(prev["color"]) == _mark_of(c["color"])):
            t = out[-1]
            t["t"] += c["c"]
            t["x1"] = max(t["x1"], c["x1"])
            t["y0"] = min(t["y0"], c["y0"])
            t["y1"] = max(t["y1"], c["y1"])
        else:
            out.append({"t": c["c"], "x0": c["x0"], "x1": c["x1"],
                        "y0": c["y0"], "y1": c["y1"], "oy": c["oy"],
                        "mark": _mark_of(c["color"]), "color": c["color"],
                        "sp": bool(out) and gap, "hl": None, "wave": False,
                        "ruby": None})
        prev = c
    return out


_RUBY_TOL = 1.5          # 주석 가운데 ↔ 낱말 가운데 허용 어긋남(pt)


def _attach_ruby(toks, label, notes):
    """주석 하나 → 가운데가 맞는 낱말 구간. **낱말 수가 적은 것**부터 본다.

    ⚠ 오차가 가장 작은 구간을 고르면 안 된다. `zero` 밑 `V1` 의 가운데가
      넉 낱말 구간 `likely zero in on` 의 가운데와도 **정확히** 같아서(249.0)
      그쪽이 이겼다(실측). 허용 오차 안이면 낱말 하나를 먼저 쓴다.
    ⚠ 분석본은 붙은 문장부호까지 받침으로 잡는다(`graduating,` 가운데 = 주석
      가운데). 가운데는 문장부호를 넣어 재고, 루비는 낱말에만 건다.
    """
    cx = (label["x0"] + label["x1"]) / 2.0
    best = None
    n = len(toks)
    for i in range(n):
        if not _ALNUM.search(toks[i]["t"]):
            continue
        for j in range(i, min(n, i + 8)):
            # 뒤에 붙은 문장부호(띄어쓰기 없이)까지는 받침에 넣어 잰다
            if not _ALNUM.search(toks[j]["t"]) and toks[j]["sp"]:
                break
            a, b = toks[i]["x0"], toks[j]["x1"]
            if not (a - 1.0 <= cx <= b + 1.0):
                continue
            d = abs((a + b) / 2.0 - cx)
            words = sum(1 for t in toks[i:j + 1] if _ALNUM.search(t["t"]))
            key = (0 if d <= _RUBY_TOL else 1, words, d)
            if best is None or key < best[0]:
                best = (key, i, j)
    if best is None:                       # 빈칸 밑 주석 — 가장 가까운 낱말
        cand = [k for k in range(n) if _ALNUM.search(toks[k]["t"])]
        if not cand:
            return None
        k = min(cand, key=lambda k: abs((toks[k]["x0"] + toks[k]["x1"]) / 2 - cx))
        best = ((1, 1, 99.0), k, k)
    (tier, _w, d), i, j = best
    while j > i and not _ALNUM.search(toks[j]["t"]):
        j -= 1                             # 루비는 낱말까지만
    if tier:
        notes.append("주석 '%s' 가운데가 낱말과 %.1fpt 어긋남" % (label["t"], d))
    return i, j


# ── 분석 면 ─────────────────────────────────────────────────
def _body_size(cs):
    cnt = Counter(c["size"] for c in cs if _LAT.match(c["c"]))
    return cnt.most_common(1)[0][0] if cnt else None


def _analysis_page(page, cs, imgs, notes):
    """분석 면 → {head, title_ko, sents:[{runs, en, ko}], grammar} 또는 None."""
    H = page.rect.height
    big = [c for c in cs if c["size"] >= 14 and c["y1"] < H * 0.12]
    head = _text(big)
    head_x1 = max((c["x1"] for c in big), default=0)
    head_y1 = max((c["y1"] for c in big), default=0)
    foot = H * 0.93
    reg = [c for c in cs if c["y0"] > head_y1 + 2 and c["oy"] < foot]
    bs = _body_size(reg)
    if not bs:
        return None
    body = [c for c in reg if abs(c["size"] - bs) < 0.25 and c["color"] != _WHITE]
    if sum(1 for c in body if _LAT.match(c["c"])) < 60:
        return None
    col_l = min(c["x0"] for c in body)
    col_r = max(c["x1"] for c in body)
    # 한글 제목은 머리 띠 **안**에서만 — 띠 밑 옆 단(GRAMMAR POINT)이 섞인다
    title_ko = _text([c for c in cs if c["y1"] <= head_y1 + 4 and c["size"] < 14
                      and c["x0"] > head_x1 and c["color"] != _WHITE]) if big else ""

    side = [c for c in reg if c["x0"] > col_r + 6]
    main = [c for c in reg if c["x1"] <= col_r + 6]
    badges = _lines([c for c in main if c["color"] == _WHITE
                     and c["x1"] < col_l + 1 and c["c"].isdigit()])
    blines = _lines(body)
    small = [c for c in main if c["size"] < bs - 0.25 and c["color"] != _WHITE]

    def above(oy):
        ups = [b for b in blines if b["oy"] < oy - 0.5]
        return ups[-1] if ups else None

    # 주석 색 = 본문 줄 **바로 밑**(1.6줄 안)에 가장 많이 오는 작은 글자의 색
    near = Counter()
    for c in small:
        b = above(c["oy"])
        if b and c["oy"] - b["oy"] < 1.6 * bs:
            near[c["color"]] += 1
    anno = near.most_common(1)[0][0] if near else None
    labels_cs = [c for c in small if c["color"] == anno]
    trans_cs = [c for c in small if c["color"] != anno]

    # 본문 줄 → 조각, 그림(형광펜·물결) 얹기
    for b in blines:
        b["toks"] = _tokens(b["cs"])
        for t in b["toks"]:
            cx = (t["x0"] + t["x1"]) / 2.0
            th = max(t["y1"] - t["y0"], 1.0)
            for im in imgs:
                if not (im["x0"] - 0.6 <= cx <= im["x1"] + 0.6):
                    continue
                ih = im["y1"] - im["y0"]
                if ih >= 0.6 * bs:
                    ov = min(t["y1"], im["y1"]) - max(t["y0"], im["y0"])
                    if ov >= 0.5 * th:
                        t["hl"] = _hl_of(im["rgb"]) or t["hl"]
                elif ih > 0.3 and t["oy"] - 0.3 * bs <= im["y0"] <= t["oy"] + 0.6 * bs:
                    t["wave"] = True

    # 주석 → 낱말. 한 본문 줄 밑에 주석 줄이 둘이면 두 번째는 **아랫줄**(dn2)
    #   — `zero` 밑 `V1` 아래에 `this variability` 가 한 줄 더 온다(실측).
    lab_lines = _lines(labels_cs)
    first_row = {}
    for lab_line in lab_lines:
        b = above(lab_line["oy"])
        if b is not None:
            first_row.setdefault(id(b), lab_line["oy"])
    for lab_line in lab_lines:
        b = above(lab_line["oy"])
        if b is None:
            continue
        row2 = lab_line["oy"] - first_row[id(b)] > 0.4 * bs
        # 한 주석 = 한 span. 같은 span 안이라도 멀리 떨어지면 나눈다.
        groups = []
        for c in lab_line["cs"]:
            if (groups and groups[-1]["span"] == c["span"]
                    and c["x0"] - groups[-1]["x1"] < 1.0 * c["size"]):
                g = groups[-1]
                g["cs"].append(c)
                g["x1"] = max(g["x1"], c["x1"])
            else:
                groups.append({"span": c["span"], "cs": [c], "x0": c["x0"],
                               "x1": c["x1"]})
        for g in groups:
            g["t"] = _text(g["cs"])
            if not g["t"]:
                continue
            hit = _attach_ruby(b["toks"], g, notes)
            if hit is None:
                continue
            i, j = hit
            tk = b["toks"][i]
            if row2:
                if tk.get("ruby2"):
                    tk["ruby2"] += " " + g["t"]
                else:
                    tk["ruby2"] = g["t"]
                continue
            if tk["ruby"]:
                # 같은 낱말 같은 줄에 주석이 둘 — 떨어져 있던 것을 잇는다
                tk["ruby"] = tk["ruby"] + " " + g["t"]
                notes.append("주석 둘을 한 낱말에 이음 '%s'" % tk["ruby"])
            else:
                tk["ruby"] = g["t"]
                tk["ruby_end"] = j

    # 문장 = 흰 번호 사이. 번호가 없으면 면 전체가 한 문장.
    starts = [bd["oy"] for bd in badges]

    def sent_of(oy):
        k = -1
        for i, s in enumerate(starts):
            if s <= oy + 1.5:
                k = i
        return max(k, 0)
    nsent = max(len(starts), 1)
    sents = [{"lines": [], "ko": []} for _ in range(nsent)]
    for b in blines:
        sents[sent_of(b["oy"])]["lines"].append(b)
    for tl in _lines(trans_cs):
        if tl["x0"] < col_l - 2:
            continue
        sents[sent_of(tl["oy"])]["ko"].append(_text(tl["cs"]))

    out = []
    for s in sents:
        if not s["lines"]:
            continue
        runs = _runs_of(s["lines"])
        en = "".join(r["t"] for r in runs).strip()
        out.append({"runs": runs, "en": _sq(en),
                    "ko": _sq(_join_ko(s["ko"], notes))})

    # GRAMMAR POINT — 옆 단. 머리표(작은 색 글자 `*`)가 항목 머리다.
    grammar = []
    if side:
        ss = _body_size(side) or 7.0
        bullets = sorted((c for c in side if c["c"].strip() in ("*", "•", "·")
                          and c["size"] < ss), key=lambda c: c["oy"])
        bset = set(id(c) for c in bullets)
        tl = _lines([c for c in side if id(c) not in bset])
        for k, bl in enumerate(bullets):
            lo = bl["oy"] - 2.5
            hi = bullets[k + 1]["oy"] - 2.5 if k + 1 < len(bullets) else foot
            txt = _join_ko([_text(l["cs"]) for l in tl if lo <= l["oy"] < hi])
            if txt:
                grammar.append(txt)
    return {"head": head, "title_ko": title_ko, "sents": out,
            "grammar": grammar, "page": page.number + 1}


def _runs_of(lines):
    """본문 줄들 → 런. 줄 사이는 띄어 쓴다(줄 끝 하이픈이면 붙인다)."""
    runs = []

    def blank(hl=None):
        return {"t": " ", "style": "", "mark": None, "hl": hl, "ruby": None,
                "slot": None}
    prev_tok = None
    for li, b in enumerate(lines):
        toks = b["toks"]
        k = 0
        while k < len(toks):
            t = toks[k]
            j = t.get("ruby_end")
            first = (k == 0)
            if runs:
                need = (t["sp"] if not first
                        else not (prev_tok and prev_tok["t"].endswith("-")))
                if need:
                    same = (prev_tok and prev_tok["hl"] and
                            prev_tok["hl"] == t["hl"])
                    runs.append(blank(t["hl"] if same else None))
            if j is not None and j > k:
                grp = toks[k:j + 1]
                marks = set(x["mark"] for x in grp if _ALNUM.search(x["t"]))
                text = ""
                for q, x in enumerate(grp):
                    text += ((" " if q and x["sp"] else "") + x["t"])
                if len(marks) <= 1:
                    m0 = grp[0]["mark"] if _ALNUM.search(grp[0]["t"]) else None
                    r = {"t": text, "style": "",
                         "mark": m0 if m0 in ("blue", "red") else None,
                         "hl": t["hl"], "ruby": t["ruby"], "slot": "dn",
                         "wave": any(x["wave"] for x in grp)}
                    _put_row2(r, t)
                    runs.append(r)
                    prev_tok = grp[-1]
                    k = j + 1
                    continue
                # 색이 섞인 구간 — 루비는 가운데 낱말 하나에만
                mid = grp[len(grp) // 2]
                mid["ruby"], mid["ruby_end"] = t["ruby"], None
                t["ruby"] = None if mid is not t else t["ruby"]
                for q, x in enumerate(grp):
                    if q and x["sp"]:
                        runs.append(blank(x["hl"] if x["hl"] == grp[q - 1]["hl"]
                                          else None))
                    runs.append(_run(x))
                prev_tok = grp[-1]
                k = j + 1
                continue
            runs.append(_run(t))
            prev_tok = t
            k += 1
    return runs


def _run(t):
    m = t["mark"] if t["mark"] in ("blue", "red") else None
    r = {"t": t["t"], "style": "", "mark": m, "hl": t["hl"],
         "ruby": t["ruby"], "slot": "dn" if t["ruby"] else None,
         "wave": bool(t["wave"])}
    _put_row2(r, t)
    return r


def _put_row2(r, t):
    """아랫줄 주석. 윗줄이 없으면 그 자리(루비)에 `dn2` 로, 있으면 `ruby2` 로."""
    if not t.get("ruby2"):
        return
    if r.get("ruby"):
        r["ruby2"] = t["ruby2"]
    else:
        r["ruby"], r["slot"] = t["ruby2"], "dn2"


# ── 정리 면(주제·요약·기출·VOCA) ─────────────────────────────
def _summary_page(page, cs):
    H = page.rect.height
    foot = H * 0.93
    cs = [c for c in cs if c["oy"] < foot]
    chips = [l for l in _lines([c for c in cs if c["color"] == _WHITE])]
    chip = {}
    for l in chips:
        t = _text(l["cs"]).replace(" ", "")
        if t in ("주제", "요약") and t not in chip:
            chip[t] = l
    if not chip:
        return None
    ink = [c for c in cs if c["color"] != _WHITE]
    lines = _lines(ink)
    got = {"topic": "", "summary": "", "exam": [], "clean": "", "voca": []}
    order = sorted(chip.items(), key=lambda kv: kv[1]["oy"])
    for n, (name, cl) in enumerate(order):
        lo = cl["oy"] - 2
        hi = order[n + 1][1]["oy"] - 2 if n + 1 < len(order) else foot
        buf = []
        for l in lines:
            if l["oy"] < lo:
                continue
            if l["oy"] >= hi or l["x0"] < cl["x1"] - 1:
                break
            buf.append(_text(l["cs"]))
        got["topic" if name == "주제" else "summary"] = _join_lines(buf)

    # 핵심기출 — 요약 아래 왼쪽 상자. 영어가 대부분인 줄이 이어진 곳이 사본이다.
    last = order[-1][1]
    mid = page.rect.width * 0.5
    ex = [l for l in lines if l["oy"] > last["oy"] + 20 and l["x1"] < mid + 10]
    # 기출 영역은 VOCA 머리 전까지
    head = _voca_header(lines)
    if head is not None:
        ex = [l for l in ex if l["oy"] < head["oy"] - 30]
    ex_txt = [_text(l["cs"]) for l in ex]
    got["exam"] = [t for t in ex_txt if t]
    run, best = [], []
    for t in ex_txt:
        lat = len(_LAT.findall(t))
        if lat >= 0.6 * max(1, len(re.sub(r"\s", "", t))):
            run.append(t)
        else:
            if len(" ".join(run)) > len(" ".join(best)):
                best = run
            run = []
    if len(" ".join(run)) > len(" ".join(best)):
        best = run
    got["clean"] = _join_lines(best)

    if head is not None:
        cols = head["cols"]
        for l in lines:
            if l["oy"] <= head["oy"] + 1:
                continue
            if any(c["color"] == head["color"] for c in l["cs"]):
                continue
            cells = [[] for _ in cols]
            for c in l["cs"]:
                k = max([i for i, x in enumerate(cols) if x - 3 <= c["x0"]] or [0])
                cells[k].append(c)
            txt = [_text(x) for x in cells]
            for i in range(0, len(cols) - 1, 2):
                w, ko = txt[i], txt[i + 1]
                if w or ko:
                    if len(_HAN.findall(w)) > len(_HAN.findall(ko)) and ko:
                        w, ko = ko, w
                    got["voca"].append({"w": w, "ko": ko})
    return got


def _voca_header(lines):
    """VOCA 머리 줄 — 칸이 넷 이상이고 전부 먹 아닌 한 색의 작은 글자인 줄."""
    for l in lines:
        cols = set(c["color"] for c in l["cs"] if c["c"].strip())
        if len(cols) != 1:
            continue
        col = cols.pop()
        if _mark_of(col) is not None or col in (_WHITE, 0x231F20, 0):
            continue
        if max(c["size"] for c in l["cs"]) > 6.5:
            continue
        cells, prev = [], None
        for c in l["cs"]:
            if not c["c"].strip():
                continue
            if prev is None or c["x0"] - prev["x1"] > 2.0 * c["size"]:
                cells.append(c["x0"])
            prev = c
        if len(cells) >= 4:
            return {"oy": l["oy"], "cols": cells, "color": col}
    return None


# ── 책 ──────────────────────────────────────────────────────
_RE_HEADNO = re.compile(r"^(.*?)\s*[\(（]\s*(\d{1,3})\s*[\)）]\s*$")


def _label(head):
    """머리말 → (라벨, 챕터, 번호). `영어 독해와 작문 추가 읽기 자료 (1)`."""
    m = _RE_HEADNO.match(head or "")
    if not m:
        return head, "", ""
    return head, m.group(1).strip(), m.group(2)


def read_book(path):
    """분석본 PDF → [지문] (analysis.read_book 과 같은 모양)."""
    doc = fitz.open(path)
    base = nfc(os.path.basename(path))
    units, cur = [], None
    for page in doc:
        cs = _chars(page)
        notes = []
        # 정리 면을 **먼저** 가린다 — 기출 상자의 깨끗한 지문 사본(7.5pt 영어)이
        # 분석 면처럼 보여 본문 뒤에 통째로 붙었다(실측).
        s = _summary_page(page, cs)
        if s:
            if cur is not None and cur["sum"] is None:
                cur["sum"] = s
                cur["pages"].append(str(page.number + 1))
            continue
        a = _analysis_page(page, cs, _images(page), notes)
        if a:
            if cur is None or (a["head"] and a["head"] != cur["head"]):
                cur = {"head": a["head"], "title_ko": a["title_ko"],
                       "sents": [], "grammar": [], "pages": [], "notes": [],
                       "sum": None}
                units.append(cur)
            cur["sents"] += a["sents"]
            cur["grammar"] += a["grammar"]
            cur["pages"].append(str(a["page"]))
            cur["notes"] += notes
    return [_build(u, base) for u in units if u["sents"]]


def _letters(s):
    return re.sub(r"[^a-z]", "", (s or "").lower())


def _build(u, base):
    runs = []
    for s in u["sents"]:
        if runs:
            runs.append({"t": " ", "style": "", "mark": None, "hl": None,
                         "ruby": None, "slot": None})
        runs += s["runs"]
    ko = " ".join(s["ko"] for s in u["sents"] if s["ko"])
    sm = u["sum"] or {}
    label, chapter, num = _label(u["head"])
    notes = list(u["notes"])
    clean = sm.get("clean") or ""
    body = "".join(r["t"] for r in runs)
    match = None
    if clean:
        match = _letters(clean) == _letters(body)
        if not match:
            notes.append("핵심기출 사본과 글자가 다르다(%d / %d자)"
                         % (len(_letters(body)), len(_letters(clean))))
    return {
        "pno": None,
        "label": label,
        "chapter": chapter,
        "labels": {"chapter": chapter, "number": num},
        "pages": u["pages"],
        "masters": [],
        "passage": [{"style": "본문", "runs": runs}] if runs else None,
        "translation": ([{"style": "한글", "runs": [
            {"t": ko, "style": "", "mark": None, "hl": None, "ruby": None,
             "slot": None}]}] if ko else None),
        "flownote": [],
        "title": {"en": "", "ko": u["title_ko"]},
        "topic": sm.get("topic") or "",
        "summary": sm.get("summary") or "",
        "synonyms": [],
        "voca": sm.get("voca") or [],
        "grammar": u["grammar"],
        "exam": sm.get("exam") or [],
        "sentences": [{"en": s["en"], "ko": s["ko"]} for s in u["sents"]],
        "links": [],
        "source": {"from": "pdf-analysis", "file": base,
                   "spread": int(u["pages"][0]) - 1 if u["pages"] else 0,
                   "notes": notes, "topic_split": "딱지" if sm else "",
                   "clean": clean, "clean_match": match},
    }


# ── 검수용 ──────────────────────────────────────────────────
def clean_texts(path):
    """G-P13 용 **깨끗한 사본** — 기출 상자(발문+지문+선택지) 글 그대로."""
    out = []
    for page in fitz.open(path):
        s = _summary_page(page, _chars(page))
        if s and s["exam"]:
            out.append("\n".join(s["exam"]))
    return out


def source_count(path):
    """지문 수를 **읽기와 따로** 센다(G-P9) — 본문 크기 영어가 많은 면의 머리말 수.

    read_book 의 셈을 그대로 믿으면 읽는 쪽이 지문을 흘려도 게이트가 통과한다.
    """
    heads, n_plain = [], 0
    for page in fitz.open(path):
        cs = _chars(page)
        bs = _body_size(cs)
        if not bs:
            continue
        lat = sum(1 for c in cs if _LAT.match(c["c"]) and abs(c["size"] - bs) < 0.25)
        if lat < 60 or not any(c["color"] == _WHITE and c["c"].isdigit()
                               and c["size"] < bs for c in cs):
            continue
        H = page.rect.height
        h = _text([c for c in cs if c["size"] >= 14 and c["y1"] < H * 0.12])
        if h:
            if not heads or heads[-1] != h:
                heads.append(h)
        else:
            n_plain += 1
    return len(heads) + (n_plain if not heads else 0)


if __name__ == "__main__":
    import json
    import sys
    ps = read_book(os.path.expanduser(sys.argv[1]))
    print("지문 %d개 · 원본 셈 %d" % (len(ps), source_count(sys.argv[1])))
    for p in ps:
        print("─" * 66)
        print("label=%r chapter=%r pages=%s" % (p["label"], p["chapter"], p["pages"]))
        body = "".join(r["t"] for pp in p["passage"] for r in pp["runs"])
        print("지문:", body[:160])
        print("해석:", "".join(r["t"] for pp in (p["translation"] or ())
                             for r in pp["runs"])[:120])
        print("주제:", p["topic"])
        print("요약:", p["summary"][:100])
        print("루비 %d · 형광펜 %d · 물결 %d · VOCA %d · 문장 %d · 어법 %d"
              % tuple([sum(1 for r in p["passage"][0]["runs"] if r.get(k))
                       for k in ("ruby", "hl", "wave")]
                      + [len(p["voca"]), len(p["sentences"]), len(p["grammar"])]))
        print("사본 일치:", p["source"]["clean_match"], "| 메모:", p["source"]["notes"][:4])
