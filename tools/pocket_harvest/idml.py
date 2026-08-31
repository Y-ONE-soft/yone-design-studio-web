# -*- coding: utf-8 -*-
"""IDML(.indd 내보내기) → 포켓북 지문 구조. **InDesign 없이 순수 파이썬.**

실측으로 밝혀진 것(강동1·광문1 완성 포켓북 IDML):

  · 구문분석 주석은 앵커 프레임이 아니라 **루비(ruby)** 다.
        <CharacterStyleRange RubyFlag="1" RubyString="S"><Content>were</Content>
    → 어느 **글자 범위**에 붙었는지가 정확히 남는다(PDF 에는 없는 정보다).
  · 위/아래는 `RubyPosition` 이 가른다.
        스타일 기본값 `BelowLeft`  = 아래 주석 (S · V · C · 관계부사 …)  7,154개
        범위 오버라이드 `AboveRight` = 위 주석 (conceivably (X) · 선행사 …)  710개
  · 강조·형광펜은 **이름 붙은 문자 스타일**이다. 그래서 변환은 색을 추측하는 일이
    아니라 **이름 → CSS 클래스 표**를 놓는 일이다.
        `지문분석:1. 일반 영어 지문 파란색` · `A 지문분석:형광펜_분홍`(밑줄 9pt) …
  · 지면 역할은 마스터 이름이 가른다. A/C/E/I=지문, B/D/F/L=암기테스트, G/H=짤지문.

역할 판정은 **문단 스타일**로 한다(`본문`·`한글`·`플로우노트`·`주제/요약문`·
`동반의어`·`암기테스트`). 좌표로 가르지 않는다 — 판형이 바뀌면 좌표는 거짓말한다.
"""
import os
import re
import urllib.parse
import zipfile
import xml.etree.ElementTree as ET

# ── 문단 스타일 → 역할 ────────────────────────────────────
ROLE_BY_PARA = {
    "본문": "passage",
    "한글": "translation",
    "플로우노트": "flownote",
    "주제/요약문": "topic",
    "동반의어": "synonyms",
    "암기테스트": "memtest",
    "암기테스트_문제 사본": "memtest_q",
}

# ── 문자 스타일 → 의미 클래스 ─────────────────────────────
#   이름이 계열마다 조금씩 다르다(`A 지문분석:…` · `지문분석:…` · `B 테스트:…`).
#   접두를 떼고 **꼬리말로** 판정한다.
_MARK = [
    (re.compile(r"파란색|중요_파랑"), "blue"),
    (re.compile(r"빨간색|중요_빨강"), "red"),
    (re.compile(r"형광펜_(\w+)"), "hl"),
    (re.compile(r"물결"), "wave"),
    (re.compile(r"동반의어_영단어"), "syn_word"),
    (re.compile(r"동반의어_파란색"), "syn_syn"),
    (re.compile(r"동반의어_빨간색"), "syn_ant"),
    (re.compile(r"동반의어 cf"), "syn_cf"),
    (re.compile(r"플로우 노트 대괄호"), "flow_bracket"),
    (re.compile(r"플로우 노트 소괄호"), "flow_paren"),
    (re.compile(r"플로우 노트 기호2"), "flow_sym2"),
    (re.compile(r"플로우 노트 기호3?"), "flow_sym"),
    (re.compile(r"지문 번호"), "pno"),
    (re.compile(r"빈칸"), "blank"),
    (re.compile(r"^숫자$"), "num"),
]

HL_NAME = {"노랑": "yellow", "민트": "mint", "분홍": "pink", "하늘": "sky",
           "보라": "violet", "오렌지": "orange"}


def _unq(s):
    return urllib.parse.unquote(s or "")


def _name(ref, kind):
    return _unq(ref or "").replace(kind + "/", "")


