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
                                    "hl": hl, "ruby": ruby,
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

        if masters & set("BDFL"):
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
