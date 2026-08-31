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
                        cur["runs"].append({
                            "t": t, "style": cstyle, "mark": mark, "hl": hl,
                            "ruby": ruby, "slot": slot if ruby else None})
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


# ── 스프레드 → 지문 ────────────────────────────────────────
_PNO = re.compile(r"^\s*([0-9]{4,8}(?:\s*[~\-]\s*[0-9]{1,8})?)\s*$")


def _para_role(paras):
    for p in paras:
        r = ROLE_BY_PARA.get(p["style"])
        if r:
            return r
    return None


def read_book(path):
    """완성 포켓북 IDML → [지문]. 지면 순서를 그대로 따른다."""
    doc = Idml(path)
    out, pending = [], None
    for sp in doc.spreads():
        masters = {p["master"][:1] for p in sp["pages"] if p["master"]}
        by_role = {}
        for fr in sp["frames"]:
            paras = doc.paragraphs(fr["story"])
            if not paras:
                continue
            role = _para_role(paras)
            if role:
                by_role.setdefault(role, []).append(paras)
        is_memtest = bool(masters & set("BDFL"))
        if is_memtest:
            if pending is not None:
                if "memtest_q" in by_role:
                    pending.setdefault("memtest", {})["q"] = by_role["memtest_q"][0]
                elif "memtest" in by_role:
                    pending.setdefault("memtest", {})["a"] = by_role["memtest"][0]
            continue
        if "passage" not in by_role:
            continue
        if pending:
            out.append(pending)
        pending = {
            "passage": by_role["passage"][0],
            "translation": by_role.get("translation", [None])[0],
            "flownote": by_role.get("flownote", [None])[0],
            "topic": by_role.get("topic", [None])[0],
            "synonyms": by_role.get("synonyms", [None])[0],
            "links": sp["links"],
            "masters": sorted(masters),
            "pages": [p["name"] for p in sp["pages"]],
        }
        # 지문번호 — 짧은 숫자만 있는 프레임
        for fr in sp["frames"]:
            t = doc.text_of(fr["story"]).strip()
            m = _PNO.match(t)
            if m:
                pending["pno"] = m.group(1).replace(" ", "")
                break
    if pending:
        out.append(pending)
    return out


if __name__ == "__main__":
    import json
    import sys
    ps = read_book(os.path.expanduser(sys.argv[1]))
    print("지문 %d개" % len(ps))
    for p in ps[:2]:
        print("─" * 60)
        print("pno", p.get("pno"), "masters", p["masters"], "pages", p["pages"])
        print("본문 문단", len(p["passage"]),
              "| 루비", sum(1 for pp in p["passage"] for r in pp["runs"] if r["ruby"]))
        print("번역", bool(p["translation"]), "플로우", bool(p["flownote"]),
              "주제", bool(p["topic"]), "동반의어", bool(p["synonyms"]))
        if p["synonyms"]:
            print("동반의어 문단", len(p["synonyms"]),
                  [("".join(r["t"] for r in q["runs"]))[:28] for q in p["synonyms"][:4]])