def mark_of(style_name):
    """문자 스타일 이름 → (클래스, 형광펜색). 모르면 (None, None)."""
    n = style_name or ""
    for pat, cls in _MARK:
        m = pat.search(n)
        if m:
            if cls == "hl":
                return "hl", HL_NAME.get(m.group(1), m.group(1))
            return cls, None
    return None, None


class Idml(object):
    def __init__(self, path):
        self.path = path
        self.z = zipfile.ZipFile(path)
        self._designmap = self.z.read("designmap.xml").decode("utf-8")
        self.spread_files = re.findall(r'<idPkg:Spread src="([^"]+)"',
                                       self._designmap)
        self.masters = self._masters()
        self.colors = self._colors()
        self.style_fill = self._style_fill()
        self.stories = self._story_index()

    # ── 자원 ──
    def _masters(self):
        out = {}
        for n in self.z.namelist():
            if not n.startswith("MasterSpreads/"):
                continue
            ms = ET.fromstring(self.z.read(n)).find("MasterSpread")
            if ms is not None:
                out[ms.get("Self")] = ms.get("Name") or ""
        return out

    # ── 색 ──
    #   이름표(`중요_파랑`)로 색을 추측하지 않는다. 책마다 같은 이름에 다른 값을
    #   쓰는 일이 실제로 있었다([[analysis_highlighter_mint_swatch_drift]]).
    #   IDML 에 값이 있으므로 **값을 읽는다**.
    def _colors(self):
        out = {}
        try:
            root = ET.fromstring(self.z.read("Resources/Graphic.xml"))
        except KeyError:
            return out
        for c in root.iter("Color"):
            self_id = c.get("Self") or ""
            vals = (c.get("ColorValue") or "").split()
            space = c.get("Space") or ""
            try:
                v = [float(x) for x in vals]
            except ValueError:
                continue
            rgb = None
            if space == "CMYK" and len(v) == 4:
                cc, mm, yy, kk = [x / 100.0 for x in v]
                rgb = tuple(int(round(255 * (1 - min(1.0, ch + kk))))
                            for ch in (cc, mm, yy))
            elif space == "RGB" and len(v) == 3:
                rgb = tuple(int(round(x)) for x in v)
            if rgb:
                out[_unq(self_id)] = "#%02X%02X%02X" % rgb
        return out

    def _style_fill(self):
        out = {}
        try:
            root = ET.fromstring(self.z.read("Resources/Styles.xml"))
        except KeyError:
            return out
        for cs in root.iter("CharacterStyle"):
            nm = _name(cs.get("Self"), "CharacterStyle")
            fc = cs.get("FillColor")
            if fc:
                out[nm] = _unq(fc)
        return out

    def color_of(self, style_name, override=None):
        ref = _unq(override) if override else self.style_fill.get(style_name)
        if not ref:
            return None
        return self.colors.get(ref)

    def _story_index(self):
        out = {}
        for n in self.z.namelist():
            if not n.startswith("Stories/"):
                continue
            try:
                root = ET.fromstring(self.z.read(n))
            except ET.ParseError:
                continue
            for st in root.iter("Story"):
                out[st.get("Self")] = st
        return out

    # ── 스토리 → 문단 ──
    def paragraphs(self, story_id):
        """[{style, runs:[{t, style, mark, hl, ruby, ruby_pos}]}]"""
        st = self.stories.get(story_id)
        if st is None:
            return []
        paras, cur = [], None
        for psr in st.findall("ParagraphStyleRange"):
            pstyle = _name(psr.get("AppliedParagraphStyle"), "ParagraphStyle")
            if cur is None:
                cur = {"style": pstyle, "runs": []}
            else:
                cur["style"] = cur["style"] or pstyle
            for csr in psr.findall("CharacterStyleRange"):
                cstyle = _name(csr.get("AppliedCharacterStyle"),
                               "CharacterStyle")
                mark, hl = mark_of(cstyle)
                color = self.color_of(cstyle, csr.get("FillColor"))
                # ⚠ 암기테스트 본문에는 **문자 스타일이 없다** — 번호(위첨자)와
                #   정답(색)이 전부 로컬 오버라이드다. 스타일 이름만 보면
                #   문제면과 정답면이 똑같이 나온다(그렇게 나왔다).
                ovr = _unq(csr.get("FillColor") or "")
                if ovr and ovr not in ("Color/Black", "Color/None",
                                       "Swatch/None"):
                    mark = mark or "ovr"
                if (csr.get("Position") or "").startswith("Superscript"):
                    mark = "num"
                ruby = csr.get("RubyString") if csr.get("RubyFlag") == "1" else None
                rpos = csr.get("RubyPosition") or ""
                # 위/아래 — 범위 오버라이드가 없으면 스타일 기본값(BelowLeft)
                slot = "up" if rpos.startswith("Above") else "dn"
                for node in csr:
                    if node.tag == "Content":
                        t = node.text or ""
                        if not t:
                            continue
                        # U+2028 = 문단 안 강제 줄바꿈. 플로우노트·동반의어는
                        # 이걸로 줄을 나눈다 — 지워 버리면 카드가 한 덩이가 된다.
                        parts = t.split("\u2028")
                        for i, piece in enumerate(parts):
                            if i:
                                cur["runs"].append({"t": "", "br": True,
                                                    "style": cstyle,
                                                    "mark": mark, "hl": hl,
                                                    "ruby": None, "slot": None})
                            if piece:
                                cur["runs"].append({
                                    "t": piece, "style": cstyle, "mark": mark,
                                    "hl": hl, "ruby": ruby, "color": color,
                                    "slot": slot if ruby else None})
                    elif node.tag == "Br":
                        paras.append(cur)
                        cur = {"style": pstyle, "runs": []}
            # ParagraphStyleRange 가 바뀌어도 <Br/> 이 없으면 같은 문단이다
        if cur and cur["runs"]:
            paras.append(cur)
        return [p for p in paras if any(r["t"].strip() for r in p["runs"])]

    def text_of(self, story_id):
        return "\n".join("".join(r["t"] for r in p["runs"])
                         for p in self.paragraphs(story_id))

    # ── 스프레드 ──
    def spreads(self):
        for f in self.spread_files:
            root = ET.fromstring(self.z.read(f))
            sp = root.find("Spread")
            if sp is None:
                continue
            pages = [{"name": p.get("Name"),
                      "master": self.masters.get(p.get("AppliedMaster"), "")}
                     for p in sp.iter("Page")]
            frames, links = [], []
            for tf in sp.iter("TextFrame"):
                frames.append({"story": tf.get("ParentStory"),
                               "tr": tf.get("ItemTransform", "")})
            for rect in sp.iter("Rectangle"):
                for im in list(rect.iter("Image")) + list(rect.iter("PDF")):
                    lk = im.find("Link")
                    if lk is not None and lk.get("LinkResourceURI"):
                        links.append(lk.get("LinkResourceURI"))
            yield {"file": f, "pages": pages, "frames": frames, "links": links}


