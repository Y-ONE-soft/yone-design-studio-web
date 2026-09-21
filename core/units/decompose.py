"""입력 → 원자 목록(`decomposed`). PDF 면은 PyMuPDF 로 직접, 이미지·프롬프트는 클로드가 같은 형식으로 그린다.

    from_pdf(path, pno)          벡터(선·면)·글(span)·이미지가 이미 오브젝트다 — 그대로 원자로
    from_ai(prompt, image=...)   클로드 — 결과 형식은 같다 (JSON 글로 받는다)
    to_part(dec, indices, ...)   후보(원자 번호 묶음) → 부품 (원점을 묶음의 왼쪽 위로 옮긴다)

색·서체는 잰 값 그대로 두지 않고 토큰(`$c1` `$f1`)으로 뺀다 — 값은 함께 나온 tokens 에 있고,
라우트가 그것을 임시 옷으로 저장한다. 그래야 부품이 옷을 갈아입을 수 있다.
"""
import collections
import json
import os

PT = 25.4 / 72.0
MODEL = os.environ.get("YONE_ASSIST_MODEL", "claude-opus-5")


def _hex(c):
    if c is None:
        return None
    if isinstance(c, int):
        return "#%06x" % c
    if isinstance(c, (tuple, list)) and len(c) >= 3:
        return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(x * 255)))) for x in c[:3])
    return None


class _Tokens(object):
    """잰 색·서체에 이름을 붙인다 — 자주 나온 순서로 c1, c2… / f1, f2…"""

    def __init__(self):
        self.color = collections.Counter()
        self.font = collections.Counter()

    def c(self, hx):
        if not hx:
            return None
        self.color[hx] += 1
        return hx

    def f(self, name):
        if not name:
            return None
        self.font[name] += 1
        return name

    def finish(self, atoms):
        cmap = {hx: f"c{i + 1}" for i, (hx, _n) in enumerate(self.color.most_common())}
        fmap = {nm: f"f{i + 1}" for i, (nm, _n) in enumerate(self.font.most_common())}
        for a in atoms:
            for k in ("color", "fill"):
                if a.get(k) in cmap:
                    a[k] = "$" + cmap[a[k]]
            st = a.get("stroke")
            if st and st.get("color") in cmap:
                st["color"] = "$" + cmap[st["color"]]
            if a.get("font") in fmap:
                a["font"] = "$" + fmap[a["font"]]
        return {"color": {v: k for k, v in cmap.items()}, "font": {v: k for k, v in fmap.items()}}