# ── 정규화 도우미 ──────────────────────────────────────────
_PNO = re.compile(r"^\s*([0-9]{4,8}(?:\s*[~\-]\s*[0-9]{1,8})?)\s*$")
_HAN = re.compile(r"[가-힣]")


def han_ratio(text):
    t = re.sub(r"\s", "", text or "")
    if not t:
        return 0.0
    return len(_HAN.findall(t)) / float(len(t))


def lines_of(paras):
    """문단 목록 → 줄 목록(U+2028 로 나뉜 것까지). 줄 = run 목록."""
    out = []
    for p in paras or ():
        cur = []
        for r in p["runs"]:
            if r.get("br"):
                out.append(cur)
                cur = []
            else:
                cur.append(r)
        out.append(cur)
    return [l for l in out if any(r["t"].strip() for r in l)]


def plain(runs):
    return "".join(r["t"] for r in runs)


def parse_synonym_cards(paras):
    """동반의어 스토리 → 카드 목록.

    카드 경계는 **표제어 스타일**(`동반의어_영단어`)이 정한다. 그게 없는 책은
    `=`·`↔` 로 시작하지 않는 줄을 새 카드의 머리로 본다.
    """
    from manuscript import parse_syn_line
    cards, buf = [], []

    def flush():
        if buf:
            c = parse_syn_line(" ".join(buf))
            if c:
                cards.append(c)
        del buf[:]

    for line in lines_of(paras):
        txt = plain(line).strip()
        if not txt:
            continue
        head = any(r.get("mark") == "syn_word" for r in line)
        if not head:
            head = not txt.startswith(("=", "↔", "cf", "cf."))
        if head:
            flush()
        buf.append(txt)
    flush()
    return cards


def split_topic(paras):
    ls = [plain(l).strip() for l in lines_of(paras)]
    ls = [l for l in ls if l]
    topic = ls[0] if ls else ""
    summary = " ".join(ls[1:]) if len(ls) > 1 else ""
    return topic, summary


# ── 스프레드 → 지문 ────────────────────────────────────────
def _looks_label(t):
    """지문 라벨인가. `TRANSLATION`·`PICTURE` 같은 **마스터 글자**를 걸러 낸다.

    라벨에는 한글이나 숫자가 있다(`3과 04`·`250923`·`올포 11강`). 대문자 영어만
    있는 것은 지면 장식이다 — 이걸 안 거르면 지문 라벨이 TRANSLATION 이 된다.
    """
    if not t:
        return False
    if re.fullmatch(r"[A-Z][A-Z \-]*", t):
        return False
    return bool(re.search(r"[가-힣0-9]", t))


def _para_role(paras):
    for p in paras:
        r = ROLE_BY_PARA.get(p["style"])
        if r:
            return r
    return None


def read_book(path):
    """완성 포켓북 IDML → [지문]. 지면 순서를 그대로 따른다.

    ⚠ 영어 지문과 한글 해석이 **둘 다 문단 스타일 `본문`** 인 책이 있다(강동1 실측).
      스타일로는 못 가른다 → **한글 비율**로 가른다(옛 JSX 도 그렇게 했다).
    ⚠ 프레임이 여럿이어도 스토리는 하나다(동반의어 9칸이 한 스토리로 엮여 있다).
      **스토리 id 로 중복을 없애지 않으면 카드가 아홉 배로 나온다.**
    """
    doc = Idml(path)
    out, pending = [], None
    for sp in doc.spreads():
        masters = {p["master"][:1] for p in sp["pages"] if p["master"]}
        seen, by_role, shorts = set(), {}, []
        for fr in sp["frames"]:
            sid = fr["story"]
            if sid in seen:
                continue
            seen.add(sid)
            paras = doc.paragraphs(sid)
            if not paras:
                continue
            role = _para_role(paras)
            txt = "\n".join(plain(p["runs"]) for p in paras)
            if role in ("passage", None) and len(txt.strip()) < 30:
                shorts.append(txt.strip())
                if role is None:
                    continue
            if role == "passage":
                role = "translation" if han_ratio(txt) > 0.35 else "passage"
            if role == "memtest" and len(txt.strip()) < 30:
                shorts.append(txt.strip())
                continue
            if role:
                by_role.setdefault(role, []).append(paras)

        # ⚠ 마스터 글자는 **책마다 다른 이름**이다 — 지문면을 B 마스터에 얹은
        #   책이 있다. 글자만 보고 암기테스트 면으로 넘기면 지문이 조용히
        #   사라진다(광문2 36→79, 한영2 14→54). 그 면에 **지문이 있으면 지문면**이다.
        #   `read_sequence` 와 같은 판정을 쓴다 — 코퍼스는 이 함수로 만들어지므로
        #   여기만 안 고치면 코퍼스에서 지문이 계속 빠진다.
        if (masters & set("BDFL")) and "passage" not in by_role:
            if pending is not None:
                mt = pending.setdefault("memtest", {})
                if "memtest_q" in by_role:
                    mt["q"] = by_role["memtest_q"][0]
                if "memtest" in by_role:
                    mt.setdefault("a", by_role["memtest"][0])
            continue
        if "passage" not in by_role:
            continue
        if pending:
            out.append(pending)

        topic, summary = split_topic(by_role.get("topic", [None])[0])
        pno, label = "", ""
        for t in shorts:
            if not t:
                continue
            m = _PNO.match(t)
            if m and not pno:
                pno = m.group(1).replace(" ", "")
            elif not label and len(t) <= 24 and _looks_label(t):
                label = t
        pending = {
            "pno": pno,
            "label": label,
            "pages": [p["name"] for p in sp["pages"]],
            "masters": sorted(masters),
            "passage": by_role["passage"][0],
            "translation": by_role.get("translation", [None])[0],
            "flownote": [plain(l).strip()
                         for l in lines_of(by_role.get("flownote", [None])[0])],
            "topic": topic,
            "summary": summary,
            "synonyms": parse_synonym_cards(by_role.get("synonyms", [None])[0]),
            "links": sp["links"],
        }
        if len(by_role.get("passage", [])) > 1:
            pending["pair"] = True
    if pending:
        out.append(pending)
    return out