def from_pdf(path, pno=1):
    import fitz
    doc = fitz.open(path)
    if not (1 <= pno <= len(doc)):
        raise ValueError(f"면 {pno} 없음 (1~{len(doc)})")
    page = doc[pno - 1]
    tb = page.trimbox if page.trimbox and page.trimbox.width > 10 else page.rect
    ox, oy = tb.x0, tb.y0
    W, H = tb.width * PT, tb.height * PT
    tk = _Tokens()
    texts, shapes, imgs = [], [], []           # 그리는 순서 = PDF 순서: 도형 → 그림 → 글

    def mm(v):
        return round(v * PT, 2)

    # ── 글: 줄 단위로 읽어 같은 서체·크기·색이 이어지면 단락 하나로. 인디자인 PDF 는 줄마다
    #    블록이 갈리는 일이 많아 블록 경계를 넘어 잇는다 (줄 머리 간격 + 가로 겹침으로 판단)
    cur = None
    for b in page.get_text("dict").get("blocks", []):
        if b.get("type") != 0:
            continue
        for ln in b.get("lines", []):
            spans = [s for s in ln.get("spans", []) if s.get("text", "").strip()]
            if not spans:
                continue
            main = max(spans, key=lambda s: len(s.get("text", "")))
            key = (main.get("font"), round(main.get("size", 0), 1), _hex(main.get("color")))
            x0, y0, x1, y1 = ln["bbox"]
            text = "".join(s.get("text", "") for s in spans)
            # 같은 서체·크기·색이고 줄 머리 간격이 두 글자 높이 안이면 같은 단락 — 브라우저가 다시 흘린다
            if (cur and cur["key"] == key and 0 < y0 - cur["last_y0"] < key[1] * 2.0
                    and x0 < cur["x1"] and x1 > cur["x0"]):
                cur["text"] += (" " if not cur["text"].endswith(" ") else "") + text
                cur["x0"], cur["x1"], cur["y1"] = min(cur["x0"], x0), max(cur["x1"], x1), max(cur["y1"], y1)
                cur["lines"] += 1
                cur["last_y0"] = y0
            else:
                if cur:
                    texts.append(_text_atom(cur, ox, oy, tk))
                cur = {"key": key, "text": text, "x0": x0, "y0": y0, "x1": x1, "y1": y1, "lines": 1, "last_y0": y0,
                       "bold": bool(main.get("flags", 0) & 16)}
    if cur:
        texts.append(_text_atom(cur, ox, oy, tk))

    # ── 도형
    page_area = tb.width * tb.height
    for d in page.get_drawings():
        r = d.get("rect")
        kinds = {it[0] for it in d.get("items", [])}
        if r is None or (r.is_empty and "l" not in kinds):             # 가로·세로 선은 rect 가 납작하다
            continue
        fill, stroke = _hex(d.get("fill")), _hex(d.get("color"))
        width = float(d.get("width") or 0)
        if fill in ("#ffffff",) and r.width * r.height > page_area * 0.9:
            continue                                                  # 면 바탕
        if not fill and (not stroke or width <= 0):
            continue
        dash = None
        ds = d.get("dashes")
        if ds and ds not in ("[] 0", "[]", "", None):
            try:
                dash = [float(x) * PT for x in ds.strip("[] 0").replace("]", "").split()] or None
            except ValueError:
                dash = None
        st = {"w": round(max(width, 0.2), 2), "color": tk.c(stroke)} if stroke and width > 0 else None
        if st and dash:
            st["dash"] = [round(x, 2) for x in dash]
        x, y, w, h = mm(r.x0 - ox), mm(r.y0 - oy), mm(r.width), mm(r.height)
        if kinds <= {"l"} and len(d.get("items", [])) == 1 and st:
            _t, p1, p2 = d["items"][0]
            shapes.append({"t": "line", "x1": mm(p1.x - ox), "y1": mm(p1.y - oy), "x2": mm(p2.x - ox), "y2": mm(p2.y - oy), "stroke": st})
            continue
        if kinds <= {"l"} and (w < 0.3 or h < 0.3) and st:
            # 가로·세로 한 줄로 이어진 선들 — 한 선으로
            if w >= h:
                shapes.append({"t": "line", "x1": x, "y1": round(y + h / 2, 2), "x2": round(x + w, 2), "y2": round(y + h / 2, 2), "stroke": st})
            else:
                shapes.append({"t": "line", "x1": round(x + w / 2, 2), "y1": y, "x2": round(x + w / 2, 2), "y2": round(y + h, 2), "stroke": st})
            continue
        a = {"t": "rect", "x": x, "y": y, "w": max(w, 0.1), "h": max(h, 0.1)}
        if "c" in kinds:
            ratio = (w / h) if h else 9
            if 0.6 <= ratio <= 1.6 and len(kinds) == 1:
                a["t"] = "ellipse"
            else:
                a["radius"] = round(min(w, h) / 4, 2)
        if fill:
            a["fill"] = tk.c(fill)
        if st:
            a["stroke"] = st
        shapes.append(a)

    # ── 이미지
    n = 0
    for info in page.get_image_info(xrefs=True):
        bx = fitz.Rect(info["bbox"])
        if bx.is_empty or bx.width < 2 or bx.height < 2:
            continue
        n += 1
        imgs.append({"t": "image", "x": mm(bx.x0 - ox), "y": mm(bx.y0 - oy), "w": mm(bx.width), "h": mm(bx.height), "src": f"img{n}"})

    # 재단 밖(도련)은 잘라 내고, 밖에만 있는 것은 버린다
    atoms = [a for a in shapes + imgs + texts if _clip(a, W, H)]
    tokens = tk.finish(atoms)
    dec = {"from": f"pdf:{os.path.basename(path)}#{pno}", "w": round(W, 2), "h": round(H, 2), "atoms": atoms, "tokens": tokens}
    dec["parts"] = group(dec)
    return dec


def _clip(a, W, H):
    """재단선 안으로 자른다. 밖에만 있으면 False."""
    if a["t"] == "line":
        x0, x1 = sorted((a["x1"], a["x2"]))
        y0, y1 = sorted((a["y1"], a["y2"]))
        if x1 < 0 or y1 < 0 or x0 > W or y0 > H:
            return False
        a["x1"], a["x2"] = round(max(x0, 0), 2), round(min(x1, W), 2)      # 방향은 뜻이 없다
        a["y1"], a["y2"] = round(max(y0, 0), 2), round(min(y1, H), 2)
        return True
    x0, y0, x1, y1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    if x1 <= 0 or y1 <= 0 or x0 >= W or y0 >= H:
        return False
    if a["t"] != "text":                          # 글은 자르면 글이 준다 — 자리만 둔다
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
        a["x"], a["y"], a["w"], a["h"] = round(x0, 2), round(y0, 2), round(max(x1 - x0, 0.1), 2), round(max(y1 - y0, 0.1), 2)
    return True


def _text_atom(cur, ox, oy, tk):
    font, size, color = cur["key"]
    h = (cur["y1"] - cur["y0"]) * PT
    lead = round(h / max(cur["lines"], 1) / PT, 1) if cur["lines"] > 1 else None
    a = {"t": "text", "x": round((cur["x0"] - ox) * PT, 2), "y": round((cur["y0"] - oy) * PT, 2),
         "w": round((cur["x1"] - cur["x0"]) * PT + 1.5, 2), "h": round(h, 2),       # 브라우저 서체가 조금 넓어도 줄이 안 늘게
         "font": tk.f(font), "size": round(size, 1), "color": tk.c(color) or "#000000", "text": cur["text"]}
    if lead:
        a["leading"] = lead
    return a


def _top(a):
    return min(a["y1"], a["y2"]) if a["t"] == "line" else a["y"]


def _bottom(a):
    return max(a["y1"], a["y2"]) if a["t"] == "line" else a["y"] + a["h"]


def _box(atoms):
    xs0 = [min(a["x1"], a["x2"]) if a["t"] == "line" else a["x"] for a in atoms]
    xs1 = [max(a["x1"], a["x2"]) if a["t"] == "line" else a["x"] + a["w"] for a in atoms]
    y0, y1 = min(_top(a) for a in atoms), max(_bottom(a) for a in atoms)
    return [round(min(xs0), 2), round(y0, 2), round(max(xs1) - min(xs0), 2), round(y1 - y0, 2)]


def group(dec, gap=3.0):
    """부품 후보 — 세로로 띄어진 띠(band)마다 하나. 면의 절반 넘는 큰 상자는 바탕으로 보고 뺀다."""
    atoms = dec.get("atoms") or []
    W, H = float(dec.get("w") or 210), float(dec.get("h") or 297)
    idx = [i for i, a in enumerate(atoms)
           if not (a["t"] in ("rect", "image") and a["w"] * a["h"] > W * H * 0.5)]
    idx.sort(key=lambda i: _top(atoms[i]))
    groups = []
    cur, cur_bottom = [], None
    for i in idx:
        a = atoms[i]
        if cur and _top(a) - cur_bottom > gap:
            groups.append(cur)
            cur, cur_bottom = [], None
        cur.append(i)
        cur_bottom = _bottom(a) if cur_bottom is None else max(cur_bottom, _bottom(a))
    if cur:
        groups.append(cur)
    out = []
    for n, g in enumerate(groups, 1):
        texts = [atoms[i]["text"] for i in g if atoms[i]["t"] == "text" and atoms[i].get("text")]
        hint = (texts[0][:18] + "…") if texts and len(texts[0]) > 18 else (texts[0] if texts else "")
        out.append({"name": f"후보 {n}" + (f" · {hint}" if hint else ""), "atoms": g, "box": _box([atoms[i] for i in g])})
    return out