def read_sequence(path):
    """지면 **순서 그대로**의 항목 목록. 지문과 암기테스트가 섞여 나온다.

    ⚠ 암기테스트 한 벌이 지문 여러 개를 한꺼번에 담는 책이 있다(교과서는 4지문을
      묶는다). 그래서 암기테스트를 **직전 지문에 매달면 안 된다** — 매달았더니
      네 지문 분량이 한 지문 밑에 붙었다. 순서 목록으로 두고 렌더러가 순서대로
      찍게 한다.
    """
    doc = Idml(path)
    items, mt_story, seen_mt, seen_story = [], [], set(), set()
    for sp in doc.spreads():
        masters = {p["master"][:1] for p in sp["pages"] if p["master"]}
        seen, by_role, shorts = set(), {}, []
        for fr in sp["frames"]:
            sid = fr["story"]
            if sid in seen:
                continue
            seen.add(sid)
            if sid in seen_story and (masters & set("BDFL")):
                continue
            paras = doc.paragraphs(sid)
            if not paras:
                continue
            role = _para_role(paras)
            if role in ("memtest", "memtest_q"):
                seen_story.add(sid)
            txt = "\n".join(plain(p["runs"]) for p in paras)
            short = len(txt.strip()) < 30
            if short:
                shorts.append(txt.strip())
                if role in (None, "passage", "memtest"):
                    continue
            if role == "passage":
                role = "translation" if han_ratio(txt) > 0.35 else "passage"
            if role:
                by_role.setdefault(role, []).append(paras)

        # ⚠ 마스터 글자는 **책마다 다른 이름**이다 — 지문면을 B 마스터에 얹은
        #   책이 있다(고2 올포14~16강, 46스프레드 94k자가 통째로 사라졌다).
        #   그래서 글자만 보고 암기테스트 면으로 넘기면 안 된다. 그 면에
        #   **지문(본문)이 있으면 지문면**이다 — 내용으로 가른다.
        if (masters & set("BDFL")) and "passage" not in by_role:
            # ⚠ 암기테스트 스토리는 **여러 면에 걸쳐 이어져 있다**(스레드).
            #   스토리 단위로 집으면 한 면에 책 전체가 들어간다(실제로 그랬다).
            #   그래서 여기서는 모아만 두고, 지문별로 자르는 것은 split_memtest 가 한다.
            body = (by_role.get("memtest") or by_role.get("memtest_q") or [None])[0]
            if body is not None:
                key = id(body)
                if key not in seen_mt:
                    seen_mt.add(key)
                    mt_story.append(body)
            continue
        if "passage" not in by_role:
            continue
        topic, summary = split_topic(by_role.get("topic", [None])[0])
        pnos, labels = [], []
        for t in shorts:
            if not t:
                continue
            m = _PNO.match(t)
            if m:
                v = m.group(1).replace(" ", "")
                if v not in pnos:
                    pnos.append(v)
            elif len(t) <= 24 and _looks_label(t) and t not in labels:
                labels.append(t)

        # ⚠ 짤지문 스프레드는 지문이 **둘**이다(G/H 마스터). 첫 스토리만 집으면
        #   둘째 지문이 조용히 사라진다. 반대로 지문 하나가 프레임 둘로 나뉜
        #   경우도 있어서, **지문번호 배지 개수**로 가른다 — 배지가 하나면
        #   한 지문의 앞뒤 토막이므로 이어 붙인다.
        stories = by_role["passage"]
        n_badge = max(len(pnos), len(labels))
        groups = (list(stories) if len(stories) > 1 and n_badge > 1
                  else [[p2 for st in stories for p2 in st]])
        trs = by_role.get("translation") or []
        for gi, grp in enumerate(groups):
            tr = trs[gi] if gi < len(trs) else (
                [p2 for st in trs for p2 in st] if trs and len(groups) == 1
                else None)
            items.append({
                "kind": "passage",
                "pno": pnos[gi] if gi < len(pnos) else (pnos[0] if pnos else ""),
                "label": labels[gi] if gi < len(labels) else (
                    labels[0] if labels else ""),
                "pages": [p["name"] for p in sp["pages"]],
                "masters": sorted(masters),
                "pair": len(groups) > 1,
                "passage": grp,
                "translation": tr,
                "flownote": [plain(l).strip()
                             for l in lines_of(by_role.get("flownote",
                                                           [None])[0])],
                "topic": topic, "summary": summary,
                "synonyms": parse_synonym_cards(
                    by_role.get("synonyms", [None])[0]),
                "links": sp["links"] if gi == 0 else [],
            })
    if mt_story:
        runs = [r for pa in mt_story for p2 in pa for r in p2["runs"]] \
            if isinstance(mt_story[0], list) and mt_story[0] and \
            isinstance(mt_story[0][0], dict) and "runs" in mt_story[0][0] \
            else []
        items = split_memtest(items, mt_story)
    return items