def to_part(dec, indices, pid, name):
    """후보 → 부품. 원점을 묶음의 왼쪽 위로 옮긴다."""
    atoms = [json.loads(json.dumps(dec["atoms"][i])) for i in indices]
    if not atoms:
        raise ValueError("원자가 없다")
    x0, y0, w, h = _box(atoms)
    for a in atoms:
        if a["t"] == "line":
            a["x1"], a["x2"] = round(a["x1"] - x0, 2), round(a["x2"] - x0, 2)
            a["y1"], a["y2"] = round(a["y1"] - y0, 2), round(a["y2"] - y0, 2)
        else:
            a["x"], a["y"] = round(a["x"] - x0, 2), round(a["y"] - y0, 2)
    return {"id": pid, "name": name, "w": max(w, 1.0), "h": max(h, 1.0), "atoms": atoms, "from": dec.get("from", "")}


# ── 클로드 — 이미지·프롬프트 ──────────────────────────────────────────
_FLAT_ATOM = {
    "type": "object",
    "properties": {
        "t": {"enum": ["text", "line", "rect", "ellipse", "image"]},
        "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "h": {"type": "number"},
        "x1": {"type": "number"}, "y1": {"type": "number"}, "x2": {"type": "number"}, "y2": {"type": "number"},
        "font": {"type": "string"}, "size": {"type": "number"}, "color": {"type": "string"},
        "fill": {"type": "string"}, "stroke_color": {"type": "string"}, "stroke_w": {"type": "number"}, "dashed": {"type": "boolean"},
        "align": {"enum": ["left", "center", "right", "justify"]}, "text": {"type": "string"}, "bind": {"type": "string"},
        "radius": {"type": "number"}, "src": {"type": "string"},
    },
    "required": ["t"], "additionalProperties": False,
}
_NV = {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "value": {"type": "string"}},
                                  "required": ["name", "value"], "additionalProperties": False}}
AI_SCHEMA = {
    "type": "object",
    "properties": {
        "w": {"type": "number"}, "h": {"type": "number"},
        "atoms": {"type": "array", "items": _FLAT_ATOM},
        "tokens": {"type": "object", "properties": {"color": _NV, "font": _NV}, "required": ["color", "font"], "additionalProperties": False},
        "parts": {"type": "array", "items": {"type": "object", "properties": {"name": {"type": "string"}, "atoms": {"type": "array", "items": {"type": "integer"}}},
                                             "required": ["name", "atoms"], "additionalProperties": False}},
        "note": {"type": "string"},
    },
    "required": ["w", "h", "atoms", "tokens", "parts", "note"], "additionalProperties": False,
}

AI_SYSTEM = """너는 인쇄 교재 조판 디자이너다. 받은 그림 또는 설명을 **인디자인 오브젝트(원자)** 로 분해해 JSON 으로만 답한다.

원자 5종: text(글상자) · line(선) · rect(면) · ellipse(원) · image(그림). 단위는 mm, 원점은 왼쪽 위. 글자 크기·선 굵기는 pt.
- text: x y w h font size color [align text bind]. 콘텐츠가 들어갈 자리는 bind 에 필드 이름(영문 소문자: no, prompt, passage, sentence, choices, answer, kr …)을 적고 text 에는 견본 글을 넣는다. 고정 글(라벨 "O", "정답")은 bind 없이 text 만.
- line: x1 y1 x2 y2 stroke_color stroke_w [dashed]
- rect: x y w h [fill stroke_color stroke_w radius]  · ellipse: x y w h [fill stroke_color stroke_w]
- image: x y w h src
색·서체는 값이 아니라 **토큰 이름**으로 적고(color: "ink", font: "body" 처럼) tokens 에 이름→값을 준다(색은 #rrggbb, 서체는 family 이름).
parts 는 원자를 부품(뜻이 있는 묶음: 지문 상자, 발문+선지, O/X 줄, 러닝헤드…)으로 묶은 것 — atoms 는 원자 번호(0부터).
w h 는 전체 캔버스 크기(mm). 그림이면 실제 비율로, 설명이면 기본 폭 170mm 안에서.
지어내지 말고 보이는 것만. 미심쩍은 것은 note 에 한 줄."""


def from_ai(prompt="", image=None, media_type="image/png", name="", tokens=None):
    """tokens(옷의 tokens)를 주면 그 이름만 쓰게 한다 — 새 요소가 지금 옷을 그대로 입는다."""
    import anthropic
    content = []
    sys_extra = ""
    if tokens:
        cs = ", ".join(sorted((tokens.get("color") or {}).keys()))
        fs = ", ".join(sorted((tokens.get("font") or {}).keys()))
        sys_extra = (f"\n\n색 토큰은 이 이름만 쓴다: {cs} (ink=본문 먹, mute=회색 글, rule=괘선, sel=강조 파랑, s1~s3=구간 주색, cream/sky=상자 바탕, white). "
                     f"서체 토큰은 이 이름만: {fs} (body=본문, disp=발문, label=라벨, num=번호). tokens 에는 새로 만든 이름만 넣는다.")
    if image:
        import base64
        content.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": base64.b64encode(image).decode()}})
        content.append({"type": "text", "text": "이 그림을 원자로 분해하라." + (f" 참고: {prompt}" if prompt else "")})
    else:
        content.append({"type": "text", "text": "이 설명대로 원자를 그려라:\n" + prompt})
    # 구조화 출력(json_schema)은 원자 스키마가 "too complex" 로 거절된다 — 글로 받아 JSON 만 잘라 읽는다
    r = anthropic.Anthropic().messages.create(
        model=MODEL, max_tokens=16000, system=AI_SYSTEM + sys_extra + "\n\n답은 JSON 하나뿐(코드 펜스·설명 없이). 형식:\n" + json.dumps(AI_SCHEMA, ensure_ascii=False),
        messages=[{"role": "user", "content": content}],
    )
    text = "".join(b.text for b in r.content if b.type == "text")
    raw = json.loads(text[text.find("{"):text.rfind("}") + 1])
    atoms = []
    for a in raw.get("atoms") or []:
        t = a.get("t")
        st = None
        if a.get("stroke_color") or a.get("stroke_w"):
            st = {"w": float(a.get("stroke_w") or 0.5), "color": "$" + a["stroke_color"] if a.get("stroke_color") else "$ink"}
            if a.get("dashed"):
                st["dash"] = [1, 1]
        if t == "text":
            o = {"t": "text", "x": a.get("x", 0), "y": a.get("y", 0), "w": a.get("w", 50), "h": a.get("h", 5),
                 "font": "$" + (a.get("font") or "body"), "size": float(a.get("size") or 8), "color": "$" + (a.get("color") or "ink")}
            for k in ("align", "text", "bind"):
                if a.get(k):
                    o[k] = a[k]
        elif t == "line":
            o = {"t": "line", "x1": a.get("x1", 0), "y1": a.get("y1", 0), "x2": a.get("x2", 10), "y2": a.get("y2", 0), "stroke": st or {"w": 0.5, "color": "$ink"}}
        elif t in ("rect", "ellipse"):
            o = {"t": t, "x": a.get("x", 0), "y": a.get("y", 0), "w": a.get("w", 10), "h": a.get("h", 10)}
            if a.get("fill"):
                o["fill"] = "$" + a["fill"]
            if st:
                o["stroke"] = st
            if t == "rect" and a.get("radius"):
                o["radius"] = a["radius"]
        elif t == "image":
            o = {"t": "image", "x": a.get("x", 0), "y": a.get("y", 0), "w": a.get("w", 20), "h": a.get("h", 20), "src": a.get("src") or "img1"}
        else:
            continue
        atoms.append(o)
    tokens = {"color": {x["name"]: x["value"] for x in raw["tokens"].get("color", [])},
              "font": {x["name"]: x["value"] for x in raw["tokens"].get("font", [])}}
    dec = {"from": f"image:{name}" if image else "prompt", "w": float(raw.get("w") or 170), "h": float(raw.get("h") or 50),
           "atoms": atoms, "tokens": tokens, "note": raw.get("note", "")}
    parts = []
    for p in raw.get("parts") or []:
        ids = [i for i in p.get("atoms", []) if 0 <= i < len(atoms)]
        if ids:
            parts.append({"name": p.get("name") or f"후보 {len(parts) + 1}", "atoms": ids, "box": _box([atoms[i] for i in ids])})
    dec["parts"] = parts or group(dec)
    return dec