_LET = re.compile(r"[A-Za-z]+")


def _sig(runs, n=40):
    return "".join(_LET.findall("".join(r["t"] for r in runs)))[:n].lower()


def split_memtest(items, stories):
    """이어진 암기테스트 스토리를 **지문별로** 자른다.

    암기테스트 본문은 지문과 같은 글이고 정답 자리에 `N[낱말]` 이 끼어 있을 뿐이다.
    그래서 지문 첫머리의 **알파벳만 남긴 지문(signature)** 으로 경계를 찾는다.
    표기·번호가 바뀌어도 글 자체는 안 바뀌므로 형식에 기대지 않는다.

    문제면은 따로 수확하지 않는다 — 정답면에서 정답 낱말만 가리면 되고,
    그래야 문제면과 정답면이 **반드시 다르다**(둘 다 정답이 보이는 사고를 막는다).
    """
    runs = [r for st in stories for p in st for r in p["runs"]]
    if not runs:
        return items
    flat = "".join(r["t"] for r in runs)
    letters, pos = [], []
    for i, ch in enumerate(flat):
        if ch.isalpha() and ch.isascii():
            letters.append(ch.lower())
            pos.append(i)
    hay = "".join(letters)

    passages = [x for x in items if x["kind"] == "passage"]
    bounds, lens, cursor = [], [], 0
    for p in passages:
        body = [r for pa in p["passage"] for r in pa["runs"]]
        sig = _sig(body)
        # ⚠ **앞에서부터 차례로** 찾는다. 아무 데서나 찾으면 짧은 머리글이
        #   엉뚱한 지문에 걸려 남의 글을 싣는다(완성본 41지문이 그렇게 틀렸다).
        at = hay.find(sig, cursor) if sig else -1
        if at < 0 and sig:
            at = hay.find(sig)          # 순서가 어긋난 책을 위한 폴백
        bounds.append(pos[at] if at >= 0 else None)
        if at >= 0:
            cursor = at + len(sig)
        lens.append(len("".join(r["t"] for r in body)))
    # 못 찾은 지문은 앞뒤 경계로 채운다(순서는 지면 순서와 같다)
    for i, p in enumerate(passages):
        start = bounds[i]
        if start is None:
            continue
        nxt = None
        for j in range(i + 1, len(passages)):
            if bounds[j] is not None:
                nxt = bounds[j]
                break
        end = nxt if nxt is not None else len(flat)
        # ⚠ 못 찾은 지문이 사이에 끼면 그 몫까지 앞 지문에 딸려 온다
        #   (완성본 41지문이 여러 지문을 한 덩이로 들고 있었다). 제 분량의
        #   1.6배(번호·대괄호가 붙어 늘어나는 몫)를 넘으면 거기서 끊는다.
        cap = start + int(lens[i] * 1.6) + 60
        if end > cap:
            end = min(end, cap)
        p["memtest_range"] = (start, end)
    # 문자 범위 → 런 조각
    acc, idx = [], 0
    spans = []
    for r in runs:
        spans.append((idx, idx + len(r["t"]), r))
        idx += len(r["t"])
    for p in passages:
        rng = p.get("memtest_range")
        if not rng:
            continue
        a, b = rng
        cut = []
        for s0, s1, r in spans:
            if s1 <= a or s0 >= b:
                continue
            t = r["t"][max(0, a - s0):len(r["t"]) - max(0, s1 - b)]
            if t:
                q = dict(r)
                q["t"] = t
                cut.append(q)
        p["memtest_runs"] = cut
        p.pop("memtest_range", None)

    for p in passages:
        if p.get("memtest_runs"):
            items.append({"kind": "memtest", "answer": False,
                          "key": p.get("pno") or p.get("label"),
                          "body_runs": _mask(p["memtest_runs"])})
            items.append({"kind": "memtest", "answer": True,
                          "key": p.get("pno") or p.get("label"),
                          "body_runs": p["memtest_runs"]})
    return items


def _mask(runs):
    """정답 낱말을 지운 문제면. 자리는 남긴다."""
    out = []
    for r in runs:
        if r.get("mark") in ("red", "ovr") or r.get("style", "").endswith("빈칸"):
            q = dict(r)
            q["mark"] = "blank"
            out.append(q)
        else:
            out.append(r)
    return out


if __name__ == "__main__":
    import json
    import sys
    ps = read_book(os.path.expanduser(sys.argv[1]))
    print("지문 %d개" % len(ps))
    empty_syn = [p for p in ps if not p["synonyms"]]
    empty_flow = [p for p in ps if not p["flownote"]]
    print("동반의어 0개 %d · 플로우 0개 %d" % (len(empty_syn), len(empty_flow)))
    for p in ps[:2]:
        print("─" * 60)
        print("pno", repr(p["pno"]), "label", repr(p["label"]),
              "masters", p["masters"], "pages", p["pages"])
        print("루비", sum(1 for pp in p["passage"] for r in pp["runs"] if r["ruby"]),
              "| 번역", len(plain(p["translation"][0]["runs"])) if p["translation"] else 0,
              "| 플로우", len(p["flownote"]), "| 동반의어", len(p["synonyms"]))
        print("주제", p["topic"][:40], "| 요약", p["summary"][:40])
        for c in p["synonyms"][:3]:
            print("   ", c)
